import lxc
import logging
import sys
import os
import shutil
import time

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

    def get_containers(self, yml):
        '''
        Generate a list of container objects

        :param yml: YAML project configuration

        :returns:   List of container objects
        '''
        containers = list()
        for name in sorted(yml.keys()):
            pname = '%s_%s' % (self.name, name)
            if len(self.args['containers']) and pname not in self.args['containers']:
                logging.debug('%s was not selected', pname)
                continue

            if pname not in lxc.list_containers():
                logging.debug('Container \"%s\" does not exist yet or is not accessible as this user.', pname)
            container = lxc.Container(pname)
            container.yml = yml[name]
            container.project = self
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
        logging.debug('Generating fstab of \"%s\": %s', container.name, fstab_file)
        with open(fstab_file, 'w') as fstab:
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
                logging.critical('Container %s is not yet defined', container.name)
                ok = False
                continue

            if container.running:
                logging.warn('Container %s is already running', container.name)
                if not self.args['restart']:
                    continue
                logging.info('Restarting container %s', container.name)
                if not container.stop():
                    logging.critical('Was not able to stop container %s - still running!', container.name)
                    ok = False
                    continue
            Project.generate_fstab(container)
            logging.info('Starting container %s', container.name)
            ok &= container.start()
            if not container.running:
                logging.critical('Could not start container %s', container.name)
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
                logging.critical('Container %s is not yet defined', container.name)
                ok = False
                continue

            if not container.running:
                logging.warn('Container %s is already stopped', container.name)
                continue
            logging.info('Stopping container %s', container.name)
            ok &= container.stop()
        return ok

    @staticmethod
    def copy_mounted(container):
        '''
        Copy data from inside the container to the host

        This method optionally enables to copy data from inside the container
        to the host so that non-empty bind mounts can be set up.

        :param container: The container to handle
        '''
        if container.project.args['dont_copy_on_create']:
            logging.debug('Skipping copying of mounts of \"%s\" from inside container to outside', container.name)
            return
        if 'volumes' not in container.yml:
            logging.debug('No volumes defined for \"%s\"', container.name)
            return

        rootfs = container.get_config_item('lxc.rootfs')
        for volume in container.yml['volumes']:
            outside, inside = [s.strip() for s in volume.split(':')]
            if os.path.exists(outside):
                logging.warn('Path %s exists, skipping', outside)
                continue
            if os.path.isfile(rootfs+inside):
                logging.warn('%s is a file (not supported yet), skipping', rootfs+inside)
                continue

            outside_parent = os.path.dirname(outside)
            if os.path.exists(outside_parent):
                input_var = input("Parent folder %s already exists. Continue to move data? [y/N]: " % (container.name))
                if input_var not in ['y', 'Y']:
                    logging.info('Skipping volume %s', volume)
                    continue
            else:
                try:
                    os.makedirs(outside_parent)
                    logging.debug('Created directory %s', outside_parent)
                except OSError:
                    logging.warn('Could not create parent directory %s. Data not moved from container to host!', outside_parent)
                    continue

            if os.path.exists(inside):
                # Move from container to host should preseve owner and group, recreate dir afterwards in container
                logging.debug('Move %s to %s', rootfs+inside, outside)
                shutil.move(rootfs+inside, outside)
                os.mkdir(rootfs+inside)
            else:
                try:
                    os.makedirs(outside)
                    logging.warn('%s did not exist within the container, created empty directory on host', outside)
                except OSError:
                    logging.warn('Could not create %s on host (%s does not exist inside the container)', outside, inside)
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
        for container in containers:
            if container.defined:
                logging.warning('Container %s already defined', container.name)
                ok = False
                continue

            if 'template' in container.yml and 'clone' in container.yml:
                logging.error('\"template\" and \"clone\" may not be used in the same configuration of \"%s\"', container.name)
                ok = False
                continue

            if 'template' in container.yml:
                logging.info('Creating \"%s\" from template \"%s\"', container.name, container.yml['template']['name'])
                container.create(container.yml['template']['name'], args=container.yml['template'])
                if not container.defined:
                    logging.info('Creation of \"%s\" from template \"%s\" did not succeed', container.name, container.yml['template']['name'])
                    ok = False
                else:
                    Project.copy_mounted(container)
            elif 'clone' in container.yml:
                clone = container.yml['clone']
                if clone not in lxc.list_containers():
                    logging.error('Cannot clone, container \"%s\" does not exist or is not accessible', clone)
                    ok = False
                    continue
                origin = lxc.Container(clone)
                logging.info('Cloning \"%s\" from \"%s\"', container.name, origin.name)
                origin.clone(container.name)
                if not container.defined:
                    logging.info('Cloning of \"%s\" from \"%s\" did not succeed', container.name, origin.name)
                    ok = False
                else:
                    Project.copy_mounted(container)
            else:
                logging.error('Neither \"template\" nor \"clone\" was specified in the configuration of \"%s\"', container.name)
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
                logging.warn('Container %s does not exist', container.name)
                ok = False
                continue
            if not self.args['delete_dont_ask']:
                input_var = input("Delete %s? [y/N]: " % (container.name))
                if input_var not in ['y', 'Y']:
                    logging.info('Skipping deletion of container %s', container.name)
                    continue
            if not self.stop([container]):
                continue
            if not container.destroy():
                ok = False
                logging.warn('Container %s was not deleted', container.name)
        return ok

    def ports(self, containers=None):
        '''
        Add firewall rules to enable port forwarding

        :param containers: List of containers or None (== all containers)

        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        os.system('iptables -t nat -N LOCKER -m comment --comment \"%s\"' % self.name)
        os.system('iptables -t nat -I PREROUTING -m addrtype --dst-type LOCAL -j LOCKER -m comment --comment \"%s\"' % self.name)
        ok = True
        for container in containers:
            if not 'ports' in container.yml:
                logging.info('No port forwarding rules for %s', container.name)
                continue
            if not container.running:
                logging.info('%s is not running, skipping ports rules', container.name)
                continue

            logging.info('Adding port forwarding rules for %s', container.name)
            for fwport in container.yml['ports']:
                ips = container.get_ips()
                while len(ips) == 0 and container.running:
                    logging.debug('Waiting for \"%s\" to aquire an IP address', container.name)
                    time.sleep(1)
                    ips = container.get_ips()
                parts = [s.strip() for s in fwport.split(':')]
                for container_ip in ips:
                    if len(parts) == 3:
                        host_ip, host_port, container_port = parts
                        rule = 'iptables -t nat -I LOCKER -d %s ! -i lxcbr0 -p tcp --dport %s -j DNAT --to %s:%s -m comment --comment \"%s\"' % (host_ip, host_port, container_ip, container_port, container.name)
                        os.system(rule)
                    elif len(parts) == 2:
                        host_port, container_port = parts
                        rule = 'iptables -t nat -I LOCKER -i lxcbr0 -p tcp --dport %s -j DNAT --to %s:%s -m comment --comment \"%s\"' % (host_port, container_ip, container_port, container.name)
                        os.system(rule)
                    else:
                        logging.warn('Malformed ports directive: %s', container.yml['ports'])
                        continue
                    os.system('iptables -t filter -I FORWARD ! -i lxcbr0 -o lxcbr0  -d %s -p tcp --dport %s -j ACCEPT' % (container_ip, container_port))
        return ok

    def rmports(self, containers=None):
        '''
        Remove firewall rules that enable port forwarding

        :param containers: List of containers or None (== all containers)

        :returns: False on any error, else True
        '''
        if containers == None:
            containers = self.containers

        ok = True
        logging.warn('Removing of iptables rules has not yet been implemented')
        return ok
