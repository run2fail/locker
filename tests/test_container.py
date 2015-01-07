#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
Test the Container class
'''

import logging
import os
import tempfile
import time

import yaml
from colorama import Fore
from locker import Container, Project
from locker.container import CommandFailed
from tests.locker_test import LockerTest

def setUpModule():
    logging.basicConfig(format='%(asctime)s, %(levelname)8s: %(message)s', level=logging.INFO)
    logging.root.setLevel(logging.INFO)

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

class TestStr(LockerTest):
    ''' Test str() and repr() '''

    def test_str(self):
        for container in self.project.containers:
            container.logger.info(str(container))

    def test_repr(self):
        for container in self.project.containers:
            container.logger.info(repr(container))

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
        super().setUp(['ubuntu'])

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
        super().setUp(['ubuntu'])

    def test_start_defined(self):
        self.project.create()
        self.project.network.start()
        self.project.stop()
        for container in self.project.containers:
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
        super().setUp((['ubuntu']))

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
        super().setUp(['ubuntu'])

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
        self.project = Project(self.yml, self.args) # due to the cloning
        sshd = self.project.all_containers[0]
        self.assertEqual(sshd.defined, True)
        self.project.start()
        self.project.stop()

class TestCreateCloneError(LockerTest):
    def setUp(self):
        super().setUp()
        self.args['containers'] = ['sshd']
        self.yml = {
                'containers': {
                    'sshd': { 'clone': 'invalid_container'},
                }
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
