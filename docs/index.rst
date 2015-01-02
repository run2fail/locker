.. Locker documentation master file, created by
   sphinx-quickstart on Fri Jan  2 16:59:19 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Locker's documentation!
==================================

.. image:: ./logo.png

.. include:: ./about.rst

Example
-------

Locker projects are defined in a YAML file similar to `fig's <http://fig.sh>`_
syntax, abbreviated example:

.. code:: yaml

    db:
        template:
            name: "ubuntu"
            release: "precise"
        ports:
        - "8001:8001"
        volumes:
        - "/opt/data/db/etc:/etc"
        fqdn: 'db.example.net'
    web:
        clone: "ubuntu"
        ports:
        - "192.168.2.123:8003:8003/tcp"
        - "192.168.2.123:8003:8003/udp"
        links:
        - "db:database"
    foo:
        template:
            name: "ubuntu"
            arch: "amd64"
        links:
        - "db"
        cgroup:
        - "cpuset.cpus=0,1"
        dns:
        - "8.8.8.8"
        - "$bridge"


Example session (with ``locker.yaml`` in the current directory):

.. image:: ./demo.gif


.. include:: ./warning.rst

License
============

Published under the GPLv3 or later

Contents
=========

.. toctree::
   :maxdepth: 2

   features
   install
   configuration
   commands
   todos
   tests
   network
   locker


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

