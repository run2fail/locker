.. image:: ./docs/logo.png

About Locker
===============

Locker is my take on `Docker <http://www.docker.com>`_  + `fig <http://fig.sh>`_
applied for `Linux containers (LXC) <https://linuxcontainers.org/>`_. Locker
wraps the lxc utilities like fig does for Docker.

Locker is not yet a production ready solution but a prototype implementation.
Its feature set is mainly focused on my personal application domain. Most
notably, I required a solution to set up groups of Ubuntu containers with
bind-mounted folders to store critical data and to make services from the
containers available to the outside world by port forwarding. I needed a
complete base installations in the containers to support security auto-updates,
cron jobs, ssh access, etc. which ruled out pure application containers. Locker
is a simple Python application that simplifies these tasks.

Please consider that Linux containers do not ship with an installed application
like Docker containers. Linux containers are usually created based on template
files, i.e., you get a base installation of your user space of choice. You
either must write your own enhanced LXC template, install your application
manually, or deploy your application by using a configuration management system
like `puppet <http://puppetlabs.com/puppet/what-is-puppet>`_,
`chef <https://www.chef.io/chef/>`_, ...

Features
--------

Locker currently supports the following features:

- Container lifecycle management

  - Define groups of containers in a YAML file similar to
    `fig's <http://fig.sh>`_ syntax
  - Create, start, stop, and remove groups or selections of containers defined
    in the particular project
  - Show status report of containers in your project
  - Create containers as clones or based on LXC templates

- Data storage

  - Create an ``fstab`` file to enable bind-mounted directories from the host
    into the container(-s)
  - Optionally, bind-mounted folders may be moved from the container to the
    host after container creation, so that you do not mount empty folders
    within your container on the first start

- Network configuration

  - Project specfic network bridge automatically created (and removed on
    demand via command)
  - IP addresses are automatically assigned to bridges and containers
    (``dnsmasq`` is not required)
  - Add or remove port forwarding netfilter rules to make services accessible
    to other hosts
  - Links containers by dynamically adding hostnames to ``/etc/hosts``
  - Dynamically adds and removes the containers' hostnames in/from
    ``/etc/hostname`` on the lxc host (must be explicitly activated)
  - DNS entries in the containers are set to ``8.8.8.8`` and ``8.8.4.4``
    (planned to be configurable in the near future)

- Miscellaneous

  - Multi-colored output (can be optionally disabled)
  - Set container cgroup configuration, e.g., CPUs, memory, ... (experimental
    feature)


Challenges implementing Locker
------------------------------

Some convenience features are missing in the lxc user utilities. Hence Locker
must implement features where `fig <http://fig.sh>`_ can simply rely on
`Docker <http://www.docker.com>`_.

- lxc does not support port forwarding, resp. does not provide an easy way to
  add/remove netfilter rules. Of course, you can always use iptables directly
  but that is not really convenient for everybody.
- lxc containers can communicate with each other in the default configuration as
  they are behind the same bridge device. Yet the hostnames/full qualified
  domain names are not known, i.e., there is no "linking" support.
- In general, the lxc container and network configuration requires manual
  work/modifications, e.g., when containers shall get static IP addresses.

Note: Please correct me if I am wrong or if there is some solution available!
This would really help me. Thanks!


Usage
===============

Under construction...

Installation
------------

Using ``easy_install``:

.. code:: bash

   $ ./setup.py install

Using ``pip`` (resp. the python3 version):

.. code:: bash

   $ pip3 install .


Defining a Project
------------------

An example project definition in YAML:

.. code:: yaml

    db:
        template:
            name: "ubuntu"
            release: "precise"
        ports:
        - "8000:8000"
        - "8000:8000/udp"
        - "8001:8001/tcp"
        volumes:
        - "/opt/data/db/var_log:/var/log"
        - "/opt/data/db/etc:/etc"
        fqdn: 'db.example.net'
    web:
        clone: "ubuntu"
        ports:
        - "192.168.2.123:8002:8002"
        - "192.168.2.123:8003:8003/tcp"
        - "192.168.2.123:8003:8003/udp"
        volumes:
        - "/opt/data/$name/var_log:/var/log"
        links:
        - "db:database"
    foo:
        template:
            name: "ubuntu"
            release: "precise"
        links:
        - "db"
        cgroup:
        - "memory.limit_in_bytes=200000000"
        - "cpuset.cpus=0,1"
        - "cpu.shares=512"

The YAML file defines a Locker ``project``, i.e., a group of containers. The
``project`` name may be provided via a command line parameter and derived
from the directory's name as default.

The first level in the YAML configuration are container names (``name``).
Containers are created as ``clone`` of other containers available on the system
or based on ``template`` files that are usually part of the lxc user space
tools. In the latter case, the map/sub-tree of ``template`` is provided as
argument to the ``template`` when creating the container. Please note that
while the container's ``name`` is ``foo`` in the YAML file, the actual name of
the container on the system will be of the format ``$project_$name`` to enable
containers with the same name in different projects.

