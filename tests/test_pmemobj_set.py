# -*- coding: utf8 -*-
import unittest

from nvm import pmemobj

from tests.support import TestCase


class PassThru(Exception):
    pass


def check_pass_thru():
    raise PassThru
    yield 1


class BadCmp:
    def __hash__(self):
        return 1

    def __eq__(self, other):
        raise RuntimeError


class ReprWrapper:
    'Used to test self-referential repr() calls'
    def __repr__(self):
        return repr(self.value)


class JointOps():
    thetype = None
    basetype = thetype

    def _make_set(self, *args):
        if not hasattr(self, "pop"):
            self.fn = self._test_fn()
            self.pop = pmemobj.create(self.fn, pool_size=32*1024*1024)
            self.pop.root = self.pop.new(pmemobj.PersistentList, [])
            self.addCleanup(self.pop.close)

        newset = self.pop.new(self.thetype, args[0] if len(args) > 0 else args)
        self.pop.root.append(newset)
        return newset

    def _track_set(self, test_set):
        self.pop.root.append(test_set)
        return test_set

    def _set_up(self):
        self.word = word = 'simsalabim'
        self.otherword = 'madagascar'
        self.letters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
        self.s = self._make_set(word)
        self.d = dict.fromkeys(word)

    def test_uniquification(self):
        self._set_up()
        actual = sorted(self.s)
        expected = sorted(self.d)
        self.assertEqual(actual, expected)
        self.assertRaises(PassThru, self.thetype, check_pass_thru())

    def test_len(self):
        self._set_up()
        self.assertEqual(len(self.s), len(self.d))

    def test_contains(self):
        self._set_up()
        fullset = self._make_set(self.letters)
        for c in self.letters:
            self.assertEqual(c in fullset, c in self.letters)

    def test_union(self):
        self._set_up()
        u = self._track_set(self.s.union(self.otherword))
        for c in self.letters:
            self.assertEqual(c in u, c in self.d or c in self.otherword)
        self.assertEqual(type(u), self.basetype)
        for C in set, frozenset, dict.fromkeys, str, list, tuple:
            self.assertEqual(self._track_set(
                    self._make_set('abcba').union(C('cdc'))), set('abcd'))
            self.assertEqual(self._track_set(
                    self._make_set('abcba').union(C('efgfe'))), set('abcefg'))
            self.assertEqual(self._track_set(
                    self._make_set('abcba').union(C('ccb'))), set('abc'))
            self.assertEqual(self._track_set(
                    self._make_set('abcba').union(C('ef'))), set('abcef'))
            self.assertEqual(self._track_set(
                    self._make_set('abcba').union(C('ef'), C('fg'))),
                                                  set('abcefg'))
        x = self._make_set([])
        self.assertEqual(self._track_set(
                    x.union(set([1]), x, set([2]))), self._make_set([1, 2]))

    def test_or(self):
        self._set_up()
        i = self._track_set(self.s.union(self.otherword))
        self.assertEqual(self._track_set(self.s | set(self.otherword)), i)
        self.assertEqual(self._track_set(
                    self.s | frozenset(self.otherword)), i)
        self.assertEqual(self._track_set(
                    self.s | self._make_set(self.otherword)), i)
        try:
            self.s | self.otherword
        except TypeError:
            pass
        else:
            self.fail("s|t did not screen-out general iterables")

    def test_intersection(self):
        self._set_up()
        i = self._track_set(self.s.intersection(self.otherword))
        for c in self.letters:
            self.assertEqual(c in i, c in self.d and c in self.otherword)
        self.assertEqual(self.s, self._make_set(self.word))
        self.assertEqual(type(i), self.basetype)

        for C in set, frozenset, dict.fromkeys, str, list, tuple:
            self.assertEqual(self._track_set(
                    self._make_set('abcba').intersection(C('cdc'))), set('cc'))
            self.assertEqual(self._track_set(
                    self._make_set('abcba').intersection(C('efgfe'))), set(''))
            self.assertEqual(self._track_set(
                    self._make_set('abcba').intersection(C('ccb'))), set('bc'))
            self.assertEqual(self._track_set(
                    self._make_set('abcba').intersection(C('ef'))), set(''))
            self.assertEqual(self._track_set(
                    self._make_set('abcba').intersection(
                        C('cbcf'), C('bag'))), set('b'))

    def test_isdisjoint(self):
        def f(s1, s2):
            'Pure python equivalent of isdisjoint()'
            return not set(s1).intersection(s2)
        for larg in '', 'a', 'ab', 'abc', 'ababac', 'cdc',\
                    'cc', 'efgfe', 'ccb', 'ef':
            s1 = self._make_set(larg)
            for rarg in '', 'a', 'ab', 'abc', 'ababac', 'cdc',\
                    'cc', 'efgfe', 'ccb', 'ef':
                for C in set, frozenset, dict.fromkeys, str, list, tuple:
                    s2 = C(rarg)
                    actual = s1.isdisjoint(s2)
                    expected = f(s1, s2)
                    self.assertEqual(actual, expected)
                    self.assertTrue(actual is True or actual is False)

    def test_and(self):
        self._set_up()
        i = self._track_set(self.s.intersection(self.otherword))
        self.assertEqual(self._track_set(self.s & set(self.otherword)), i)
        self.assertEqual(self._track_set(
                    self.s & frozenset(self.otherword)), i)
        self.assertEqual(self._track_set(
                    self.s & self._make_set(self.otherword)), i)
        try:
            self.s & self.otherword
        except TypeError:
            pass
        else:
            self.fail("s&t did not screen-out general iterables")

    def test_difference(self):
        self._set_up()
        i = self._track_set(self.s.difference(self.otherword))
        for c in self.letters:
            self.assertEqual(c in i, c in self.d and c not in self.otherword)
        self.assertEqual(self.s, self._make_set(self.word))
        self.assertEqual(type(i), self.basetype)
        self.assertRaises(PassThru, self.s.difference, check_pass_thru())
        for C in set, frozenset, dict.fromkeys, str, list, tuple:
            self.assertEqual(self._track_set(
                        self._make_set('abcba').difference(
                            C('cdc'))), set('ab'))
            self.assertEqual(self._track_set(
                        self._make_set('abcba').difference(
                            C('efgfe'))), set('abc'))
            self.assertEqual(self._track_set(
                        self._make_set('abcba').difference(
                            C('ccb'))), set('a'))
            self.assertEqual(self._track_set(
                        self._make_set('abcba').difference(
                            C('ef'))), set('abc'))
            self.assertEqual(self._track_set(
                        self._make_set('abcba').difference()), set('abc'))
            self.assertEqual(self._track_set(
                        self._make_set('abcba').difference(
                            C('a'), C('b'))), set('c'))

    def test_sub(self):
        self._set_up()
        i = self._track_set(self.s.difference(self.otherword))
        self.assertEqual(self._track_set(
                            self.s - set(self.otherword)), i)
        self.assertEqual(self._track_set(
                            self.s - frozenset(self.otherword)), i)
        try:
            self.s - self.otherword
        except TypeError:
            pass
        else:
            self.fail("s-t did not screen-out general iterables")

    def test_symmetric_difference(self):
        self._set_up()
        i = self._track_set(self.s.symmetric_difference(self.otherword))
        for c in self.letters:
            self.assertEqual(c in i, (c in self.d) ^ (c in self.otherword))
        self.assertEqual(self.s, self._make_set(self.word))
        self.assertEqual(type(i), self.basetype)
        self.assertRaises(PassThru, self.s.symmetric_difference,
                          check_pass_thru())
        for C in set, frozenset, dict.fromkeys, str, list, tuple:
            self.assertEqual(self._track_set(
                        self._make_set('abcba').symmetric_difference(
                            C('cdc'))), set('abd'))
            self.assertEqual(self._track_set(
                        self._make_set('abcba').symmetric_difference(
                            C('efgfe'))), set('abcefg'))
            self.assertEqual(self._track_set(
                        self._make_set('abcba').symmetric_difference(
                            C('ccb'))), set('a'))
            self.assertEqual(self._track_set(
                        self._make_set('abcba').symmetric_difference(
                            C('ef'))), set('abcef'))

    def test_xor(self):
        self._set_up()
        i = self._track_set(self.s.symmetric_difference(self.otherword))
        self.assertEqual(self._track_set(
                            self.s ^ set(self.otherword)), i)
        self.assertEqual(self._track_set(
                            self.s ^ frozenset(self.otherword)), i)
        try:
            self.s ^ self.otherword
        except TypeError:
            pass
        else:
            self.fail("s^t did not screen-out general iterables")

    def test_equality(self):
        self._set_up()
        self.assertEqual(self.s, set(self.word))
        self.assertEqual(self.s, frozenset(self.word))
        self.assertEqual(self.s == self.word, False)
        self.assertNotEqual(self.s, set(self.otherword))
        self.assertNotEqual(self.s, frozenset(self.otherword))
        self.assertEqual(self.s != self.word, True)

    def test_sub_and_super(self):
        p, q, r = map(self._make_set, ['ab', 'abcde', 'def'])
        self.assertTrue(p < q)
        self.assertTrue(p <= q)
        self.assertTrue(q <= q)
        self.assertTrue(q > p)
        self.assertTrue(q >= p)
        self.assertFalse(q < r)
        self.assertFalse(q <= r)
        self.assertFalse(q > r)
        self.assertFalse(q >= r)
        self.assertTrue(self._make_set('a').issubset('abc'))
        self.assertTrue(self._make_set('abc').issuperset('a'))
        self.assertFalse(self._make_set('a').issubset('cbs'))
        self.assertFalse(self._make_set('cbs').issuperset('a'))


