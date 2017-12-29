:mod:`pmemobj` tutorial
===============================================================================

:mod:`pmem`, :mod:`pmemblk`, and :mod:`pmemlog` will be interesting to people
with specific needs that match the services provided by those libraries.  The
vast majority of Python programmers interested in utilizing persistent memory,
however, will be interested in :mod:`pmemobj`, which provides a Python-object
oriented interface to persistent memory.  This chapter aims to explain how to
use Python :mod:`pmemobj`, and how to write your own
:class:`~pmemobj.Persistent` objects.


Conceptual Overview
-------------------------------------------------------------------------------

In a normal Python program we create a bunch of objects and use them to
accomplish a goal.  When the program ends, all of the objects are thrown away,
to be rebuilt from scratch the next time the program is run.  :mod:`pmemobj`
provides the opportunity to change this paradigm: to be able to create objects
in a program, and have their state preserved between program runs, so that they
do not need to be reconstructed the next time the program is run.  The
guarantee made by :mod:`pmemobj` is that the state of the objects will be
self-consistent no matter when the program terminates.  Further, it provides a
:meth:`~pmemobj.PersistentObjectPool.transaction` that can be placed around
multiple persistent object modifications to guarantee that either *all* of the
modifications are made, or *none* of them are made.

Contrast this with a persistence paradigm such as that provided by `SQL Alchemy
<http://www.sqlalchemy.org/>`_.  Here we have objects whose data is mapped to
relational database tables.  When the program starts up, it can query the
database in any of several ways in order to retrieve objects.  The object state
is thus persistent in the sense that an object will have the same state it had
the last time that object was flushed to disk in a previous program.
SQLAlchemy also provides transactions that guarantee that either all of the
changes in a block are committed to the database, or none of them are.

So, how do the two paradigms differ?  At the higher conceptual levels, not by
much.  In the SQLAlchemy case objects are retrieved by running a query to find
selected instances of a given object class.  In :mod:`pmemobj` objects are
retrieved by walking an object tree from a
:attr:`~pmemobj.PersistentObjectPool.root` object defined by the program.  The
difference, for both better and worse, is that persistent memory is entirely an
"object store", and *not* a relational database.  It is thus more similar to
the `ZODB <http://www.zodb.org/en/latest/>`_ than to SQLAlchemy.

Where it differs from the ZODB is in how objects are stored.  In the ZODB
Python objects are serialized using the :mod:`pickle` module and stored on
disk.  In :mod:`pmemobj`, objects are stored directly in persistent memory,
written to and read from using the same *store* and *fetch* instructions used
to access RAM memory.  This means that in principle read access can be nearly
as fast as RAM access, and write access can be orders of magnitude more
efficient than disk writes.

In practice we're at the early stages of development, and at least in the
Python case we aren't anywhere near as fast as we could be.  But it's fast
enough to be useful.

To be a bit more concrete, consider the example of a Python list.  CPython
stores a list in RAM via an object header that points to an area of allocated
memory that holds a list of pointers to the objects in the list.  In
:mod:`pmemobj`, a list is stored in *persistent* memory as an object header
that points to an area of allocated *persistent* memory that contains a list of
*persistent* pointers to the objects in the list.  An access to a list element
is a normal ``addr+offset`` fetch of a pointer.  Pointer resolution is another
quick arithmetic operation.  Updating a list element is the reverse:
calculating the persistent pointer to the object and storing it at the correct
offset in the persistent data structure.  It is clear that this is going
to be more efficient than SQLAlchemy marshalling to SQL-DB-update to
disk-write to disk-flush, or ZODB-pickling to disk-write to disk-flush.

There is, however, overhead involved in the integrity guarantees.
``libpmemobj`` uses a change-log to record all changes that are taking place in
a transaction, and if the transaction is aborted or not marked as complete,
then all of the changes that did take place during the aborted transaction are
rolled back, either immediately in the case of an abort, or the next time the
persistent memory is accessed by ``libmemobj`` in the case of a crash.  This
log overhead has a non-zero cost, but what you buy with that cost is the object
and transactional integrity in the face of hard crashes.  And all of the log
and rollback activity takes place using direct memory *fetch* and *store*
instructions, so it is still fast, relatively speaking.

In this first version of :mod:`pmemobj` we have focused on proof of concept and
portability rather than efficiency.  That is, it is implemented entirely in
Python, using `CFFI <http://cffi.readthedocs.io/en/latest/>`_ to access the
``libpmemobj`` functions.  In addition, most immutable persistent objects are
handled by converting them back to normal Python RAM based instances when
accessed, rather than accessing them directly in persistent memory.  All of
this adds conceptually unnecessary overhead and results in execution times that
are slower than optimal.  There is no conceptual barrier, however, to making it
all quite efficient by moving the object access to the C level in a future
version.  The object algorithms are, for the most part, copied directly from
the CPython codebase, with a few modifications to deal with persistent pointers
and updating the rollback log.  So in principle the object implementations can
be almost as fast as the CPython objects they are emulating.