``volumes`` define bind-mounts of directories on the host system into the
container. You can use some simple placeholders like ``$name``, ``$project``,
and ``$fqdn`` in your volume definitions.

Different formats of port forwarding rules (``ports``) are supported.  The
format is ``HOST_IP:HOST_PORT:CONTAINER_PORT/PROTOCOL`` where as ``HOST_IP`` and
``PROTOCOL`` are optional. If the protocol is not specified, the default
(``tcp``) will be used to configure netfilter rules.

The ``fqdn`` attribute enables to set the container's hostname
and full qualified domain name (``fqdn``). This is realized by a lxc hook script
that is run after the mounting has been done. Several applications rely on the
``fqdn``, e.g., the puppet agent of the puppet configuration system generates
and selects TLS/SSL certificates for the authentication at the puppet master
based on the ``fqdn``.

``links`` entries will add the specified, i.e., linked container's hostname,
(optional) alias, and (optional) ``fqdn`` to the linking container's
``/etc/hosts`` file. This way a container with a webserver based application
can access a database in another container using the particular hostname.

You can apply ``cgroup`` settings by providing a list of strings where each
string is of the format ``key=value``. All ``cgroup`` settings are also written
to the container's ``config`` file and are hence set even when you use
``lxc-start`` to start containers later on. Be careful with this feature.

You can find some examples in the `docs/examples/ <./docs/examples>`_ directory.

Validation
----------

You can optionally validate your project configuration with the
`schema file <./docs/schema.yaml>`_ that is available in the ``docs/``
directory:

.. code::

    $ locker status -f myconf.yaml --validate docs/schema.yaml

Please note that the `pykwalify <https://github.com/Grokzen/pykwalify>`_
module must be available.

Managing the Lifecycle
----------------------

Example session (with ``locker.yaml`` in the current directory):

.. image:: ./docs/demo.gif

Help & Commands
----------------

Locker's command line interface is split in multiple parts:

1. General arguments
2. Command
3. Command specific arguments
4. Optional list of containers

Locker's default help output shows the general (optional) arguments and the
commands (positional arguments):

.. code::

    $ locker --help
    usage: locker [-h] [--verbose] [--version] [--file FILE] [--project PROJECT]
              [--no-color] [--validate VALIDATE]
              {rm,create,start,stop,reboot,status,ports,rmports,links,rmlinks,cgroup,cleanup}
              ...

    Manage LXC containers

    positional arguments:
    {rm,create,start,stop,reboot,status,ports,rmports,links,rmlinks,cgroup,cleanup}
                            sub-command help
        rm                  Delete container
        create              Create container
        start               Start container
        stop                Stop container
        reboot              Reboot container
        status              Show container status
        ports               Add port forwarding netfilter rules
        rmports             Remove port forwarding netfilter rules
        links               Add links between containers
        rmlinks             Remove links between containers
        cgroup              Set cgroup configuration
        cleanup             Stop containers, remove netfilter rules and bridge

    optional arguments:
    -h, --help            show this help message and exit
    --verbose, -v         Show more output
    --version             Print version and exit
    --file FILE, -f FILE  Specify an alternate Locker file (default:
                            ./locker.yaml)
    --project PROJECT, -p PROJECT
                            Specify an alternate project name (default: current
                            directory name)
    --no-color, -o        Do not use colored output
    --validate VALIDATE   Validate YAML configuration against the specified

You can get more information about specific commands and their arguments as
follows:

.. code::

    $ locker start --help
    usage: locker start [-h] [--restart] [--no-ports] [--add-hosts] [--no-links]
                        [--timeout TIMEOUT]
                        [containers [containers ...]]

    positional arguments:
    containers            Space separated list of containers (default: all
                            containers)

    optional arguments:
    -h, --help            show this help message and exit
    --restart, -r         Restart already running containers when using "start"
                            command
    --no-ports, -n        Do not add/remove netfilter rules (used with command
                            start/stop)
    --add-hosts, -a       Add the containers' hostnames to the /etc/hosts file
                            of this host
    --no-links, -m        Do not add/remove links (used with command start/stop)
    --timeout TIMEOUT, -t TIMEOUT
                            Timeout for container shutdown


About the commands:

:create:
    Create new containers based on templates or as clones. The container's
    "template" subtree in the YAML configuration is provided as the template's
    arguments.
:start:
    Start the container and run the ports command, i.e., add netfilter rules on.
:stop:
    Stop the container and run the rmports command, i.e., remove netfilter rules.
:reboot:
    As the name implies: stop the container (if running) and start it afterwards.
