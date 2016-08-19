import collections

from .compat import recursive_repr, abc

from _pmem import ffi

# XXX CPython has a dictionary structure that has an optimization for a common
# Python case: multiple instances of a class, where each instance has the same
# unicode *keys* in its attribute dictionary, but may have different values.
# This is called a "split key dictionary".  In this module I'm following the
# data structure layout that CPython uses that caters to this split dictionary
# case, but I'm only implementing the "combined" dictionary case at the present
# time.  I'm using the CPython layout, even though it is a bit more complex
# than needed for a combined dictionary, to make it easier to come back later
# when I add support for arbitrary Persistent subclasses, and implement the
# split dictionary case if desired.  It also makes it easier to port the
# CPython code.
MIN_SIZE_SPLIT = 4

# This constant is taken from CPython 3.6.  Since our dictionaries are *not*
# used principally for keyword argument passing the way CPython's are, a
# different constant may be appropriate.
MIN_SIZE_COMBINED = 8

# This is a well tested constant and should be correct for us as well.
PERTURB_SHIFT = 5

# These will never be real OIDs, so we can use them as flag entries in an OID
# field.  Even if another module uses the same value it shouldn't be a problem,
# since the value should never leak outside the module that uses it.
# XXX need to make None, True, and False similar constants, and figure
# how to manage the numbers so we don't risk collisions.  Oh, and they
# need to come out of mm, which should help solve the management problem.
DUMMY = (0, 10)

# Arbitrary number.  XXX find a way to make sure we don't duplicate these.
PDICTKEYSOBJECT_TYPE_NUM = 40

def _usable_fraction(n):
    return (2*n+1)//3

