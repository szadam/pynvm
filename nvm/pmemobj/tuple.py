import collections
import sys

from .compat import recursive_repr, abc
from .list import PersistentList
from _pmem import ffi

TUPLE_POBJPTR_ARRAY_TYPE_NUM = 50


class PersistentTuple(PersistentList):
    """Persistent version of the 'tuple' type."""

    def __init__(self, *args, **kw):
        if not args:
            return
        if len(args) != 1:
            raise TypeError("PersistentTuple takes at most 1"
                            " argument, {} given".format(len(args)))
        item_count = len(args[0])
        mm = self._p_mm
        with mm.transaction():
            mm.snapshot_range(
                ffi.addressof(self._body, 'ob_items'), ffi.sizeof('PObjPtr'))
            self._body.ob_items = mm.zalloc(
                                    item_count * ffi.sizeof('PObjPtr'),
                                    type_num=TUPLE_POBJPTR_ARRAY_TYPE_NUM)

            ob = ffi.cast('PVarObject *', self._body)
            mm.snapshot_range(ffi.addressof(ob, 'ob_size'),
                              ffi.sizeof('size_t'))
            ob.ob_size = item_count

            for index, value in enumerate(args[0]):
                super(self.__class__, self).__setitem__(index, value)

    def _p_new(self, manager):
        mm = self._p_mm = manager
        with mm.transaction():
            self._p_oid = mm.zalloc(ffi.sizeof('PTupleObject'))

            ob = ffi.cast('PObject *', mm.direct(self._p_oid))
            ob.ob_type = mm._get_type_code(PersistentTuple)

            self._body = ffi.cast('PTupleObject *', mm.direct(self._p_oid))
            self._body.ob_items = mm.OID_NULL

    def _p_resurrect(self, manager, oid):
        mm = self._p_mm = manager
        self._p_oid = oid
        self._body = ffi.cast('PTupleObject *', mm.direct(oid))

    # Methods and properties needed to implement the ABC required methods.

    def __eq__(self, other):
        if not (isinstance(other, PersistentTuple) or
                isinstance(other, tuple)):
            return NotImplemented
        if len(self) != len(other):
            return False
        for i in range(len(self)):
            if self[i] != other[i]:
                return False
        return True

    @property
    def _allocated(self):
        return self._size

    def __setitem__(self, index, value):
        raise TypeError(
                "'PersistentTuple' object does not support item assignment")

    def __delitem__(self, index):
        raise TypeError(
                "'PersistentTuple' object does not support item deletion")

    def _resize(self, newsize):
        raise TypeError("'PersistentTuple' object does not support resizing")

    def insert(self, index, value):
        raise TypeError("'PersistentTuple' object does not support insertion")

    def clear(self):
        raise TypeError("'PersistentTuple' object does not support clear")

    # Additional list methods not provided by the ABC.
    @recursive_repr()
    def __repr__(self):
        return "{}(({}))".format(self.__class__.__name__,
                                 ', '.join("{!r}".format(x) for x in self))

    def _p_substructures(self):
        return ((self._body.ob_items, TUPLE_POBJPTR_ARRAY_TYPE_NUM),)
