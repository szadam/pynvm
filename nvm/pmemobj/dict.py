import collections
import hashlib
import logging
import sys

from .compat import recursive_repr, abc

from _pmem import ffi

log = logging.getLogger('nvm.pmemobj.dict')

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

# Python3's hash function is not guaranteed to produce the same results
# between versions or across platforms, so we need a stable hash of our own.
# XXX This is a prime candidate for being recoded in C, hopefully avoiding
# the string conversion step somehow.
def is_hashable(s):
    return hasattr(s, "__len__") == False or len(s) > 0

def fixed_hash(s):
    if not is_hashable(s):
        raise TypeError("Key is not hashable")
    s = str(s)
    if sys.version_info[0] > 2:
        s = s.encode()
    digits = hashlib.md5(s).hexdigest()
    return int(digits[:16], 16) ^ int(digits[16:], 16)

def _usable_fraction(n):
    return (2*n+1)//3

class PersistentDict(abc.MutableMapping):
    """Persistent version of the 'dict' type."""

    # XXX locking

    def __init__(self, *args, **kw):
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

    def _p_new(self, manager):
        mm = self._p_mm = manager
        with mm.transaction():
            # XXX will want to implement a freelist here.
            self._p_oid = mm.zalloc(ffi.sizeof('PDictObject'))
            ob = ffi.cast('PObject *', mm.direct(self._p_oid))
            ob.ob_type = mm._get_type_code(PersistentDict)
            d = self._body = ffi.cast('PDictObject *', mm.direct(self._p_oid))
            # This code may get moved to a _new_dict method when we implement
            # split dicts.
            d.ma_keys = self._new_keys_object(MIN_SIZE_COMBINED)
            d.ma_values = mm.OID_NULL

    def _p_resurrect(self, manager, oid):
        mm = self._p_mm = manager
        self._p_oid = oid
        self._body = ffi.cast('PDictObject *', mm.direct(oid))

    # Methods and properties needed to implement the ABC required methods.

    @property
    def _keys(self):
        mm = self._p_mm
        keys_oid = mm.otuple(self._body.ma_keys)
        return ffi.cast('PDictKeysObject *', mm.direct(keys_oid))

    def _growth_rate(self):
        return self._body.ma_used*2 + (self._keys.dk_size >> 1)

    def _new_keys_object(self, size):
        assert size >= MIN_SIZE_SPLIT
        mm = self._p_mm
        with mm.transaction():
            dk_oid = mm.zalloc(ffi.sizeof('PDictKeysObject')
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
        mm = self._p_mm
        dk = ffi.cast('PDictKeysObject *', mm.direct(oid))
        ep = ffi.cast('PDictKeyEntry *', ffi.addressof(dk.dk_entries[0]))
        with mm.transaction():
            for i in range(dk.dk_size):
                mm.xdecref(ep[i].me_key)
                mm.xdecref(ep[i].me_value)
            mm.free(oid)

    def _lookdict(self, key, khash):
        # Generalized key lookup method.
        mm = self._p_mm
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
        mm = self._p_mm
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

    def _insertion_resize(self):
        # This is modeled on CPython's insertion_resize/dictresize, but
        # assuming we always have a combined dict.  We copy the keys and values
        # into a new dict structure and free the old one.  We don't touch the
        # refcounts.
        mm = self._p_mm
        minused = self._growth_rate()
        newsize = MIN_SIZE_COMBINED
        while newsize <= minused and newsize > 0:
            newsize = newsize << 1
        oldkeys = self._keys
        oldkeys_oid = mm.otuple(self._body.ma_keys)
        with mm.transaction():
            mm.snapshot_range(ffi.addressof(self._body, 'ma_keys'),
                              ffi.sizeof('PObjPtr'))
            self._body.ma_keys = self._new_keys_object(newsize)
            oldsize = oldkeys.dk_size
            old_ep0 = ffi.cast('PDictKeyEntry *',
                               ffi.addressof(oldkeys.dk_entries[0]))
            for i in range(oldsize):
                old_ep = old_ep0[i]
                me_value = mm.otuple(old_ep.me_value)
                if me_value != mm.OID_NULL:
                    me_key = mm.otuple(old_ep.me_key)
                    assert me_key != DUMMY
                    me_hash = old_ep.me_hash
                    new_ep = self._find_empty_slot(me_key, me_hash)
                    new_ep.me_key = me_key
                    new_ep.me_hash = me_hash
                    new_ep.me_value = me_value
            self._keys.dk_usable -= self._body.ma_used
            mm.free(oldkeys_oid)

    def _dumpdict(self):
        # This is for debugging.
        mm = self._p_mm
        keys = self._keys
        ep0 = ffi.cast('PDictKeyEntry *', ffi.addressof(keys.dk_entries[0]))
        log.debug('size: %s', keys.dk_size)
        for i in range(keys.dk_size):
            ep = ep0[i]
            log.debug('hash: %s, key oid: %s, value oid: %s',
                    ep.me_hash, mm.otuple(ep.me_key), mm.otuple(ep.me_value))

    def __len__(self):
        return self._body.ma_used

    def __setitem__(self, key, value):
        # This is modeled on CPython's insertdict.
        khash = fixed_hash(key)
        mm = self._p_mm
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
                assert keys.dk_usable >= 0, "dk_usable is %s" % keys.dk_usable
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
        mm = self._p_mm
        khash = fixed_hash(key)
        ep = self._lookdict(key, khash)
        if ep is None or mm.otuple(ep.me_value) == mm.OID_NULL:
            raise KeyError(key)
        mm = self._p_mm
        return self._p_mm.resurrect(ep.me_value)

    def __delitem__(self, key):
        mm = self._p_mm
        khash = fixed_hash(key)
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
        mm = self._p_mm
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

    def _p_traverse(self):
        mm = self._p_mm
        keys = self._keys
        ep0 = ffi.cast('PDictKeyEntry *', ffi.addressof(keys.dk_entries[0]))
        for i in range(keys.dk_size):
            ep = ep0[i]
            if (ep.me_hash == ffi.NULL
                    or mm.otuple(ep.me_key) in (mm.OID_NULL, DUMMY)):
                continue
            yield mm.otuple(ep.me_key)
            yield mm.otuple(ep.me_value)

    def _p_substructures(self):
        return ((self._p_mm.otuple(self._body.ma_keys),
                 PDICTKEYSOBJECT_TYPE_NUM),
               )

    def _p_deallocate(self):
        self.clear()
        self._p_mm.free(self._body.ma_keys)
