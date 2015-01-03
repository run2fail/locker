Project Configuration
=====================

The YAML file defines a Locker ``project``, i.e., a group of containers. The
``project`` name may be provided via a command line parameter and is derived
from the current directory's name as default. Use the ``--project`` parameter
to explicitly specify the project name. The project name may only consist of
alphanumeric characters but may not start with a digit.

The project configuration file and project name can be specified as follows:

.. code:: sh

    $ locker --file config.yaml --project foobar

Containers
----------

Example:

.. code:: yaml

    foobar:
        template:
            name: "ubuntu"
            release: "precise"
            arch: "amd64"

The first level in the YAML configuration are container names (``name``).
Containers are created as ``clone`` of other containers available on the system
or based on ``template`` files that are usually part of the lxc user space
tools. In the latter case, the map/sub-tree of ``template`` is provided as
argument to the ``template`` when creating the container. The creation from the
the template will fail if you are specifying unknown keys or are missing
critical key-value pairs.

If you specify ``clone`` make sure that the container to clone from already
exists.

Please note that while the container's ``name`` is ``foo`` in the YAML file,
the actual name of the container on the system will be of the format
``$project_$name`` to enable containers with the same name in different
projects.

The container name may only consist of alphanumeric characters but may not start
with a digit.

Data Storage
------------

Example:

.. code:: yaml

    volumes:
     - "/opt/data/$project_$name/var/log:/var/log"

Locker containers may store data outside of the container's root file system,
e.g., in ``/opt/data`` on the host system. In many use cases you probably want
to store all data of your special application that is running inside the
container outside on the host system, e.g., ``/var/lib/postgres`` and
``/var/www`` if you are running a typical web application with a database.

``volumes`` define bind-mounts of directories on the host system into the
container. You can use some simple placeholders like ``$name``, ``$project``,
and ``$fqdn`` in your volume definitions. The format is
``DIR_ON_THE_HOST:DIR_IN_THE_CONTAINER``.

Bind-mounted directories are moved after the creation of the container from
the container's root file system to the particular location on the host system.
This ensures that the mounted directories are not empty and have the right
owner. Of course directories can only be moved to the host, when they are
created by the template / exist in the cloned container and when the destination
does not yet exist.

You can suppress the moving of directories with ``--dont-copy-on-create``
(legacy name that may be changed in future releases). Directories are only
moved immediately after the container creation phase! If you add ``volumes`` at
a later time, you must move/create the directories yourself.

Please note that as user and group IDs can differ between the host system and
inside the container, the bind-mounted directories may appear to be owned by
different users/groups on the host system.


Port Forwarding
---------------

Example:

.. code:: yaml

   ports:
    - "80:80"
    - "8000:8000/udp"
    - "8001:8001/tcp"
    - "192.168.2.123:8003:8003/udp"

Port forwarding can make particular services on the containers available to
external entities. For example, a container running a web server on tcp port 80
may make its service available on port 8080 of the host system.

Different formats of port forwarding rules (``ports``) are supported.  The
format is ``HOST_IP:HOST_PORT:CONTAINER_PORT/PROTOCOL`` where as ``HOST_IP`` and
``PROTOCOL`` are optional. If the protocol is not specified, the default
(``tcp``) will be used to configure netfilter rules. If ``HOST_IP`` is missing,
IP datagrams destined to any interface/IP address on the host system will be
forwarded. In many use cases ``HOST_IP`` will not be required.

Please note that Locker does not support dynamic/automatic assignment of port
numbers. At this time Locker will also not check if there are conflicting
netfilter rules.

Port forwarding only works for IP datagrams that are received from external
entities. The responsible netfilter rules are not applied for datagrams
originating from the host system.


FQDN and Hostname
-----------------

Example:

.. code:: yaml

    fqdn: "db.example.net"

Several applications rely on the full qualified domain name (``fqdn``).
For example, the puppet agent of the puppet configuration management system
generates and selects TLS/SSL certificates for the authentication at the
puppet master based on the ``fqdn``.

The ``fqdn`` attribute enables to set the container's hostname
and ``fqdn``. It will be set in the container's ``/etc/hostname`` and also
replace any other name for ``127.0.1.1`` in ``/etc/hosts``.

Currently, Locker will also register the container's "raw" name, i.e., the name
specified in the YAML configuration file without the project name prefix, in
``/etc/hosts``. This may change in future releases.

Linking Containers
------------------

Example:

.. code:: yaml

    links:
     - "db:database"

Links will make containers accessible to other containers. ``links`` entries
will add the specified, i.e., linked container's hostname,
alias, and ``fqdn`` to the linking container's
``/etc/hosts`` file. This way a container with a webserver based application
can access a database in another container using the particular hostname.

The format is ``container_name:alias`` where as the alias can be omitted. You
must specify the container name without the project prefix. The above example
will add the following entry to ``/etc/hosts`` (assuming the ``db`` container
also specified ``fqdn: db.example.net``):

.. code::

    10.1.1.2   db.example.net db database

Additionally, Locker will add netfilter rules that enable the forwarding of IP
datagrams between the linked containers (any protocol, any port). This is
required if your ``FORWARD`` chain in the ``FILTER`` has ``DROP`` as policy.

Control Group Configuration
---------------------------

Example:

.. code:: yaml

    cgroup:
     - "memory.limit_in_bytes=200000000"
     - "cpuset.cpus=0,1"
     - "cpu.shares=512"

You can apply ``cgroup`` settings by providing a list of strings where each
string is of the format ``key=value``. All ``cgroup`` settings are also written
to the container's ``config`` file and are hence set even when you use
``lxc-start`` to start containers later on. Be careful with this feature.

Nameservers
-----------

Example:

.. code:: yaml

    dns:
    - "8.8.8.8"
    - "$bridge"
    - "$copy"

Nameservers can be specified via the ``dns`` section. You can specify addresses
as follows:

- Specify the IP address as string
- Use the magic work ``$bridge`` to use the project's bridge IP address
  (e.g. if you are running a custom dnsmasq process listening on this interface)
- Use the magic word ``$copy`` which will copy the nameserver entries from
  ``/etc/resolv.conf`` into the container (excluding loopback addresses!)

Locker will keep the order of the speficied entries. Hence specify your primary
nameserver first.

Please note that without a valid nameserver you will not be able to resolve
hostnames from within the container and Internet access may fail for many
applications.

YAML Validation
===============

You can optionally validate your project configuration with the
`schema file <./docs/schema.yaml>`_ that is available in the ``docs/``
directory:

.. code:: sh

    $ locker -f myconf.yaml --validate docs/schema.yaml status

Due to some legacy issues, you currently must always specify any command to run
the validation (use ``status`` to avoid side-effects). Further releases may
introduce a custom ``validate`` command.

Please note that the `pykwalify <https://github.com/Grokzen/pykwalify>`_
module must be available. It is not specified as requirement in ``setup.py``.