Real and Fake Persistent Memory
-------------------------------------------------------------------------------

"Real" persistent memory in the context of this library is physical
non-volatile memory that is accessible via the linux kernel `DAX
<https://nvdimm.wiki.kernel.org/>`_ extensions.  Persistent memory thus
configured appears as a mounted filesystem to Linux.  An allocated area of
persistent memory is labeled by a filename according to normal unix rules.
Thus if your DAX memory is mounted at /mnt/persistent, your would refer to an
allocated area of memory named ``myprog.pmem`` via the path:

    /mnt/persistent/myprog.pmem

The persistent file system is a normal unix filesystem when viewed through the
file system drivers.  The magic of DAX, however, is that it allows a program to
bypass the file system drivers and have direct, unbuffered access to the memory
using normal CPU *fetch* and *store* instructions.  There are, of course,
concerns with respect to CPU caches and when exactly a change gets committed to
the physical memory.  See the :mod:`pmem` module for more details.
:mod:`pmemobj` handles all of those details so your program doesn't have to.

There are two sorts of "fake" persistent memory.  One is discussed on the
`Persistent Memory Wiki <https://nvdimm.wiki.kernel.org/>`_ referenced above:
you can emulate real persistent memory using regular RAM by reserving RAM to
accessed through DAX via kernel configuration.

The second sort of "fake" persistent memory is to simply ``mmap`` a normal
file.  In this case the pmem libraries use different calls to ensure changes
are flushed to disk, but the remainder of the pmem programming infrastructure
can be tested.  All of the pmem libraries automatically use this mode when the
specified path is not a DAX-backed path.

So, anywhere in the following examples where a filename is used, you can
substitute a path that will access the fake or real persistent memory as you
choose, and the examples should all work the same.  (Except for losing the
persistent data on machine reboot, if you are using RAM emulation.)


Object Types and Persistence
-------------------------------------------------------------------------------

For the purposes of considering persistence, we can divide Python objects up
into three classes: immutable non-container objects, mutable non-container
objects, and container objects.

Immutable non-container objects are the easiest to handle.  We can store them
in whatever form we want in persistent memory, and upon access we can
reconstruct the equivalent Python object and let the program use that.  Because
the object is immutable, it doesn't matter that the object in persistent memory
and object in use aren't the same object.  (Or if it does, that's a bug in your
program, since Python makes no guarantees about the identity of immutable
objects.)

