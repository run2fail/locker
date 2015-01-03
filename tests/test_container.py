#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
Test the Container class
'''

import logging
import os
import tempfile
import time
import unittest

import yaml
from colorama import Fore
from locker import Container, Project
from locker.container import CommandFailed

def setUpModule():
    logging.basicConfig(format='%(asctime)s, %(levelname)8s: %(message)s', level=logging.INFO)
    logging.root.setLevel(logging.INFO)

class LockerTest(unittest.TestCase):
    ''' Defines two containers that have not yet been created

    - The args are side effect free.
    - Creates project instance in setUp()
    - Cleans project instance in tearDown()
    - Does not create any containers
    - Does not start network instance
    '''

    def init_config(self, containers=[]):
        self.yml = {
            'ubuntu': {
                'template': {
                    'name':    "ubuntu",
                    'release': "trusty",
                    'arch':    "amd64",
                },
                "ports": [
                    "8000:8000",
                    "8000:8000/udp",
                    "8001:8001/tcp",
                    "192.168.2.123:8002:8002",
                    "192.168.2.123:8003:8003/tcp",
                    "192.168.2.123:8003:8003/udp",
                    "invalid",
                ],
                "fqdn": "test.example.net",
                "dns": [
                    "8.8.8.8",
                    "$bridge",
                    "$copy",
                ],
                "links": [
                    "sshd:something",
                ],
                "cgroup": [
                    "memory.limit_in_bytes=200000000",
                ],
                "volumes": [
                    self.tmpdir.name + "/var/log:/var/log/",
                    self.tmpdir.name + "/foo:/bar",
                ],
            },
            'sshd': {
                'clone': 'test_ubuntu',
                "links": [
                    "ubuntu",
                ],
            }
        }
        self.args = {
            'project':          'test',
            'containers':       containers,
            'verbose':          False,
            'lxcpath':          self.tmpdir.name,
            'no_ports':         False,
            'no_links':         False,
            'add_hosts':        False,
            'restart':          False,
            'delete_dont_ask':  True,
        }

    def setUp(self, containers=[]):
        self.tmpdir = tempfile.TemporaryDirectory(dir='/tmp/locker')
        self.init_config(containers)
        self.project = Project(self.yml, self.args)

    def tearDown(self):
        self.project.cleanup()
        self.tmpdir.cleanup()

class TestInit(LockerTest):
    ''' Test instantiation of the Container class

    Does not have any side effects
    '''

    def test_init_negative(self):
        with self.assertRaises(TypeError):
            Container()
        with self.assertRaises(TypeError):
            Container('project_sshd', None, self.project)
        with self.assertRaises(TypeError):
            Container('project_sshd', dict(), None)
        self.assertIsInstance(Container('project_sshd', dict(), self.project), Container)

    def test_init_positive(self):
        self.assertIsInstance(Container('project_new', dict(), self.project), Container)

class TestProperties(LockerTest):
    ''' Test getter and setter

    Does not have any side effects
    '''

    def test_color(self):
        for invalid_color in [' ', '1test', '$Svs', 'fön', 'test test', None, [], {}]:
            with self.assertRaises(ValueError):
                self.project.containers[1].color = invalid_color

        for valid_color in [Fore.BLACK, Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, Fore.MAGENTA, Fore.CYAN, Fore.WHITE, '']:
            self.project.containers[1].color = valid_color
            self.assertEqual(self.project.containers[1].color, valid_color)

    def test_logger(self):
        for invalid_logger in [None, [], {}, logging, lambda x: x+1, '']:
            with self.assertRaises(TypeError):
                self.project.containers[1].logger = invalid_logger
        for valid_logger in [logging.getLogger(name) for name in ['foo', 'bar', '']]:
            self.project.containers[1].logger = valid_logger
            self.assertEqual(self.project.containers[1].logger, valid_logger)

    def test_yml(self):
        for invalid_yml in [None, [], logging, lambda x: x+1, '']:
            with self.assertRaises(TypeError):
                self.project.containers[1].yml = invalid_yml
        for valid_yml in [{}, {'foo': 'bar'}]:
            self.project.containers[1].yml = valid_yml
            self.assertEqual(self.project.containers[1].yml, valid_yml)

class TestStatic(LockerTest):
    ''' Test static methods of Container class

    Does not have any side effects
    '''

    def setUp(self):
        super().setUp(['test_ubuntu'])

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

class TestStartStop(LockerTest):
    ''' Test if containers can be started, restarted, and stopped

    Has side effects:
    - Creates container
    - Creates bridge
    '''

    def setUp(self):
        super().setUp(['test_ubuntu'])

    def test_start_defined(self):
        self.project.create()
        self.project.network.start()
        self.project.stop()
        for container in self.project.containers:
            print(container.name)
            self.assertEqual(container.state, 'STOPPED')
            self.assertTrue(container.defined)
            container.start()
        self.project.args['restart'] = True
        for container in self.project.containers:
            self.assertEqual(container.state, 'RUNNING')
            container.start()
            container.get_port_rules()
            container.linked_to()
            container.get_cgroup_item('memory.limit_in_bytes')
            container.get_cgroup_item('invalid')
            container.stop()
            self.assertEqual(container.state, 'STOPPED')
            container.get_cgroup_item('memory.limit_in_bytes')
            container.get_cgroup_item('invalid')

    #def test_start_undefined(self):
        #undefined = [c for c in self.project.all_containers if c not in self.project.containers]
        #self.assertTrue(len(undefined) > 0)
        #for container in undefined:
            #self.assertEqual(container.state, 'STOPPED')
            #with self.assertRaises(CommandFailed):
                #container.start()
            #self.assertEqual(container.state, 'STOPPED')
        #self.project.args['restart'] = True
        #for container in undefined:
            #container.start()
            #self.assertEqual(container.state, 'STOPPED')

class TestPorts(LockerTest):

    def setUp(self):
        super().setUp((['test_ubuntu']))

    def test_ports(self):
        self.project.create()
        self.project.network.start()
        self.project.stop()
        for container in self.project.containers:
            container.start()
            self.assertEqual(container.state, 'RUNNING')
            container.ports()
            if 'ports' in container.yml:
                self.assertEqual(container._has_netfilter_rules(), True)
            else:
                self.assertEqual(container._has_netfilter_rules(), False)
            print(container.get_port_rules())
        for container in self.project.containers:
            container.rmports()
            container.stop()
            self.assertEqual(container.state, 'STOPPED')
            container.rmports()
            self.assertEqual(container._has_netfilter_rules(), False)

class TestRm(LockerTest):
    ''' Test removal of containers
    '''

    def setUp(self):
        super().setUp(['test_ubuntu'])

    def test_rm_undefined(self):
        undefined = [c for c in self.project.all_containers if c not in self.project.containers]
        for container in undefined:
            self.assertEqual(container.defined, False)
            container.remove()
            self.assertEqual(container.defined, False)

    def test_rm(self):
        for container in self.project.containers:
            if not container.defined:
                container.create()
            self.assertEqual(container.defined, True)
            container.remove()
            self.assertEqual(container.defined, False)

class TestCreateClone(LockerTest):

    def test_create_clone(self):
        ubuntu = self.project.all_containers[1]
        sshd = self.project.all_containers[0]
        self.assertEqual(ubuntu.defined, False)
        self.assertEqual(sshd.defined, False)
        ubuntu.create()
        self.assertEqual(ubuntu.defined, True)
        sshd.create()
        self.assertEqual(sshd.defined, True)
        self.project.start()
        self.project.stop()

class TestCreateCloneError(LockerTest):
    def setUp(self):
        super().setUp()
        self.args['containers'] = ['test_sshd']
        self.yml = {
                'sshd': { 'clone': 'invalid_container'},
            }
        self.project = Project(self.yml, self.args)

    def test_create_clone(self):
        for container in self.project.containers:
            if container.defined:
                container.remove()
            self.assertEqual(container.defined, False)
            with self.assertRaises(ValueError):
                container.create()
            self.assertEqual(container.defined, False)

if __name__ == "__main__":
    unittest.main()
