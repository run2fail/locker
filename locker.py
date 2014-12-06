#!/usr/bin/env python3
'''
Manage LXC containers like with Docker's fig

Locker enables to specify containers and their configuration in a file similar
to the YAML confuguration used by fig.

Features:
- Enables to create new containers from templates or by cloning
- Creates an fstab for bind mounts from the host into the container
- Enables to start and stop all containers defined in the same configuration
  file
- Makes services in containers available to the outside world by port
  forwarding
- ...
'''

__author__ = "BB"
__copyright__ = "Copyright 2014"
__license__ = "GPLv3 or later"
__version__ = "0.1"
__status__ = "Prototype"

import os
import sys
import yaml
import argparse
import lxc
import logging
from project import Project

def parse_args():
    parser = argparse.ArgumentParser(description='Manage LXC containers.')
    parser.add_argument('--verbose', '-v', nargs='?', type=bool, const=True, default=False, help='Show more output')
    parser.add_argument('--version', nargs='?', type=bool, const=True, default=False, help='Print version and exit')
    parser.add_argument('--delete-dont-ask', '-x', nargs='?', type=bool, const=True, default=False, help='Don\'t ask for confirmation when deleting')
    parser.add_argument('--dont-copy-on-create', '-d', nargs='?', type=bool, const=True, default=False, help='Don\'t copy directories/files defined as bind mounts to host after container creation (default: copy directories/files)')
    parser.add_argument('--file', '-f', default='./locker.yml', help='Specify an alternate locker file (default: locker.yml)')
    parser.add_argument('--project', '-p', default=os.path.basename(os.getcwd()), help='Specify an alternate project name (default: directory name)')
    parser.add_argument('--restart', '-r', nargs='?', type=bool, const=True, default=False, help='Restart already running containers when using \"start\" command')
    parser.add_argument('command', nargs='?', choices=['start', 'stop', 'rm', 'create', 'status', 'ports', 'rmports'], default='start', help='Commmand to run')
    parser.add_argument('containers', nargs='*', default=None, help='Selection of containers (default: all containers)')
    args_dict = vars(parser.parse_args())
    return args_dict

def main():
    logging.basicConfig(format='%(asctime)s, %(levelname)s, %(message)s', level=logging.INFO)
    args = parse_args()
    if args['verbose']:
        logging.root.setLevel(logging.DEBUG)
    logging.debug('Parsed arguments:\n\t%s', args)

    if args['version']:
        sys.stdout.write('%s\n' % __version__)
        sys.exit()

    with open('%s' % (args['file'])) as yaml_file:
        yml = yaml.load(yaml_file)
    logging.debug('Parsed YAML Configuration:\n\t%s', yml)
    
    pro = Project(yml, args)

    if args['command'] == 'status':
        pro.status()
    elif args['command'] == 'start':
        pro.start()
    elif args['command'] == 'stop':
        pro.stop()
    elif args['command'] == 'create':
        pro.create()
    elif args['command'] == 'rm':
        pro.remove()
    elif args['command'] == 'ports':
        pro.ports()
    elif args['command'] == 'rmports':
        pro.rmports()

if __name__ == '__main__':
    main()

