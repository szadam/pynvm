# -*- coding: utf8 -*-
import unittest

from nvm import pmemobj

from tests.support import TestCase


class Foo(pmemobj.PersistentObject):
    class_attr = 10
    def no_fubar(self, x):
        return x + 1

class Foo2(pmemobj.PersistentObject):
    def _v__init__(self):
        self._v_bar = 'baz'


class TestPersistentObject(TestCase):

    def _make_object(self, cls, *args, **kw):
        self.fn = self._test_fn()
        self.pop = pmemobj.create(self.fn, debug=True)
        self.addCleanup(self.pop.close)
        self.pop.root = self.pop.new(cls, *args, **kw)
        return self.pop.root

    def _reload_root(self):
        self.pop.close()
        self.pop = pmemobj.open(self.fn, debug=True)
        return self.pop.root

    def test_constructor_defaults(self):
        # This just tests that the constructor doesn't blow up.
        d = self._make_object(Foo)
        self._reload_root()

    def test_attribute_assignment(self):
        d = self._make_object(Foo)
        d.bar = 1
        d.baz = 'bing'
        self.assertEqual(d.bar, 1)
        self.assertEqual(d.baz, 'bing')
        d = self._reload_root()
        self.assertEqual(d.bar, 1)
        self.assertEqual(d.baz, 'bing')

    def test_invalid_attribute(self):
        d = self._make_object(Foo)
        with self.assertRaises(AttributeError):
            d.bar
        d.bar = 1
        self.assertEqual(d.bar, 1)

    def test_attribute_deleting(self):
        d = self._make_object(Foo)
        d.bar = 1
        d.baz = 'bing'
        del d.bar
        with self.assertRaises(AttributeError):
            d.bar
        self.assertEqual(d.baz, 'bing')
        d = self._reload_root()
        with self.assertRaises(AttributeError):
            d.bar
        self.assertEqual(d.baz, 'bing')
        del d.baz
        with self.assertRaises(AttributeError):
            d.baz
        with self.assertRaises(AttributeError):
            del d.foo

    def test_modify_immutable_attribute(self):
        d = self._make_object(Foo)
        d.bar = 1
        d.bar += 1
        self.assertEqual(d.bar, 2)
        d = self._reload_root()
        self.assertEqual(d.bar, 2)

    def test_dict_as_attribute(self):
        d = self._make_object(Foo)
        d.bar = self.pop.new(pmemobj.PersistentDict)
        d.bar['a'] = 'b'
        self.assertEqual(d.bar, {'a': 'b'})
        d = self._reload_root()
        self.assertEqual(d.bar, {'a': 'b'})

    def test_class_attribute(self):
        d = self._make_object(Foo)
        self.assertEqual(d.class_attr, 10)
        d = self._reload_root()
        self.assertEqual(d.class_attr, 10)

    def test_modify_immutable_class_attribute(self):
        d = self._make_object(Foo)
        d.class_attr += 10
        self.assertEqual(d.class_attr, 20)
        d = self._reload_root()
        self.assertEqual(d.class_attr, 20)

    def test_method(self):
        d = self._make_object(Foo)
        self.assertEqual(d.no_fubar(10), 11)
        d = self._reload_root()
        self.assertEqual(d.no_fubar(10), 11)

    def test_hasattr(self):
        d = self._make_object(Foo)
        self.assertFalse(hasattr(d, 'foo'))
        d.foo = 10
        self.assertTrue(hasattr(d, 'foo'))
        self.assertTrue(hasattr(d, '_p_mm'))

    def test__v__init__(self):
        # We use a Foo2 here so that previous tests test having a class without
        # a subclass-defined _v__init__.
        d = self._make_object(Foo2)
        self.assertEqual(d._v_bar, 'baz')
        d = self._reload_root()
        self.assertEqual(d._v_bar, 'baz')


if __name__ == '__main__':
    unittest.main()
