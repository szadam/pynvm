# -*- coding: utf8 -*-
import unittest

from nvm import pmemobj

from tests.support import TestCase


class Foo(pmemobj.PersistentObject):
    pass


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


if __name__ == '__main__':
    unittest.main()
