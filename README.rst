.. image:: ./logo.png

About Locker
===============

Locker is my take on `Docker <http://www.docker.com>`_  + `fig <http://fig.sh>`_ applied for `Linux containers (LXC) <https://linuxcontainers.org/>`_. Locker wraps the lxc utilities like fig does for Docker.

Locker is not yet a production ready solution but a prototype implementation. Its feature set is mainly focused on my personal application domain. Most notably, I required a solution to set up groups of Ubuntu containers with bind-mounted folders to store critical data and to make services from the containers available to the outside world by port forwarding. I needed complete base installations in the containers to support security auto-updates, cron jobs, ssh access, etc. which ruled out pure application containers. Locker is a simple application that eases these tasks.

Please consider that Linux containers do not ship with an installed application like Docker containers. Linux containers are usually created based on template files, i.e., you get a base installation of your user space of choice. You either must write your own enhanced LXC template, install your application manually, or deploy your application by using a configuration management system like `puppet <http://puppetlabs.com/puppet/what-is-puppet>`_, `chef <https://www.chef.io/chef/>`_, ...

Locker currently supports the following features:

- Define containers in a YAML file similar to fig's syntax
- Create, start, stop, and remove groups or selections of containers
- Show the status of containers in your project
- Create containers as clones or based on LXC templates
- Create an fstab file for bind mounts into the container
- Optionally move bind-mounted folders from container after container creation to host, so that you do not mount empty folders within your container (need testing)
- Add or remove port forwarding netfilter rules (prototypical)

Usage
===============

Under construction...

Defining a Project
------------------

An example project definition in YAML::

    db:
      template:
        name: "ubuntu"
        release: "precise"
      ports:
       - "8000:1234"
      volumes:
       - "/opt/data/locker_db/var_log:/var/log"
       - "/opt/data/locker_db/etc:/etc"
    web:
      clone: "ubuntu"
      ports:
       - "8001:8001"
      volumes:
       - "/opt/data/$name/var_log:/var/log"
    foo:
      template:
        name: "ubuntu"
        release: "precise"

Managing the Lifecycle
----------------------

Creating, starting, stopping, and removing containers (output some omitted)::

    $ ./locker.py create
    [...]
    $ ./locker.py start locker_web locker_db
    2014-12-07 12:56:23,596, INFO, Starting container locker_db
    2014-12-07 12:56:24,758, INFO, Starting container locker_web
    $ ./locker.py stop locker_web
    2014-12-07 12:57:14,198, INFO, Stopping container locker_web
    $ ./locker.py rm locker_web
    Delete locker_web? [y/N]: y
    2014-12-07 12:57:32,940, WARNING, Container locker_web is already stopped
    $ ./locker.py ports
    2014-12-07 13:47:56,917, INFO, Adding port forwarding rules for locker_db
    2014-12-07 13:47:56,944, INFO, No port forwarding rules for locker_foo
    2014-12-07 13:47:56,947, INFO, locker_web is not running, skipping adding ports rules
    $ ./locker.py rmports
    2014-12-07 13:48:51,413, INFO, Removing netfilter rules
    2014-12-07 13:48:51,416, WARNING, Container locker_db is still running, services will not be available anymore
    2014-12-07 13:48:51,422, INFO, Removing DNAT udp rule of "locker_db"
    2014-12-07 13:48:51,424, INFO, Removing DNAT tcp rule of "locker_db"
    2014-12-07 13:48:51,434, INFO, Removing FORWARD udp rule of "locker_db"
    2014-12-07 13:48:51,435, INFO, Removing FORWARD tcp rule of "locker_db"

Container Status
----------------

::

    $ locker.py status
    Defined Name       State   IPs
    --------------------------------------------
    True    locker_db  RUNNING ('10.0.3.219',)
    True    locker_foo RUNNING ('10.0.3.179',)
    True    locker_web RUNNING ('10.0.3.162',)

Help
----

::

    usage: locker.py [-h] [--verbose [VERBOSE]] [--version [VERSION]]
                     [--delete-dont-ask [DELETE_DONT_ASK]]
                     [--dont-copy-on-create [DONT_COPY_ON_CREATE]] [--file FILE]
                     [--project PROJECT] [--restart [RESTART]]
                     [{start,stop,rm,create,status,ports,rmports}]
                     [containers [containers ...]]

    Manage LXC containers.

    positional arguments:
      {start,stop,rm,create,status,ports,rmports}
                            Commmand to run
      containers            Selection of containers (default: all containers)

    optional arguments:
      -h, --help            show this help message and exit
      --verbose [VERBOSE], -v [VERBOSE]
                            Show more output
      --version [VERSION]   Print version and exit
      --delete-dont-ask [DELETE_DONT_ASK], -x [DELETE_DONT_ASK]
                            Don't ask for confirmation when deleting
      --dont-copy-on-create [DONT_COPY_ON_CREATE], -d [DONT_COPY_ON_CREATE]
                            Don't copy directories/files defined as bind mounts to
                            host after container creation (default: copy
                            directories/files)
      --file FILE, -f FILE  Specify an alternate locker file (default: locker.yml)
      --project PROJECT, -p PROJECT
                            Specify an alternate project name (default: directory
                            name)
      --restart [RESTART], -r [RESTART]
                            Restart already running containers when using "start"
                            command

Limitations & Issues
====================

- Must be run as root
- There is no "up" command yet, you must manually execute the rm, create, start, ports commands
- Does not catch malformed YAML files and statements
- Only directories are supported as bind mounts
- Missing adequate documentation
- No test cases
- Does not support unprivileged containers
- Unstructured project: neither a Python module, nor an installable application - no Debian package meta-data yet
- Extensive code refactoring required

Requirements
============

- Python3 and the following modules

  - yaml
  - argparse
  - lxc
  - logging
  - shutil
  - os, sys, time
  - `iptables <https://github.com/ldx/python-iptables>`_

- Linux Containers userspace tools and libraries

To-Dos / Feature Wish List
==========================

- Resolve everything on the limitations & issues list :-)
- Export and import of containers, optionally including the bind-mounted data
- Support IPv6 addresses and netfilter rules
- Add a hostname parameter and support the configuration of the FQDN
- Support different container paths
- Support setting parameters in the container's config config (e.g. /var/lib/lxc/container/contig) via the YAML configuration
- Evaluate the order in which to create new cloned containers to handle dependency problems (containers are currently created in alphabetical order)
- Support execution of commands inside the container after creation, e.g., to install the puppet agent
- Colored output

Words of Warning
================

- Use at your own risk
- May destroy your data
- Many errors and misconfigurations are not caught yet and may result in undefined states
- Test in an expendable virtual machine first!
- Compatibility may be broken in future versions

License
============

Published under the GPLv3 or later
