'''
This module provides an extended lxc container class.
'''

import logging
import os
import re
import shutil
import time
from collections import OrderedDict
from functools import wraps

import iptc
import locker.project
import lxc
import netaddr
from colorama import Fore
from locker.etchosts import Hosts
from locker.network import Network
from locker.util import (regex_cgroup, regex_container_name, regex_link,
                         regex_ports, regex_volumes, rule_to_str)


class CommandFailed(RuntimeError):
    ''' Generic command failed RuntimeError '''
    pass

def return_if_not_defined(func):
    ''' Return if the container has not been defined '''
    @wraps(func)
    def return_if_not_defined_wrapper(*args, **kwargs):
        if not args[0].defined:
            args[0].logger.debug('Container is not yet defined')
            return
        else:
            return func(*args, **kwargs)
    return return_if_not_defined_wrapper

def return_if_defined(func):
    ''' Return if the container has been defined '''
    @wraps(func)
    def return_if_defined_wrapper(*args, **kwargs):
        if args[0].defined:
            args[0].logger.debug('Container is defined')
            return
        else:
            return func(*args, **kwargs)
    return return_if_defined_wrapper

def return_if_not_running(func):
    ''' Return if the container is not running '''
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

        :param name: Name of the container
        :param project: Project instance of this container
        :param color: ASCII color escape sequence for log messages
        :param config_path: Path to the container's config file
        '''
        if not re.match(regex_container_name, name):
            raise ValueError('Invalid value for container name: %s' % name)
        self.yml = yml
        self.project = project
        self.color = color
        self.logger = logging.getLogger(name)
        if self.logger.propagate:
            self.logger.propagate = False
            reset_color = Fore.RESET if self.color else ''
            sname = name.split('_')[1]
            formatter = logging.Formatter('%(asctime)s, %(levelname)8s: ' + color + '[' + sname + '] %(message)s' + reset_color)
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        lxc.Container.__init__(self, name, config_path)

    def __str__(self):
        return self.name

    def __repr__(self):
        return 'Container(%s: project=%s, config_path=%s)' % (self, self.project.name, self.get_config_path())

    @staticmethod
    def get_containers(project, yml):
        ''' Generate a list of container objects

        Returns lists of containers that have been defined in the YAML
        configuration file.
        TODO Use dict instead of list

        :param yml: YAML project configuration
        :returns:  (List of selected containers, List of all containers)
        '''
        containers = list()
        all_containers = list()
        colors = [Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, Fore.MAGENTA, Fore.CYAN]

        for num, name in enumerate(sorted(yml['containers'].keys())):
            pname = '%s_%s' % (project.name, name)
            if pname not in lxc.list_containers():
                logging.debug('Container does not exist yet or is not accessible: %s', pname)
            color = colors[num % len(colors)] if not project.args.get('no_color', False) else ''
            lxcpath = project.args.get('lxcpath', '/var/lib/lxc')
            container = Container(pname, yml['containers'][name], project, color, lxcpath)

            all_containers.append(container)
            if ('containers' in project.args and # required for cleanup command
                len(project.args['containers']) and
                name not in project.args['containers']):
                continue
            containers.append(container)
        logging.debug('Selected containers: %s', [con.name for con in containers])
        return (containers, all_containers)

    def _network_conf(self):
        ''' Apply network configuration

        The the container's network configuration in the config file.
        '''
        ip = self.project.network.get_ip(self)
        gateway = self.project.network.gateway
        link = self.project.network.bridge_ifname
        veth_pair = self.name

        #self.network[0].link = link
        #self.network[0].veth_pair = veth_pair
        #self.network[0].ipv4 = ip
        #self.network[0].ipv4_gateway = gateway

        self.set_config_item('lxc.network.0.link', link)
        self.set_config_item('lxc.network.0.veth.pair', veth_pair)
        self.set_config_item('lxc.network.0.ipv4', ip.split('/')[0])
        self.set_config_item('lxc.network.0.ipv4.gateway', gateway)

        self.save_config()

    def _get_dns(self):
        ''' Get DNS server configuration as defined in the yml configuration

        Creates a list of DNS servers to use by this container based on the YAML
        configuration file. The following are supported:
        - Magic word "$bridge": takes the project bridges IP address, e.g., if
            you are running a custom dnsmasq process listening on this interface
        - Magic word "$copy": copies the DNS from the container's host system
        - Any valid IP address as string

        Additionally, the default DNS configuration is evaluated and used to
        derive the container's nameserver configuration. Container specific
        DNS servers have precedence over the default configuration.

        :returns: list of DNS IP addresses (as strings)
        '''
        list_of_dns = list()
        try:
            defaults = self.project.yml['defaults']
        except KeyError:
            defaults = {}
        defaults_dns = defaults.get('dns', [])
        container_dns = self.yml.get('dns', [])
        dns_list = container_dns + defaults_dns
        for dns in list(OrderedDict.fromkeys(dns_list)):
            if dns == "$bridge":
                list_of_dns.append(self.project.network.gateway)
            elif dns == "$copy":
                list_of_dns.extend(Network.get_dns_from_host())
            else:
                try:
                    list_of_dns.append(str(netaddr.IPAddress(dns)))
                except netaddr.AddrFormatError:
                    self.logger.warning('Invalid DNS address specified: %s', dns)
        # remove duplicates but keep original order
        return list(OrderedDict.fromkeys(list_of_dns))

    @return_if_not_defined
    def _enable_dns(self, dns=[], files=['/etc/resolv.conf', '/etc/resolvconf/resolv.conf.d/base']):
        ''' Set DNS servers in /etc/resolv.conf and further files

        Write the specified DNS server IP addresses as name server entries to
        the specified files. Please note that the file will be overwritten but
        will not be created if missing.

        :param dns: List of IPs (as string) to set as name servers
        :param files: List of filenames where to write the name server entries
        '''
        self.logger.debug('Enabling name resolution: %s', dns)
        assert self.rootfs.startswith(self.project.args.get('lxcpath', '/var/lib/lxc'))

        _files = ['%s/%s' % (self.rootfs, rfile) for rfile in files]
        for rconf_file in _files:
            try:
                with open(rconf_file, 'w') as rconf:
                    for server in dns:
                        self.logger.debug('Adding nameserver: %s (in %s)', server, rconf_file)
                        rconf.write('nameserver %s\n' % server)
                    rconf.write('\n')
            except Exception as exception:
                self.logger.warning('Could not update nameservers in %s: %s', rconf_file, exception)
            self.logger.debug('Updated: %s', rconf_file)

    @return_if_not_defined
    def cgroup(self):
        ''' Apply cgroup settings

        Apply the cgroup configuration that is available as key-value pair
        in the YAML configuration file in the "cgroups" subtree.
        The method will update the current values of the container if it is
        running and always write the new values to the container's config file.
        '''
        self.logger.info('Setting cgroup configuration')
        regex = re.compile(regex_cgroup)

        try:
            defaults = self.project.yml['defaults']
        except KeyError:
            defaults = {}
        defaults_cgroup = defaults.get('cgroup', [])
        container_cgroup = self.yml.get('cgroup', [])
        cgroup_items = dict()
        for cgroup in defaults_cgroup + container_cgroup: # defaults go first
            match = regex.match(cgroup)
            if not match:
                self.logger.warning('Malformed cgroup setting: %s', cgroup)
                continue
            key = match.group(1)
            value = match.group(2)
            cgroup_items[key] = value # will overwrite defaults

        for key, value in cgroup_items.items():
            if self.running and not self.set_cgroup_item(key, value):
                self.logger.warning('Was not able to set while running: %s = %s', key, value)
            elif not self.set_config_item('lxc.cgroup.' + key, value):
                self.logger.warning('Was not able to set in config: %s = %s', key, value)
        self.save_config()

    @return_if_not_defined
    @return_if_not_running
    def get_ips(self, retries=10, family='inet'):
        ''' Get IP addresses of the container

        Sleeps for 1s between each retry.

        :param retries: Try a again this many times if IPs are not available yet
        :param family: Filter by the address family
        :returns: List of IPs or None if the container is not defined or stopped
        '''
        ips = lxc.Container.get_ips(self, family=family)
        while len(ips) == 0 and self.running and retries > 0:
            self.logger.debug('Waiting to acquire an IP address')
            time.sleep(1)
            ips = lxc.Container.get_ips(self, family=family)
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
        valid_colors = [Fore.BLACK, Fore.RED, Fore.GREEN, Fore.YELLOW,
                        Fore.BLUE, Fore.MAGENTA, Fore.CYAN, Fore.WHITE, '']
        if value not in valid_colors:
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

    @property
    def rootfs(self):
        rootfs = self.get_config_item('lxc.rootfs')
        if not len(rootfs):
            raise ValueError('rootfs is empty, container defined = %s', self.defined)
        return rootfs

    @return_if_not_defined
    def start(self):
        ''' Start container

        Starts the container after:
        - Generation of the fstab file for bind mount support
        - Setting the hostname inside the rootfs
        - Setting the network ocnfiguration in the container's config file
        - Setting the nameservers in the rootfs

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
        self._set_hostname()
        self._network_conf()
        self._enable_dns(dns=self._get_dns())
        self.logger.info('Starting container')
        lxc.Container.start(self)
        if not self.running:
            self.logger.critical('Could not start container')
            raise CommandFailed('Could not start container')

    @return_if_not_defined
    @return_if_not_running
    def stop(self):
        ''' Stop container

        :raises: CommandFailed
        '''
        self.logger.info('Stopping container')
        self.rmlinks()
        if not self.shutdown(self.project.args.get('timeout', 30)):
            self.logger.warning('Could not shutdown, forcing stop')
            lxc.Container.stop(self)
        if self.running:
            self.logger.critical('Could not stop container')
            raise CommandFailed('Could not stop container')

    @return_if_defined
    def create(self):
        ''' Create container based on template or as clone

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
            self._move_dirs()

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
            self.logger.debug('Config patch: %s', self.project.args.get('lxcpath', '/var/lib/lxc'))
            if clone not in lxc.list_containers(config_path=self.project.args.get('lxcpath', '/var/lib/lxc')):
                self.logger.error('Cannot clone, container does not exist or is not accessible: %s', clone)
                raise ValueError('Cannot clone, container does not exist or is not accessible: %s' % clone)
            origin = lxc.Container(clone, self.project.args.get('lxcpath', '/var/lib/lxc'))
            assert origin.defined
            self.logger.info('Cloning from: %s', origin.name)
            cloned = origin.clone(self.name, config_path=self.project.args.get('lxcpath', '/var/lib/lxc'))
            if not cloned or not cloned.defined:
                self.logger.error('Cloning failed from: %s', origin.name)
                raise CommandFailed('Cloning failed from: %s' % origin.name)
            self._move_dirs()

        def _download(self):
            ''' Create container by downloading a base image

            The "download" subtree in the YAML configuration will be provided as
            arguments to the download template.
            '''
            try:
                dist = self.yml['download']['dist']
            except KeyError:
                self.logger.error('Missing value for key: %s', 'dist')
                return
            try:
                arch = self.yml['download']['arch']
            except KeyError:
                self.logger.error('Missing value for key: %s', 'arch')
                return
            try:
                release = self.yml['download']['release']
            except KeyError:
                self.logger.error('Missing value for key: %s', 'release')
                return
            self.logger.info('Downloading base image: dist=%s, release=%s, arch=%s', dist, release, arch)
            flags = lxc.LXC_CREATE_QUIET
            if self.project.args.get('verbose', False):
                flags = 0
            lxc.Container.create(self, 'download', flags, args=self.yml['download'])
            if not self.defined:
                self.logger.error('Download of base image failed')
                self.logger.error('Try again with \"--verbose\" for more information')
                raise CommandFailed('Download of base image failed')
            self._move_dirs()

        if len([x for x in self.yml if x in ['template', 'clone', 'download']]) != 1:
            self.logger.error('You must provide either "template", "clone", or "download" in the container configuration')
            raise ValueError('You must provide either "template", "clone", or "download" in the container configuration')

        if 'template' in self.yml:
            _create_from_template(self)
        elif 'clone' in self.yml:
            _clone_from_existing(self)
        else:
            _download(self)

    @return_if_not_defined
    def remove(self):
        ''' Destroy container

        Stops the container and deletes the image. The user must confirm the
        deletion (of each container) if --delete-dont-ask was not provided.

        :raises: CommandFailed
        '''

        self.logger.info('Removing container')
        if not self.project.args.get('force_delete', False):
            # TODO Implement a timeout here?!?
            input_var = input("Delete %s? [y/N]: " % (self.name.split('_')[1]))
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
        ''' Remove netfilter rules that enable port forwarding

        This method removes all netfilter that have been added to make ports
        of the container accessible from external sources.
        This will not remove the netfilter rules added for linking!
        '''
        self.logger.info('Removing netfilter rules')
        if self.running:
            self.logger.warning('Container is still running, services will be unavailable')

        nat_table = iptc.Table(iptc.Table.NAT)
        locker_chain = iptc.Chain(nat_table, 'LOCKER_PREROUTING')
        Network._delete_if_comment(self.name, nat_table, locker_chain)

        filter_table = iptc.Table(iptc.Table.FILTER)
        forward_chain = iptc.Chain(filter_table, 'LOCKER_FORWARD')
        Network._delete_if_comment(self.name, filter_table, forward_chain)

    def _has_netfilter_rules(self):
        ''' Check if there are any netfilter rules for this container

        Netfilter rules are matched by the comment - if it exists.

        :returns: True if any rule found, else False
        '''
        self.logger.debug('Checking if container has already rules')
        nat_table = iptc.Table(iptc.Table.NAT)
        locker_chain = iptc.Chain(nat_table, 'LOCKER_PREROUTING')
        filter_table = iptc.Table(iptc.Table.FILTER)
        forward_chain = iptc.Chain(filter_table, 'LOCKER_FORWARD')

        return Network.find_comment_in_chain(self.name, locker_chain) or Network.find_comment_in_chain(self.name, forward_chain)

    def _add_port_rules(self, container_ip, port_conf, locker_chain, forward_chain):
        ''' Add rule to the LOCKER chain in the NAT table and to the FORWARD
        chain in the FILTER table

        :param container_ip: IP addresss of the container
        :param port_conf: dictionary with parsed port configuration
        :param locker_chain: LOCKER chain in the NAT table
        :param forward_chain: FORWARD chain in the FILTER table
        '''
        locker_rule = iptc.Rule()
        locker_rule.protocol = port_conf['proto']
        if port_conf['host_ip']:
            locker_rule.dst = port_conf['host_ip']
        locker_rule.in_interface = '!%s' % self.project.network.bridge_ifname
        tcp_match = locker_rule.create_match(port_conf['proto'])
        tcp_match.dport = port_conf['host_port']
        comment_match = locker_rule.create_match('comment')
        comment_match.comment = self.name
        target = locker_rule.create_target('DNAT')
        target.to_destination = '%s:%s' % (container_ip, port_conf['container_port'])
        locker_chain.insert_rule(locker_rule)

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
        forward_chain.insert_rule(forward_rule)

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
                raise ValueError('Invalid port forwarding directive: %s', fwport)
            mdict = match.groupdict()
            mdict['proto'] = mdict['proto_udp'] or 'tcp'
            return mdict

        self.logger.info('Adding port forwarding rules')
        if not 'ports' in self.yml:
            self.logger.debug('No port forwarding rules found')
            return

        locker_nat_chain = iptc.Chain(iptc.Table(iptc.Table.NAT), 'LOCKER_PREROUTING')
        filter_forward = iptc.Chain(iptc.Table(iptc.Table.FILTER), 'LOCKER_FORWARD')
        if self._has_netfilter_rules():
            if not indirect:
                self.logger.warning('Existing netfilter rules found - must be removed first')
            return

        for fwport in self.yml['ports']:
            try:
                port_conf = _parse_port_conf(self, fwport)
            except ValueError:
                continue
            for container_ip in self.get_ips():
                self._add_port_rules(container_ip, port_conf, locker_nat_chain, filter_forward)

    def _set_hostname(self):
        ''' Set container hostname

        Sets the container's hostname and FQDN in /etc/hosts and /etc/hostname if
        fqdn is specified in the YAML configuration.
        '''
        fqdn = self.yml.get('fqdn', None)
        if not fqdn:
            self.logger.debug('Empty fqdn')
            return
        hostname = fqdn.split('.')[0]
        etc_hosts = '%s/etc/hosts' % (self.rootfs)
        try:
            hosts = Hosts(etc_hosts, self.logger)
            names = [fqdn, hostname]
            hosts.update_ip('127.0.1.1', names)
            hosts.save()
        except:
            pass
        etc_hostname = '%s/etc/hostname' % (self.rootfs)
        with open(etc_hostname, 'w+') as hostname_fd:
            hostname_fd.write('%s\d' % hostname)

    @return_if_not_defined
    def _generate_fstab(self):
        ''' Generate a file system table for the container

        This function generates a fstab file based on the volume information in the
        YAML configuration.
        Currently only bind mounted directories are supported.
        TODO Revvaluate if the fstab file is better than lxc.mount.entry
        '''
        fstab_file = self.get_config_item('lxc.mount')
        if not fstab_file:
            fstab_file = os.path.join(*[self.get_config_path(), self.name, 'fstab'])
        self.logger.debug('Generating fstab: %s', fstab_file)
        with open(fstab_file, 'w+') as fstab:
            if 'volumes' in self.yml:
                regex = re.compile(regex_volumes)
                for volume in self.yml['volumes']:
                    match = regex.match(volume)
                    if not match:
                        logging.warning('Invalid volume specification: %s', volume)
                        continue
                    remote = locker.util.expand_vars(match.group(1), self)
                    mountpt = locker.util.expand_vars(match.group(2), self)
                    self.logger.debug('Adding to fstab: %s %s none bind 0 0', remote, mountpt)
                    fstab.write('%s %s none bind 0 0\n' % (remote, mountpt))
            fstab.write('\n')

    def get_port_rules(self):
        ''' Get port forwarding netfilter rules of the container

        This method only searches the LOCKER chain in the NAT table and ignores
        the FORWARD chain in the FILTER table!

        :returns: list of rules as tuple (protocol, (dst, port), (ip, port))
        '''
        nat_table = iptc.Table(iptc.Table.NAT)
        locker_nat_chain = iptc.Chain(nat_table, 'LOCKER_PREROUTING')
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
            self.logger.warning('An arror occured searching the netfiler rules: %s', err)
        return dnat_rules

    def _move_dirs(self):
        ''' Move directories from inside the container to the host

        This method optionally enables to move data from inside the container
        to the host so that non-empty bind mounts can be set up. If a directory
        does not exist within the container, it will be created.

        This method moves the data from the container to the host to
        preserve the owner, group, and mode configuration.
        TODO Is there no way to "cp -ar" with shutil or another module?
        '''

        def _remove_slash(string):
            ''' Temp. work-around '''
            if string.endswith('/'):
                return string[:-1]
            return string

        if self.project.args.get('no_move', False):
            self.logger.debug('Skipping moving of directories from container to host system')
            return
        if 'volumes' not in self.yml:
            self.logger.debug('No volumes defined')
            return

        rootfs = self.rootfs
        for volume in self.yml['volumes']:
            # TODO Use regex!
            outside, inside = [_remove_slash(locker.util.expand_vars(s.strip(), self)) for s in volume.split(':')]
            outside_parent = os.path.dirname(outside)

            if os.path.exists(outside):
                self.logger.warning('Directory exists on host system, skipping: %s', outside)
                continue
            if os.path.isfile(rootfs+inside):
                self.logger.warning('Files are not supported, skipping: %s', rootfs+inside)
                continue

            if not os.path.exists(outside_parent):
                try:
                    os.makedirs(outside_parent)
                except OSError as error:
                    self.logger.error('Could not create parent directory on host system: %s, %s', outside_parent, error)
                    continue
                else:
                    self.logger.debug('Created parent directory on host system: %s', outside_parent)

            if os.path.isdir(rootfs+inside):
                # Move should preseve owner and group,
                # recreate dir afterwards in container again as mount point
                self.logger.debug('Moving directory: %s -> %s', rootfs+inside, outside)
                try:
                    shutil.move(rootfs+inside, outside)
                except shutil.Error as error:
                    self.logger.error('Could not move directory: %s', error)
                    continue

                try:
                    os.mkdir(rootfs+inside)
                except OSError:
                    self.logger.error('Could not create directory in the container: %s', rootfs+inside)
                    continue
                continue

            try:
                os.makedirs(outside)
            except OSError:
                self.logger.error('Could not create directory on host system: %s', outside)
                continue
            else:
                self.logger.info('Created empty on host system: %s', outside)

            try:
                os.makedirs(rootfs+inside)
            except OSError:
                self.logger.error('Could not create directory in the container: %s', rootfs+inside)
                continue
            else:
                self.logger.info('Created empty directory in the container: %s', rootfs+inside)

    @return_if_not_defined
    def links(self, auto_update=False):
        ''' Link container with other containers

        Links the container to any other container that is specified in the
        particular "links" subtree in YAML file.

        :param auto_update: Set to True to suppress some logger output because
                            the container to link to is purposely stopped and
                            unavailable.
        '''
        self.logger.info('Updating links')
        if not 'links' in self.yml:
            self.logger.debug('No links defined')
            return
        link_regex = re.compile(regex_link)
        hosts_entries = list()
        for link in self.yml['links']:
            match = link_regex.match(link)
            if not match:
                self.logger.error('Invalid link statement: %s', link)
                continue
            group_dict = match.groupdict()
            name = group_dict['name']
            container = self.project.get_container(name)
            if not container:
                self.logger.error('Cannot link with unavailable container: %s', name)
                continue
            if not container.running:
                # Suppress message when it's clear that the particular container
                # may have been stopped
                if auto_update:
                    self.logger.debug('Cannot link with stopped container: %s', name)
                else:
                    self.logger.warning('Cannot link with stopped container: %s', name)
                continue
            names = [container.yml.get('fqdn', None), name, group_dict.get('alias', None)]
            names = [x for x in names if x]
            hosts_entries.extend([(ip, name, names) for ip in container.get_ips()])
        self._update_etc_hosts(hosts_entries)
        self._update_link_rules(hosts_entries)

    @return_if_not_running
    def _add_link_rules(self, entries):
        ''' Add netfilter rules to enable communication between containers

        This method adds netfilter rules that enable this container to
        communicate with the linked containers. Communication is allowing using
        any port and any protocol.
        These netfilter rules are required if the policy of the forward chain
        in the filter table has been set to drop.

        :params: List of entries to add, format (ipaddr, container name, names)
        '''
        forward_chain = iptc.Chain(iptc.Table(iptc.Table.FILTER), 'LOCKER_FORWARD')
        if Network.find_comment_in_chain(self.name + ':link', forward_chain):
            self.logger.debug('Found netfilter link rules, skipping')
            return

        for ipaddr, _name, _names in entries:
            for ip in self.get_ips():
                # self -> other containers
                rule = iptc.Rule()
                rule.src = ip
                rule.dst = ipaddr
                rule.in_interface = self.project.network.bridge_ifname
                rule.out_interface = self.project.network.bridge_ifname
                comment_match = rule.create_match('comment')
                comment_match.comment = self.name + ':link'
                rule.create_target('ACCEPT')
                forward_chain.insert_rule(rule)

                # other containers -> self
                rule = iptc.Rule()
                rule.src = ipaddr
                rule.dst = ip
                rule.in_interface = self.project.network.bridge_ifname
                rule.out_interface = self.project.network.bridge_ifname
                comment_match = rule.create_match('comment')
                comment_match.comment = self.name + ':link'
                rule.create_target('ACCEPT')
                forward_chain.insert_rule(rule)

    def _remove_link_rules(self):
        ''' Remove netfilter rules required for link support '''
        filter_table = iptc.Table(iptc.Table.FILTER)
        forward_chain = iptc.Chain(filter_table, 'LOCKER_FORWARD')
        Network._delete_if_comment(self.name + ':link', filter_table, forward_chain)

    def _update_link_rules(self, entries):
        ''' Wrapper that first removes all rules and then adds the specified ones

        TODO Find a better solution than completely removing all rules first

        :params: List of entries to add, format (ipaddr, container name, names)
        '''
        self._remove_link_rules()
        self._add_link_rules(entries)

    @return_if_not_defined
    def _update_etc_hosts(self, entries):
        ''' Update /etc/hosts with new entries

        This method deletes old, project specific entries from /etc/hosts and
        then adds the specified ones.
        Locker entries are suffixed with the project name as comment

        :params: List of entries to add, format (ipaddr, container name, names)
        '''
        etc_hosts = '%s/etc/hosts' % (self.rootfs)
        try:
            hosts = Hosts(etc_hosts, self.logger)
            hosts.remove_by_comment('^%s_.*$' % self.project.name)
            for ipaddr, name, names in entries:
                comment = '%s_%s' % (self.project.name, name)
                hosts.add(ipaddr, names, comment)
            hosts.save()
        except:
            pass

    def rmlinks(self):
        ''' Update /etc/hosts by removing all links
        '''
        self.logger.info('Removing links')
        self._update_etc_hosts([])
        self._remove_link_rules()

    @return_if_not_defined
    def linked_to(self):
        ''' Return list of linked containers based on /etc/hosts

        Does not evaluate the YAML configuration but the actual state of the
        container.
        TODO Does not yet check netfilter rules

        :returns: List of linked containers
        '''
        linked = list()
        etc_hosts = '%s/etc/hosts' % (self.rootfs)
        try:
            with open(etc_hosts, 'r') as etc_hosts_fd:
                lines = etc_hosts_fd.readlines()
        except FileNotFoundError:
            return linked

        # TODO Use a better regex
        regex = re.compile('^.* # %s_(.+)$' % self.project.name)
        for line in lines:
            match = regex.match(line)
            if match:
                linked.append(match.group(1))
        return linked

    def get_cgroup_item(self, key):
        ''' Get cgroup item

        Tries to get the cgroup item and returns only single item if a list
        was returned. The method first tries to query the key's value from the
        running container and if this fails tries to get the value from the
        config file.

        :param key: The key / name of the cgroup item
        :returns: cgroup item
        '''
        self.logger.debug('Getting cgroup item: %s', key)
        try:
            # will fail if the container is not running
            value = lxc.Container.get_cgroup_item(self, key)
            return value
        except KeyError:
            pass

        try:
            # 2nd try: get value from config file
            # get_config_item() can return either
            # - an empty string
            # - a list with a single value
            # - something else that I do not expect
            value = self.get_config_item('lxc.cgroup.' + key)
        except KeyError:
            return None

        if value == '':
            # This seems to be the standard value if the key was not found
            pass
        elif isinstance(value, list) and len(value) == 1:
            # Locker relevant cgroup keys should always return only one
            # value but this may still be a list.
            value = value[0]
        else:
            raise ValueError('Unexpected value for cgroup item: %s = %s' % (key, value))
        return value
