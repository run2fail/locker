Features
========

Locker currently supports the following features:

- Container lifecycle management

  - Define groups of containers in a YAML file similar to
    `fig's <http://fig.sh>`_ syntax
  - Create, start, stop, and remove groups or selections of containers defined
    in the particular project
  - Show status report of containers in your project
  - Create containers as clones, create them based on LXC templates, or download
    base images provided by the LXC project

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
