import os
from nvm import pmemlog
from tests.support import TestCase


class TestPmemLog(TestCase):

    def _create_log(self):
        self.fn = self._test_fn()
        self.log = pmemlog.create(self.fn)
        self.addCleanup(self._close_log)

    def _open_log(self, filename):
        self.log = pmemlog.open(filename)

    def _close_log(self):
        if self.log:
            self.log.close()
            self.log = None

    def _read_data(self, size=0, max_iters=-1):
        def _walker(data):
            self.data += data
            self.walk_calls += 1
            if self.walk_calls == max_iters:
                return 0
            return 1

        self.data = b""
        self.walk_calls = 0
        self.log.walk(_walker, size)

    def test_create_and_open_log(self):
        self._create_log()
        self.assertTrue(os.path.isfile(self.fn))
        self._close_log()
        self._open_log(self.fn)
        self.assertNotEqual(self.log, None)

    def test_read_write(self):
        data = b"abcdef" * 128
        self._create_log()
        self.log.append(data)
        self._close_log()
        self._open_log(self.fn)
        self._read_data()
        self.assertEqual(self.data, data)

    def test_tell(self):
        nb_bytes = 255
        data = b"a" * nb_bytes
        self._create_log()
        self.log.append(data)
        self.assertEqual(self.log.tell(), nb_bytes)

    def test_rewind(self):
        nb_bytes = 255
        data_a = b"a" * nb_bytes
        data_b = b"b" * nb_bytes
        self._create_log()
        self.log.append(data_a)
        self.log.rewind()
        self.log.append(data_b)
        self._read_data()
        self.assertEqual(self.data, data_b)

    def test_read_one_chunk(self):
        read_size = 127
        pattern = b"abcdef"
        data = pattern * (read_size * len(pattern))
        self._create_log()
        self.log.append(data)
        self._read_data(read_size, 1)
        self.assertEqual(len(self.data), read_size)
        self.assertEqual(self.data, data[:read_size])

    def test_iter(self):
        read_size = 127
        pattern = b"abcdef"
        data = pattern * (read_size * 1000)
        self._create_log()
        self.log.append(data)
        self._read_data(read_size)
        self.assertEqual(data, self.data)
        self.assertEqual(self.walk_calls, len(data) // read_size)

    def test_check_version(self):
        major_version = 1
        minor_version = 1
        with self.assertRaises(RuntimeError):
            pmemlog.check_version(major_version, minor_version)
        minor_version = 0
        self.assertTrue(pmemlog.check_version(major_version, minor_version))

    def test_check(self):
        self._create_log()
        self._close_log()
        self.assertEqual(pmemlog.check(self.fn), True)

    def test_nbyte(self):
        self._create_log()
        self.assertNotEqual(self.log.nbyte(), 0)


if __name__ == '__main__':
    unittest.main()
