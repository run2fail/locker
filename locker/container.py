'''
This module provides an extended lxc container class.
'''

import lxc
import logging
from colorama import Fore
import iptc
import re
import time
import locker.util
import os
import shutil

class Container(lxc.Container):
    '''
    Extended lxc.Container class

    The class adds:

      - Checks and logging
      - Locker specific attributes
      - Handling of project specifc parameters
    '''

    @staticmethod
    def get_containers(project, yml):
        '''
        Generate a list of container objects

        :param yml: YAML project configuration

        :returns:   List of container objects
        '''
        containers = list()
        all_containers = list()
        colors = [Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, Fore.MAGENTA, Fore.CYAN]

        for num, name in enumerate(sorted(yml.keys())):
            pname = '%s_%s' % (project.name, name)
            if pname not in lxc.list_containers():
                logging.debug('Container \"%s\" does not exist yet or is not accessible as this user.', pname)
            color = colors[num % len(colors)]
            container = Container(pname, yml[name], project, color)

            all_containers.append(container)
            if len(project.args['containers']) and pname not in project.args['containers']:
                logging.debug('%s was not selected', pname)
                continue
            containers.append(container)
        logging.debug('Containers: %s', [con.name for con in containers])
        return (containers, all_containers)

    def get_ips(self, retries=10):
        '''
        Get IPs of the container

        :param retries: Try a again this many times if IPs are not available yet
        :returns: List of IPs
        '''
        ips = lxc.Container.get_ips(self)
        while len(ips) == 0 and self.running and retries > 0:
            # TODO Should implement a timeout here
            self.logger.debug('Waiting to acquire an IP address')
            time.sleep(1)
            ips = lxc.Container.get_ips(self)
            retries -= 1
        return ips

    def __init__(self, name, yml, project, color=Fore.RESET, config_path=None):
        self.yml = yml
        self.project = project
        self.color = color
        self.logger = logging.getLogger(name)
        self.logger.propagate = False
        formatter = logging.Formatter('%(asctime)s, %(levelname)8s: ' + color + '[' + name + '] %(message)s' + Fore.RESET)
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        lxc.Container.__init__(self, name, config_path)

    def start(self):
        '''
        Start container

        :returns: False on any error, else True
        '''
        if not self.defined:
            self.logger.critical('Container is not yet defined')
            return False
        if self.running:
            self.logger.debug('Container is already running')
            if not self.project.args['restart']:
                return True
            self.logger.info('Restarting container')
            if not self.stop():
                self.logger.critical('Was not able to stop container - still running!')
                return False
        self._generate_fstab()
        self._set_fqdn_hook()
        self.logger.info('Starting container')
        lxc.Container.start(self)
        if not self.running:
            self.logger.critical('Could not start container')
            return False
        return True

    def stop(self):
        '''
        Stop container

        :returns: False on any error, else True
        '''
        if not self.defined:
            self.logger.debug('Container is not yet defined')
            return True
        if not self.running:
            self.logger.debug('Container is already stopped')
            return True
        self.logger.info('Stopping container')
        lxc.Container.stop(self)
        if self.running:
            self.logger.critical('Could not stop container')
            return False
        return True

    def create(self):
        '''
        Create container

        :returns: False on any error, else True
        '''
        def create_from_template():
            ''' Create container from template specified in YAML configuration
            '''
            self.logger.info('Creating container from template \"%s\"', self.yml['template']['name'])
            flags = lxc.LXC_CREATE_QUIET
            if self.logger.level == logging.DEBUG:
                flags = 0
            self.create(self.yml['template']['name'], flags, args=self.yml['template'])
            if not self.defined:
                self.logger.info('Creation from template \"%s\" did not succeed', self.yml['template']['name'])
                return False
            self._copy_mounted()
            return True

        def clone_from_existing():
            ''' Clone container from an existing container
            '''
            clone = self.yml['clone']
            if clone not in lxc.list_containers():
                self.logger.error('Cannot clone, container \"%s\" does not exist or is not accessible', clone)
                return False
            origin = Container(clone)
            self.logger.info('Cloning from \"%s\"', origin.name)
            cloned = origin.clone(self)
            if not cloned or not cloned.defined:
                self.logger.info('Cloning from \"%s\" did not succeed', origin.name)
                return False
            cloned._copy_mounted()
            return True

        if self.defined:
            self.logger.debug('Container is already defined')
            return True
        if 'template' in self.yml and 'clone' in self.yml:
            self.logger.error('\"template\" and \"clone\" may not be used in the same configuration')
            return False

        if 'template' in self.yml:
            return create_from_template()
        elif 'clone' in self.yml:
            return clone_from_existing()
        else:
            self.logger.error('Neither \"template\" nor \"clone\" was specified in the configuration')
            return False

    def clone(self, proxy):
        '''
        Clone this container

        Create a clone of this container and copy extended attributes
        to the clone.

        :returns: Container clone of False
        '''
        cloned = lxc.Container.clone(self, proxy.name)
        if not cloned.defined:
            self.logger.info('Cloning from \"%s\" did not succeed', self.name)
            return False
        cloned.yml = proxy.yml
        cloned.project = proxy.project
        cloned.color = proxy.color
        cloned.logger = proxy.logger
        return cloned

    def remove(self):
        '''
        Destroy container

        :returns: False on any error, else True
        '''
        if not self.defined:
            self.logger.debug('Container has not been created yet')
            return False
        if not self.project.args['delete_dont_ask']:
            input_var = input("Delete %s? [y/N]: " % (self.name))
            if input_var not in ['y', 'Y']:
                self.logger.info('Skipping deletion')
                return True
        if not self.stop():
            return False
        if not lxc.Container.destroy(self):
            self.logger.warn('Container was not deleted')
            return False
        return True

    def rmports(self):
        ''' Remove netfilter rules
        '''
        if self.running:
            self.logger.warn('Container is still running, services will not be available anymore')

        nat_table = iptc.Table(iptc.Table.NAT)
        locker_nat_chain = iptc.Chain(nat_table, 'LOCKER')
        for rule in locker_nat_chain.rules:
            for match in rule.matches:
                if match.name == 'comment' and match.comment == self.name:
                    self.logger.debug('Removing DNAT %s rule', rule.protocol)
                    locker_nat_chain.delete_rule(rule)

        filter_table = iptc.Table(iptc.Table.FILTER)
        filter_forward = iptc.Chain(filter_table, 'FORWARD')
        for rule in filter_forward.rules:
            for match in rule.matches:
                if match.name == 'comment' and match.comment == self.name:
                    self.logger.debug('Removing FORWARD %s rule', rule.protocol)
                    filter_forward.delete_rule(rule)

    def ports(self):
        ''' Add firewall rules to enable port forwarding

        :param containers: List of containers or None (== all containers)
        :returns: False on any error, else True
        '''
        def add_dnat_rule(container_ip, port_conf, locker_nat_chain):
            ''' Add rule to the LOCKER chain in the NAT table
            '''
            port_forwarding = iptc.Rule()
            port_forwarding.protocol = port_conf['proto']
            if port_conf['host_ip']:
                port_forwarding.dst = port_conf['host_ip']
            port_forwarding.in_interface = '!lxbr0'
            tcp_match = port_forwarding.create_match(port_conf['proto'])
            tcp_match.dport = port_conf['host_port']
            comment_match = port_forwarding.create_match('comment')
            comment_match.comment = self.name
            target = port_forwarding.create_target('DNAT')
            target.to_destination = '%s:%s' % (container_ip, port_conf['container_port'])
            locker_nat_chain.insert_rule(port_forwarding)

        def add_forward_rule(container_ip, port_conf, filter_forward):
            ''' Add rule to the FORWARD chain in the FILTER table
            '''
            forward_rule = iptc.Rule()
            forward_rule.protocol = port_conf['proto']
            forward_rule.dst = container_ip
            forward_rule.in_interface = '!lxcbr0'
            forward_rule.out_interface = 'lxcbr0'
            tcp_match = forward_rule.create_match(port_conf['proto'])
            tcp_match.dport = port_conf['container_port']
            comment_match = forward_rule.create_match('comment')
            comment_match.comment = self.name
            forward_rule.create_target('ACCEPT')
            filter_forward.insert_rule(forward_rule)

        def container_has_rules(locker_nat_chain, filter_forward):
            ''' Check if there are any netfilter rules for this container
            '''
            self.logger.debug('Checking if container has already rules')
            for rule in locker_nat_chain.rules:
                for match in rule.matches:
                    if match.name == 'comment' and match.comment == self.name:
                        self.logger.info('Found rule(-s) in LOCKER chain: remove with command \"rmports\"')
                        return True
            for rule in filter_forward.rules:
                for match in rule.matches:
                    if match.name == 'comment' and match.comment == self.name:
                        self.logger.info('Found rule(-s) in FORWARD chain: remove with command \"rmports\"')
                        return True
            return False

        def parse_port_conf(fwport):
            ''' Split port forward directive in parts
            '''
            regex = re.compile(r'^(?:(?P<host_ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):)?(?P<host_port>\d{1,5}):(?P<container_port>\d{1,5})(?:/(?:(?P<proto_udp>udp)|(?P<proto_tcp>tcp)))?$')
            match = regex.match(fwport)
            if not match:
                self.logger.error('Invalid port forwarding directive: %s', fwport)
                return None
            mdict = match.groupdict()
            mdict['proto'] = mdict['proto_udp'] or 'tcp'
            return mdict

        if not 'ports' in self.yml:
            self.logger.debug('No port forwarding rules')
            return True
        if not self.running:
            self.logger.info('Container is not running, skipping adding ports rules')
            return True
        self.logger.debug('Adding port forwarding rules')

        locker_nat_chain = iptc.Chain(iptc.Table(iptc.Table.NAT), 'LOCKER')
        filter_forward = iptc.Chain(iptc.Table(iptc.Table.FILTER), 'FORWARD')
        if container_has_rules(locker_nat_chain, filter_forward):
            return True

        for fwport in self.yml['ports']:
            port_conf = parse_port_conf(fwport)
            if not port_conf:
                continue
            ips = self.get_ips()
            for container_ip in ips:
                if container_ip.find(':') >= 0:
                    self.logger.warn('Found IPv6 address %s - not yet supported', container_ip)
                    continue
                add_dnat_rule(container_ip, port_conf, locker_nat_chain)
                add_forward_rule(container_ip, port_conf, filter_forward)
        return True

    def _set_fqdn_hook(self):
        ''' Set FQDN hook script to set the FQDN

        This works when the container and when /etc is a bind-mount as long as
        / and /locker are not covered by another mount.
        '''
        if 'fqdn' not in self.yml:
            self.logger.debug('No FQDN in configuration')
            return
        fqdn = self.yml['fqdn']
        hostname = fqdn.split('.')[0]
        self.logger.debug('Setting FQDN hook script')
        try:
            rootfs = self.get_config_item('lxc.rootfs')
        except KeyError:
            self.logger.debug('rootfs is still empty, container defined = %s',
                              self.defined)
            return
        assert len(rootfs)
        # TODO Maybe we should mount /usr/share/locker/hooks from the host
        # to /locker in the container? This would enable to have a common
        # script for all containers.
        hooks_dir = '%s/locker/hooks'  % (rootfs)
        if not os.path.isdir(hooks_dir):
            os.makedirs(hooks_dir)
        hook = hooks_dir + '/mount'
        with open(hook, 'w+') as wfile:
            # TODO Ugly
            script = '''\
#!/bin/sh
sed -i 's|^127\.0\.1\.1.*$|127.0.1.1   %s %s|g' %s/etc/hosts
echo "%s" > "%s/etc/hostname"
''' % (fqdn, hostname, rootfs, hostname, rootfs)
            wfile.write(script)
        os.chmod(hook, 0o754)
        self.set_config_item('lxc.hook.mount', hook)
        self.save_config()

    def _generate_fstab(self):
        ''' Generate a file system table for the container

        This function generates a fstab file based on the volume information in the
        YAML configuration.
        Currently only bind mounts are supported and no syntax check is run!
        '''
        fstab_file = self.get_config_item('lxc.mount')
        if not fstab_file:
            # TODO Why is lxc.mount sometimes empty?!?
            self.logger.debug('Empty fstab config item')
            fstab_file = '%s/%s/fstab' % (self.get_config_path(), self.name)
        assert len(fstab_file)
        self.logger.debug('Generating fstab: %s', fstab_file)
        with open(fstab_file, 'w+') as fstab:
            if 'volumes' in self.yml:
                for volume in self.yml['volumes']:
                    remote, mountpt = [s.strip() for s in volume.split(':')]
                    remote = locker.util.expand_vars(remote, self)
                    if mountpt.startswith('/'):
                        mountpt = mountpt[1:]
                    fstab.write('%s %s none bind 0 0\n' % (remote, mountpt))
            fstab.write('\n')

    def get_netfiler_rules(self):
        '''
        Get port forwarding netfilter rules of the container
        '''
        nat_table = iptc.Table(iptc.Table.NAT)
        locker_nat_chain = iptc.Chain(nat_table, 'LOCKER')
        dnat_rules = list()
        try:
            self.logger.debug('Searching netfilter rules')
            for rule in [rul for rul in locker_nat_chain.rules if rul.protocol in ['tcp', 'udp']]:
                for match in rule.matches:
                    if match.name == 'comment' and match.comment == self.name:
                        dport = [m.dport for m in rule.matches if m.name in ['tcp', 'udp']][0]
                        to_ip, to_port = rule.target.to_destination.split(':')
                        dnat_rules.append((rule.protocol, (rule.dst, dport), (to_ip, to_port)))
        except iptc.IPTCError as err:
            self.logger.warn('An arror occured searching the netfiler rules: %s', err)
        return dnat_rules

    def _copy_mounted(self):
        ''' Copy data from inside the container to the host

        This method optionally enables to copy data from inside the container
        to the host so that non-empty bind mounts can be set up.

        Actually, this method moves the data from the container to the host to
        preserve the owner, group, and mode configuration.
        TODO Is there no way to "cp -ar" with shutil or another module?
        TODO Refactor method in smaller parts

        :param container: The container to handle
        '''

        def remove_trailing_slash(string):
            '''
            Dirty work-around that should be removed in the future, especially
            when files should be supported as bind-mounts
            '''
            if string.endswith('/'):
                return string[:-1]
            return string

        if self.project.args['dont_copy_on_create']:
            self.logger.debug('Skipping copying of mounts from inside container to outside')
            return
        if 'volumes' not in self.yml:
            self.logger.debug('No volumes defined')
            return

        rootfs = self.get_config_item('lxc.rootfs')
        assert len(rootfs)
        for volume in self.yml['volumes']:
            outside, inside = [remove_trailing_slash(locker.util.expand_vars(s.strip(), self)) for s in volume.split(':')]
            if os.path.exists(outside):
                self.logger.warn('Path \"%s\" exists on host, skipping', outside)
                continue
            if os.path.isfile(rootfs+inside):
                self.logger.warn('\"%s\" is a file (not supported yet), skipping', rootfs+inside)
                continue

            outside_parent = os.path.dirname(outside)
            if os.path.exists(outside_parent):
                input_var = input("Parent folder \"%s\" already exists. Continue to move data to \"%s\"? [y/N]: " % (outside_parent, outside))
                if input_var not in ['y', 'Y']:
                    self.logger.info('Skipping volume \"%s\"', volume)
                    continue
            else:
                try:
                    os.makedirs(outside_parent)
                    self.logger.debug('Created directory \"%s\"', outside_parent)
                except OSError:
                    self.logger.warn('Could not create parent directory \"%s\". Data not moved from container to host!', outside_parent)
                    continue

            if os.path.exists(inside):
                # Move from container to host should preseve owner and group, recreate dir afterwards in container
                self.logger.debug('Move \"%s\" to \"%s\"', rootfs+inside, outside)
                shutil.move(rootfs+inside, outside)
                os.mkdir(rootfs+inside)
            else:
                try:
                    os.makedirs(outside)
                    self.logger.warn('\"%s\" did not exist within the container, created empty directory on host', outside)
                except OSError:
                    self.logger.warn('Could not create \"%s\" on host (\"%s\" does not exist inside the container)', outside, inside)
                    continue

    def links(self, auto_update=False):
        '''
        Link container to another container

        :returns: False on any error, else True
        '''

        def link_container(name, alias=None, auto_update=False):
            self.logger.debug('Linking with %s', name)
            container = self.project.get_container(name)
            if not container:
                self.logger.error('Cannot link with unavailable container: %s', name)
                return False
            if not container.running:
                # Suppress message when it's clear that the container may have been stopped
                if auto_update:
                    self.logger.debug('Cannot link with stopped container: %s', name)
                else:
                    self.logger.warning('Cannot link with stopped container: %s', name)
                return False
            ips = container.get_ips()
            aliases = list()
            if 'fqdn' in container.yml:
                aliases.append(container.yml['fqdn'])
            if alias:
                aliases.append(alias)
            entries = list()
            for ip in ips:
                entries.append((ip, name, aliases))
            self._update_etc_hosts(entries)


        self.logger.debug('Updating links')
        if not 'links' in self.yml:
            self.logger.debug('No links defined')
            return True
        # TODO What are valid container names/identifiers?!? the documentation
        # only mentions "alphanumeric string" but, e.g., underscores are also ok.
        # TODO Check should be moved to project
        # TODO Add support for multiple aliases. Alt: Change YAML conf. format.
        link_regex = re.compile(r'^(?P<name>[\d\w_-]+)(?::(?P<alias>[\d\w_-]*))?$')
        for link in self.yml['links']:
            match = link_regex.match(link)
            if not match:
                self.logger.error('Invalid link statement: %s', link)
                continue
            group_dict = match.groupdict()
            name = group_dict['name']
            alias = None
            if 'alias' in group_dict:
                alias = group_dict['alias']
            link_container(name, alias, auto_update)
        return True

    def _update_etc_hosts(self, entries):
        '''
        Update /etc/hosts with new entries

        This method deletes old, project specific entries from /etc/hosts and
        then adds the specified ones.
        Locker entries are suffixed with the project name as comment

        :params: List of entries to add
        '''
        rootfs = self.get_config_item('lxc.rootfs')
        assert len(rootfs)
        etc_hosts = '%s/etc/hosts' % (rootfs)
        with open(etc_hosts, 'r') as etc_hosts_rfile:
            lines = etc_hosts_rfile.readlines()
        regex = re.compile('^.* # %s_.+$' % self.project.name)
        with open(etc_hosts, 'w+') as etc_hosts_wfile:
            for line in lines:
                if regex.match(line):
                    self.logger.debug('Removing from /etc/hosts: %s', line[:-1])
                    continue
                etc_hosts_wfile.write(line)
            for ip, name, aliases in entries:
                new_entry = '%s %s %s # %s_%s' % (ip, name, ' '.join(aliases), self.project.name, name)
                self.logger.debug('Adding to /etc/hosts: %s', new_entry)
                etc_hosts_wfile.write('%s\n' % (new_entry))

    def rmlinks(self):
        ''' Update /etc/hosts by removing all links
        '''
        self.logger.debug('Removing links')
        self._update_etc_hosts([])
        return True

    def linked_to(self):
        '''
        Return list of linked containers based on /etc/hosts

        :returns: List of linked containers
        '''
        linked = list()
        try:
            rootfs = self.get_config_item('lxc.rootfs')
        except KeyError:
            return linked
        assert len(rootfs)
        etc_hosts = '%s/etc/hosts' % (rootfs)
        with open(etc_hosts, 'r') as etc_hosts_rfile:
            lines = etc_hosts_rfile.readlines()
        regex = re.compile('^.* # (%s_.+)$' % self.project.name)
        for line in lines:
            match = regex.match(line)
            if match:
                linked.append(match.group(1))
        return linked