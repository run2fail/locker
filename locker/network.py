'''
Network related functionality like bridge and netfilter setup
'''

import itertools
import logging
import re

import iptc
import locker
import netaddr
import pyroute2
from locker.util import regex_ip


class BridgeUnavailable(Exception):
    ''' Bridge device does not exist

    Raised if the project specific bridge is unavailable, i.e., it cannot be
    access by the current user (due to privileges or because it has not yet
    been created).
    '''
    pass

class Network(object):
    '''
    The network class handles the bridge and container-unspecific netfilter rules
    '''

    def __init__(self, project):
        ''' Calls start() to setup netfilter rules and bridge
        '''
        self.project = project
        self._bridge = self._get_existing_bridge()

    @property
    def project(self):
        ''' Get locker project instance '''
        return self._project

    @project.setter
    def project(self, value):
        ''' Set locker project instance '''
        if not isinstance(value, locker.Project):
            raise TypeError('Invalid type for property project: %s, required type = %s' % (type(value), type(locker.Project)))
        self._project = value

    @property
    def bridge(self):
        ''' Get bridge assigned to the project '''
        if not self._bridge:
            raise BridgeUnavailable()
        return self._bridge

    @bridge.setter
    def bridge(self, value):
        ''' Set bridge assigned to the project '''
        if not isinstance(value, pyroute2.ipdb.interface.Interface):
            raise TypeError('Invalid type for property bridge: %s, required type = %s' % (type(value), type(pyroute2.ipdb.interface.Interface)))
        self._bridge = value

    @property
    def bridge_ifname(self):
        ''' Get the name of the bridge assigned to the project '''
        return self.bridge.ifname

    @property
    def gateway(self):
        ''' Get gateway / IP address of the bridge '''
        bridge_ip, bridge_cidr = Network._if_to_ip(self.bridge)
        return bridge_ip

    @staticmethod
    def find_comment_in_chain(comment, chain):
        ''' Search rule with a matching comment

        :param comment: The comment to match
        :param chain: The chain  to search
        :returns: True if any matching rule found, else False
        '''
        for rule in chain.rules:
            for match in rule.matches:
                if match.name == 'comment' and match.comment == comment:
                    logging.debug('Found rule with comment \"%s\" in \"%s\" chain', comment, chain.name)
                    return True
        return False

    @staticmethod
    def _delete_if_comment(comment, table, chain):
        ''' Search rule with a matching comment and delete it

        :param comment: The comment to match
        :param table: The table containing the chain
        :param chain: The chain to search
        '''
        # work-around (iptc.ip4tc.IPTCError: can't commit: b'Resource temporarily unavailable')
        table.autocommit = False
        for rule in chain.rules:
            for match in rule.matches:
                if match.name == 'comment' and match.comment == comment:
                    logging.debug('Cleaning up rule from chain: %s', chain.name)
                    try:
                        chain.delete_rule(rule)
                    except iptc.IPTCError as exception:
                        logging.warn('Could not cleanup rule from chain \"%s\": %s', chain, exception)
        table.commit()
        table.refresh()
        table.autocommit = True

    def _setup_locker_chain(self):
        ''' Add container unspecific netfilter modifications

        This method does the following

          - Adds LOCKER chain to the NAT table
          - Creates a rule from the PREROUTING chain in the NAT table to the
            LOCKER chain
          - Ensures that the jump rule is only added once (the rule's comments
            are checked for a match)

        :raises: iptc.IPTCError if the LOCKER chain cannot be retrieved or
                 created
        '''
        nat_table = iptc.Table(iptc.Table.NAT)
        if 'LOCKER' not in [c.name for c in nat_table.chains]:
            try:
                logging.debug('Adding LOCKER chain to NAT table')
                nat_table.create_chain('LOCKER')
            except iptc.IPTCError as exception:
                logging.error('Was not able to create LOCKER chain in NAT table, cannot add rules: %s', exception)
                raise

        nat_prerouting_chain = iptc.Chain(nat_table, 'PREROUTING')
        if not Network.find_comment_in_chain('LOCKER', nat_prerouting_chain):
            jump_to_locker_rule = iptc.Rule()
            jump_to_locker_rule.create_target("LOCKER")
            addr_type_match = jump_to_locker_rule.create_match("addrtype")
            addr_type_match.dst_type = "LOCAL"
            comment_match = jump_to_locker_rule.create_match("comment")
            comment_match.comment = 'LOCKER'
            nat_prerouting_chain.insert_rule(jump_to_locker_rule)

    def start(self):
        ''' Sets bridge and netfilter rules up
        '''
        self._setup_locker_chain()
        self._create_bridge()
        self._enable_nat()

    def _enable_nat(self):
        ''' Add netfilter rules that enable direct communication from the containers
        '''
        filter_forward = iptc.Chain(iptc.Table(iptc.Table.FILTER), 'FORWARD')
        if not Network.find_comment_in_chain(self.bridge_ifname, filter_forward):
            logging.info('Adding NAT rules for external access')
            # enable access the containers to external destinations
            enable_outbound = iptc.Rule()
            enable_outbound.in_interface = self.bridge_ifname
            enable_outbound.out_interface = '!%s' % self.bridge_ifname
            enable_outbound.create_target('ACCEPT')
            comment_match = enable_outbound.create_match("comment")
            comment_match.comment = self.bridge_ifname
            filter_forward.insert_rule(enable_outbound)

            # enable access from external source to the containers
            enable_inbound = iptc.Rule()
            enable_inbound.in_interface = '!%s' % self.bridge_ifname
            enable_inbound.out_interface = self.bridge_ifname
            enable_inbound.create_target('ACCEPT')
            comment_match = enable_inbound.create_match("comment")
            comment_match.comment = self.bridge_ifname
            filter_forward.insert_rule(enable_inbound)

        nat_prerouting = iptc.Chain(iptc.Table(iptc.Table.NAT), 'POSTROUTING')
        if not Network.find_comment_in_chain(self.bridge_ifname, nat_prerouting):
            logging.info('Adding masquerade rules for external access')
            # masquerade outbound connections
            bridge_ip, bridge_cidr = Network._if_to_ip(self.bridge)
            network = netaddr.IPNetwork('%s/%s' % (bridge_ip, bridge_cidr))
            masquerade_rule = iptc.Rule()
            masquerade_rule.create_target('MASQUERADE')
            masquerade_rule.src = str(network.cidr)
            masquerade_rule.dst = '!%s' % str(network.cidr)
            comment_match = masquerade_rule.create_match("comment")
            comment_match.comment = self.bridge_ifname
            nat_prerouting.insert_rule(masquerade_rule)

    def _disable_nat(self):
        ''' Remove netfilter rules that enable direct communication from the containers
        '''
        try:
            bridge_ifname = self.bridge_ifname
        except BridgeUnavailable:
            return

        filter_table = iptc.Table(iptc.Table.FILTER)
        forward_chain = iptc.Chain(filter_table, 'FORWARD')
        Network._delete_if_comment(bridge_ifname, filter_table, forward_chain)

        nat_table = iptc.Table(iptc.Table.NAT)
        postrouting_chain = iptc.Chain(nat_table, 'POSTROUTING')
        Network._delete_if_comment(bridge_ifname, nat_table, postrouting_chain)

    def _get_existing_bridge(self):
        ''' Get bridge device if it exists

        :returns: pyroute2.ipdb.interface.Interface if found, else None
        '''
        bridge_ifname = 'locker_%s' % self.project.name
        ipdb = pyroute2.IPDB()
        try:
            bridge = ipdb.by_name[bridge_ifname]
        except KeyError:
            logging.debug('Bridge was not found: %s', bridge_ifname)
            return None
        finally:
            ipdb.release()
        return bridge

    def _create_bridge(self):
        ''' Create project specific bridge interface

        :raises: Any exception that pyroute2 may raise
        '''
        bridge_ifname = 'locker_%s' % self.project.name
        ipdb = pyroute2.IPDB()
        try:
            if not bridge_ifname in ipdb.by_name.keys():
                logging.info('Creating bridge: %s', bridge_ifname)
                network = Network._get_unused_subnet()
                with ipdb.create(kind='bridge', ifname=bridge_ifname) as bridge:
                    bridge.add_ip(network)
                    bridge.up()
                    self.bridge = bridge
            else:
                self.bridge = ipdb.by_name[bridge_ifname]
                logging.debug('Bridge exists: %s', self.bridge_ifname)
        except Exception as exception:
            logging.error('Could not create bridge: %s', exception)
            raise
        finally:
            ipdb.release()

    def _delete_bridge(self):
        ''' Delete project specific bridge

        :param bridge_ifname: Name of the bridge
        :raises: Any exception that pyroute2 may raise
        '''
        try:
            bridge_ifname = self.bridge_ifname
        except BridgeUnavailable:
            return

        ipdb = pyroute2.IPDB()
        try:
            with ipdb.by_name[bridge_ifname] as brdev:
                logging.info('Deleting bridge: %s', bridge_ifname)
                brdev.remove()
        except Exception as exception:
            logging.error('Could not delete bridge: %s', exception)
            raise
        finally:
            ipdb.release()

    def _get_used_ips(self):
        ''' Get list of IPs used by all containers

        Note: This does not include the bridge's IP and the broadcast address!

        :returns: List of IPs (strings)
        '''
        ips = [con.get_ips() for con in self.project.all_containers if con.get_ips()]
        ips = list(itertools.chain(*ips))
        logging.debug('IP addresses in use by containers: %s', ips)
        return ips

    @staticmethod
    def _get_unused_subnet():
        ''' Get an unused  /24 subnet

        Get the first unused IP subnetwork in the 10.0.0.0 net.
        The method queries all networks that are reachable by the currently
        known network interfaces.
        Search starts at 10.1.1.0.

        TODO Enable to select range for subnets, e.g., (10.2.3.0, 10.42.6.0)
        TODO Method could be refactored to be more pythonic

        :returns: First valid IP address in the subnet/CIDR_Mask as string
        :raises: RuntimeError if out of available networks
        '''

        # Get all used subnets
        ipdb = pyroute2.IPDB()
        ipset = netaddr.IPSet()
        try:
            for ifname, vals in ipdb.by_name.items():
                ips = Network._if_to_ip(vals, all_ips=True)
                for ipaddr, cidr in [(x, y) for x, y in ips if x.startswith('10.')]:
                    network = netaddr.IPNetwork('%s/%s' % (ipaddr, cidr))
                    ipset.add(network)
        finally:
            ipdb.release()

        # Find unused subnet
        for oct3 in range(1, 256):
            for oct2 in range(1, 256):
                network = '10.%d.%d.1/24' % (oct2, oct3)
                if ipset.isdisjoint(netaddr.IPSet([network])):
                    logging.debug('Found free /24 subnet: %s', network)
                    return network
        logging.critical('No unused /24 network availabe in 10.0.0.0')
        raise RuntimeError('No unused /24 network availabe in 10.0.0.0')

    def get_ip(self, container):
        ''' Get IP address

        Get the first unused IP address in the network associated bridge.

        :returns: IP address as string
        :raises: RuntimeError if out of available addresses
        '''
        used = self._get_used_ips()
        bridge_ip, bridge_cidr = Network._if_to_ip(self.bridge)
        network = netaddr.IPNetwork('%s/%s' % (bridge_ip, bridge_cidr))
        used.extend([bridge_ip, str(network.broadcast)])
        used = [netaddr.IPAddress(u) for u in used]
        logging.debug('IP addresses in use: %s', used)
        for ipaddr in netaddr.IPRange(network.first+1, network.last-1):
            if ipaddr not in used:
                ipaddr = '%s/%s' % (str(ipaddr), bridge_cidr)
                container.logger.debug('Found unused IP address: %s', ipaddr)
                return ipaddr
        raise RuntimeError('Network out of IP addresses')

    @staticmethod
    def _if_to_ip(iface, all_ips=False):
        ''' Return first IP address and CIDR netmask of interface

        TODO Handle IPv6 addresses

        :param all_ips: If True return all IP addresses as list, else only the first
        :returns: Firt IPv4 address of the interface or all addresses as list
        '''
        tuples = [(x, y) for x, y in iface.ipaddr if x.find(':') < 0]
        if all_ips:
            return tuples
        return tuples[0]

    @staticmethod
    def get_dns_from_host():
        ''' Return list of DNS servers form the host system

        Extracts nameservers from /etc/resolv.conf but filters loopback
        addresses, e.g. 127.0.1.1

        :returns: list of DNS IP addresses (as strings)
        '''
        list_of_dns = list()
        try:
            with open('/etc/resolv.conf', 'r') as resolv_fd:
                # TODO Check if this isn't actually to restrictive
                # TODO Support IPv6 in the future
                regex = re.compile(r'^\s*nameserver\s+(' + regex_ip + r')\s*$')
                for line in resolv_fd.readlines():
                    match = regex.match(line)
                    if match:
                        dns = match.group(1)
                        try:
                            ip = netaddr.IPAddress(dns)
                        except netaddr.AddrFormatError:
                            logging.warn('Invalid DNS address in /etc/hosts: %s', dns)
                            continue
                        if ip.is_loopback():
                            logging.debug('Ignoring address from /etc/hosts: %s', ip)
                            continue
                        logging.debug('Found valid DNS address in /etc/hosts: %s', ip)
                        list_of_dns.append(str(ip))
        except (FileNotFoundError, PermissionError) as exception:
            logging.warn('Could not read /etc/resolv.conf: %s', exception)
        return list_of_dns

    def stop(self):
        ''' Delete all netfilter rules

        This method deletes rules from the following chains if they have a
        matching comment ("locker_$project"):

        - rules from FORWARD chain, FILTER table
        - rules from POSTROUTING chain, NAT table
        '''
        self._disable_nat()
        self._delete_bridge()
