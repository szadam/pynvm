# -*- coding: utf8 -*-
import unittest

from nvm import pmemobj

from tests.support import TestCase


class TestPersistentDict(TestCase):

    def _make_dict(self, *args, **kw):
        self.fn = self._test_fn()
        self.pop = pmemobj.create(self.fn, debug=True)
        self.addCleanup(self.pop.close)
        self.pop.root = self.pop.new(pmemobj.PersistentDict, *args, **kw)
        return self.pop.root

    def _reload_root(self):
        self.pop.close()
        self.pop = pmemobj.open(self.fn, debug=True)
        return self.pop.root

    def test_constructor_defaults(self):
        # This just tests that the constructor doesn't blow up.
        d = self._make_dict()
        self._reload_root()

    def test_set_get_one_item(self):
        d = self._make_dict()
        d['a'] = 1
        self.assertEqual(d['a'], 1)
        d = self._reload_root()
        self.assertEqual(d['a'], 1)

    def test_get_unknown_key(self):
        d = self._make_dict()
        with self.assertRaises(KeyError):
            d['a']
        d['a'] = 1
        with self.assertRaises(KeyError):
            d['aa']

    def test_set_get_mulitiple_keys_of_various_types(self):
        data = {'a': 1, 2: 3.7, 4.1: 3, 'something': 'somewhere', 'főo': 'bàr'}
        d = self._make_dict()
        for key, value in data.items():
            d[key] = value
            self.assertEqual(d[key], value)
        d = self._reload_root()
        for key, value  in data.items():
            self.assertEqual(d[key], value)

    def test_replace_value(self):
        d = self._make_dict()
        d['a'] = 1
        self.assertEqual(d['a'], 1)
        d['a'] = 'foo'
        self.assertEqual(d['a'], 'foo')
        d = self._reload_root()
        self.assertEqual(d['a'], 'foo')

    def test_iter(self):
        d = self._make_dict()
        d[1] = 2
        d[45] = 7
        d['a'] = 'b'
        self.assertCountEqual(list(d), [1, 45, 'a'])

    def test_delitem(self):
        d = self._make_dict()
        d['a'] = 1
        self.assertEqual(d, {'a': 1})
        del d['a']
        self.assertEqual(d, {})

    def test_delitem_bad_key(self):
        d = self._make_dict()
        with self.assertRaises(KeyError):
            del d['a']

    def test_constructor(self):
        kw = dict(a=1, b=2, c=3)
        arg = (('z', 5), ('a', 7))
        self.assertEqual(self._make_dict(**kw), kw)
        self.assertEqual(self._make_dict(arg), dict(arg))
        self.assertEqual(self._make_dict(kw), kw)
        self.assertEqual(self._make_dict(arg, **kw), dict(arg, **kw))
        self.assertEqual(self._make_dict(kw, **dict(arg)), dict(kw, **dict(arg)))

    def test_repr(self):
        def assertRepr(pdict, rdict):
            # Since the repr order isn't consistent, we parse it and turn it
            # back into a normal dict...
            r = repr(pdict)
            self.assertTrue(r.startswith('PersistentDict('), 'repr is:' +  r)
            disp = r.split('(', 1)[1].rsplit(')', 1)[0]
            self.assertEqual(eval(disp), data)
        data = dict(a=1, b=250, c='abc', foo='bár')
        d = self._make_dict(data)
        assertRepr(d, data)
        d = self._reload_root()
        assertRepr(d, data)

    def test_len(self):
        d = self._make_dict()
        self.assertEqual(len(d), 0)
        d['a'] = 1
        self.assertEqual(len(d), 1)
        d['b'] = 7
        self.assertEqual(len(d), 2)
        d[999] = -1
        self.assertEqual(len(d), 3)
        del d['b']
        self.assertEqual(len(d), 2)
        d = self._reload_root()
        self.assertEqual(len(d), 2)
        del d[999]
        self.assertEqual(len(d), 1)
        del d['a']
        self.assertEqual(len(d), 0)

    def test_clear(self):
        d = self._make_dict(a=1, b=2, c=3)
        d.clear()
        self.assertEqual(d, {})
        self.assertEqual(len(d), 0)
        d = self._reload_root()
        self.assertEqual(d, {})
        self.assertEqual(len(d), 0)
        # Make sure clear didn't break it.
        d[1] = 7
        self.assertEqual(d, {1: 7})

    def test_multiple_dicts(self):
        e = [
            dict(a='foo', b='bar'),
            dict(a=1, bp=3),
            dict(z=7, p=300),
            dict(l=9),
            ]
        for i in range(4, 20):
            e.append(dict(a=1, b=2, c=3, d=4))
        self._make_dict()
        # Use a list instead so that this doesn't test resize.
        l = self.pop.root = self.pop.new(pmemobj.PersistentList)
        for i in range(len(e)):
            l.append(self.pop.new(pmemobj.PersistentDict, e[i]))
        for i in range(len(l)):
            self.assertEqual(l[i], e[i])
        l = self._reload_root()
        for i in range(len(l)):
            self.assertEqual(l[i], e[i])
        # Test GC.
        for i in range(10):
            l[i] = None
        l = self._reload_root()
        for i in range(10):
            self.assertIsNone(l[i])
        for i in range(10, len(l)):
            self.assertEqual(l[i], e[i])
        self.pop.root = None
        l = self._reload_root()
        self.assertIsNone(self.pop.root)

    def test_dict_resize(self):
        d = self._make_dict()
        for i in range(3):
            d[i] = i
        self.assertEqual(d, {i: i for i in range(3)})
        d = self._reload_root()
        for i in range(3, 20):
            d[i] = i
        self.assertEqual(d, {i: i for i in range(20)})
        d = self._reload_root()
        for i in range(20, 40):
            d[i] = i
        self.assertEqual(d, {i: i for i in range(40)})
        d = self._reload_root()
        for i in range(7):
            del d[i]
        self.assertEqual(d, {i: i for i in range(7, 40)})
        d = self._reload_root()
        for i in range(10, 40):
            del d[i]
        self.assertEqual(d, {i: i for i in range(7, 10)})
        d = self._reload_root()
        self.assertEqual(d, {i: i for i in range(7, 10)})
        d.clear()
        self.assertEqual(d, {})
        d = self._reload_root()
        self.assertEqual(d, {})


    # XXX test(s) for dict mutating on comparison during lookdict


if __name__ == '__main__':
    unittest.main()
