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
