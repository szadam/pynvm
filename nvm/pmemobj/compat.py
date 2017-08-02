import sys

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
