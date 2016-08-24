import collections
import logging

from _pmem import ffi

from .dict import PersistentDict


log = logging.getLogger('nvm.pmemobj.object')


class PersistentObject(object):
    """Base class for arbitrary persistent objects."""

    # XXX locking

    def _p_new(self, manager):
        self._p_dict = {}    # This makes __getattribute__ simpler
        mm = self._p_mm = manager
        with mm.transaction():
            # XXX will want to implement a freelist here.
            self._p_oid = mm.malloc(ffi.sizeof('PObjectObject'))
            ob = ffi.cast('PObject *', mm.direct(self._p_oid))
            ob.ob_type = mm._get_type_code(self.__class__)
            d = self._p_body = ffi.cast('PObjectObject *',
                                        mm.direct(self._p_oid))
            self._p_dict = mm.new(PersistentDict)
            d.ob_dict = self._p_dict._p_oid
            mm.incref(self._p_dict._p_oid)
        self._v_init()

    def _p_resurrect(self, manager, oid):
        mm = self._p_mm = manager
        self._p_oid = oid
        self._p_body = ffi.cast('PObjectObject *', mm.direct(oid))
        self._p_dict = mm.resurrect(self._p_body.ob_dict)
        self._v_init()

    def _v_init(self):
        pass

    # Methods to emulate a normal class.

    def __getattribute__(self, name):
        if not name.startswith(('_p_', '_v_')) and name in self._p_dict:
            return self._p_dict[name]
        return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        if name.startswith(('_p_', '_v_')):
            object.__setattr__(self, name, value)
            return
        self._p_dict[name] = value

    def __delattr__(self, name):
        if name.startswith(('_p_', '_v_')):
            object.__delattr__(self, name)
        try:
            del self._p_dict[name]
        except KeyError as e:
            raise AttributeError(str(e))

    # methods required for pmemobj Persistent API.

    def _p_traverse(self):
        yield self._p_mm.otuple(self._p_body.ob_dict)

    def _p_deallocate(self):
        self._p_mm.decref(self._p_body.ob_dict)

    def _p_substructures(self):
        return []
