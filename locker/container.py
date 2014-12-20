'''
This module provides an extended lxc container class.
'''

import lxc
import logging
from colorama import Fore
import iptc
import re
import time
import os
import shutil
from locker.util import rule_to_str, regex_container_name, regex_link, regex_ports, regex_volumes, regex_cgroup
import locker.project
from locker.network import Network
from functools import wraps

class CommandFailed(RuntimeError):
    ''' Generic command failed RuntimeError '''
    def __init__(self, arg):
        self.msg = arg

    def __str__(self):
        return repr(self.msg)

def return_if_not_defined(func):
    @wraps(func)
    def return_if_not_defined_wrapper(*args, **kwargs):
        if not args[0].defined:
            args[0].logger.debug('Container is not yet defined')
            return
        else:
            return func(*args, **kwargs)
    return return_if_not_defined_wrapper

def return_if_defined(func):
    @wraps(func)
    def return_if_defined_wrapper(*args, **kwargs):
        if args[0].defined:
            args[0].logger.debug('Container is defined')
            return
        else:
            return func(*args, **kwargs)
    return return_if_defined_wrapper

def return_if_not_running(func):
    @wraps(func)
    def return_if_not_running_wrapper(*args, **kwargs):
        if not args[0].running:
            args[0].logger.debug('Container is stopped')
            return
        else:
            return func(*args, **kwargs)
    return return_if_not_running_wrapper

