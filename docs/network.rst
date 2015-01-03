Network Configuration
=====================

Each Locker project uses a custom bridge with a dedicated ``/24`` network that
bridges the containers' ethernet interfaces. At this time this is the only
supported way (``lxc.network.type = veth``).

Bridge
------

The bridge will be automatically created when you start any container in the
project. Properties:

- The bridge's name will be ``locker_$project`` where ``$project`` is the
  project's name
- A free ``/24`` network in the range ``10.1.1.0`` to ``10.255.255.0`` will be
  searched. Locker will evaluate the subnets that are accessible via all known
  network interfaces on the host system and avoid collisions.
- The bridge will get the first valid IP address of the subnet.
- All containers in the matching project will use the bridge as gateway.

The bridge can be removed with the ``cleanup`` command.

Please note that, e.g., the ``NetworkManager`` may try to autoconfigure the
bridge as soon as it is detected and may signal problems because DHCP failed.

Due to the ``/24`` network you are limited to 253 containers in each project.

Netfilter Rules
---------------

netfilter rules are required for the following tasks:

- Port forwarding
- Linking
- Enabling access from the containers to external entities (e.g. Internet
  access)

  - Masquerading, i.e., "NAT-ting" of the containers
  - Forwarding of datagrams inbound and outbound

Locker creates to new netfilter chains to keep its rules out of the way of
the other rules:

:``LOCKER_FORWARD``:
    Chain in the ``FILTER`` table that is  accessed via a jump from the
    ``FORWARD`` chain
:``LOCKER_PREROUTING``:
    Chain in the ``NAT`` table that is accessed via a jump from the
    ``PREROUTING`` chain

The particular jump rules are automatically created.
Rules will always have a specific comment that is used to easily filter them.

The port forwarding and linking netfilter rules are automatically removed when
the particular container is stopped with the ``stop`` command. The ``cleanup``
command mentioned above will additionally remove the masquerading and other
forwarding rules but will neither remove the two custom chains nor the jumps
into these chains because other projects may still run containers.

Event based Rule Updates
------------------------

Locker will update the netfilter rules (and other linking information) when
containers are started or stopped using the specific command. Nevertheless,
Locker cannot detect if containers are started or stopped by other means.

If a container crashed or you started/stopped a container by the normal lxc
user space tools, you must manually update the ``port`` and ``links`` specific
rules via the particular Locker commands.

The ``status`` command will always show the actualy state of netfilter rules
and container links and will never show what is currently configured in the YAML
file. This way you can easily spot deviations.

Security Considerations
-----------------------

The network configuration is one way to isolate and protect host from malicious
entities. Nevertheless, containers that are complete user space root file
systems should be managed and secured like normal hosts. It is better to
shutdown or update a vulnerable daemon listening for incoming connections than
to prevent communication.


The following notes shall give Locker users some insight about the default
network configuration in a security context.

- Locker managed containers are not prevented from accessing the Internet, like
  in the default configuration of lxc. Locker adds the following rules to the
  ``LOCKER_FORWARD`` chain:

  .. code::

    target  prot  opt  in  out  source    destination
    ACCEPT  all   --   !br br   anywhere  anywhere
    ACCEPT  all   --   br  !br  anywhere  anywhere

  where ``br`` is the bridge device. Further on, the following rule is added to
  the ``PREROUTING`` chain:

  .. code::

    target      prot  opt  in   out  source       destination
    MASQUERADE  all   --   any  any  10.1.1.0/24  !10.1.1.0/24

  where ``10.1.1.0/24`` is an example subnet used by a particular project.
- Missing ``dns`` configuration will probably prevent communication of
  applications from inside the container with external entities but IP based
  communication may still be possible.
- Locker managed containers can communicate with each other (independent of the
  ``links`` configuration). Likewise, Locker managed containers from different
  projects can communicate with each other. This may be configurable in future
  releases.
- If you want your containers never to be acessible from the outside but still
  want to provide services to external entitites you should consider:

  - Removing all ``ports`` from the containers' config
  - Setting up a webserver (Apache, nginx, ...) as reverse proxy on the host
    system that proxies incoming connections based on the URL or port to the
    right container
- Connection between the containers and the host system (and vice versa) is not
  prevented. If some daemon is listening on the bridge device, the containers
  will be able to use the service. For example, you will probably be able to
  ``ssh`` from the container to the host system.
