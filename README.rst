.. image:: ./docs/logo.png

.. image:: https://readthedocs.org/projects/locker/badge/?version=latest
    :target: https://readthedocs.org/projects/locker/?badge=latest
    :alt: Documentation Status

About Locker
===============

Locker is inspired by `fig <http://fig.sh>`_, a simple yet power tool that
simplifies the management of `Docker <http://www.docker.com>`_  containers.
Locker wraps the `Linux containers (LXC) <https://linuxcontainers.org/>`_
utilities using the Python bindings of ``liblxc`` and takes some manual work out
of the common container management.

With Locker you can define your containers in a descriptive YAML configuration
file which enables to manage their lifecycle (creation, start, stop, ...) in a
very easy manner. Locker automatically creates dedicated network bridges for
each separate project, auto-configures the IP addresses, and container specific
configuration like the hostnames, cgroup settings, etc. In general, Locker tries
to be your frontend to LXC so that you do not have to touch the containers'
configs, fstabs, or dnsmasq files.

Locker is not yet a production ready solution but a prototype implementation.
Nevertheless, you are invited to test, use, and extend Locker. Please report
bugs and ask for missing features.



Usage
===============

This is just a very brief overview of Locker. Please have a look at the
`complete documentation <http://locker.readthedocs.org>`_.

Locker projects are defined in a YAML file similar to `fig's <http://fig.sh>`_
syntax, abbreviated example:

.. code:: yaml

    containers:
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

.. image:: ./docs/demo.gif

Installation
============

Clone the repository:

.. code:: sh

   $ git clone https://github.com/run2fail/locker.git locker
   $ cd locker

Install using ``easy_install``:

.. code:: sh

   $ ./setup.py install

Install using ``pip`` (resp. the python3 version):

.. code:: sh

   $ pip3 install .


Requirements
============

- Python3 and the following modules:

  - lxc (official lxc bindings from the linux containers project)
  - see list of requirements in ``setup.py``
  - `pykwalify <https://github.com/Grokzen/pykwalify>`_ is optionally required
    if you want to validate your YAML configuration file

- Linux containers userspace tools and libraries

Please note that the offical lxc module is not listed in ``install_requires`` in
``setup.py`` as the module is not yet available on PyPi.


Features
========

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
  - DNS entries in the containers are automatically set based on your
    specification (copy the host system's nameservers, use the bridge IP, or
    use custom provided addresses)

- Miscellaneous

  - Multi-colored output (can be optionally disabled)
  - Set container cgroup configuration, e.g., CPUs, memory, ... (experimental
    feature)
  - Bash tab completion via `argcomplete <https://github.com/kislyuk/argcomplete>`_

Limitations
===========

- Must be run as root. Unprivileged containers are not yet supported.
- Only directories are supported as bind mounts (``volumes``)
- Documentation and examples should be further extended.
- When changing memory or CPU limits via the cgroup settings, these changes are
  not "seen" by most user space tools. For more information have a look at the
  `blog post <http://fabiokung.com/2014/03/13/memory-inside-linux-containers/>`_
  of Fabio Kung.
- Please consider that Linux containers do not ship with an installed
  application like Docker containers. Linux containers are usually created based
  on template files that create base installation of your user space of choice.
  You either must:

  - write your own enhanced lxc template that includes a specific application
    (this way the template file get somehow similar to a ``Dockerfile``),
  - install your application manually, or
  - deploy your application by using a configuration management system like
    `puppet <http://puppetlabs.com/puppet/what-is-puppet>`_,
    `chef <https://www.chef.io/chef/>`_, ...

  The latter alternative is what I use as it enables to specify your system's
  state in a declarative language in contrast to some hacked together script.


To-Dos / Feature Wish List
==========================

- Resolve everything on the limitations list :-)
- Networking related:

  - Support IPv6 addresses and netfilter rules
  - Link backwards, i.e., add name + fqdn of the linking container to target
    container. This may be beneficial, e.g., when database logs shall contain
    the hostname
  - Make network configuration more restrictive, e.g.,

    - Enable to configure if containers (in the same or different projects)
      should be isolated from each other.
    - Enable to configure if containers shall be able to establish outbound
      connections with external entities.

- Configuration related:

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

  - Further improve test coverage (currently about 80%)

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


Words of Warning
================

.. warning::
    - Use at your own risk
    - May destroy your data
    - Some errors and misconfigurations may not be caught and may result in
      undefined states
    - Test in an expendable virtual machine first!
    - Compatibility may be broken in future versions



License
============

Published under the GPLv3 or later
