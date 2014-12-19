#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
Test the Container class
'''

import unittest
from colorama import Fore
from locker import Container, Project
from locker.container import CommandFailed
import logging
import yaml
import os

class TestInit(unittest.TestCase):
    ''' Test instantiation of the Container class

    Uses fake configuration data.
    '''

    def setUp(self):
        name = 'name'
        yml = {
                'containerA':   dict(),
                'containerB':   dict(),
                }
        args = {
                'project':      'project',
                'containers':   [],
                'verbose':      True,
            }
        self.project = Project(yml, args)

    def test_init(self):
        with self.assertRaises(TypeError):
            Container()
        with self.assertRaises(TypeError):
            Container('project_foo', None, self.project)
        with self.assertRaises(TypeError):
            Container('project_foo', dict(), None)
        self.assertIsInstance(Container('project_foo', dict(), self.project), Container)

class TestProperties(unittest.TestCase):
    ''' Test getter and setter

    Uses fake configuration data.
    '''
    def setUp(self):
        yml = {
                'containerA':   dict(),
                'containerB':   dict(),
                }
        args = {
                'project':      'project',
                'containers':   [],
                'verbose':      True,
            }
        project = Project(yml, args)
        self.container = Container('project_containerA', yml['containerA'], project)

    def test_color(self):
        for invalid_color in [' ', '1test', '$Svs', 'fön', 'test test', None, [], {}]:
            with self.assertRaises(ValueError):
                self.container.color = invalid_color

        for valid_color in [Fore.BLACK, Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, Fore.MAGENTA, Fore.CYAN, Fore.WHITE, '']:
            self.container.color = valid_color
            self.assertEqual(self.container.color, valid_color)

    def test_logger(self):
        for invalid_logger in [None, [], {}, logging, lambda x: x+1, '']:
            with self.assertRaises(TypeError):
                self.container.logger = invalid_logger
        for valid_logger in [logging.getLogger(name) for name in ['foo', 'bar', '']]:
            self.container.logger = valid_logger
            self.assertEqual(self.container.logger, valid_logger)

    def test_yml(self):
        for invalid_yml in [None, [], logging, lambda x: x+1, '']:
            with self.assertRaises(TypeError):
                self.container.yml = invalid_yml
        for valid_yml in [{}, {'foo': 'bar'}]:
            self.container.yml = valid_yml
            self.assertEqual(self.container.yml, valid_yml)

class TestStatic(unittest.TestCase):
    ''' Test static methods of Container class

    Uses fake configuration data.
    '''

    def setUp(self):
        name = 'name'
        self.yml = {
                'containerA':   dict(),
                'containerB':   dict(),
                }
        args = {
                'project':      'project',
                'containers':   ['project_containerA'],
                'verbose':      True,
            }
        self.project = Project(self.yml, args)

    def test_get_containers(self):
        containers, all_containers = Container.get_containers(self.project, self.yml)
        self.assertIsInstance(containers, list)
        self.assertEqual(len(containers), 1)
        self.assertIsInstance(all_containers, list)
        self.assertEqual(len(all_containers), 2)
        for container in containers:
            self.assertIsInstance(container, Container)
        for container in all_containers:
            self.assertIsInstance(container, Container)

class TestStart(unittest.TestCase):
    def setUp(self):
        args = {
                'project':      'locker',
                'containers':   [],
                'file':         'docs/locker.yaml',
                'verbose':      True,
                'restart':      True,
                'no_ports':     False,
                'no_links':     False,
            }
        self.yml = yaml.load(open('%s' % (args['file'])))
        self.project = Project(self.yml, args)

    def test_start_with_restart(self):
        for container in self.project.containers:
            container.start()
            self.assertEqual(container.state, 'RUNNING')

    def test_start_without_restart(self):
        self.project.args['restart'] = False
        for container in self.project.containers:
            container.start()
            self.assertEqual(container.state, 'RUNNING')

    def test_start_undefined(self):
        yml_str = '''\
undefined:
  template:
    name: "ubuntu"
    release: "precise"
'''
        args = {
            'project':      'locker',
            'containers':   [],
            'verbose':      True,
            'restart':      True,
            'no_ports':     False,
            'no_links':     False,
        }
        yml = yaml.load(yml_str)
        project = Project(yml, args)
        self.assertEqual(len(project.containers), 1)
        self.assertEqual(project.containers[0].defined, False)
        self.assertEqual(project.containers[0].state, 'STOPPED')
        project.containers[0].start()
        self.assertEqual(project.containers[0].state, 'STOPPED')


class TestStop(unittest.TestCase):
    def setUp(self):
        args = {
                'project':      'locker',
                'containers':   [],
                'file':         'docs/locker.yaml',
                'verbose':      True,
                'restart':      True,
                'no_ports':     False,
                'no_links':     False,
            }
        self.yml = yaml.load(open('%s' % (args['file'])))
        self.project = Project(self.yml, args)

    def test_stop(self):
        for container in self.project.containers:
            container.stop()
            self.assertEqual(container.state, 'STOPPED')
        for container in self.project.containers:
            container.stop()
            self.assertEqual(container.state, 'STOPPED')

    def test_stop_undefined(self):
        yml_str = '''\
undefined:
  template:
    name: "ubuntu"
    release: "precise"
