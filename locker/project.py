'''
This module provides the Project class that abstracts a group of containers
that are defined in a Loocker project. Each function public method reflects
a Locker command and may handle selected containers in the project.
'''

import logging
import re
import sys
from functools import wraps

import locker
import prettytable
from colorama import Fore
from locker.container import CommandFailed, Container
from locker.etchosts import Hosts
from locker.network import Network
from locker.util import break_and_add_color, regex_project_name, rules_to_str


def container_list(func):
    ''' Set value of "containers" parameter

    This decorator is for methods that have a named / keyword parameter named
    "containers". The parameter will be set to all containers if missing or
    set to None.
    All methods using this decorator should force the use of the keyword for
    "containers" to avoid errors due to duplicated values for the parameter.
    '''
    @wraps(func)
    def container_list_wrapper(*args, **kwargs):
        ''' Sets containers keyword argument if necessary '''
        if 'containers' not in kwargs or not kwargs['containers']:
            kwargs['containers'] = args[0].containers
        return func(*args, **kwargs)
    return container_list_wrapper

class Project(object):
    '''
    Abtracts a group of containers
    '''

    @property
    def args(self):
        ''' Get the parsed command line arguments '''
        return self._args

    @args.setter
    def args(self, value):
        ''' Set the parsed command line arguments '''
        if not isinstance(value, dict):
            raise TypeError('Invalid type for args: %s' % type(value))
        self._args = value

    @property
    def name(self):
        ''' Get name of the project '''
        return self._name

    @name.setter
    def name(self, value):
        ''' Set name of the project '''
        if not re.match(regex_project_name, value):
            raise ValueError('Invalid value for project name: %s' % value)
        self._name = value

    @property
    def containers(self):
        ''' Get all selected containers '''
        return self._containers

    @containers.setter
    def containers(self, value):
        ''' Set selected containers '''
        if not isinstance(value, list):
            raise TypeError('Invalid type for container: %s' % type(value))
        if len([x for x in value if not isinstance(x, locker.Container)]):
            raise TypeError('List contains invalid type: [%s]' %
                            ','.join([type(x) for x in value]))
        self._containers = value

    @property
    def all_containers(self):
        ''' Get all containers '''
        return self._all_containers

    @all_containers.setter
    def all_containers(self, value):
        ''' Set all containers '''
        if not isinstance(value, list):
            raise TypeError('Invalid type for all_containers: %s' % type(value))
        if len([x for x in value if not isinstance(x, locker.Container)]):
            raise TypeError('List contains invalid type: [%s]' %
                            ','.join([type(x) for x in value]))
        self._all_containers = value

    @property
    def yml(self):
        ''' Get parsed YAML configuration '''
        return self._yml

    @yml.setter
    def yml(self, value):
        ''' Set parsed YAML configuration '''
        if not isinstance(value, dict):
            raise TypeError('Invalid type for yml: %s' % type(value))
        self._yml = value

    @property
    def network(self):
        ''' Get the network instance '''
        return self._network

    @network.setter
    def network(self, value):
        ''' Set the network instance '''
        if not isinstance(value, Network):
            raise TypeError('Invalid type for network: %s' % type(value))
        self._network = value

    def __init__(self, yml, args):
        ''' Initialize a new project instance

        :param yml: YAML configuration file of the project
        :param args: Parsed command line parameters
        '''
        self.args = args
        self.name = args['project']
        self.network = Network(self)
        containers, all_containers = Container.get_containers(self, yml)
        self.containers = containers
        self.all_containers = all_containers
        self.yml = yml

    def get_container(self, name):
        '''
        Get container based on name (excluding project prefix)

        :param name: Name of the container
        :returns: Container object if found, else None
        '''
        pname = '%s_%s' % (self.name, name)
        for con in self.all_containers:
            if con.name == pname:
                return con
        return None

    @container_list
    def status(self, *, containers=None):
        ''' Show status of all project specific containers

        TODO Status report functionality requires some refactoring

        :param containers: List of containers or None (== all containers)
        '''
        if not self.args.get('extended', False):
            header = ['Def.', 'Name', 'FQDN', 'State', 'IPs', 'Ports', 'Links']
        else:
            header = ['Def.', 'Name', 'FQDN', 'State', 'IPs', 'Ports', 'Links', 'CPUs', 'Shares', 'Memory [MB]']
        table = prettytable.PrettyTable(header)
        table.align = 'l'
        table.hrules = prettytable.HEADER
        table.vrules = prettytable.NONE
        table.align['CPUs'] = 'r'
        table.align['Shares'] = 'r'
        table.align['Memory [MB]'] = 'r'

        for container in containers:
            defined = container.defined
            name = container.name
            state = container.state
            fqdn = container.yml.get('fqdn', '')
            ips = container.get_ips()
            if ips:
                ips = ','.join(ips)
            dnat_rules = container.get_port_rules()
            ports = rules_to_str(dnat_rules)
            reset_color = Fore.RESET if container.color else ''
            ports = break_and_add_color(container, ports)
            linked_to = break_and_add_color(container, container.linked_to())

            if not self.args.get('extended', False):
                table.add_row(['%s%s%s' % (container.color, x, reset_color) for x in [defined, name, fqdn, state, ips, ports, linked_to]])
            else:
                cpus = container.get_cgroup_item('cpuset.cpus')
                cpu_shares = container.get_cgroup_item('cpu.shares')
                mem_limit = container.get_cgroup_item('memory.limit_in_bytes')
                if not mem_limit or int(mem_limit) == 2**64 - 1:
                    mem_limit = 'unlimited'
                else:
                    mem_limit = int(int(mem_limit) / 10**6)

                try:
                    with open('/sys/fs/cgroup/memory/lxc/%s/memory.max_usage_in_bytes' % container.name) as memf:
                        mem_used = int(int(memf.readline()) / 10**6)
                except FileNotFoundError:
                    mem_used = 0

                memory = '%s/%s' % (mem_used, mem_limit)
                table.add_row(['%s%s%s' % (container.color, x, reset_color) for x in [defined, name, fqdn, state, ips, ports, linked_to, cpus, cpu_shares, memory]])
        sys.stdout.write(table.get_string()+'\n')

    @container_list
    def start(self, *, containers=None):
        ''' Start all or selected containers

        Starts the container, sets cgroup settings and optionally set ports.
        Subsequently, all links of all containers are updated.

        :param containers: List of containers or None (== all containers)
        '''
        self.network.start()
        for container in containers:
            try:
                container.start()
                container.cgroup()
                if not self.args.get('no_ports', False):
                    container.ports(indirect=True)
            except CommandFailed:
                pass
        if not self.args.get('no_links', False):
            self.links(containers=self.all_containers, auto_update=True)
        if self.args.get('add_hosts', False):
            self._update_etc_hosts()

    @container_list
    def reboot(self, *, containers=None):
        ''' Reboot all or selected containers

        This method runs the stop command and then the start command to ensure
        that all netfilter rules and links are removed and re-added.

        :param containers: List of containers or None (== all containers)
        '''
        for container in containers:
            try:
                self.stop(containers=[container])
                self.start(containers=[container])
            except CommandFailed:
                pass

    @container_list
    def stop(self, containers=None):
        ''' Stop all or selected containers

        :param containers: List of containers or None (== all containers)
        '''
        for container in containers:
            try:
                container.stop()
                if not self.args.get('no_ports', False):
                    self.rmports(containers=[container])
            except CommandFailed:
                pass
        if not self.args.get('no_links', False):
            self.links(containers=self.all_containers, auto_update=True)
        if self.args.get('add_hosts', False):
            self._update_etc_hosts()

    @container_list
    def create(self, *, containers=None):
        ''' Create all or selected containers

        :param containers: List of containers or None (== all containers)
        '''
        for container in containers:
            try:
                container.create()
            except CommandFailed:
                pass
            except ValueError:
                pass

    @container_list
    def remove(self, *, containers=None):
        ''' Destroy all or selected containers

        :param containers: List of containers or None (== all containers)
        '''
        for container in containers:
            try:
                container.remove()
            except CommandFailed:
                pass

    @container_list
    def ports(self, *, containers=None):
        ''' Add firewall rules to enable port forwarding

        :param containers: List of containers or None (== all containers)
        '''
        for container in containers:
            try:
                container.ports()
            except CommandFailed:
                pass

    @container_list
    def rmports(self, *, containers=None):
        ''' Remove firewall rules that enable port forwarding

        :param containers: List of containers or None (== all containers)
        '''
        for container in containers:
            try:
                container.rmports()
            except CommandFailed:
                pass

    @container_list
    def links(self, *, containers=None, auto_update=False):
        ''' Add links in all or selected containers

        :param containers: List of containers or None (== all containers)
        '''
        for container in containers:
            try:
                container.links(auto_update)
            except CommandFailed:
                pass

    @container_list
    def rmlinks(self, *, containers=None):
        ''' Remove links in all or selected containers

        :param containers: List of containers or None (== all containers)
        '''
        for container in containers:
            try:
                container.rmlinks()
            except CommandFailed:
                pass

    @container_list
    def cgroup(self, *, containers=None):
        ''' Set cgroup configuration

        :param containers: List of containers or None (== all containers)
        '''
        for container in containers:
            try:
                container.cgroup()
            except CommandFailed:
                pass

    def cleanup(self):
        ''' Stop all container, remove bridge and all netfilter rules

        Stops all containers and on success, removes the netfilter rules,
        and then the project bridge.
        Exception: This does not remove the LOCKER chain in the NAT table and
        the jump from the PREROUTING chain to the LOCKER chain!
        '''
        self.stop(containers=self.all_containers)
        if len([con for con in self.all_containers if con.running]):
            logging.error('Was not able to stop all container, cannot cleanup')
            return
        self.network.stop()

    def _update_etc_hosts(self):
        ''' Add containers hostnames to /etc/hosts for name resolution
        '''
        logging.debug('Updating /etc/hosts')
        etc_hosts = '/etc/hosts'
        try:
            hosts = Hosts(etc_hosts, logger=logging.getLogger(), lax=True)
            num_removed = hosts.remove_by_comment('^%s_.*$' % (self.name))
            logging.debug('Removed %d entries from %s', num_removed, etc_hosts)
            hosts.save()
        except Exception as exception:
            logging.warn('Some exception occured: ', exception)
            return

        for container in [con for con in self.all_containers if con.running]:
            for ipaddr in container.get_ips():
                fqdn = container.yml.get('fqdn', None)
                hostname = None
                if fqdn:
                    hostname = fqdn.split('.')[0]
                names = [n for n in [fqdn, hostname, container.name] if n]
                comment = container.name
                hosts.add(ipaddr, names, comment)
        hosts.save()
