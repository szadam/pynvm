import os
from nvm import pmemblk
from tests.support import TestCase


class TestPmemBlk(TestCase):

    def _create_blk_pool(self):
        self.fn = self._test_fn()
        self.pool = pmemblk.create(self.fn)
        self.addCleanup(self._close_blk_pool)

    def _create_blk_pool_with_size(self, block_size, pool_size):
        self.fn = self._test_fn()
        self.pool = pmemblk.create(self.fn, block_size, pool_size)
        self.addCleanup(self._close_blk_pool)

    def _open_blk_pool(self, filename):
        self.pool = pmemblk.open(filename)

    def _close_blk_pool(self):
        if self.pool:
            self.pool.close()
            self.pool = None

    def test_create_and_open_blk_pool(self):
        self._create_blk_pool()
        self.assertTrue(os.path.isfile(self.fn))
        self._close_blk_pool()
        self._open_blk_pool(self.fn)
        self.assertNotEqual(self.pool, None)

    def test_bsize(self):
        block_size = 512
        self._create_blk_pool_with_size(block_size, 32 * 1024 * 1024)
        self.assertEqual(block_size, self.pool.bsize())

    def test_nblock(self):
        block_size = 512
        pool_size = 32 * 1024 * 1024
        nblocks = pool_size // block_size
        self._create_blk_pool_with_size(block_size, pool_size)
        self.assertTrue(nblocks - self.pool.nblock() <= 2000)

    def test_read_write(self):
        block_size = 512
        pool_size = 32 * 1024 * 1024
        data = [b"a" * block_size,
                b"b" * block_size,
                b"c" * block_size,
                b"d" * block_size,
                b"e" * block_size,
                b"f" * block_size]
        self._create_blk_pool_with_size(block_size, pool_size)
        nblocks = self.pool.nblock()
        data_idx = 0
        for idx in range(0, nblocks, 256):
            res = self.pool.write(data[data_idx % len(data)], idx)
            self.assertEqual(res, 0)
            data_idx += 1
        self._close_blk_pool()
        self._open_blk_pool(self.fn)
        data_idx = 0
        for idx in range(0, nblocks, 256):
            read_data = self.pool.read(idx)
            self.assertEqual(read_data, data[data_idx % len(data)])
            data_idx += 1

    def test_read_invalid(self):
        self._create_blk_pool()
        nblocks = self.pool.nblock()
        with self.assertRaises(ValueError):
            self.pool.read(nblocks)

    def test_write_invalid(self):
        self._create_blk_pool()
        nblocks = self.pool.nblock()
        with self.assertRaises(ValueError):
            self.pool.write(b"abc", nblocks)

    def test_set_zero(self):
        data = b"abc" * 128
        self._create_blk_pool()
        nblocks = self.pool.nblock()
        for idx in range(0, nblocks, 256):
            self.pool.write(data, idx)
            read_data = self.pool.read(idx)
            self.assertEqual(read_data, data)
            res = self.pool.set_zero(idx)
            self.assertEqual(res, 0)
            read_data = self.pool.read(idx)
            self.assertEqual(read_data, "")

    def test_set_error(self):
        data = b"abc" * 128
        self._create_blk_pool()
        nblocks = self.pool.nblock()
        for idx in range(0, nblocks, 256):
            self.pool.write(data, idx)
            read_data = self.pool.read(idx)
            self.assertEqual(read_data, data)
            res = self.pool.set_error(idx)
            self.assertEqual(res, 0)
            with self.assertRaises(OSError):
                self.pool.read(idx)
        self._close_blk_pool()
        self._open_blk_pool(self.fn)
        for idx in range(0, nblocks, 256):
            with self.assertRaises(OSError):
                self.pool.read(idx)
            self.pool.write(data, idx)
        self._close_blk_pool()
        self._open_blk_pool(self.fn)
        for idx in range(0, nblocks, 256):
            read_data = self.pool.read(idx)
            self.assertEqual(read_data, data)

    def test_check(self):
        self._create_blk_pool()
        self._close_blk_pool()
        self.assertEqual(pmemblk.check(self.fn), True)

    def test_check_version(self):
        major_version = 1
        minor_version = 1
        with self.assertRaises(RuntimeError):
            pmemblk.check_version(major_version, minor_version)
        minor_version = 0
        self.assertTrue(pmemblk.check_version(major_version, minor_version))

if __name__ == '__main__':
    unittest.main()
