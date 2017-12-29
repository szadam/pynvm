.. module:: pmemobj
.. moduleauthor:: R. David Murray

:mod:`pmemobj` --- Pesistent Python objects
===========================================




Creating and Accessing a :mod:`PersistentObjectPool`
----------------------------------------------------



.. function:: create(filename, pool_size=MIN_POOL_SIZE, mode=0o666, debug=False)

   Return a :class:`PersistentObjectPool` backed by a file named *filename*,
   allocating *pool_size* bytes for the pool, and setting the mode of the file
   on the filesystem to *mode*.  Raise an :exc:`OSError` if the file already
   exists.  Pass *debug* to the :class:`PersistentObjectPool` constructor.

   If *filename* is in a filesystem backed by persistent memory, the memory
   will be directly accessed.  Otherwise persistent memory will be emulated by
   memory mapping a disk file.

   The actual amount of memory available for objects is smaller than
   *pool_size* transaction and object management overhead.  The default is the
   default used by ``libpmemobj``.



.. function:: open(filename, debug=False)

   Return a :class:`PersistentObjectPool` backed by the file named *filename*.
   Raise an an :exc:`OSError` if the file does not exist.  If the previous
   shutdown was not clean, call the :class:`PersistentObjectPool.gc` method.
   Pass *debug* to the :class:`PersistentObjectPool` constructor.



.. class:: PersistentObjectPool(filename, flag='w', pool_size=MIN_POOL_SIZE, \
                                mode=0x666, debug=False)

   Open or create a persistent object pool backd by *filename*.  If *flag* is
   ``w``, raise an :exc:`OSError` if the file does not exist and otherwise
   open it for reading and writing.  If *flag* is ``x``, raise an
   :exc:`OSError` if the file already exists, and otherwise create the file
   and open it for reading and writing.  If *flag* is ``c``, create the file
   if it does not exist, but in any case open it for reading and writing.

   If the file gets created, allocate *pool_size* bytes for the pool,
   and set its mode in the filesystem to *mode*.

   If the object pool was previously not closed cleanly, call :meth:`gc`.

   Use *debug* as the default value for the *debug* parameter to the :meth:`gc`
   method.


   .. attribute:: root

      The "root" object of the pool.  This can be set to any object
      that can be persisted, but it is really only useful to set it to
      a Perisistent collection type.  Only objects that are reachable
      by traversing the object graph starting from the root object will
      be preserved once the object pool is closed.


   .. method:: gc(debug=None)

      Free all unreferenced objects: objects not accessible by tracing
      the object graph starting at the :attr:`root` object.


   .. method:: new(typ, *args, **kw)

      Create a new instance of *typ* managed by this pool, passing its
      constructor *args* and *kw*.  *typ* must support the :class:`Persistent`
      API.

   .. method:: persist_via_pickle(*types)

      Add *types* to the list of types that will be persisted via pickle.
      Nominated types must be non-container immutable types (this is not
      currently enforced, but confusing things will happen if you violate it).
      If a version of pmemobj to which support for a given type has been added
      is used to open a pool with instances of that type stored via pickle, the
      object will be resurrected from pickle, but any new instances written to
      the pool will use the direct support.


   .. method:: transaction()

      Return a context manager object that manages a transaction.  If the
      context is exited normally, all changes to objects managed by the pool
      should be committed; if the context exits abnormally or the program stops
      running for any reason in the middle of the context, then none of the
      changes to the persistent objects inside the transaction context should
      be visible.  Note that the transaction does not affect changes to normal
      Python objects; only changes to Persistent objects will be rolled back on
      abnormal exit.


   .. method:: close()

      Call :meth:`gc`, mark the pool as clean, and close the underlying file.
      The object pool lives on in the file that contains it and may be
      reopened at a later date, and all the objects reachable from the
      :attr:`root` object will be in the same state they were in when the pool
      was closed.




Managing Persistent Memory
--------------------------



