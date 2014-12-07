import lxc
import logging
import sys
import os
import shutil
import time
import iptc
import colorama
from colorama import Fore, Back, Style

class Project(object):
    '''
    Abtracts a group of containers
    '''

    def __init__(self, yml, args):
        '''
        Initialize a new project instance

        :param yml: YAML configuration file of the project
        :param args: Parsed command line parameters
        '''
        self.args = args
        self.name = args['project']
        self.containers = self.get_containers(yml)
        self.yml = yml

    def get_containers(self, yml):
        '''
        Generate a list of container objects

        :param yml: YAML project configuration

        :returns:   List of container objects
        '''
        containers = list()
        colors = [Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, Fore.MAGENTA, Fore.CYAN]

        for num, name in enumerate(sorted(yml.keys())):
            pname = '%s_%s' % (self.name, name)
            if len(self.args['containers']) and pname not in self.args['containers']:
                logging.debug('%s was not selected', pname)
                continue

            if pname not in lxc.list_containers():
                logging.debug('Container \"%s\" does not exist yet or is not accessible as this user.', pname)
            container = lxc.Container(pname)
            container.yml = yml[name]
            container.project = self
            container.logger = logging.getLogger(container.name)
            container.logger.propagate = False
            formatter = logging.Formatter('%(asctime)s, %(levelname)8s: ' + colors[num % len(colors)] + '[' + container.name + '] %(message)s' + Fore.RESET)
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            container.logger.addHandler(handler)
            containers.append(container)
        logging.debug('Containers:\n\t%s', containers)
        return containers

    @staticmethod
    def expand_vars(text, container):
        '''
        Expand some variables

        :param text: The string with variables to expand
        :param container: Container instance to access the replacement strings

        :returns: Expanded string
        '''
        text = text.replace('$name', container.name)
        text = text.replace('$project', container.project.name)
        return text

    @staticmethod
    def generate_fstab(container):
        '''
        Generate a file system table for the container

        This function generates a fstab file based on the volume information in the
        YAML configuration.
        Currently only bind mounts are supported and no syntax check is run!

        :param container: The container object
        '''
        fstab_file = container.get_config_item('lxc.mount')
        if not fstab_file:
            # TODO Why is lxc.mount sometimes empty?!?
            container.logger.debug('Empty fstab config item')
            fstab_file = '%s/%s/fstab' % (container.get_config_path(), container.name)
        assert len(fstab_file)
        container.logger.debug('Generating fstab: %s', fstab_file)
        with open(fstab_file, 'w+') as fstab:
            if 'volumes' in container.yml:
                for volume in container.yml['volumes']:
                    remote, mountpt = [s.strip() for s in volume.split(':')]
                    remote = Project.expand_vars(remote, container)
                    if mountpt.startswith('/'):
                        mountpt = mountpt[1:]
                    fstab.write('%s %s none bind 0 0\n' % (remote, mountpt))
            fstab.write('\n')

    def status(self, containers=None):
        '''
        Show status of all project specific containers

        :param containers: List of containers or None (== all containers)
        '''

        def get_netfiler_rules(container):
            nat_table = iptc.Table(iptc.Table.NAT)
            locker_nat_chain = iptc.Chain(nat_table, 'LOCKER')
            dnat_rules = list()
            try:
                container.logger.debug('Searching netfilter rules')
                if not container.running:
                    return ''
                for rule in [rul for rul in locker_nat_chain.rules if rul.protocol == 'tcp']:
                    for match in rule.matches:
                        if match.name == 'comment' and match.comment == container.name:
                            dport = [m.dport for m in rule.matches if m.name == 'tcp'][0]
                            to_ip, to_port = rule.target.to_destination.split(':')
                            dnat_rules.append(((rule.dst, dport), (to_ip, to_port)))
            except iptc.IPTCError:
                container.logger.warn('An arror occured searching the netfiler rules')
            return dnat_rules

        if containers == None:
            containers = self.containers

        max_len_name = max(len(c.name) for c in containers)
        max_len_state = max(len(c.state) for c in containers)
        max_len_ips = max(len(str(c.get_ips())) for c in containers)
        print(max_len_ips)

        sys.stdout.write('%-5s %-*s %-*s %-*s %s\n' % ('Defined', max_len_name, 'Name', max_len_state, 'State', max_len_ips, 'IPs', 'Ports'))
        sys.stdout.write('%s\n' % ''.join(['-' for x in range(len('Defined') + max_len_name + max_len_state + max_len_ips + 3)]))

        for container in containers:
            defined = container.defined
            name = container.name
            state = container.state
            ips = '-'
            if container.running:
                ips = container.get_ips()
            dnat_rules = get_netfiler_rules(container)
            ports = ','.join(['%s:%s->%s' % (dip.split('/')[0], dport, to_port) for (dip, dport), (to_ip, to_port) in dnat_rules])
            sys.stdout.write('%-7s %-*s %-*s %-*s %s\n' % (defined, max_len_name, name, max_len_state, state, max_len_ips, ips, ports))

    def start(self, containers=None):
        '''
        Start all or selected containers

        :param containers: List of containers or None (== all containers)

        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        ok = True
        for container in containers:
            if not container.defined:
                container.logger.critical('Container is not yet defined')
                ok = False
                continue

            if container.running:
                container.logger.warn('Container is already running')
                if not self.args['restart']:
                    continue
                container.logger.info('Restarting container')
                if not container.stop():
                    container.logger.critical('Was not able to stop container - still running!')
                    ok = False
                    continue
            Project.generate_fstab(container)
            container.logger.info('Starting container')
            ok &= container.start()
            if not container.running:
                container.logger.critical('Could not start container')
        return ok

    def stop(self, containers=None):
        '''
        Stop all or selected containers

        :param containers: List of containers or None (== all containers)

        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        ok = True
        for container in containers:
            if not container.defined:
                container.logger.critical('Container is not yet defined')
                ok = False
                continue

            if not container.running:
                container.logger.warn('Container is already stopped')
                continue
            container.logger.info('Stopping container')
            ok &= container.stop()
        return ok

    @staticmethod
    def copy_mounted(container):
        '''
        Copy data from inside the container to the host

        This method optionally enables to copy data from inside the container
        to the host so that non-empty bind mounts can be set up.

        Actually, this method moves the data from the container to the host to
        preserve the owner, group, and mode configuration.
        TODO Is there no way to "cp -ar" with shutil or another module?

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

        if container.project.args['dont_copy_on_create']:
            container.logger.debug('Skipping copying of mounts from inside container to outside')
            return
        if 'volumes' not in container.yml:
            container.logger.debug('No volumes defined')
            return

        rootfs = container.get_config_item('lxc.rootfs')
        assert len(rootfs)
        for volume in container.yml['volumes']:
            outside, inside = [remove_trailing_slash(Project.expand_vars(s.strip(), container)) for s in volume.split(':')]
            if os.path.exists(outside):
                container.logger.warn('Path %s exists on host, skipping', outside)
                continue
            if os.path.isfile(rootfs+inside):
                container.logger.warn('%s is a file (not supported yet), skipping', rootfs+inside)
                continue

            outside_parent = os.path.dirname(outside)
            if os.path.exists(outside_parent):
                input_var = input("Parent folder %s already exists. Continue to move data to %s? [y/N]: " % (outside_parent, outside))
                if input_var not in ['y', 'Y']:
                    container.logger.info('Skipping volume %s', volume)
                    continue
            else:
                try:
                    os.makedirs(outside_parent)
                    container.logger.debug('Created directory %s', outside_parent)
                except OSError:
                    container.logger.warn('Could not create parent directory %s. Data not moved from container to host!', outside_parent)
                    continue

            if os.path.exists(inside):
                # Move from container to host should preseve owner and group, recreate dir afterwards in container
                container.logger.debug('Move %s to %s', rootfs+inside, outside)
                shutil.move(rootfs+inside, outside)
                os.mkdir(rootfs+inside)
            else:
                try:
                    os.makedirs(outside)
                    container.logger.warn('%s did not exist within the container, created empty directory on host', outside)
                except OSError:
                    container.logger.warn('Could not create %s on host (%s does not exist inside the container)', outside, inside)
                    continue

    def create(self, containers=None):
        '''
        Create all or selected containers

        :param containers: List of containers or None (== all containers)

        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        ok = True
        for pos, container in enumerate(containers):
            if container.defined:
                container.logger.warning('Container is already defined')
                ok = False
                continue

            if 'template' in container.yml and 'clone' in container.yml:
                container.logger.error('\"template\" and \"clone\" may not be used in the same configuration')
                ok = False
                continue

            if 'template' in container.yml:
                container.logger.info('Creating container from template \"%s\"', container.yml['template']['name'])
                container.create(container.yml['template']['name'], lxc.LXC_CREATE_QUIET, args=container.yml['template'])
                if not container.defined:
                    container.logger.info('Creation from template \"%s\" did not succeed', container.yml['template']['name'])
                    ok = False
                else:
                    Project.copy_mounted(container)
            elif 'clone' in container.yml:
                clone = container.yml['clone']
                if clone not in lxc.list_containers():
                    container.logger.error('Cannot clone, container \"%s\" does not exist or is not accessible', clone)
                    ok = False
                    continue
                origin = lxc.Container(clone)
                container.logger.info('Cloning from \"%s\"', origin.name)
                cloned_container = origin.clone(container.name)
                if not container.defined:
                    container.logger.info('Cloning from \"%s\" did not succeed', origin.name)
                    ok = False
                else:
                    # TODO Modifying lists in a loop is foobar but necessary due to the way
                    # lxc is handling container objects
                    cloned_container.yml = self.yml[container.name.replace('%s_' % self.name, '')]
                    cloned_container.project = self
                    containers[pos] = cloned_container # maybe we need this list again after create!
                    Project.copy_mounted(cloned_container)
            else:
                container.logger.error('Neither \"template\" nor \"clone\" was specified in the configuration')
                ok = False
        return ok

    def remove(self, containers=None):
        '''
        Destroy all or selected containers

        :param containers: List of containers or None (== all containers)

        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        ok = True
        for container in containers:
            if not container.defined:
                container.logger.warn('Container does not exist')
                ok = False
                continue
            if not self.args['delete_dont_ask']:
                input_var = input("Delete %s? [y/N]: " % (container.name))
                if input_var not in ['y', 'Y']:
                    container.logger.info('Skipping deletion')
                    continue
            if not self.stop([container]):
                continue
            if not container.destroy():
                ok = False
                container.logger.warn('Container was not deleted')
        return ok

    @staticmethod
    def prepare_locker_table():
        '''
        Add container unspecific netfilter modifications

        This method does the following

          - Adds LOCKER chain to the NAT table
          - Creates a rule from the PREROUTING chain in the NAT table to the
            LOCKER chain
          - Ensures that the jump rule is only added once (the rule's comments
            are checked for a match)

        :throws: iptc.IPTCError if the LOCKER chain cannot be retrieved or
                 created

        :returns: LOCKER chain in NAT table, type = iptc.ip4tc.Chain
        '''
        nat_table = iptc.Table(iptc.Table.NAT)
        if 'LOCKER' not in [c.name for c in nat_table.chains]:
            try:
                logging.debug('Adding LOCKER chain to NAT table')
                locker_nat_chain = nat_table.create_chain('LOCKER')
            except iptc.IPTCError:
                logging.error('Was not able to create LOCKER chain in NAT table, cannot add rules')
                raise
        else:
            locker_nat_chain = iptc.Chain(nat_table, 'LOCKER')

        nat_prerouting_chain = iptc.Chain(nat_table, 'PREROUTING')
        for rule in nat_prerouting_chain.rules:
            for match in rule.matches:
                if match.name == 'comment' and match.comment == 'LOCKER':
                    logging.debug('Found rule to jump from PREROUTING chain to LOCKER chain')
                    return locker_nat_chain

        jump_to_locker_rule = iptc.Rule()
        jump_to_locker_rule.create_target("LOCKER")
        addr_type_match = jump_to_locker_rule.create_match("addrtype")
        addr_type_match.dst_type = "LOCAL"
        comment_match = jump_to_locker_rule.create_match("comment")
        comment_match.comment = 'LOCKER'
        nat_prerouting_chain.insert_rule(jump_to_locker_rule)
        return locker_nat_chain

    def ports(self, containers=None):
        '''
        Add firewall rules to enable port forwarding

        :param containers: List of containers or None (== all containers)

        :returns: False on any error, else True
        '''
        def add_dnat_rule():
            for proto in ['tcp', 'udp']:
                port_forwarding = iptc.Rule()
                port_forwarding.protocol = proto
                if host_ip:
                    port_forwarding.dst = host_ip
                port_forwarding.in_interface = '!lxbr0'
                tcp_match = port_forwarding.create_match(proto)
                tcp_match.dport = host_port
                comment_match = port_forwarding.create_match('comment')
                comment_match.comment = container.name
                target = port_forwarding.create_target('DNAT')
                target.to_destination = '%s:%s' % (container_ip, container_port)
                locker_nat_chain.insert_rule(port_forwarding)

        def add_forward_rule():
            for proto in ['tcp', 'udp']:
                forward_rule = iptc.Rule()
                forward_rule.protocol = proto
                forward_rule.dst = container_ip
                forward_rule.in_interface = '!lxcbr0'
                forward_rule.out_interface = 'lxcbr0'
                tcp_match = forward_rule.create_match(proto)
                tcp_match.dport = container_port
                comment_match = forward_rule.create_match('comment')
                comment_match.comment = container.name
                forward_rule.create_target('ACCEPT')
                filter_forward.insert_rule(forward_rule)

        if containers == None:
            containers = self.containers

        try:
            locker_nat_chain = Project.prepare_locker_table()
        except iptc.IPTCError:
            return False
        filter_forward = iptc.Chain(iptc.Table(iptc.Table.FILTER), 'FORWARD')

        ok = True
        for container in containers:
            if not 'ports' in container.yml:
                container.logger.info('No port forwarding rules')
                continue
            if not container.running:
                container.logger.info('Container is not running, skipping adding ports rules')
                continue

            container.logger.info('Adding port forwarding rules')

            try:
                container.logger.debug('Checking if container has already rules')
                for rule in locker_nat_chain.rules:
                    for match in rule.matches:
                        if match.name == 'comment' and match.comment == container.name:
                            container.logger.info('Found rule(-s) in LOCKER chain: remove with command \"rmports\"')
                            raise Exception('Existing rules found') # TODO use more specific exception
                for rule in filter_forward.rules:
                    for match in rule.matches:
                        if match.name == 'comment' and match.comment == container.name:
                            container.logger.info('Found rule(-s) in FORWARD chain: remove with command \"rmports\"')
                            raise Exception('Existing rules found') # TODO use more specific exception
            except Exception:
                continue

            for fwport in container.yml['ports']:
                ips = container.get_ips()
                while len(ips) == 0 and container.running:
                    container.logger.debug('Waiting to aquire an IP address')
                    time.sleep(1)
                    ips = container.get_ips()
                parts = [s.strip() for s in fwport.split(':')]
                for container_ip in ips:
                    if container_ip.find(':') >= 0:
                        container.logger.warn('Found IPv6 address %s - not yet supported', container_ip)
                        continue

                    host_ip = None
                    if len(parts) == 3:
                        host_ip, host_port, container_port = parts
                    elif len(parts) == 2:
                        host_port, container_port = parts
                    else:
                        container.logger.warn('Malformed ports directive: %s', container.yml['ports'])
                        continue

                    add_dnat_rule()
                    add_forward_rule()
        return ok

    def rmports(self, containers=None):
        '''
        Remove firewall rules that enable port forwarding

        :param containers: List of containers or None (== all containers)

        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        filter_table = iptc.Table(iptc.Table.FILTER)
        filter_forward = iptc.Chain(filter_table, 'FORWARD')
        filter_table.autocommit = False

        nat_table = iptc.Table(iptc.Table.NAT)
        locker_nat_chain = iptc.Chain(nat_table, 'LOCKER')
        nat_table.autocommit = False

        try:
            logging.info('Removing netfilter rules')
            for container in containers:
                if container.running:
                    container.logger.warn('Container is still running, services will not be available anymore')
                for rule in locker_nat_chain.rules:
                    for match in rule.matches:
                        if match.name == 'comment' and match.comment == container.name:
                            container.logger.debug('Removing DNAT %s rule', rule.protocol)
                            locker_nat_chain.delete_rule(rule)
                for rule in filter_forward.rules:
                    for match in rule.matches:
                        if match.name == 'comment' and match.comment == container.name:
                            container.logger.debug('Removing FORWARD %s rule', rule.protocol)
                            filter_forward.delete_rule(rule)
        except iptc.IPTCError:
            logging.warn('An arror occured during the deletion of rules for \"%s\", check for relics', container.name)
        finally:
            filter_table.commit()
            filter_table.autocommit = True
            nat_table.commit()
            nat_table.autocommit = True
        return True
