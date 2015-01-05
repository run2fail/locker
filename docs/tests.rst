Test Cases
==========

.. warning:: These are not unit tests that can be run without any side effects.
             In fact, the test cases are more akin to integration or system
             tests. Each test case actually creates, starts, stops, etc.
             containers on the test system. Additionally bridgs are created,
             configured, and destroyed. As these "external resources" are
             used, you will change the state of your system.
             Currently I refrain from writing test cases with mocked
             classes/methods that do not change the running system. As far as I
             know there is no easy way to replace ``lxc.Container`` with a mock
             where all derived classes (e.g. ``locker.Container``) also will use
             the mocked base class.

Test cases can be run easily with ``nosetest`` including a coverage analysis,
example:

.. code::

    nosetests3 --with-coverage --cover-package=locker --cover-html --cover-erase

The test cases are independent from particular project configuration files.
Containers are created in ``/tmp/locker``. This directory must exist, have
at least 1 GB of free storage, and should be a ``tmpfs`` to increase speed and
to avoid "wearing out" solid state disks (each run creates and deletes dozens
containers of ~350 MB).