:ports:
    Add port, i.e., netfilter rules. Automatically done when using start
    command.
:rmport:
    Remove port i.e., netfilter rules. Automatically done when using stop
    command.
:status:
    Show container status. An extended status report is available when the
    particular parameter is used.
:links:
    Add/updates links in container. Automatically done when using start command.
    Subsequent calls will update the links and remove stale entries of
    not properly stopped/crashed containers.
:rmlinks:
    Removes all links from the container.
:cgroup:
    (Re-)Apply cgroup settings. Automatically done when starting containers.
:cleanup:
    Stop all containers and cleanup netfilter rules and bridge

Limitations & Issues
====================

- Must be run as root. Unprivileged containers are not yet supported.
- Only directories are supported as bind mounts (``volumes``)
- Documentation and examples should be further extended.
- When changing memory or CPU limits via the cgroup settings, these changes are
  not "seen" by most user space tools. For more information have a look at the
  `blog post <http://fabiokung.com/2014/03/13/memory-inside-linux-containers/>`_
  of Fabio Kung.

Requirements
============

- Python3 and the following modules:

  - lxc (official lxc bindings from the linux containers project)
  - see list of requirements in setup.py
  - `pykwalify <https://github.com/Grokzen/pykwalify>`_ is optionally required
    if you want to validate your YAML configuration file

- Linux containers userspace tools and libraries

To-Dos / Feature Wish List
==========================

- Resolve everything on the limitations & issues list :-)
- Networking related:

  - Support IPv6 addresses and netfilter rules
  - Bridging

    - Prevent communication between containers in the default configuration
    - Add netfilter rules for inter-container commmunication when "links" are
      defined

  - Link backwards, i.e., add name + fqdn of the linking container to target
    container. This may be beneficial, e.g., when database logs shall contain
    the hostname
  - Enable to remove LOCKER chain in the NAT table + rules in the FORWARD chain
  - Enable to specify DNS servers for each container via the configuration

- Configuration related:

  - Support different container paths
  - Support setting parameters in the container's config
    (e.g. ``/var/lib/lxc/container/config``) via the YAML configuration.
  - Setting environment variables in linked containers?! Not required in my use
    cases. Name resolution is more important as the initial configuration of
    applications is realized by a configuration management system.
  - ``lxc-create`` may use the ``download`` template to download images from the
    `offical LXC website <http://images.linuxcontainers.org/images/>`_. Maybe
    this can be used via the Python binding?!? For sure the YAML configuration
    needs to be extended to support this feature.
  - In general, I am not fully convinced of the YAML file's structure and the
    format of some string attributes, e.g., ``ports`` or ``volumes``. The format
    tries to mimic the particular format of
    `Docker <http://www.docker.com>`_  and `fig <http://fig.sh>`_ but I think
    it would be easier (for users to define and for Locker to parse) to replace
    these strings with YAML maps and/or sequences.

- Source code related:

  - Write real unit tests without side-effects (see next section for further
    information)
  - Provide dedicated YAML files for the tests and stop using example files.

- User interface related:

  - The status report is getting larger and is already wider than 80 columns.
    The extended version using the particular command line parameter is even
    wider. It may be necessary to enable the user to specify the columns of
    interest, for examle like ``--columns="Name,Ports,CPUs,Memory"``.

- Miscellaneous:

  - Evaluate the order in which to create new cloned containers to handle
    dependency problems (containers are currently created in alphabetical order)
  - Add Debian package meta-data
  - Export and import of containers, optionally including the bind-mounted data
  - Support execution of commands inside the container after creation, e.g., to
    install and run the `puppet <http://puppetlabs.com/puppet/what-is-puppet>`_
    agent

Test Cases
==========

.. warning:: These are not unit tests that can be run without any side effects.
             In fact, the test cases are more akin to integration tests. Each
             test case actually creates, starts, stops, etc. containers on the
             test system. As these "external resources" are used, you will
             change the state of your system.
             Currently I refrain from writing better test cases with mocked
             classes/methods that do not change the running system. As far as I
             know there is no easy way to replace ``lxc.Container`` with a mock
             where all derived classes (e.g. ``locker.Container``) also will use
             the mocked base class.

Test cases can be run easily with ``nosetest`` including a coverage analysis,
example:

.. code::

    nosetests3 --with-coverage --cover-package=locker --cover-html --cover-erase

Many test cases rely on the example YAML project configuration that is available
`here <./docs/examples/locker.yaml>`_.


Words of Warning
================

.. warning::
    - Use at your own risk
    - May destroy your data
    - Many errors and misconfigurations are not caught yet and may result in
      undefined states
    - The feature to set cgroup configuration via the YAML file has high
      potential to shoot yourself in the foot
    - Test in an expendable virtual machine first!
    - Compatibility may be broken in future versions

License
============

Published under the GPLv3 or later
