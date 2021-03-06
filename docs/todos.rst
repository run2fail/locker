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
