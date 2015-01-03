#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
Test the Container class
'''

import logging
import os
import time
import unittest

import yaml
from colorama import Fore
from locker import Container, Project
from test_container import LockerTest

def setUpModule():
    logging.basicConfig(format='%(asctime)s, %(levelname)8s: %(message)s', level=logging.INFO)
    logging.root.setLevel(logging.INFO)

class TestStatus(LockerTest):
    ''' Test status command

    Uses fake configuration data.
    '''

    def test_status(self):
        self.project.args['extended'] = True
        self.project.status()
        self.project.create(containers=[self.project.get_container('ubuntu')])
        self.project.create(containers=[self.project.get_container('sshd')])
        return
        self.project.network.start()
        self.project.start()
        self.project.status()
        self.project.stop()
        self.project.status()

class TestUndefined(LockerTest):
    ''' Test start command '''

    def test_start(self):
        self.project.start()

    def test_stop(self):
        self.project.stop()

    def test_reboot(self):
        self.project.reboot()

    def test_ports(self):
        self.project.ports()

    def test_rmports(self):
        self.project.rmports()

    def test_links(self):
        self.project.links()

    def test_rmlinks(self):
        self.project.rmlinks()

    def test_rm(self):
        self.project.remove()

    def test_cgroup(self):
        self.project.cgroup()

class TestLifeCycle(LockerTest):
    ''' Test start command

    Uses fake configuration data.
    '''

    def test_lifecycle(self):
        self.project.create(containers=[self.project.get_container('ubuntu')])
        self.project.create()
        self.project = Project(self.yml, self.args) # due to the cloning
        self.project.start()
        self.project.reboot()
        self.project.stop()
        self.project.remove()
