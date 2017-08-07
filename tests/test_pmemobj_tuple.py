# -*- coding: utf8 -*-
import unittest

from nvm import pmemobj

from tests.support import TestCase


class TestPersistentTuple(TestCase):

    def _make_tuple(self, arg):
        self.fn = self._test_fn()
        self.pop = pmemobj.create(self.fn, debug=True)
        self.addCleanup(self.pop.close)
        self.pop.root = self.pop.new(pmemobj.PersistentTuple, arg)
        return self.pop.root

    def _reread_tuple(self):
        self.pop.close()
        self.pop = pmemobj.open(self.fn)
        return self.pop.root

    def test_insert(self):
        tpl = self._make_tuple([])
        with self.assertRaises(TypeError):
            tpl.insert(0, 'a')

    def test_append(self):
        tpl = self._make_tuple([])
        with self.assertRaises(TypeError):
            tpl.append(['a'])

    def test_repr(self):
        expected = "PersistentTuple(('a', 'b', 'c'))"
        tpl = self._make_tuple(['a', 'b', 'c'])
        self.assertEqual(repr(tpl), expected)
        self.assertEqual(repr(self._reread_tuple()), expected)

    def test_getitem(self):
        tpl = self._make_tuple(['a', 'b', 'c'])
        self.assertEqual(tpl[0], 'a')
        self.assertEqual(tpl[1], 'b')
        self.assertEqual(tpl[2], 'c')
        tpl = self._reread_tuple()
        self.assertEqual(tpl[0], 'a')
        self.assertEqual(tpl[1], 'b')
        self.assertEqual(tpl[2], 'c')

    def test_getitem_index_errors(self):
        tpl = self._make_tuple(['a', 'b', 'c'])
        with self.assertRaises(IndexError):
            tpl[3]
        with self.assertRaises(IndexError):
            tpl[-4]
        with self.assertRaises(IndexError):
            tpl[10]
        with self.assertRaises(IndexError):
            tpl[-10]

    def test_setitem(self):
        tpl = self._make_tuple(['a', 'b', 'c'])
        with self.assertRaises(TypeError):
            tpl[1] = 'z'
        with self.assertRaises(TypeError):
            tpl[10] = 'z'
        with self.assertRaises(TypeError):
            tpl[-10] = 'z'
        tpl = self._reread_tuple()
        with self.assertRaises(TypeError):
            tpl[1] = 'z'
        with self.assertRaises(TypeError):
            tpl[10] = 'z'
        with self.assertRaises(TypeError):
            tpl[-10] = 'z'

    def test_delitem(self):
        tpl = self._make_tuple(['a', 'b', 'c'])
        with self.assertRaises(TypeError):
            del tpl[1]

    def test_len(self):
        lst = []
        for x in range(0, 6):
            tpl = self._make_tuple(lst)
            self.assertEqual(len(tpl), x)
            lst.append(x)

    def test_clear(self):
        tpl = self._make_tuple([1, 3, 2])
        with self.assertRaises(TypeError):
            tpl.clear()

    def test_eq(self):
        tpl_1 = self._make_tuple([1, 3, 2])
        self.assertEqual(tpl_1, (1, 3, 2))
        tpl_2 = self._make_tuple([1, 3, 2])
        self.assertEqual(tpl_1, tpl_2)
        tpl_2 = self._make_tuple([1, 2, 3])
        self.assertNotEqual(tpl_1, tpl_2)

if __name__ == '__main__':
    unittest.main()
