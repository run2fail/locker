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
files that create base installation of your user space of choice. You
either must

- write your own enhanced lxc template that includes a specific application
  (this way the template file get somehow similar to a ``Dockerfile``),
- install your application manually, or
- deploy your application by using a configuration management system like
  `puppet <http://puppetlabs.com/puppet/what-is-puppet>`_,
  `chef <https://www.chef.io/chef/>`_, ...

The latter alternative is what I use as it enables to specify your system's
state in a declarative language in contrast to some hacked together script.
