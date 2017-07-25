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

Providing the infrastructure to do this reliably is the purpose of Intel's
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

