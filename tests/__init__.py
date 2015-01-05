#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
assert os.geteuid() == 0

from tests.locker_test import LockerTest
