'''
This module provides the Project class that abstracts a group of containers
that are defined in a Loocker project. Each function public method reflects
a Locker command and may handle selected containers in the project.
'''

import logging
import iptc
from colorama import Fore
import prettytable
from locker.container import Container
import sys

class Project(object):
    '''
    Abtracts a group of containers
    '''

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

    def status(self, containers=None):
        ''' Show status of all project specific containers

        :param containers: List of containers or None (== all containers)
        '''
        def break_and_add_color(vals):
            return '\n'.join(['%s%s%s' % (container.color, v, Fore.RESET) for v in vals])

        if containers == None:
            containers = self.containers

        header = ['Def.', 'Name', 'FQDN', 'State', 'IPs', 'Ports', 'Links']
        table = prettytable.PrettyTable(header)
        table.align = 'l'
        table.hrules = prettytable.HEADER
        table.vrules = prettytable.NONE
        for container in containers:
            defined = container.defined
            name = container.name
            state = container.state
            fqdn = '' if 'fqdn' not in container.yml else container.yml['fqdn']
            ips = '-'
            if container.running:
                ips = ','.join(container.get_ips())
            dnat_rules = container.get_netfiler_rules()
            ports = ['%s:%s->%s/%s' % (dip.split('/')[0], dport, to_port, proto) for proto, (dip, dport), (to_ip, to_port) in dnat_rules]
            ports = break_and_add_color(ports)
            linked_to = break_and_add_color(container.linked_to())
            table.add_row(['%s%s%s' % (container.color, x, Fore.RESET) for x in [defined, name, fqdn, state, ips, ports, linked_to]])
        sys.stdout.write(table.get_string()+'\n')

    def start(self, containers=None):
        ''' Start all or selected containers

        :param containers: List of containers or None (== all containers)
        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        result = True
        for container in containers:
            cresult = container.start()
            if cresult and not self.args['no_ports']:
                cresult = self.ports([container])
            result &= cresult
        if not self.args['no_links']:
            self.links(self.all_containers, auto_update=True)
        return result

    def stop(self, containers=None):
        ''' Stop all or selected containers

        :param containers: List of containers or None (== all containers)
        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        result = True
        for container in containers:
            cresult = container.stop()
            if cresult and not self.args['no_ports']:
                cresult = self.rmports([container])
            result &= cresult
        if not self.args['no_links']:
            self.links(containers=self.all_containers, auto_update=True)
        return result

    def create(self, containers=None):
        ''' Create all or selected containers

        :param containers: List of containers or None (== all containers)
        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        result = True
        for container in containers:
            result &= container.create()
        return result

    def remove(self, containers=None):
        ''' Destroy all or selected containers

        :param containers: List of containers or None (== all containers)
        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        result = True
        for container in containers:
            result &= container.remove()
        return result

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

    def ports(self, containers=None):
        ''' Add firewall rules to enable port forwarding

        :param containers: List of containers or None (== all containers)
        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        try:
            Project.prepare_locker_table()
        except iptc.IPTCError:
            return False

        result = True
        for container in containers:
            result &= container.ports()
        return result

    def rmports(self, containers=None):
        ''' Remove firewall rules that enable port forwarding

        :param containers: List of containers or None (== all containers)
        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        filter_table = iptc.Table(iptc.Table.FILTER)
        filter_table.autocommit = False

        nat_table = iptc.Table(iptc.Table.NAT)
        nat_table.autocommit = False

        # TODO try catch should be moved to Container.rmports()
        try:
            logging.debug('Removing netfilter rules')
            for container in containers:
                container.rmports()
        except iptc.IPTCError:
            logging.warn('An arror occured during the deletion of rules for \"%s\", check for relics', container.name)
        finally:
            filter_table.commit()
            filter_table.refresh() # work-around (iptc.ip4tc.IPTCError: can't commit: b'Resource temporarily unavailable')
            filter_table.autocommit = True
            nat_table.commit()
            nat_table.refresh() # work-around (iptc.ip4tc.IPTCError: can't commit: b'Resource temporarily unavailable')
            nat_table.autocommit = True
        return True

    def links(self, containers=None, auto_update=False):
        ''' Add links in all or selected containers

        :param containers: List of containers or None (== all containers)
        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        result = True
        for container in containers:
            result &= container.links(auto_update)
        return result

    def rmlinks(self, containers=None):
        ''' Remove links in all or selected containers

        :param containers: List of containers or None (== all containers)
        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        result = True
        for container in containers:
            result &= container.rmlinks()
        return result
