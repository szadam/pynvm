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

    def _reread_dict(self):
        self.pop.close()
        self.pop = pmemobj.open(self.fn)
        return self.pop.root

    def test_constructor_defaults(self):
        # This just tests that the constructor doesn't blow up.
        d = self._make_dict()
        self._reread_dict()

    def test_set_get_one_item(self):
        d = self._make_dict()
        d['a'] = 1
        self.assertEqual(d['a'], 1)
        d = self._reread_dict()
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
        d = self._reread_dict()
        for key, value  in data.items():
            self.assertEqual(d[key], value)

    def test_replace_value(self):
        d = self._make_dict()
        d['a'] = 1
        self.assertEqual(d['a'], 1)
        d['a'] = 'foo'
        self.assertEqual(d['a'], 'foo')
        d = self._reread_dict()
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
        d = self._reread_dict()
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
        d = self._reread_dict()
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
        d = self._reread_dict()
        self.assertEqual(d, {})
        self.assertEqual(len(d), 0)
        # Make sure clear didn't break it.
        d[1] = 7
        self.assertEqual(d, {1: 7})


    # XXX test(s) for dict mutating on comparison during lookdict


if __name__ == '__main__':
    unittest.main()