class Container(lxc.Container):
    ''' Extended lxc.Container class

    This class adds:

      - Checks and logging
      - Locker specific attributes
      - Handling of project specifc parameters
    '''

    def __init__(self, name, yml, project, color='', config_path=None):
        ''' Init instance with custom property values and init base class
        '''
        if not re.match(regex_container_name, name):
            raise ValueError('Invalid value for container name: %s' % name)
        self.yml = yml
        self.project = project
        self.color = color
        self.logger = logging.getLogger(name)
        self.logger.propagate = False
        reset_color = Fore.RESET if self.color else ''
        formatter = logging.Formatter('%(asctime)s, %(levelname)8s: ' + color + '[' + name + '] %(message)s' + reset_color)
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        lxc.Container.__init__(self, name, config_path)

    @staticmethod
    def get_containers(project, yml):
        '''
        Generate a list of container objects

        :param yml: YAML project configuration
        :returns:   Tuple: List of selected containers, List of all containers
        '''
        containers = list()
        all_containers = list()
        colors = [Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, Fore.MAGENTA, Fore.CYAN]

        for num, name in enumerate(sorted(yml.keys())):
            pname = '%s_%s' % (project.name, name)
            if pname not in lxc.list_containers():
                logging.debug('Container \"%s\" does not exist yet or is not accessible as this user.', pname)
            if project.args.get('no_color', False):
                color = ''
            else:
                color = colors[num % len(colors)]
            container = Container(pname, yml[name], project, color)

            all_containers.append(container)
            if len(project.args['containers']) and pname not in project.args['containers']:
                continue
            containers.append(container)
        logging.debug('Selected containers: %s', [con.name for con in containers])
        return (containers, all_containers)

    def _network_conf(self):
        ''' Apply network configuration
        '''
        # TODO Should check if there is any network device at all
        self.network[0].link = self.project.network.bridge_ifname
        self.network[0].veth_pair = self.name
        self.network[0].ipv4 = self.project.network.get_ip(self)
        # BUG Setting the gateway does not work as expected
        # TODO Activate once its clear how the gateway can be set
        #self.network[0].ipv4_gateway = self.project.network.gateway
        self.logger.debug('Network configuration: link=%s, veth=%s, ipv4=%s, gateway=%s',
                          self.network[0].link, self.network[0].veth_pair,
                          self.network[0].ipv4, self.network[0].ipv4_gateway)
        self.save_config()

    @return_if_not_defined
    def _enable_dns(self, dns=['8.8.8.8', '8.8.4.4'], files=['/etc/resolv.conf', '/etc/resolvconf/resolv.conf.d/base']):
        ''' Set DNS servers in /etc/resolv.conf and further files

        Write the specified DNS server IP addresses as name server entries to
        the specified files. Please note that the file will be overwritten but
        will not be created if missing.

        :param dns: List of IPs (as string) to set as name servers
        :param files: List of filenames where to write the name server entries
        '''
        self.logger.debug('Enabling name resolution: %s', dns)
        try:
            rootfs = self.get_config_item('lxc.rootfs')
        except KeyError:
            self.logger.debug('rootfs is still empty, container defined = %s',
                              self.defined)
            return

        _files = ['%s/%s' % (rootfs, rfile) for rfile in files]
        for rconf_file in _files:
            try:
                with open(rconf_file, 'w') as rconf:
                    for server in dns:
                        rconf.write('nameserver %s\n' % server)
                    rconf.write('\n')
                self.logger.debug('Updated: %s', rconf_file)
            except Exception as exception:
                self.logger.warn('Could not set %s: %s', rconf_file, exception)

    @return_if_not_defined
    def cgroup(self):
        ''' Apply cgroup settings

        Apply the cgroup configuration that is available as key-value pair
        in the YAML configuration file in the "cgroups" subtree.
        The method will update the current values of the container if it is
        running and always write the new values to the container's config file.
        '''
        if not 'cgroup' in self.yml:
            self.logger.debug('No cgroup settings')
            return
        self.logger.debug('Applying cgroup settings')
        regex = re.compile(regex_cgroup)
        for cgroup in self.yml['cgroup']:
            match = regex.match(cgroup)
            if not match:
                self.logger.warn('Malformed cgroup setting: %s', cgroup)
                continue
            key = match.group(1)
            value = match.group(2)
            if self.running:
                if not self.set_cgroup_item(key, value):
                    self.logger.warn('Was not able to set: %s = %s', key, value)
            self.set_config_item('lxc.cgroup.' + key, value)
        self.save_config()

    @return_if_not_defined
    @return_if_not_running
    def get_ips(self, retries=10):
        '''
        Get IPs of the container

        :param retries: Try a again this many times if IPs are not available yet
        :returns: List of IPs or None if the container is not defined or stopped
        '''
        ips = lxc.Container.get_ips(self)
        while len(ips) == 0 and self.running and retries > 0:
            self.logger.debug('Waiting to acquire an IP address')
            time.sleep(1)
            ips = lxc.Container.get_ips(self)
            retries -= 1
        return ips

    @property
    def project(self):
        return self._project

    @project.setter
    def project(self, value):
        if not isinstance(value, locker.Project):
            raise TypeError('Invalid type for property project: %s, required type = %s' % (type(value), type(locker.Project)))
        self._project = value

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value):
        if value not in [Fore.BLACK, Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, Fore.MAGENTA, Fore.CYAN, Fore.WHITE, '']:
            raise ValueError('Invalid color: %s' % value)
        self._color = value

    @property
    def yml(self):
        return self._yml

    @yml.setter
    def yml(self, value):
        if not isinstance(value, dict):
            raise TypeError('Invalid type for value: %s' % type(value))
        self._yml = value

    @property
    def logger(self):
        return self._logger

    @logger.setter
    def logger(self, value):
        if not isinstance(value, logging.Logger):
            raise TypeError('Invalid type for property logger: %s, required type = %s' % (type(value), type(logging.Logger)))
        self._logger = value

    @return_if_not_defined
    def start(self):
        '''
        Start container

        :raises: CommandFailed
        '''
        if self.running:
            self.logger.debug('Container is already running')
            if not self.project.args.get('restart', False):
                self.logger.debug('Container will not be restarted')
                return
            self.logger.info('Restarting container')
            try:
                self.stop()
            except CommandFailed:
                raise
        self._generate_fstab()
        self._set_fqdn_hook()
        self._network_conf()
        self._enable_dns()
        self.logger.info('Starting container')
        lxc.Container.start(self)
        if not self.running:
            self.logger.critical('Could not start container')
            raise CommandFailed('Could not start container')

    @return_if_not_defined
    @return_if_not_running
    def stop(self):
        '''
        Stop container

        :raises: CommandFailed
        '''
        self.logger.info('Stopping container')
        self.rmlinks()
        if not self.shutdown(self.project.args.get('timeout', 30)):
            self.logger.warn('Could not shutdown, forcing stop')
            lxc.Container.stop(self)
        if self.running:
            self.logger.critical('Could not stop container')
            raise CommandFailed('Could not stop container')

    @return_if_defined
    def create(self):
        '''
        Create container based on template or as clone

        :raises: CommandFailed
        '''

        def _create_from_template(self):
            ''' Create container from template specified in YAML configuration

            The "template" subtree in the YAML configuration will be provided as
            arguments to the template.
            '''
            self.logger.info('Creating container from template: %s', self.yml['template']['name'])
            flags = lxc.LXC_CREATE_QUIET
            if self.project.args.get('verbose', False):
                flags = 0
            lxc.Container.create(self, self.yml['template']['name'], flags, args=self.yml['template'])
            if not self.defined:
                self.logger.error('Creation failed from template: %s', self.yml['template']['name'])
                self.logger.error('Try again with \"--verbose\" for more information')
                raise CommandFailed('Creation failed from template: %s' % self.yml['template']['name'])
            self._copy_mounted()

        def _clone_from_existing(self):
            ''' Clone container from an existing container

            This method is a little "awkward" because this container (self) will
            create a new, temp. container instance of the container to clone
            from which then creates the clone. Hence the clone and this instance
            (self) are not the same. The Python lxc bindings allow to create
            multiple lxc.Container instances for the same lxc container.
            As the clone is only of type lxc.Container and not locker.Container,
            we will use this container instance (self) for further actions.
            '''
            clone = self.yml['clone']
            if clone not in lxc.list_containers():
                self.logger.error('Cannot clone, container does not exist or is not accessible: %s', clone)
                raise ValueError('Cannot clone, container does not exist or is not accessible: %s' % clone)
            origin = lxc.Container(clone)
            self.logger.info('Cloning from: %s', origin.name)
            cloned = origin.clone(self.name)
            if not cloned or not cloned.defined:
                self.logger.error('Cloning failed from: %s', origin.name)
                raise CommandFailed('Cloning failed from: %s' % origin.name)
            self._copy_mounted()

        if len([x for x in self.yml if x in ['template', 'clone']]) != 1:
            self.logger.error('You must provide either \"template\" or \"clone\" in container configuration')
            raise ValueError('You must provide either \"template\" or \"clone\" in container configuration')

        if 'template' in self.yml:
            _create_from_template(self)
        else:
            _clone_from_existing(self)

    @return_if_not_defined
    def remove(self):
        '''
        Destroy container

        :raises: CommandFailed
        '''
        if not self.project.args.get('delete_dont_ask', False):
            # TODO Implement a timeout here?!?
            input_var = input("Delete %s? [y/N]: " % (self.name))
            if input_var not in ['y', 'Y']:
                self.logger.info('Skipping deletion')
                return
        try:
            try:
                self.stop()
            except CommandFailed:
                raise
            if not lxc.Container.destroy(self):
                self.logger.error('Container was not deleted')
                raise CommandFailed('Container was not deleted')
        except CommandFailed:
            raise

    def rmports(self):
        ''' Remove netfilter rules
        '''
        self.logger.debug('Removing netfilter rules')
        if self.running:
            self.logger.warn('Container is still running, services will be unavailable')

        nat_table = iptc.Table(iptc.Table.NAT)
        locker_chain = iptc.Chain(nat_table, 'LOCKER')
        Network._delete_if_comment(self.name, nat_table, locker_chain)

        filter_table = iptc.Table(iptc.Table.FILTER)
        forward_chain = iptc.Chain(filter_table, 'FORWARD')
        Network._delete_if_comment(self.name, filter_table, forward_chain)

    def _has_netfilter_rules(self):
        ''' Check if there are any netfilter rules for this container

        Netfilter rules are matched by the comment - if it exists.

        :returns: True if any rule found, else False
        '''
        self.logger.debug('Checking if container has already rules')
        nat_table = iptc.Table(iptc.Table.NAT)
        locker_chain = iptc.Chain(nat_table, 'LOCKER')
        filter_table = iptc.Table(iptc.Table.FILTER)
        forward_chain = iptc.Chain(filter_table, 'FORWARD')

        return Network.find_comment_in_chain(self.name, locker_chain) or Network.find_comment_in_chain(self.name, forward_chain)

    def _add_dnat_rule(self, container_ip, port_conf, locker_nat_chain):
        ''' Add rule to the LOCKER chain in the NAT table
        '''
        port_forwarding = iptc.Rule()
        port_forwarding.protocol = port_conf['proto']
        if port_conf['host_ip']:
            port_forwarding.dst = port_conf['host_ip']
        port_forwarding.in_interface = '!%s' % self.project.network.bridge_ifname
        tcp_match = port_forwarding.create_match(port_conf['proto'])
        tcp_match.dport = port_conf['host_port']
        comment_match = port_forwarding.create_match('comment')
        comment_match.comment = self.name
        target = port_forwarding.create_target('DNAT')
        target.to_destination = '%s:%s' % (container_ip, port_conf['container_port'])
        locker_nat_chain.insert_rule(port_forwarding)

    def _add_forward_rule(self, container_ip, port_conf, filter_forward):
        ''' Add rule to the FORWARD chain in the FILTER table
        '''
        forward_rule = iptc.Rule()
        forward_rule.protocol = port_conf['proto']
        forward_rule.dst = container_ip
        forward_rule.in_interface = '!%s' % self.project.network.bridge_ifname
        forward_rule.out_interface = self.project.network.bridge_ifname
        tcp_match = forward_rule.create_match(port_conf['proto'])
        tcp_match.dport = port_conf['container_port']
        comment_match = forward_rule.create_match('comment')
        comment_match.comment = self.name
        forward_rule.create_target('ACCEPT')
        filter_forward.insert_rule(forward_rule)

    @return_if_not_defined
    @return_if_not_running
    def ports(self, indirect=False):
        ''' Add netfilter rules to enable port forwarding

        :param indirect: Set to True to avoid the warning output that there
                          already are netfilter rules for this container. This
                          is usualy desired when ports() is indirectly called
                          via the "start" command.
        '''
        def _parse_port_conf(self, fwport):
            ''' Split port forward directive in parts

            :param fwport: Port forwarding configuration
            :raises: ValueError if fwport is invalid
            '''
            regex = re.compile(regex_ports)
            match = regex.match(fwport)
            if not match:
                self.logger.error('Invalid port forwarding directive: %s', fwport)
                raise ValueError('Invalid port forwarding directive: %s', fwport)
            mdict = match.groupdict()
            mdict['proto'] = mdict['proto_udp'] or 'tcp'
            return mdict

        if not 'ports' in self.yml:
            self.logger.debug('No port forwarding rules')
            return
        self.logger.debug('Adding port forwarding rules')

        locker_nat_chain = iptc.Chain(iptc.Table(iptc.Table.NAT), 'LOCKER')
        filter_forward = iptc.Chain(iptc.Table(iptc.Table.FILTER), 'FORWARD')
        if self._has_netfilter_rules():
            if not indirect:
                self.logger.warn('Existing netfilter rules found - must be removed first')
            return

        for fwport in self.yml['ports']:
            try:
                port_conf = _parse_port_conf(self, fwport)
            except ValueError:
                continue
            ips = self.get_ips()
            for container_ip in ips:
                if container_ip.find(':') >= 0:
                    self.logger.warn('Found unsupported IPv6 address: %s', container_ip)
                    continue
                self._add_dnat_rule(container_ip, port_conf, locker_nat_chain)
                self._add_forward_rule(container_ip, port_conf, filter_forward)

    def _set_fqdn_hook(self):
        ''' Set FQDN hook script to set the FQDN

        This works when the container and when /etc is a bind-mount as long as
        / and /locker are not covered by another mount. The hook script must be
        inside the containers namespace.
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
        Currently only bind mounted directories are supported.
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
                regex = re.compile(regex_volumes)
                for volume in self.yml['volumes']:
                    match = regex.match(volume)
                    if not match:
                        logging.warn('Invalid volume specification: %s', volume)
                        continue
                    remote = locker.util.expand_vars(match.group(1), self)
                    mountpt = locker.util.expand_vars(match.group(2), self)
                    self.logger.debug('Adding to fstab: %s %s none bind 0 0', remote, mountpt)
                    fstab.write('%s %s none bind 0 0\n' % (remote, mountpt))
            fstab.write('\n')

    def get_netfiler_rules(self):
        '''
        Get port forwarding netfilter rules of the container

        This method only searches the LOCKER chain in the NAT table and ignores
        the FORWARD chain in the FILTER table!
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

        def _remove_trailing_slash(string):
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
            # TODO Use regex!
            outside, inside = [_remove_trailing_slash(locker.util.expand_vars(s.strip(), self)) for s in volume.split(':')]
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

    @return_if_not_defined
    def links(self, auto_update=False):
        ''' Link container with other containers

        Links the container to any other container that is specified in the
        particular "links" subtree in YAML file.
        TODO Refactor, the _link_container is not really a descriptive/matching
             name

        :param auto_update: Set to True to suppress some logger output because
                            the container to link to is purposely stopped and
                            unavailable.
        '''

        def _link_container(self, name, alias=None, auto_update=False):
            self.logger.debug('Linking with %s', name)
            container = self.project.get_container(name)
            if not container:
                self.logger.error('Cannot link with unavailable container: %s', name)
                return
            if not container.running:
                # Suppress message when it's clear that the particular container may have been stopped
                if auto_update:
                    self.logger.debug('Cannot link with stopped container: %s', name)
                else:
                    self.logger.warning('Cannot link with stopped container: %s', name)
                return
            ips = container.get_ips()
            aliases = list()
            if 'fqdn' in container.yml:
                aliases.append(container.yml['fqdn'])
            if alias:
                aliases.append(alias)
            entries = [(ip, name, aliases) for ip in ips]
            self._update_etc_hosts(entries)

        self.logger.debug('Updating links')
        if not 'links' in self.yml:
            self.logger.debug('No links defined')
            return
        link_regex = re.compile(regex_link)
        for link in self.yml['links']:
            match = link_regex.match(link)
            if not match:
                self.logger.error('Invalid link statement: %s', link)
                continue
            group_dict = match.groupdict()
            name = group_dict['name']
            alias = group_dict.get('alias', None)
            _link_container(self, name, alias, auto_update)

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
        try:
            with open(etc_hosts, 'r') as etc_hosts_rfile:
                lines = etc_hosts_rfile.readlines()
        except FileNotFoundError:
            self.logger.warn('/etc/hosts does not exists inside rootfs')
            return
        # TODO Use better regex
        regex = re.compile('^.* # (%s_.+)$' % self.project.name)
        with open(etc_hosts, 'w+') as etc_hosts_wfile:
            for line in lines:
                if regex.match(line):
                    self.logger.debug('Removing from /etc/hosts: %s', line[:-1])
                    continue
                etc_hosts_wfile.write(line)
            for ipaddr, name, aliases in entries:
                new_entry = '%s %s %s # %s_%s' % (ipaddr, name, ' '.join(aliases), self.project.name, name)
                self.logger.debug('Adding to /etc/hosts: %s', new_entry)
                etc_hosts_wfile.write('%s\n' % (new_entry))

    def rmlinks(self):
        ''' Update /etc/hosts by removing all links
        '''
        self.logger.debug('Removing links')
        self._update_etc_hosts([])

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
        try:
            with open(etc_hosts, 'r') as etc_hosts_rfile:
                lines = etc_hosts_rfile.readlines()
        except FileNotFoundError:
            return linked

        # TODO Use a better regex
        regex = re.compile('^.* # (%s_.+)$' % self.project.name)
        for line in lines:
            match = regex.match(line)
            if match:
                linked.append(match.group(1))
        return linked