'''
        args = {
            'project':      'locker',
            'containers':   [],
            'verbose':      True,
            'restart':      True,
            'no_ports':     False,
            'no_links':     False,
        }
        yml = yaml.load(yml_str)
        project = Project(yml, args)
        self.assertEqual(len(project.containers), 1)
        self.assertEqual(project.containers[0].defined, False)
        self.assertEqual(project.containers[0].state, 'STOPPED')
        project.containers[0].stop()
        self.assertEqual(project.containers[0].state, 'STOPPED')

class TestPorts(unittest.TestCase):
    def setUp(self):
        args = {
                'project':    'locker',
                'containers': [],
                'file':       'docs/locker.yaml',
                'verbose':    True,
                'restart':    False,
                'no_ports':   False,
                'no_links':   False,
            }
        self.yml = yaml.load(open('%s' % (args['file'])))
        self.project = Project(self.yml, args)

    def test_ports_running(self):
        for container in self.project.containers:
            container.start()
            self.assertEqual(container.state, 'RUNNING')
            container.ports()
            if 'ports' in container.yml:
                self.assertEqual(container._has_netfilter_rules(), True)
            else:
                self.assertEqual(container._has_netfilter_rules(), False)

    def test_ports_stopped(self):
        return # Don't run this this as rmports should be called via the
               # Project instance to avoid errors in iptc module
        for container in self.project.containers:
            container.stop()
            self.assertEqual(container.state, 'STOPPED')
            self.assertEqual(container.ports(), True)
            self.assertEqual(container.has_netfilter_rules(), False)

class TestRmPorts(unittest.TestCase):
    def setUp(self):
        args = {
                'project':    'locker',
                'containers': [],
                'file':       'docs/locker.yaml',
                'verbose':    True,
                'restart':    True,
                'no_ports':   False,
                'no_links':   False,
            }
        self.yml = yaml.load(open('%s' % (args['file'])))
        self.project = Project(self.yml, args)

    def test_rmports(self):
        return # Don't run this this as rmports should be called via the
               # Project instance to avoid errors in iptc module
        for container in self.project.containers:
            print(container.name, container.state)
            container.rmports()
            self.assertEqual(container._has_netfilter_rules(), False)

class TestRmUndefined(unittest.TestCase):
    ''' Test removal of undefined container

    Uses fake configuration data.
    '''

    def setUp(self):
        name = 'name'
        self.yml = {
                'containerA':   dict(),
                'containerB':   dict(),
                }
        args = {
                'project':      'project',
                'containers':   ['project_containerA'],
                'verbose':      True,
            }
        self.project = Project(self.yml, args)

    def test_rm(self):
        for container in self.project.containers:
            self.assertEqual(container.defined, False)
            container.remove()
            self.assertEqual(container.defined, False)

if __name__ == "__main__":
    unittest.main()

class TestCreateClone(unittest.TestCase):
    def setUp(self):
        args = {
                'project':    'test',
                'containers': ['test_ssh'],
                'verbose':    True,
                'restart':    True,
                'no_ports':   False,
                'no_links':   False,
                'delete_dont_ask': True,
                'dont_copy_on_create': True,
            }
        self.yml = {
                'ssh': { 'clone': 'sshd'},
                }
        self.project = Project(self.yml, args)

    def test_create_clone(self):
        for container in self.project.containers:
            if container.defined:
                container.remove()
            self.assertEqual(container.defined, False)
            container.create()
            self.assertEqual(container.defined, True)

class TestCreateCloneError(unittest.TestCase):
    def setUp(self):
        args = {
                'project':    'test',
                'containers': ['test_ssh'],
                'verbose':    True,
                'restart':    True,
                'no_ports':   False,
                'no_links':   False,
                'delete_dont_ask': True,
                'dont_copy_on_create': True,
            }
        self.yml = {
                'ssh': { 'clone': 'doesnotexist'},
                }
        self.project = Project(self.yml, args)

    def test_create_clone(self):
        for container in self.project.containers:
            if container.defined:
                container.remove()
            self.assertEqual(container.defined, False)
            with self.assertRaises(ValueError):
                container.create()
            self.assertEqual(container.defined, False)

class TestCreateTemplate(unittest.TestCase):
    def setUp(self):
        args = {
                'project':    'test',
                'containers': ['test_ssh'],
                'verbose':    True,
                'restart':    True,
                'no_ports':   False,
                'no_links':   False,
                'delete_dont_ask': True,
                'dont_copy_on_create': True,
            }
        self.yml = {
                'ssh': {
                    'template': {
                        'name': 'sshd',
                    }
                },
            }
        self.project = Project(self.yml, args)

    def test_create_template(self):
        for container in self.project.containers:
            if container.defined:
                container.remove()
            self.assertEqual(container.defined, False)
            # Removed container instances cannot be re-created
            container = Container(container.name, container.yml, container.project)
            self.assertEqual(container.defined, False)
            container.create()
            self.assertEqual(container.defined, True)

class TestRm(unittest.TestCase):
    def setUp(self):
        args = {
                'project':    'test',
                'containers': ['test_ssh'],
                'verbose':    True,
                'restart':    True,
                'no_ports':   False,
                'no_links':   False,
                'delete_dont_ask': True,
                'dont_copy_on_create': True,
            }
        self.yml = {
                'ssh': { 'clone': 'sshd'},
                }
        self.project = Project(self.yml, args)

    def test_rm(self):
        for container in self.project.containers:
            if not container.defined:
                container.create()
            self.assertEqual(container.defined, True)
            container.remove()
            self.assertEqual(container.defined, False)