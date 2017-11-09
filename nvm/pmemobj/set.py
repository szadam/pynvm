import collections
import sys

from .compat import recursive_repr, abc
from _pmem import ffi
from .dict import fixed_hash

PERM_SET_MINSIZE = 64

HASH_DUMMY = ffi.cast('uint64_t', -1)
HASH_UNUSED = 0
HASH_INVALID = HASH_DUMMY

ADD_RESULT_RESTART = 0
ADD_RESULT_FOUND_UNUSED = 1
ADD_RESULT_FOUND_DUMMY = 2
ADD_RESULT_FOUND_ACTIVE = 3

LINEAR_PROBES = 9
PERTURB_SHIFT = 5

SET_POBJPTR_ARRAY_TYPE_NUM = 60


class PersistentSet(abc.MutableSet):

    """Persistent version of the 'Set' type."""
    def __init__(self, *args, **kw):
        if not args:
            return
        if len(args) != 1:
            raise TypeError("PersistentSet takes at most 1"
                            " argument, {} given".format(len(args)))
        for item in args[0]:
            self._add(item)

    def _alloc_empty_table(self, tablesize):
        return self._p_mm.zalloc(ffi.sizeof('PSetEntry') * tablesize,
                                 type_num=SET_POBJPTR_ARRAY_TYPE_NUM)

    def _p_new(self, manager):
        mm = self._p_mm = manager
        with mm.transaction():
            self._p_oid = mm.zalloc(ffi.sizeof('PSetObject'))
            ob = ffi.cast('PObject *', mm.direct(self._p_oid))
            ob.ob_type = mm._get_type_code(self.__class__)
            size = PERM_SET_MINSIZE
            self._body = ffi.cast('PSetObject *', mm.direct(self._p_oid))
            self._body.mask = (size - 1)
            self._body.hash = HASH_INVALID
            self._body.table = self._alloc_empty_table(PERM_SET_MINSIZE)

    """ Derived from set_insert_clean in setobject.c """
    def _insert_clean(self, table, mask, key_oid, khash):
        mm = self._p_mm
        perturb = khash
        i = khash & mask
        table_data = ffi.cast('PSetEntry *', mm.direct(table))
        found_index = -1

        while True:
            if table_data[i].hash == HASH_UNUSED:
                found_index = i
                break

            for j in range(i + 1, min(i + LINEAR_PROBES, mask) + 1):
                if table_data[j].hash == HASH_UNUSED:
                    found_index = j
                    break

            if found_index != -1:
                break

            perturb >>= PERTURB_SHIFT
            i = (i * 5 + 1 + perturb) & mask

        with mm.transaction():
            mm.snapshot_range(ffi.addressof(table_data, found_index),
                              ffi.sizeof('PSetEntry'))
            table_data[found_index].hash = khash
            table_data[found_index].key = key_oid

    @classmethod
    def _make_new_set(cls, manager, iterable):
        return manager.new(cls, iterable)

    """ Derived from set_table_resize in setobject.c. """
    def _table_resize(self, minused):
        mm = self._p_mm

        if minused > 50000:
            minused = (minused << 1)
        else:
            minused = (minused << 2)

        newsize = PERM_SET_MINSIZE

        while(newsize <= minused):
            newsize = (newsize << 1)

        newsize = ffi.cast('size_t', newsize)

        if newsize == 0:
            raise MemoryError("Out of memory")

        newsize = int(newsize)

        with mm.transaction():
            oldtable = mm.otuple(self._body.table)
            oldtable_data = ffi.cast('PSetEntry *', mm.direct(oldtable))
            newtable = self._alloc_empty_table(newsize)

            newmask = newsize - 1

            for i in range(0, self._body.mask + 1):
                if oldtable_data[i].hash == HASH_UNUSED or \
                   oldtable_data[i].hash == HASH_DUMMY:
                    continue
                self._insert_clean(newtable, newmask,
                                   oldtable_data[i].key,
                                   oldtable_data[i].hash)

            mm.snapshot_range(ffi.addressof(self._body, 'fill'),
                              ffi.sizeof('PSetObject') - ffi.sizeof('PObject'))

            self._body.mask = newmask
            self._body.fill = self._body.used
            self._body.table = newtable

            mm.free(oldtable)

    """ Derived from set_add_entry in setobject.c """
    def _get_available_entry_slot(self, key, khash):
        mm = self._p_mm
        mask = self._body.mask
        i = khash & mask
        table_data = ffi.cast('PSetEntry *', mm.direct(self._body.table))

        entry = table_data[i]
        if entry.hash == HASH_UNUSED:
            return i, ADD_RESULT_FOUND_UNUSED

        perturb = khash
        freeslot = -1

        while True:
            if entry.hash == khash:
                startkey = self._p_mm.resurrect(entry.key)
                if startkey == key:
                    return i, ADD_RESULT_FOUND_ACTIVE

                """ TODO: find a test for this unlikely behaviour """
                crtkey = self._p_mm.resurrect(entry.key)
                crttable = ffi.cast('PSetEntry *', mm.direct(self._body.table))
                if crtkey is not startkey or crttable is not table_data:
                    return -1, ADD_RESULT_RESTART

            elif entry.hash == HASH_DUMMY and freeslot == -1:
                freeslot = i

            for j in range(i + 1, min(i + LINEAR_PROBES, mask) + 1):
                entry = table_data[j]
                if entry.hash == HASH_UNUSED:
                    if freeslot == -1:
                        return j, ADD_RESULT_FOUND_UNUSED
                    return freeslot, ADD_RESULT_FOUND_DUMMY

                if entry.hash == khash:
                    startkey = self._p_mm.resurrect(entry.key)
                    if startkey == key:
                        return j, ADD_RESULT_FOUND_ACTIVE

                    """ TODO: find a test for this unlikely behaviour """
                    crtkey = self._p_mm.resurrect(entry.key)
                    crttable = ffi.cast('PSetEntry *',
                                        mm.direct(self._body.table))
                    if crtkey is not startkey or crttable is not table_data:
                        return -1, ADD_RESULT_RESTART

                elif entry.hash == HASH_DUMMY and freeslot == -1:
                    freeslot = j

            perturb >>= PERTURB_SHIFT
            i = (i * 5 + 1 + perturb) & mask
            entry = table_data[i]

            if entry.hash == HASH_UNUSED:
                if freeslot == -1:
                    return i, ADD_RESULT_FOUND_UNUSED
                return freeslot, ADD_RESULT_FOUND_DUMMY

    def _add(self, key):
        mm = self._p_mm
        khash = fixed_hash(key)
        result = ADD_RESULT_RESTART
        with mm.transaction():
            while result == ADD_RESULT_RESTART:
                index, result = self._get_available_entry_slot(key, khash)
            if result == ADD_RESULT_FOUND_UNUSED or \
               result == ADD_RESULT_FOUND_DUMMY:
                table_data = ffi.cast('PSetEntry *',
                                      mm.direct(self._body.table))
                mm.snapshot_range(ffi.addressof(table_data, index),
                                  ffi.sizeof('PSetEntry'))
                oid = mm.persist(key)
                mm.incref(oid)
                p_obj = ffi.cast('PObject *', mm.direct(oid))
                table_data[index].key = oid
                table_data[index].hash = khash
                mm.snapshot_range(
                    ffi.addressof(self._body, 'fill'),
                    ffi.sizeof('PSetObject') - ffi.sizeof('PObject'))
                self._body.used += 1

                if result == ADD_RESULT_FOUND_UNUSED:
                    self._body.fill += 1
                    if self._body.fill * 3 >= self._body.mask * 2:
                        self._table_resize(self._body.used)

    def add(self, key):
        self._add(key)

    """ Derived from set_lookkey in setobject.c """
    def _lookkey(self, key, khash):
        mm = self._p_mm
        mask = self._body.mask
        i = khash & mask
        table_data = ffi.cast('PSetEntry *', mm.direct(self._body.table))

        entry = table_data[i]
        if entry.hash == HASH_UNUSED:
            return -1

        perturb = khash

        while(True):
            if entry.hash == khash:
                startkey = self._p_mm.resurrect(entry.key)
                if startkey == key:
                    return i

                """ TODO: find a test for this unlikely behaviour """
                crtkey = self._p_mm.resurrect(entry.key)
                crttable = ffi.cast('PSetEntry *', mm.direct(self._body.table))
                if crtkey != startkey:
                    return self._lookkey(key, khash)

            for j in range(i + 1, min(i + LINEAR_PROBES, mask) + 1):
                entry = table_data[j]
                if entry.hash == HASH_UNUSED:
                    return -1

                if entry.hash == khash:
                    startkey = self._p_mm.resurrect(entry.key)
                    if startkey == key:
                        return j

                    """ TODO: find a test for this unlikely behaviour """
                    crtkey = self._p_mm.resurrect(entry.key)
                    crttable = ffi.cast('PSetEntry *',
                                        mm.direct(self._body.table))
                    if crtkey is not startkey or crttable is not table_data:
                        return self._lookkey(key, khash)

            perturb >>= PERTURB_SHIFT
            i = (i * 5 + 1 + perturb) & mask
            entry = table_data[i]

            if entry.hash == HASH_UNUSED:
                return -1

    @recursive_repr()
    def __repr__(self):
        str_repr = "%s:[%s]" % (self.__class__.__name__,
                                ", ".join(str(key) for key in self))
        return str_repr

    def __debug_repr__(self):
        mm = self._p_mm
        table_data = ffi.cast('PSetEntry *', mm.direct(self._body.table))
        set_content = ""
        for i in range(0, self._body.mask + 1):
            entry = table_data[i]
            if entry.hash == HASH_UNUSED:
                set_content += "<U>, "
            elif entry.hash == HASH_DUMMY:
                set_content += "<D>, "
            else:
                p_obj = ffi.cast('PObject *', mm.direct(entry.key))
                set_content += "(%s h:%s rct:%s), " % (
                                mm.resurrect(entry.key),
                                entry.hash,
                                p_obj.ob_refcnt)
        return "%s:[%s]" % (self.__class__.__name__, set_content)

    def __contains__(self, key):
        return self._lookkey(key, fixed_hash(key)) != -1

    def __iter__(self):
        mm = self._p_mm
        table_data = ffi.cast('PSetEntry *', mm.direct(self._body.table))
        for i in range(0, self._body.mask + 1):
            entry = table_data[i]
            if entry.hash in [HASH_UNUSED, HASH_DUMMY]:
                continue
            yield mm.resurrect(entry.key)

    def union(self, *args):
        mm = self._p_mm
        with mm.transaction():
            new_set = self.__class__._make_new_set(self._p_mm, self)
            for arg in args:
                try:
                    for item in arg:
                        new_set._add(item)
                except TypeError:
                    new_set._add(arg)
            return new_set

    """ Derived from set_intersection in setobject.c """
    def _set_intersection(self, other):
        mm = self._p_mm
        with mm.transaction():
            new_set = self.__class__._make_new_set(self._p_mm, [])
            if len(other) < len(self):
                tmp = self
                self = other
                other = tmp
            for item in self:
                if item in other:
                    new_set._add(item)
            return new_set

    def _check_set(self, other):
        return (isinstance(other, PersistentSet) or
                isinstance(other, set) or
                isinstance(other, frozenset))

    def intersection(self, *args):
        mm = self._p_mm
        with mm.transaction():
            if len(args) == 0:
                return self.__class__._make_new_set(mm, self)
            result = self._set_intersection(args[0])
            for arg in args[1:]:
                newresult = result._set_intersection(arg)
                mm._deallocate(result._p_oid)
                result = newresult
            return result

    def difference(self, *args):
        mm = self._p_mm
        with mm.transaction():
            new_set = self.__class__._make_new_set(self._p_mm, [])
            for item in self:
                for other in args:
                    if item in other:
                        item = None
                        break
                if item:
                    new_set._add(item)
            return new_set

    def symmetric_difference(self, other):
        mm = self._p_mm
        with mm.transaction():
            new_set = self.__class__._make_new_set(self._p_mm, self)
            for item in other:
                if item in self:
                    new_set._discard(item)
                else:
                    new_set._add(item)
            return new_set

    def is_disjoint(self, other):
        if len(other) < len(self):
                tmp = self
                self = other
                other = tmp
        for item in self:
            if item in other:
                return False
        return True

    @staticmethod
    def _issubset(iter_one, iter_two):
        for item in iter_one:
            if item not in iter_two:
                return False
        return True

    def issubset(self, other):
        return PersistentSet._issubset(self, other)

    def issuperset(self, other):
        return PersistentSet._issubset(other, self)

    def __or__(self, other):
        if not self._check_set(other):
            raise TypeError("unsupported operand type(s) for | %s and %s" %
                            (self.__class__.__name__,
                             other.__class__.__name__))
        return self.union(other)

    def __and__(self, other):
        if not self._check_set(other):
            raise TypeError("unsupported operand type(s) for & %s and %s" %
                            (self.__class__.__name__,
                             other.__class__.__name__))
        return self.intersection(other)

    def __sub__(self, other):
        if not self._check_set(other):
            raise TypeError("unsupported operand type(s) for - %s and %s" %
                            (self.__class__.__name__,
                             other.__class__.__name__))
        return self.difference(other)

    def __xor__(self, other):
        if not self._check_set(other):
            raise TypeError("unsupported operand type(s) for ^ %s and %s" %
                            (self.__class__.__name__,
                             other.__class__.__name__))
        return self.symmetric_difference(other)

    def __len__(self):
        return self._body.used

    def _discard(self, key):
        mm = self._p_mm
        with mm.transaction():
            keyindex = self._lookkey(key, fixed_hash(key))
            if keyindex != -1:
                table_data = ffi.cast('PSetEntry *',
                                      mm.direct(self._body.table))
                mm.snapshot_range(ffi.addressof(table_data, keyindex),
                                  ffi.sizeof('PSetEntry'))
                mm.decref(table_data[keyindex].key)
                table_data[keyindex].key = mm.OID_NULL
                table_data[keyindex].hash = HASH_DUMMY
                self._body.used -= 1

    def discard(self, key):
        self._discard(key)

    def _p_traverse(self):
        mm = self._p_mm
        table_data = ffi.cast('PSetEntry *', mm.direct(self._body.table))
        for i in range(0, self._body.mask + 1):
            entry = table_data[i]
            if entry.hash in (HASH_UNUSED, HASH_DUMMY):
                continue
            yield entry.key

    def _p_substructures(self):
        return ((self._body.table, SET_POBJPTR_ARRAY_TYPE_NUM),)

    def _p_deallocate(self):
        mm = self._p_mm
        for key_oid in self._p_traverse():
            mm.decref(key_oid)
        mm.free(self._body.table)

    def _p_resurrect(self, manager, oid):
        mm = self._p_mm = manager
        self._p_oid = oid
        self._body = ffi.cast('PSetObject *', mm.direct(oid))


class PersistentFrozenSet(PersistentSet):
    def add(self, key):
        raise AttributeError("PersistentFrozenSet has no attribute 'add'")

    def discard(self, key):
        raise AttributeError("PersistentFrozenSet has no attribute 'discard'")
