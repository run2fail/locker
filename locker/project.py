'''
This module provides the Project class that abstracts a group of containers
that are defined in a Loocker project. Each function public method reflects
a Locker command and may handle selected containers in the project.
'''

import logging
import iptc
from colorama import Fore
import prettytable
import locker
from locker.container import Container, CommandFailed
from locker.util import break_and_add_color, rule_to_str, rules_to_str, regex_project_name
import sys
import re
from functools import wraps

def container_list(func):
    ''' Set value of "containers" parameter

    This decorator is for methods that have a named / keyword parameter named
    "containers". The parameter will be set to all containers if missing or
    set to None.
    All methods using this decorator should force the use of the keyword for
    "containers" to avoid errors due to duplicated values for the parameter.
    '''
    @wraps(func)
    def func_wrapper(*args, **kwargs):
        if 'containers' not in kwargs or not kwargs['containers']:
            kwargs['containers'] = args[0].containers
        return func(*args, **kwargs)
    return func_wrapper

def needs_locker_table(func):
    ''' Ensures that the locker table exists
    '''
    @wraps(func)
    def func_wrapper(*args, **kwargs):
        try:
            Project.prepare_locker_table()
        except iptc.IPTCError:
            raise
        return func(*args, **kwargs)
    return func_wrapper

class Project(object):
    '''
    Abtracts a group of containers
    '''

    @property
    def args(self):
        return self._args

    @args.setter
    def args(self, value):
        if not isinstance(value, dict):
            raise TypeError('Invalid type for args: %s' % type(value))
        self._args = value

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if not re.match(regex_project_name, value):
            raise ValueError('Invalid value for project name: %s' % value)
        self._name = value

    @property
    def containers(self):
        return self._containers

    @containers.setter
    def containers(self, value):
        if not isinstance(value, list):
            raise TypeError('Invalid type for container: %s' % type(value))
        if len([x for x in value if not isinstance(x, locker.Container)]):
            raise TypeError('List contains invalid type: [%s]' % ','.join([type(x) for x in value]))
        self._containers = value

    @property
    def all_containers(self):
        return self._all_containers

    @all_containers.setter
    def all_containers(self, value):
        if not isinstance(value, list):
            raise TypeError('Invalid type for all_containers: %s' % type(value))
        if len([x for x in value if not isinstance(x, locker.Container)]):
            raise TypeError('List contains invalid type: [%s]' % ','.join([type(x) for x in value]))
        self._all_containers = value

    @property
    def yml(self):
        return self._yml

    @yml.setter
    def yml(self, value):
        if not isinstance(value, dict):
            raise TypeError('Invalid type for yml: %s' % type(value))
        self._yml = value

    def __init__(self, yml, args):
        ''' Initialize a new project instance

        :param yml: YAML configuration file of the project
        :param args: Parsed command line parameters
        '''
        self.args = args
        self.name = args['project']
        # TODO Add YAML configuration check here
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
        name = '%s_%s' % (self.name, name)
        for con in self.containers:
            if con.name == name:
                return con
        return None

    @container_list
    def status(self, *, containers=None):
        ''' Show status of all project specific containers

        :param containers: List of containers or None (== all containers)
        '''
        header = ['Def.', 'Name', 'FQDN', 'State', 'IPs', 'Ports', 'Links']
        table = prettytable.PrettyTable(header)
        table.align = 'l'
        table.hrules = prettytable.HEADER
        table.vrules = prettytable.NONE
        for container in containers:
            defined = container.defined
            name = container.name
            state = container.state
            fqdn = container.yml.get('fqdn', '')
            ips = container.get_ips()
            if ips:
                ips = ','.join(ips)
            dnat_rules = container.get_netfiler_rules()
            ports = rules_to_str(dnat_rules)
            reset_color = Fore.RESET if container.color else ''
            ports = break_and_add_color(container, ports)
            linked_to = break_and_add_color(container, container.linked_to())
            table.add_row(['%s%s%s' % (container.color, x, reset_color) for x in [defined, name, fqdn, state, ips, ports, linked_to]])
        sys.stdout.write(table.get_string()+'\n')

    @container_list
    def start(self, *, containers=None):
        ''' Start all or selected containers

        :param containers: List of containers or None (== all containers)
        '''
        for container in containers:
            try:
                container.start()
                if not 'not_ports' in self.args or not self.args['no_ports']:
                    self.ports(containers=[container])
            except CommandFailed:
                pass
        if not 'no_links' in self.args or not self.args['no_links']:
            self.links(containers=self.all_containers, auto_update=True)

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
                if not 'no_ports' in self.args or not self.args['no_ports']:
                    self.rmports(containers=[container])
            except CommandFailed:
                pass
        if not 'no_links' in self.args or not self.args['no_links']:
            self.links(containers=self.all_containers, auto_update=True)

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

    @staticmethod
    def prepare_locker_table():
        ''' Add container unspecific netfilter modifications

        This method does the following

          - Adds LOCKER chain to the NAT table
          - Creates a rule from the PREROUTING chain in the NAT table to the
            LOCKER chain
          - Ensures that the jump rule is only added once (the rule's comments
            are checked for a match)

        :throws: iptc.IPTCError if the LOCKER chain cannot be retrieved or
                 created
        '''
        nat_table = iptc.Table(iptc.Table.NAT)
        if 'LOCKER' not in [c.name for c in nat_table.chains]:
            try:
                logging.debug('Adding LOCKER chain to NAT table')
                nat_table.create_chain('LOCKER')
            except iptc.IPTCError:
                logging.error('Was not able to create LOCKER chain in NAT table, cannot add rules')
                raise
        assert 'LOCKER' in [c.name for c in nat_table.chains]

        nat_prerouting_chain = iptc.Chain(nat_table, 'PREROUTING')
        for rule in nat_prerouting_chain.rules:
            for match in rule.matches:
                if match.name == 'comment' and match.comment == 'LOCKER':
                    logging.debug('Found rule to jump from PREROUTING chain to LOCKER chain')
                    return

        jump_to_locker_rule = iptc.Rule()
        jump_to_locker_rule.create_target("LOCKER")
        addr_type_match = jump_to_locker_rule.create_match("addrtype")
        addr_type_match.dst_type = "LOCAL"
        comment_match = jump_to_locker_rule.create_match("comment")
        comment_match.comment = 'LOCKER'
        nat_prerouting_chain.insert_rule(jump_to_locker_rule)

    @needs_locker_table
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
        # TODO Move the autocommit disabling + enabling to Container
        filter_table = iptc.Table(iptc.Table.FILTER)
        filter_table.autocommit = False

        nat_table = iptc.Table(iptc.Table.NAT)
        nat_table.autocommit = False

        logging.debug('Removing netfilter rules')
        for container in containers:
            try:
                container.rmports()
            except CommandFailed:
                pass

        filter_table.commit()
        filter_table.refresh() # work-around (iptc.ip4tc.IPTCError: can't commit: b'Resource temporarily unavailable')
        filter_table.autocommit = True
        nat_table.commit()
        nat_table.refresh() # work-around (iptc.ip4tc.IPTCError: can't commit: b'Resource temporarily unavailable')
        nat_table.autocommit = True

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
