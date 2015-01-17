Commands
========

Locker's command line interface is split in multiple parts:

1. General arguments
2. Command
3. Command specific arguments
4. Optional list of containers

General Options
---------------

Locker's default help output shows the general (optional) arguments and the
commands (positional arguments):

.. code:: sh

    $ locker --help
    usage: locker [-h] [--verbose] [--version] [--file FILE] [--project PROJECT]
              [--no-color] [--validate VALIDATE]
              {rm,create,start,stop,reboot,status,ports,rmports,links,rmlinks,cgroup,cleanup, freeze,unfreeze,validate}
              ...

    Manage LXC containers

    positional arguments:
    {rm,create,start,stop,reboot,status,ports,rmports,links,rmlinks,cgroup,cleanup, freeze,unfreeze,validate}
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
        freeze              Freeze containers
        unfreeze            Unfreeze containers
        validate            Validate YAML configuration file against schema

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
                          schema
    --lxcpath LXCPATH, -P LXCPATH
                          Root path the containers (default=/var/lib/lxc)


Command specific Options
------------------------

You can get more information about specific commands and their arguments as
follows:

.. code:: sh

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


Additional information about the commands:

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
    particular parameter is used. The command shows the current state of the
    running containers and ignores non-applied changes in the the YAML
    configuration file or direct changes to the lxc container's ``config`` file.
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
:freeze:
    Freeze the container - stops contained processes
:unfreeze:
    Unfreeze the container - continues contained processes

Tab Completion
==============

Locker supports Bash tab completion thanks to the
`argcomplete <https://github.com/kislyuk/argcomplete>`_ module. After installing
Locker you can temporarily activate the tab completion as follows:

.. code:: sh

    $ eval "$(register-python-argcomplete locker)"

Add this line to your ``~/.bashrc`` to enable persistence.