class TestPersistentSet(JointOps, TestCase):
    thetype = pmemobj.PersistentSet
    basetype = thetype

    def test_constructor_identity(self):
        s = self._make_set(range(3))
        t = self._make_set(s)
        self.assertNotEqual(id(s), id(t))

    def test_set_literal(self):
        s = self._make_set([1, 2, 3])
        t = {1, 2, 3}
        self.assertEqual(s, t)

    def test_hash(self):
        self._set_up()
        self.assertRaises(TypeError, hash, self.s)

    def test_clear(self):
        self._set_up()
        self.s.clear()
        self.assertEqual(self.s, self._make_set())
        self.assertEqual(len(self.s), 0)

    def test_add(self):
        self._set_up()
        self.s.add('Q')
        self.assertIn('Q', self.s)

    def test_remove(self):
        self._set_up()
        self.s.remove('a')
        self.assertNotIn('a', self.s)
        self.assertRaises(KeyError, self.s.remove, 'Q')
        self.assertRaises(TypeError, self.s.remove, [])

    def test_remove_keyerror_unpacking(self):
        # bug:  www.python.org/sf/1576657
        self._set_up()
        for v1 in ['Q', (1,)]:
            try:
                self.s.remove(v1)
            except KeyError as e:
                v2 = e.args[0]
                self.assertEqual(v1, v2)
            else:
                self.fail()

    def test_remove_keyerror_set(self):
        self._set_up()
        key = self._make_set([3, 4])
        try:
            self.s.remove(key)
        except KeyError as e:
            self.assertTrue(
                e.args[0] is key,
                "KeyError should be {0}, not {1}".format(key, e.args[0]))
        else:
            self.fail()

    def test_discard(self):
        self._set_up()
        self.s.discard('a')
        self.assertNotIn('a', self.s)
        self.s.discard('Q')
        self.assertRaises(TypeError, self.s.discard, [])

    def test_pop(self):
        self._set_up()
        for i in range(len(self.s)):
            elem = self.s.pop()
            self.assertNotIn(elem, self.s)
        self.assertRaises(KeyError, self.s.pop)


class TestPersistentFrozenSet(JointOps, TestCase):
    thetype = pmemobj.PersistentFrozenSet
    basetype = thetype


if __name__ == '__main__':
    unittest.main()
