#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
Test the Container class
'''

import unittest
from colorama import Fore
from locker import Container, Project
import logging
import yaml
import os

class TestStatus(unittest.TestCase):
    ''' Test status command

    Uses fake configuration data.
    '''

    def setUp(self):
        args = {
            'project':      'locker',
            'containers':   [],
            'file':         'docs/examples/locker.yaml',
            'verbose':      True,
            }
        self.yml = yaml.load(open('%s' % (args['file'])))
        self.project = Project(self.yml, args)

    def test_status(self):
        self.project.status()
        self.project.stop()
        self.project.status()

class TestStartUndefined(unittest.TestCase):
    ''' Test start command

    Uses fake configuration data.
    '''

    def setUp(self):
        self.yml = {
            'containerA':   dict(),
            'containerB':   dict(),
        }
        args = {
            'project':      'locker',
            'containers':   [],
            'verbose':      True,
            'no_ports':     False,
            'no_links':     False,
            }
        self.project = Project(self.yml, args)

    def test_start(self):
        self.assertEqual(self.project.start(), False)

class TestStartUndefined(unittest.TestCase):
    ''' Test start command

    Uses fake configuration data.
    '''

    def setUp(self):
        self.yml = {
            'containerA':   dict(),
            'containerB':   dict(),
        }
        args = {
            'project':      'locker',
            'containers':   [],
            'verbose':      True,
            'no_ports':     False,
            'no_links':     False,
            }
        self.project = Project(self.yml, args)

    def test_stop(self):
        self.project.stop()

class TestRmPorts(unittest.TestCase):
    ''' Test status command

    Uses fake configuration data.
    '''

    def setUp(self):
        args = {
            'project':      'locker',
            'containers':   [],
            'file':         'docs/examples/locker.yaml',
            'verbose':      True,
            }
        self.yml = yaml.load(open('%s' % (args['file'])))
        self.project = Project(self.yml, args)

    def test_status(self):
        self.project.start()
        for container in self.project.containers:
            self.assertEqual(container.running, True)
        self.project.rmports()
        for container in self.project.containers:
            self.assertEqual(container._has_netfilter_rules(), False)