Getting Started
===============================================================================

Installation and Requirements
-------------------------------------------------------------------------------
To install **pynvm** you need to first install NVML:

    * `NVM Library <https://github.com/pmem/nvml>`_ (install instructions at
      Github)

You can then install **pynvm** using **pip**::

    pip install pynvm

**pip** will automatically install all dependencies for the Python package.
To use **pynvm** in your program, import the submodule you wish to use
via the ``nvm`` namespace.  For example, to use pmemobj you can do::

    import nvm.pmemobj


Using pmem (*low level persistent memory*)
-------------------------------------------------------------------------------
The :mod:`nvm.pmem` module provides an interface to the `NVML libpmem API
<http://pmem.io/nvml/manpages/master/libpmem.3.html>`_, which provides low
level persistent memory support.  This module provides tools you can
use to implement tear-proof persistent memory updates, but working at this
level your application is solely responsible for protecting against tears.

.. seealso:: For more information regarding **libpmem**, please refer to the
             `libpmem documentation <http://pmem.io/nvml/libpmem/>`_.

Here is an example of opening a PMEM file, writing to it, and reading from it:

.. code-block:: python

    import os
    from nvm import pmem
    from fallocate import posix_fallocate

    # (optional) check the pmem library version
    pmem.check_version(1, 0)

    # Open file to write and fallocate space
    fhandle = open("dst.dat", "w+")
    posix_fallocate(fhandle, 0, 4096)

    # mmap it using pmem
    reg = pmem.map(fhandle, 4096)

    # Write on it and seek to position zero
    reg.write("lol" * 10)
    reg.write("aaaa")
    reg.seek(0)

    # Read what was written
    print(reg.read(10))
    print(reg.read(10))

    # Persist the data into the persistent memory
    # (flush and hardware drain)
    pmem.persist(reg)


Here is an example of using context managers for flush and drain and numpy
buffers:

.. code-block:: python

    import os
    import numpy as np
    from nvm import pmem
    from fallocate import posix_fallocate

    fhandle = open("dst.dat", "w+")
    posix_fallocate(fhandle, 0, 4096)

    # Will persist (pmem_persist) and unmap
    # automatically
    with pmem.map(fhandle, 4096) as reg:
        reg.write("lol" * 10)
        reg.write("aaaa")

        # This will create a numpy array located at
        # persistent memory (very cool indeed) where you
        # can reshape as you like
        n = np.frombuffer(reg.buffer, dtype=np.int32)
        print(n.shape)

    # Flush context will only flush processor caches, useful
    # in cases where you want to flush several discontiguous ranges
    # and then run hardware drain only once
    m = pmem.map(fhandle, 4096)
    with pmem.FlushContext(m) as reg:
        reg.write("lol" * 10)
        reg.write("aaaa")

    # Will only execute the hardware drain (if available)
    m = pmem.map(fhandle, 4096)
    with pmem.DrainContext(m) as reg:
        reg.write("lol" * 10)
        reg.write("aaaa")

    fhandle.close()


Using pmemlog (*pmem-resident log file*)
-------------------------------------------------------------------------------
The :mod:`nvm.pmemlog` module provides an interface to the `NVML libpmemlog API
<http://pmem.io/nvml/manpages/master/libpmemlog.3.html>`_, which provides
pmem-resident log (*append-only*) file memory support.  Writes to the
log are atomic.

.. seealso:: For more information regarding the **libpmemlog**, please refer to
             the `libpmemlog documentation <http://pmem.io/nvml/libpmemlog/>`_.

Here is an example of creating a persistent log, appending a record to it, and
printing out the logged record:

.. code-block:: python

    from nvm import pmemlog

    # Create the logging and print the size (default is 2MB when not
    # specified)
    log = pmemlog.create("mylogging.pmemlog")
    print(log.nbyte())

    # Append to the log
    log.append("persistent logging!")

    # Walk over the log (you can also specify chunk sizes)
    def take_walk(data):
        print("Data: " + data)
        return 1

    log.walk(take_walk)
    # This will show: "Data: persistent logging!"

    # Close the log pool
    log.close()


