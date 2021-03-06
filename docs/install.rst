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

- Linux containers userspace tools and libraries, version >= ``1.0.7`` (see
  `Issue 385 <https://github.com/lxc/lxc/issues/385>`_) but note that  ``1.1.0``
  may also show problems (see
  `Issue 394 <https://github.com/lxc/lxc/issues/394>`_)

Please note that the offical lxc module is not listed in ``install_requires`` in
``setup.py`` as the module is not yet available on PyPi (see
`Issue 392 <https://github.com/lxc/lxc/issues/392>`_)
