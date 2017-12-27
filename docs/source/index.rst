PyNVM: A Python Interface to PMDK
=================================

This framework aims to bring NVM (*non-volatile memory*)/SCM (*storage-class
memory*) technology functionality to the Python ecosystem.  The PyNVM package
provides an 'nvm' namespace that contains several sub-packages.  These packages
wrap the sub-modules provided by `PMDK: Persistent Memory Development Kit
<https://github.com/pmem/pmdk>`_.  Most of the sub-modules are relatively thin
wrappers around the corresponding PMDK API calls, with some scaffolding to make
them more easily used from Python.  The :mod:`~nvm.pmemobj` submodule provides
a fully Pythonic interface to persistent memory, allowing the easy persistence
of Python objects via a :class:`~nvm.pmemobj.PersistentObjectPool`.

Contents:

.. toctree::
   :maxdepth: 4

   intro
   getting_started
   pmemobj_tutorial
   pmem
   pmemlog
   pmemblk
   pmemobj
   changelog
   license

.. note:: This framework is in active development and it is still in beta release.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