Using pmemblk (*arrays of pmem-resident blocks*)
-------------------------------------------------------------------------------
The :mod:`nvm.pmemblk` module provides an interface to the `NVML libpmemblk API
<http://pmem.io/nvml/manpages/master/libpmemblk.3.html>`_, which provides
support for arrays of pmem-resident blocks.  Writes to the blocks are atomic.

.. seealso:: For more information regarding the **libpmemblk**, please refer to
             the `libpmemblk documentation <http://pmem.io/nvml/libpmemblk/>`_.

Here is an example of creating a block pool and writing into the blocks:

.. code-block:: python

    from nvm import pmemblk

    # This will create a block pool with block size of 256 and
    # 1GB pool
    blockpool = pmemblk.create("happy_blocks.pmemblk", 256, 1<<30)

    # Print the number of blocks available
    print(blockpool.nblock())

    # Write into the 20th block
    blockpool.write("persistent block!", 20)

    # Read the block 20 back
    data = blockpool.read(20)
    blockpool.close()

    # Reopen the blockpool and print 20th block
    blockpool = pmemblk.open("happy_blocks.pmemblk")
    print(blockpool.read(20))

    blockpool.close()


Using pmemobj (*persistent objects*)
-------------------------------------------------------------------------------
The :mod:`nvm.pmemobj` module provides an interface to the `NVML libpmemobj API
<http://pmem.io/nvml/manpages/master/libpmemobj.3.html>`_, which provides
transactionally managed access to memory that supports allocating and freeing
memory areas.  In this case, rather than providing a simple wrapper around the
pmemobj API, which by itself isn't very useful from Python, pynvm provides a
full Python interface.  This interface allows to you store Python objects
persistently.

This is a work in progress: currently persistence is supported only for lists
(PersistentList), dicts (PersistentDict), objects (PersistentObject),
integers, strings, floats, None, True, and False.  This is, however, enough
to do some interesting things, and an example (pminvaders2, a port
to python of the C example) is included in the examples subdirectory.

Here is an example of creating a PersistentObjectPool and storing and
retrieving objects:

.. code-block:: python

    from nvm import pmemobj

    # An object to be our root.
    class AppRoot(pmemobj.PersistentObject):
        def __init__(self):
            self.accounts = self._p_mm.new(pmemobj.PersistentDict)

        def deposit(self, account, amount):
            self.accounts[account].append(amount)

        def transfer(self, source, sink, amount):
            # Both parts of the transfer will succeed, or neither will.
            with self._p_mm.transaction():
                self.accounts[source].append(-amount)
                self.accounts[sink].append(amount)

        def balance(self, account):
            return sum(self.accounts[account])

        def balances(self):
            for account in self.accounts:
                yield account, self.balance(account)

    # Open the object pool, creating it if it doesn't exist yet.
    pop = pmemobj.PersistentObjectPool('myaccounts.pmemobj', flag='c')

    # Create an instance of our AppRoot class as the object pool root.
    if pop.root is None:
        pop.root = pop.new(AppRoot)

    # Less typing.
    accounts = pop.root.accounts

    # Make sure two accounts are created.  In a real ap you'd create these
    # accounts with subcommands from the command line.
    for account in ('savings', 'checking'):
        if account not in accounts:
            # List of transactions.
            accounts[account] = pop.new(pmemobj.PersistentList)
            # Starting balance.
            accounts[account].append(0)

    # Pretend we have some money.
    pop.root.deposit('savings', 200)

    # Transfer some to checking.
    pop.root.transfer('savings', 'checking', 20)

    # Close and reopen the pool.  The open call will fail if the file
    # doesn't exist.
    pop.close()
    pop = pmemobj.PersistentObjectPool('myaccounts.pmemobj')

    # Print the current balances.  In a real ap this would be another
    # subcommand, run at any later time, perhaps after a system reboot...
    for account_name, balance in pop.root.balances():
        print("{:10s} balance is {:4.2f}".format(account_name, balance))

    # You can run this demo multiple times to see that the deposit and
    # transfer are cumulative.
