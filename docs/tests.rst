Test Cases
==========

.. warning:: These are not unit tests that can be run without any side effects.
             In fact, the test cases are more akin to integration or system
             tests. Each test case actually creates, starts, stops, etc.
             containers on the test system. As these "external resources" are
             used, you will change the state of your system.
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
