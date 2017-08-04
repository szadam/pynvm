import sys
import os
import errno
from _pmem import ffi

try:
    import collections.abc as abc
except ImportError:
    import collections as abc

try:
    from reprlib import recursive_repr
except ImportError:
    from thread import get_ident
    def recursive_repr(fillvalue='...'):
        'Decorator to make a repr function return fillvalue for a recursive call'
        def decorating_function(user_function):
            repr_running = set()
            def wrapper(self):
                key = id(self), get_ident()
                if key in repr_running:
                    return fillvalue
                repr_running.add(key)
                try:
                    result = user_function(self)
                finally:
                    repr_running.discard(key)
                return result
            return wrapper
        return decorating_function


def _coerce_fn(file_name):
    """Return 'char *' compatible file_name on both python2 and python3."""
    if sys.version_info[0] > 2 and hasattr(file_name, 'encode'):
        file_name = file_name.encode(errors='surrogateescape')
    return file_name


class ErrChecker:
    def __init__(self, msg_func):
        self.msg_func = msg_func

    def raise_per_errno(self):
        """Raise appropriate error, based on current errno using current message.

        Assume the pmem library has detected an error, and use the current
        errno and error message to raise an appropriate Python exception.
        Convert EINVAL into ValueError, ENOMEM into MemoryError,
        and all others into OSError.
        """
        err = ffi.errno
        msg = ffi.string(self.msg_func())
        if err == 0:
            raise OSError("raise_per_errno called with errno 0", 0)
        if msg == "":
            msg = os.strerror(err)
        # In python3 OSError would do this check for us.
        if err == errno.EINVAL:
            raise ValueError(msg)
        elif err == errno.ENOMEM:
            raise MemoryError(msg)
        else:
            # In Python3 some errnos may result in subclass exceptions, but
            # the above are not covered by the OSError subclass logic.
            raise OSError(err, msg)

    def check_null(self, value):
        """Raise an error if value is NULL."""
        if value == ffi.NULL:
            self.raise_per_errno()
        return value

    def check_errno(self, errno):
        """Raise an error if errno is not zero."""
        if errno:
            self.raise_per_errno()