Mutable non-container objects *must* directly store, update, and retrieve
their data from persistent memory, since everything that points to
that mutable object will expect to see any updates.  (An example of a
mutable non-container object is a :class:`bytearray`.  :mod:`pmemobj`
does not yet support any of Python's mutable non-container types.)

Container objects may contain pointers to other objects.  The rule in
:mod:`pmemobj` is that every object pointed to by a persistent container must
itself be stored persistently.  This means that all pointers inside persistent
objects are persistent pointers; that is, pointers that can be resolved into a
valid pointer if the program is shut down and restarted running in a different
memory location.  Therefore we can't map a persistent immutable container
object (such as a tuple) to its Python equivalent, because the stored pointers
are persistent pointers, and may not even have the same length as a normal RAM
pointer.

Mostly these distinctions matter only to someone implementing a new
:class:`persistent` type.  However, the first category, the immutable
non-container objects, matter at the Python programming level.  This is because
there are two possibilities for such objects: :mod:`pmemobj` may support them
directly, or it may support them through :class:`pickle`.  If a class is
supported directly, a :class:`Pesistent` container may reference them and
:mod:`pmemobj` will automatically deal with storing their data persistently,
and accessing it when referenced.  If a class is not supported directly, then a
program using :mod:`pmemobj` can still reference them, if the program nominates
them for persistence via pickling.  This is less efficient than direct support,
but allows programs to use data types for which support has not yet been
written.  (Pickling is not applied automatically because there is no way for
:mod:`pmemobj` to determine if a specific class is immutable or not.)


Hello <your_name_here>
-------------------------------------------------------------------------------

We'll start the tutorial proper with the traditional "Hello, World" program.
To make it interesting from a persistence standpoint, we'll skip past the
static "Hello, world!" to the second part of the traditional example, where you
make it say hello to a specified name, and we'll make it remember the name from
one call to the next:

.. literalinclude:: examples/hello_you.py

This simple example demonstrates several things.  Persistent memory is accessed
through a :class:`PesistentObjectPool` object.  By passing ``flag='c'`` to the
constructor, we tell :mod:`pmemobj` to create the pool if it doesn't exist
yet, and to open it if it does.  It creates the pool with a fairly generous
size, but a real application might need to increase the allocated size
depending on how much data it is handling.

Note that a pool's size is fixed once created.  There are plans for future
improvements that will either provide a way to resize a pool or, at a minimum,
a way to dump the data from one pool and restore it into another.  Neither of
these facilities exist as of this writing.

The pool object returned by the constructor has several methods and one
attribute.  That attribute, :attr:`~pmemobj.PersistentObjectPool.root`, names
an arbitrary persistent object, and its default value is ``None``.  When a pool
is first created, then, ``root`` is ``None``.  Our program checks if
``root`` is ``None``, and if it is, sets about getting a value (the name to
use).  It assigns that to the ``root`` attribute, which is enough to cause that
object to be persisted.  It then prints out the "Hello" greeting.

If ``root`` is not ``None``, then it has a value, so we use that value to print
out the greeting.

If we name this script ``hello.py``, running it from the command line would
look like this::

    > python hello.py
    What is your name? David
    Hello, David
    > python hello.py
    Hello, David
    > python hello.py
    Hello, David


Guessing Game
-------------------------------------------------------------------------------

Another frequent example of a simple program is a guessing game.  It might
looks something like this:

.. literalinclude:: examples/normal_guess.py

A playing session might look like this::

    Hello, what is your name? David
    David, I've picked a number between 1 and 50.
    Take a guess.
    > 25
    Your guess is too low.
    Take a guess.
    > 40
    Your guess is too low.
    Take a guess.
    > 45
    Your guess is too low.
    Take a guess.
    > 48
    You guessed my number in 4 tries, David.

The magic of persistence is that everything is remembered between program runs.
So lets rewrite this so instead of a loop, we're using commands typed at the
shell prompt to play the game.

First, we need a command to start the game:

.. literalinclude:: examples/start_guessing

This introduces several new concepts.  The :func:`~pmemobj.create`
function raises an error if the persistent memory file already exists.
This is equivalent to specifying ``flag='x'`` in the
:class:`~pmemobj.PersistentObjectPool` constructor.  This command is
only dealing with creating the pool, so it doesn't have an if test
to see if root is ``None``, it can just go ahead and do the setup.

However, we want the setup to either work or fail completely, so we use the
pool's :func:`~pmemobj.PersistentObjectPool.transaction` context manager to
wrap all of our initialization in a transaction.

The first thing we do is create a namespace to hold our persistent program
data.  We use a dictionary for this, but we can't persist a normal Python dict.
Instead we use the :class:`pmemobj.PersistentDict`.  To create one, we use the
:func:`~pmemobj.PersistentObjectPool.new` method of the pool.  The ``new``
method requires a class object that supports the :class:`~pmemobj.Persistent`
interface, and given one it creates an instance of the object that will store
its data in the pool.  We could also pass constructor arguments after the class
name.  :class:`~pmemobj.PersistentDict` accepts the same constructor arguments
as a normal dict.

Note that in addition to giving the :class:`~pmemobj.PersistentDict` a local
name, we also assign it to the :attr:`~pmemobj.PersistentObjectPool.root`
attribute of the pool.  If we failed to do that, :mod:`pmemobj` would forget
about the object once the pool was closed, since nothing would be referring to
it.  That is, when the pool is closed, :mod:`pmemobj` looks through all the
objects in the pool, and any that cannot be reached from
:attr:`~pmemobj.PersistentObjectPool.root` are garbage collected.

Once we have our namespace, we store the player's name, and the number we want
them to guess, and create an empty :class:`~pmemobj.PersistentList` in which to
store the guesses.

Then we tell the player what to do next, and we're ready to play.

We've told the player to type ``guess <their_guess>`` at the command line,
so now we need to implement the ``guess`` command:

.. literalinclude:: examples/guess

Here we've used :func:`~pynvm.open` to get access to the existing pool.  It
will throw an error if the pool does *not* exist.  This is equivalent to
passing ``flag='r'`` to the constructor.

We do need to check :attr:`~pynvm.PersistentObjectPool.root` to see if it is
``None`` here, since it could be if the initialization did not complete.  In
that case we just delete the pool and tell the player to start over from the
beginning.

Notice how we can use a local name for the ``guess`` list, and append to it,
and the list is updated persistently.  This is because each
:class:`~pynvm.Persistent` class knows which pool it belongs to, so it can find
the persistent memory it needs to update.

The other thing to notice about this example is that we haven't used an
explicit transaction anywhere.  We only do one data structure update, and
that's the append of the new guess to the list.  That append is guaranteed to
be atomic, so there is no need for an explicit transaction in this case.

With our persistent version of the guessing game, running the game
looks like this::

    > start_guessing
    Hello, what is your name?  David
    David, I've picked a number between 1 and 50.
    Type 'guess' followed by your guess at the prompt.
    > guess 25
    Your guess is too low.
    > guess 35
    Your guess is too low.
    > guess 45
    Your guess is too high.
    > guess 40
    Your guess is too high.
    > guess 38
    Your guess is too high.
    > guess 37
    Your guess is too high.
    > guess 36
    You guessed my number in 7 tries, David.

Now, this code is somewhat more complicated than the non-persistent version,
but it would allow you to start a game one day, and come back days later and
finish the game.  We could add a 'status' command that let you know now many
guesses you'd made, and even replay the guesses.  While this is a trivial
example, I think you can see how these principles would apply to more useful
programs with retained state.


Persistent Objects
-------------------------------------------------------------------------------

Python is an object oriented language, so we of course would like to be able to
persist arbitrary objects.  We can't do that in the general case, since
anything that has a specific memory layout requires specific support in
:mod:`pmemobj`.  However, Python objects that do not subclass built-in types
are, from the point of view of persistent memory, just a dictionary wrapped in
some extra behavior.  So :mod:`pmemobj` does support persisting arbitrary
objects that do not subclass built-ins, via the
:class:`~pmemobj.PersistentObject` base class.

Our ``guess`` code above has to awkwardly pull the data of interest out of the
dictionary that we used as a namespace.  It would provide simpler code if we
can instead have that data be attributes on an object.  To do that, we'll need
to be able to access that object from both programs, so we'll want a separate
python file to hold our class definition:

.. literalinclude:: examples/guess_lib.py

The first thing to notice about the :class:`~pmemobj.PersistentObject` subclass
is that for the most part it doesn't look any different from a normal Python
class.  There is an ``__init__`` that is executed when the object is first
created, and most attributes are referenced and set normally.  The one
exception is our ``self.guesses`` attribute.  We want that to be a list.  Since
it is not a non-container immutable, it needs to be a
:class:`~pmemobj.Persistent` object itself.

To accomplish this we make use of the :attr:`~pmemobj.Persistent._p_mm`
attribute of our :class:`~pmemobj.PersistentObject` instance.  This attribute
points to the :class:`~pmemobj.MemoryManager` instance associated with the
:class:`~pmemobj.PersistentObject`.  We can use that reference to access the
``MemoryManager's`` :meth:`~pmemobj.MemoryManager.new` method, and use that
method to create an empty :class:`~pmemobj.PersistentList` that is associated
with the same ``Memorymanager`` managing our ``PersistentObject``.

We can also use the :attr:`~pmemobj.Persistent._p_mm` attribute to access the
``MemoryManager's`` :meth:`~pmemobj.MemoryManager.transaction` context manager,
as you can see in the ``check_guess`` method of the example.  Unlike our
previous example, in this code block we are making several updates to our class
that should either all be done, or none of them done.  By using the
transaction, we ensure that either the guess is completely processed, or it is
not processed at all, no matter when the program gets interrupted.

With the game logic now factored out into a class, our command scripts are much
simpler.

``start_guessing`` becomes:

.. literalinclude:: examples/start_guessing2

To start the game, we check there's no existing game file and create
it, but now initializing the data structures in the pool consists of just
calling :meth:`~pmemobj.PersistentObjectPool.new` on our ``guesser`` class and
assigning that to :attr:`~pmemobj.PersistemtObjectPool.root`.

The ``guess`` command is now almost trivial:

.. literalinclude:: examples/guess2

We use our library function to reopen the pool, which checks for the various
error conditions and aborts with the appropriate message if we run into any of
them.  Then we grab the ``guesser`` instance from the pool's
:attr:`~pmemobj.PersistemtObjectPool.root` and pass the guess the player made
its ``check_guess`` method to evaluate, printing the message associated with
whatever guess status it returns, removing the game file if and only if the
game is over:

And now we can easily implement the ``game_status`` command mentioned earlier:

.. literalinclude:: examples/guess_status2

The pattern here is one I expect many persistent memory applications will share
(possibly via a single program with subcommands or sub-functions, rather than
the multiple program files in this example):  the persistent memory is accessed
through an instance of an application specific class that is assigned to the
:attr:`~pmemobj.PersistemtObjectPool.root` of the object pool.  When run, the
application makes sure it can access the pool, then grabs the instance from
:attr:`~pmemobj.PersistemtObjectPool.root` and uses the instance's methods to
accomplish the application's goals.