class PersistentDict(abc.MutableMapping):
    """Persistent version of 'dict' type."""

    # XXX locking

    def __init__(self, *args, **kw):
        if '__manager__' not in kw:
            raise ValueError('__manager__ is required')
        # XXX __manager__ could be a legit key...need a method to set
        # __manager__ instead, which will then finish the __init__.
        mm = self.__manager__ = kw.pop('__manager__')
        if '_oid' not in kw:
            with mm.transaction():
                # XXX will want to implement a freelist here.
                self._oid = mm.malloc(ffi.sizeof('PDictObject'))
                ob = ffi.cast('PObject *', mm.direct(self._oid))
                ob.ob_type = mm._get_type_code(PersistentDict)
                d = self._body = ffi.cast('PDictObject *', mm.direct(self._oid))
                # XXX size here could be based on args.  Also, this code may get
                # moved to a _new_dict method when we implement split dicts.
                d.ma_keys = self._new_keys_object(MIN_SIZE_COMBINED)
                d.ma_values = mm.OID_NULL
                d.ma_used = 0
                if len(args) > 1:
                    raise TypeError("PersistentDict expected at most 1"
                                    "argument, got {}", len(args))
                if args:
                    arg = args[0]
                    if hasattr(arg, 'items'):
                        arg = arg.items()
                    for key, value in arg:
                        self[key] = value
                if kw:
                    for key, value in kw.items():
                        self[key] = value
        else:
            self._oid = kw.pop('_oid')
            if args or kw:
                raise TypeError("Only __manager__ and _oid arguments are valid",
                                " for resurrection, not {}".format((args, kw)))
            self._body = ffi.cast('PDictObject *', mm.direct(self._oid))

    # Methods and properties needed to implement the ABC required methods.

    @property
    def _keys(self):
        mm = self.__manager__
        keys_oid = mm.otuple(self._body.ma_keys)
        return ffi.cast('PDictKeysObject *', mm.direct(keys_oid))

    def _growth_rate(self):
        self._body.ma_used * 2 + self._ma_keys.dk_size / 2

    def _new_keys_object(self, size):
        assert size >= MIN_SIZE_SPLIT
        mm = self.__manager__
        with mm.transaction():
            dk_oid = mm.malloc(ffi.sizeof('PDictKeysObject')
                               + ffi.sizeof('PDictKeyEntry') * (size - 1),
                               type_num=PDICTKEYSOBJECT_TYPE_NUM)
            dk = ffi.cast('PDictKeysObject *', mm.direct(dk_oid))
            dk.dk_refcnt = 1
            dk.dk_size = size
            dk.dk_usable = _usable_fraction(size)
            ep = ffi.cast('PDictKeyEntry *', ffi.addressof(dk.dk_entries[0]))
            # Hash value of slot 0 is used by popitem, so it must be initizlied
            ep[0].me_hash = 0
            for i in range(size):
                ep[i].me_key = mm.OID_NULL
                ep[i].me_value = mm.OID_NULL
            # XXX Set dk_lookup to lookdict_unicode_nodummy if we end up using it.
        return dk_oid

    def _free_keys_object(self, oid):
        mm = self.__manager__
        dk = ffi.cast('PDictKeysObject *', mm.direct(oid))
        ep = ffi.cast('PDictKeyEntry *', ffi.addressof(dk.dk_entries[0]))
        with mm.transaction():
            for i in range(dk.dk_size):
                mm.xdecref(ep[i].me_key)
                mm.xdecref(ep[i].me_value)
            mm.free(oid)

    def _lookdict(self, key, khash):
        # Generalized key lookup method.
        mm = self.__manager__
        while True:
            keys_oid = mm.otuple(self._body.ma_keys)
            keys = ffi.cast('PDictKeysObject *', mm.direct(keys_oid))
            mask = keys.dk_size - 1
            ep0 = ffi.cast('PDictKeyEntry *', ffi.addressof(keys.dk_entries[0]))
            i = khash & mask
            ep = ffi.addressof(ep0[i])
            me_key = mm.otuple(ep.me_key)
            if me_key == mm.OID_NULL:
                return ep
            if me_key == DUMMY:
                freeslot = ep
            else:
                if ep.me_hash == khash:
                    match = mm.resurrect(me_key) == key  # dict could mutate
                    if (mm.otuple(self._body.ma_keys) == keys_oid
                            and mm.otuple(ep.me_key) == me_key):
                        if match:
                            return ep
                    else:
                        continue  # mutatation, start over from the top.
                freeslot = None
            perturb = khash
            while True:
                i = (i << 2) + i + perturb + 1
                ep = ep0[i & mask]
                me_key = mm.otuple(ep.me_key)
                if me_key == mm.OID_NULL:
                    return ep if freeslot is None else freeslot
                if ep.me_hash == khash and me_key != DUMMY:
                    match = mm.resurrect(me_key) == key  # dict could mutate
                    if (mm.otuple(self._body.ma_keys) == keys_oid
                            and mm.otuple(ep.me_key) == me_key):
                        if match:
                            return ep
                    else:
                        break  # mutation, start over from the top.
                elif me_key == DUMMY and freeslot is None:
                    freeslot = ep
                perturb = perturb >> PERTURB_SHIFT
                # We will eventually visit every key slot in the dict, once
                # perturb goes to zero, so we will eventually do a return.

    def _find_empty_slot(self, key, khash):
        # Find slot from hash when key is not in dict.
        mm = self.__manager__
        keys = self._keys
        mask = keys.dk_size - 1
        ep0 = ffi.cast('PDictKeyEntry *', ffi.addressof(keys.dk_entries[0]))
        i = khash & mask
        ep = ffi.addressof(ep0[i])
        perturb = khash
        while mm.otuple(ep.me_key) != mm.OID_NULL:
            i = (i << 2) + i + perturb + 1
            ep = ep0[i & mask]
            perturb = perturb >> PERTURB_SHIFT
        assert mm.otuple(ep.me_key) == mm.OID_NULL
        return ep

    def __dumpdict(self):
        # This is for debugging.
        mm = self.__manager__
        keys = self._keys
        ep0 = ffi.cast('PDictKeyEntry *', ffi.addressof(keys.dk_entries[0]))
        print('size: ', keys.dk_size)
        for i in range(keys.dk_size):
            ep = ep0[i]
            print('hash: %s, key oid: %s, value oid: %s' % (
                    ep.me_hash, mm.otuple(ep.me_key), mm.otuple(ep.me_value)))

    def __len__(self):
        return self._body.ma_used

    def __setitem__(self, key, value):
        khash = hash(key)
        mm = self.__manager__
        keys = self._keys
        ep = self._lookdict(key, khash)
        with mm.transaction():
            v_oid = mm.persist(value)
            old_v_oid = mm.otuple(ep.me_value)
            me_key = mm.otuple(ep.me_key)
            if old_v_oid != mm.OID_NULL:
                assert me_key not in (mm.OID_NULL, DUMMY)
                ep.me_value = v_oid
                mm.incref(v_oid)
                mm.decref(old_v_oid)
                return
            k_oid = mm.persist(key)
            if me_key == mm.OID_NULL:
                if keys.dk_usable <= 0:
                    self._insertion_resize()
                    keys = self._keys
                ep = self._find_empty_slot(key, khash)
                keys.dk_usable -= 1
                assert keys.dk_usable >= 0
                ep.me_key = k_oid
                mm.incref(k_oid)
                ep.me_hash = khash
            else:
                if me_key == DUMMY:
                    ep.me_key = k_oid
                    mm.incref(k_oid)
                    ep.me_hash = khash
                else:
                    raise NotImplementedError("CPython algo thinks this should"
                                              " be a split dict at this point")
            self._body.ma_used += 1
            ep.me_value = v_oid
            mm.incref(v_oid)
            assert mm.otuple(ep.me_key) not in (mm.OID_NULL, DUMMY)

    def __getitem__(self, key):
        mm = self.__manager__
        khash = hash(key)
        ep = self._lookdict(key, khash)
        if ep is None or mm.otuple(ep.me_value) == mm.OID_NULL:
            raise KeyError(key)
        mm = self.__manager__
        return self.__manager__.resurrect(ep.me_value)

    def __delitem__(self, key):
        mm = self.__manager__
        khash = hash(key)
        ep = self._lookdict(key, khash)
        if ep is None or mm.otuple(ep.me_value) == mm.OID_NULL:
            raise KeyError(key)
        with mm.transaction():
            old_value_oid = mm.otuple(ep.me_value)
            ep.me_value = mm.OID_NULL
            self._body.ma_used -= 1
            old_key_oid = mm.otuple(ep.me_key)
            ep.me_key = DUMMY
            mm.decref(old_value_oid)
            mm.decref(old_key_oid)

    def __iter__(self):
        mm = self.__manager__
        keys = self._keys
        ep0 = ffi.cast('PDictKeyEntry *', ffi.addressof(keys.dk_entries[0]))
        for i in range(keys.dk_size):
            ep = ep0[i]
            if (ep.me_hash == ffi.NULL
                    or mm.otuple(ep.me_key) in (mm.OID_NULL, DUMMY)):
                continue
            yield mm.resurrect(ep.me_key)

    # Additional dict methods not provided by the ABC.

    @recursive_repr()
    def __repr__(self):
        return "{}({{{}}})".format(self.__class__.__name__,
                                   ', '.join("{!r}: {!r}".format(k, v)
                                             for k, v in self.items()))

    # Additional methods required by the pmemobj API.

    def _traverse(self):
        mm = self.__manager__
        keys = self._keys
        ep0 = ffi.cast('PDictKeyEntry *', ffi.addressof(keys.dk_entries[0]))
        for i in range(keys.dk_size):
            ep = ep0[i]
            if (ep.me_hash == ffi.NULL
                    or mm.otuple(ep.me_key) in (mm.OID_NULL, DUMMY)):
                continue
            yield mm.otuple(ep.me_key)
            yield mm.otuple(ep.me_value)

    def _substructures(self):
        return ((self.__manager__.otuple(self._body.ma_keys),
                 PDICTKEYSOBJECT_TYPE_NUM),
               )

    def _deallocate(self):
        self.clear()
        self.__manager__.free(self._body.ma_keys)