.. class:: MemoryManager(pool_pr, type_table=None)

   Create a manager for a :class:`PersistentObjectPool`'s memory.  This class
   should never be instantiated directly, but instead the automatically
   created instance should be accessed through a pool object.

   All of the methods below are atomic from the point of view of the caller.
   If the program crashes in the middle of the method it will either have
   completed or on pool reopen it will be as if it had never been started.  All
   methods may be called from inside a transaction to make them part of a
   larger atomic unit of change.


   .. method:: new(typ, *args, **kw)

      Create a new instance of *typ* managed by the pool, passing its
      constructor *args* and *kw*.  *typ* must support the :class:`Persistent`
      API.


   .. method:: transaction()

      Return a context manager object that manages a transaction.  If the
      context is exited normally, all changes to objects managed by the pool
      should be committed; if the context exits abnormally or the program
      stops running for any reason in the middle of the context, then none of
      the changes to the persistent objects inside the transaction context
      should be visible when the pool is next opened.


   .. method:: otuple(oid)

      Ensure that *oid* is in tuple form.  An ``oid`` retreived from memory is
      actually a pointer to the memory the oid was retrieved from, so if
      contents of that memory location changes the value of the raw ``oid``
      would change.  This method copies the ``oid`` data into a tuple not
      subject to such modification, but which can be assigned to a memory field
      to store its value at that location.

      All ``MemoryManager`` methods that return oids return them in tuple form.


   .. method:: alloc(size, type_num=POBJECT_TYPE_NUM)

      Return an ``oid`` pointing to *size* bytes of newly allocated persistent
      memory, passing *type_num* to libpmemobj as the new memory object's type.
      Raise an error if called outside of any :meth:`transaction`.

      A :class:`Persistent` class should use POBJECT_TYPE_NUM for its base
      memory allocation, but should use a unique number for any non-PObject
      memory structures it allocates.  (There is currently no way to manage
      allocating these numbers to guarnatee uniqueness, but in fact as long as
      something other than POBJECT_TYPE_NUM is used, nothing should break even
      if the number collides with at used by a different :class:`Persistent`
      type, you just lose some memory type safety.)


   .. method:: zalloc(size, type_num=POBJECT_TYPE_NUM)

      Same as :meth:`alloc`, but the allocated persistent memory is also zeroed.


   .. method:: free(oid)

      Return the persistent memory pointed to by *oid* to the pool, so
      that it is avaiable for future allocation.  Raise an error if
      called outside of any transaction.


   .. method:: realloc(oid, size, type_num=None)

      Return an ``oid`` pointing to *size* bytes of newly allocated persistent
      memory and copy the data pointed to by *oid* into it, truncating or
      zero-filling as needed.  Raise an error if *type_num* is not ``None`` and
      does not match the pmem type of *oid*.  :meth:`free` the memory
      originally pointed to by *oid*.  Raise an error if called outside
      of any transaction.


   .. method:: zrealloc(size, type_num=POBJECT_TYPE_NUM)

      Same as :meth:`realloc`, but the newly allocated persistent memory is also
      zeroed.


   .. method:: incref(oid)

      Increment the reference count of the ``PObject`` pointed to by *oid*.


   .. method:: decref(oid)

      Decrement the reference count of the ``POjbect`` pointed to by *oid*.  If
      the reference count is zero after the decrement, then if the object has a
      :meth:`~Peristent._p_deallocate` method call it, and in any case call
      :meth:`free` on *oid*.


   .. method:: xdecref(oid)

      Call :meth:`decref` on *oid* if *oid* is not ``OID_NULL``.

      :meth:`decref` should be used whever possible, so that cases where
      an ``oid`` is unexpectedly null raise an error.  If, however,
      the poitner can legitimately be null, this method eliminates the
      need for an if test, and this is a common enough case to be worth
      having extra method.


   .. method:: persist(obj)

      Return an ``oid`` pointing to the representation of *obj* in peristent
      memory, creating that representation if necessary.  *obj* must be one of
      the directly supported immutable types, or one of the immutable types
      nominated for persistence via ``pickle``, or a :class:`Persistent` type.


   .. method:: resurrect(oid)

      Return a Python object representing the ``POjbect`` stored at *oid*.
      This may be a pure Python object if the stored object is a non-container
      immutable, or is otherwise an object that redirects data accesses to data
      stored in persistent memory.


   .. method:: direct(oid)

      Return the real memory address of the persistent memory pointed
      to by *oid*.




Persistent Classes
------------------



.. class:: Persistent()

   :class:`Persistent` is an Abstract Base Class for objects that implement the
   ``Persistent`` interface.  All classes that want to store their data in
   persistent memory and manage it must implement the interface described here,
   but they are not required to use the ABC as their base.


   .. attribute:: _p_mm

      A :class:`MemoryManager` instance from the :class:`PersistentObjectPool`
      in which this object is stored.


   .. attribute:: _p_oid

      The ``oid`` that points to the ``PObject`` data structure in
      persistent memory that anchors this objects data.


   .. method:: _p_new(manager)

      Initialize the objects data structures when the object is initially
      created, and store the provided :class:`MemoryManager` *manager*
      in :attr:`_p_mm` and the ``oid`` pointing to the initialized
      data structures (a ``POjbect``) in :attr:`_p_oid`.


   .. method:: _p_resurrect(manager, oid)

      Restore the object's state from the data located at *oid*, using
      *manager*, storing the *manager* in :attr:`_p_mm` and the *oid*
      in :attr:`_p_oid`.


   .. method:: _p_traverse()

      Return an iterable over the ``oids`` of all of the objects pointed to by
      this object.


   .. method:: _p_substructures()

      Return an iterable over the oids of all of the non-``PObject`` data
      structures allocated by this object.


   .. method:: _p_deallocate()

      Remove all pointers to any other objects, and :meth:`~MemoryManager.free`
      any allocated data structures.  When this method returns, only
      the memory pointed to by :attr:`_p_oid` should remain allocated.



.. class:: PersistentList([iterable])

   A :class:`Persistent` version of the normal Python :class:`list`.  Its
   behavior should be identical except for being persistent.  (Note:
   currently slices are not supported.)



.. class:: PersistentDict([mapping_or_iterable], **kwarg)

   A :class:`Persistent` version of the normal Python :class:`dict`.  Its
   behavior should be identical except for being persistent.



.. class:: PersistentObject()

   Base class for user defined :class:`Persistent` objects.  May not
   be mixed with any other :class:`Persistent` type.

   As with a normal class, ``__init__`` is called when the object is
   initially created.  It is *not* called during object resurrection.


   .. method:: _v__init__()

   This method is called both when the object is initially created *and* when
   the object is resurrected.  It does nothing by default, but can be
   overridden to (re)acquire volatile resources.  It is called before
   ``__init__`` during object creation.
