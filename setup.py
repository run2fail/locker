#!/usr/bin/env python3

from setuptools import setup
import re

version_file = 'locker/_version.py'
line = open(version_file, 'r').readline()
match = re.compile(r'^__version__\s*=\s*\'(\d+\.\d+\.\d+)\'$').match(line)
if match:
    version = match.group(1)
else:
    raise RuntimeError('Could not find version in: %s' % line)

try:
    import lxc
except ImportError:
    sys.stderr.write('WARNING: lxc module is not available (not available on PyPi but part of lxc user space tools)\n')

setup(
    name='Locker',
    version=version,
    author='BB',
    author_email='run2fail@users.noreply.github.com',
    packages=['locker'],
    scripts=['bin/locker'],
    url='https://github.com/run2fail/locker',
    license='LICENSE',
    description='LXC container management',
    long_description=open('README.rst').read(),
    install_requires=[
        'python-iptables',
        'colorama',
        'PrettyTable',
        'PyYaml',
        'pyroute2',
        'argcomplete',
        'sphinx_rtd_theme',
    ],
)
