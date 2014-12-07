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
            formatter = logging.Formatter('%(asctime)s, %(levelname)8s: ' + colors[num % len(colors)] + '%(message)s' + Fore.RESET)
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
            container.logger.debug('Empty fstab config item for \"%s\"', container.name)
            fstab_file = '%s/%s/fstab' % (container.get_config_path(), container.name)
        assert(len(fstab_file))
        container.logger.debug('Generating fstab of \"%s\": %s', container.name, fstab_file)
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
        if containers == None:
            containers = self.containers

        max_len_name = max(len(c.name) for c in containers)
        max_len_state = max(len(c.state) for c in containers)

        sys.stdout.write('%-5s %-*s %-*s %s\n' % ('Defined', max_len_name, 'Name', max_len_state, 'State', 'IPs'))
        sys.stdout.write('%s\n' % ''.join(['-' for x in range(len('Defined') + max_len_name + max_len_state + 20)]))

        for container in containers:
            defined = container.defined
            name = container.name
            state = container.state
            ips = '-'
            if container.running:
                ips = container.get_ips()
            sys.stdout.write('%-7s %-*s %-*s %s\n' % (defined, max_len_name, name, max_len_state, state, ips))

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
                container.logger.critical('Container %s is not yet defined', container.name)
                ok = False
                continue

            if container.running:
                container.logger.warn('Container %s is already running', container.name)
                if not self.args['restart']:
                    continue
                container.logger.info('Restarting container %s', container.name)
                if not container.stop():
                    container.logger.critical('Was not able to stop container %s - still running!', container.name)
                    ok = False
                    continue
            Project.generate_fstab(container)
            container.logger.info('Starting container %s', container.name)
            ok &= container.start()
            if not container.running:
                container.logger.critical('Could not start container %s', container.name)
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
                container.logger.critical('Container %s is not yet defined', container.name)
                ok = False
                continue

            if not container.running:
                container.logger.warn('Container %s is already stopped', container.name)
                continue
            container.logger.info('Stopping container %s', container.name)
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
            container.logger.debug('Skipping copying of mounts of \"%s\" from inside container to outside', container.name)
            return
        if 'volumes' not in container.yml:
            container.logger.debug('No volumes defined for \"%s\"', container.name)
            return

        rootfs = container.get_config_item('lxc.rootfs')
        assert(len(rootfs))
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
                input_var = input("Parent folder %s already exists. Continue to move data to %s? [y/N]: " % (container.name, outside))
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
                container.logger.warning('Container %s already defined', container.name)
                ok = False
                continue

            if 'template' in container.yml and 'clone' in container.yml:
                container.logger.error('\"template\" and \"clone\" may not be used in the same configuration of \"%s\"', container.name)
                ok = False
                continue

            if 'template' in container.yml:
                container.logger.info('Creating \"%s\" from template \"%s\"', container.name, container.yml['template']['name'])
                container.create(container.yml['template']['name'], lxc.LXC_CREATE_QUIET, args=container.yml['template'])
                if not container.defined:
                    container.logger.info('Creation of \"%s\" from template \"%s\" did not succeed', container.name, container.yml['template']['name'])
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
                container.logger.info('Cloning \"%s\" from \"%s\"', container.name, origin.name)
                cloned_container = origin.clone(container.name)
                if not container.defined:
                    container.logger.info('Cloning of \"%s\" from \"%s\" did not succeed', container.name, origin.name)
                    ok = False
                else:
                    # TODO Modifying lists in a loop is foobar but necessary due to the way
                    # lxc is handling container objects
                    cloned_container.yml = self.yml[container.name.replace('%s_' % self.name, '')]
                    cloned_container.project = self
                    containers[pos] = cloned_container # maybe we need this list again after create!
                    Project.copy_mounted(cloned_container)
            else:
                container.logger.error('Neither \"template\" nor \"clone\" was specified in the configuration of \"%s\"', container.name)
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
                container.logger.warn('Container %s does not exist', container.name)
                ok = False
                continue
            if not self.args['delete_dont_ask']:
                input_var = input("Delete %s? [y/N]: " % (container.name))
                if input_var not in ['y', 'Y']:
                    container.logger.info('Skipping deletion of container %s', container.name)
                    continue
            if not self.stop([container]):
                continue
            if not container.destroy():
                ok = False
                container.logger.warn('Container %s was not deleted', container.name)
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
                target = forward_rule.create_target('ACCEPT')
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
                container.logger.info('No port forwarding rules for %s', container.name)
                continue
            if not container.running:
                container.logger.info('%s is not running, skipping adding ports rules', container.name)
                continue

            container.logger.info('Adding port forwarding rules for %s', container.name)

            try:
                container.logger.debug('Checking if container has already rules')
                for rule in locker_nat_chain.rules:
                    for match in rule.matches:
                        if match.name == 'comment' and match.comment == container.name:
                            container.logger.info('Found rule(-s) for %s in LOCKER chain: remove with command \"rmports\"', container.name)
                            raise Exception('Existing rules found') # TODO use more specific exception
                for rule in filter_forward.rules:
                    for match in rule.matches:
                        if match.name == 'comment' and match.comment == container.name:
                            container.logger.info('Found rule(-s) for %s in FORWARD chain: remove with command \"rmports\"', container.name)
                            raise Exception('Existing rules found') # TODO use more specific exception
            except Exception:
                continue

            for fwport in container.yml['ports']:
                ips = container.get_ips()
                while len(ips) == 0 and container.running:
                    container.logger.debug('Waiting for \"%s\" to aquire an IP address', container.name)
                    time.sleep(1)
                    ips = container.get_ips()
                parts = [s.strip() for s in fwport.split(':')]
                for container_ip in ips:
                    if container_ip.find(':') >= 0:
                        container.logger.warn('Found IPv6 address %s for \"%s\", not yet supported', container_ip, container.name)
                        continue

                    host_ip = ''
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
                    container.logger.warn('Container %s is still running, services will not be available anymore', container.name)
                for rule in locker_nat_chain.rules:
                    for match in rule.matches:
                        if match.name == 'comment' and match.comment == container.name:
                            container.logger.info('Removing DNAT %s rule of \"%s\"', rule.protocol, container.name)
                            locker_nat_chain.delete_rule(rule)
                for rule in filter_forward.rules:
                    for match in rule.matches:
                        if match.name == 'comment' and match.comment == container.name:
                            container.logger.info('Removing FORWARD %s rule of \"%s\"', rule.protocol, container.name)
                            filter_forward.delete_rule(rule)
        except iptc.IPTCError:
            logging.warn('An arror occured during the deletion of rules for \"%s\", check for relics', container.name)
        finally:
            filter_table.commit()
            filter_table.autocommit = True
            nat_table.commit()
            nat_table.autocommit = True
        return True
