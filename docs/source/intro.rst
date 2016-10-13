Introduction
===============================================================================

This library provides Python bindings for the `NVM Library
<https://github.com/pmem/nvml>`_.


Overview and Rationale
-------------------------------------------------------------------------------

Currently, there are no Python packages supporting *persistent memory*, where
by *persistent memory* we mean memory that is accessed like volatile memory,
using processor **load** and **store** instructions, but retaining its contents
across power loss just like traditional storages.

The goal of this project is to provide Python bindings for the libraries that
are part of the `NVM Library <https://github.com/pmem/nvml>`_. The **pynvml**
project aims to create bindings for the NVM Library without modifying the
Python interpreter itself, thus making it compatible to a wide range of Python
interpreters (including PyPy).


How it works
-------------------------------------------------------------------------------

.. figure:: _static/imgs/swarch.jpg
   :scale: 100 %

   *Image from: http://pmem.io*


In the image above, we can see different types of access to a NVDIMM device.
There are the standard and well known types of access like the one using the
standard file API (fopen/open, etc.).  Then on the far right is the type of
access that this package is concerned with, using Load/Store and bypassing all
kernel space code. This is the fastest way an application can access memory,
and in our case, this is not the traditional volatile memory, it is
**persistent memory**.  The significance of this is that you don't need to
serialize data to disk anymore to save it between program runs, you just keep
your data structures in memory that is **persistent**.

However with great power comes great responsibility: it is the duty of the
program doing the memory access to provide things such as flushes and hardware
drains (i.e. `CLWB/PCOMMIT instructions <http://danluu.com/clwb-pcommit/>`_).
If a machine crashes during a write to persistent memory, the write can be in
some cases be "torn": only part of the change actually reaches the persistent
memory, and another part of it is lost.  The application must be aware of when
it can rely on a change being completely preserved and when it can't.
Providing the infrastructure to do this reliably, so that writes to memory
cannot be torn from the application's point of view, is the purpose of Intel's
`NVM Library <https://github.com/pmem/nvml>`_, for which this package provides
Python bindings.

.. seealso ::

    `Planning the Next Decade of NVM Programming
    <http://www.snia.org/sites/default/files/SDC15_presentations/gen_sessions/AndyRudoff_Planning_for_Next_Decade.pdf>`_.

    `Programming Models for Emerging Non-Volatile Memory Technologies
    <https://www.usenix.org/system/files/login/articles/08_rudoff_040-045_final.pdf>`_.

    `Persistent Memory Byte-Addressable Non-Volatile Memory
    <http://storageconference.us/2014/Presentations/Panel3.Rudoff.pdf>`_.

    `Persistent Memory: What's Done, Coming Soon, Expected Long-term
    <https://linuxplumbersconf.org/2015/ocw//system/presentations/3015/original/plumbers_2015.pdf>`_.

