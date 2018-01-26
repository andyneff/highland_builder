import unittest
import mock


def easy_dict(*args):
    return {a: "<{}>".format(a) for a in args}


def patch_open(content=None):
    def decorator(f):
        def wrapper(*args, **kwargs):
            mock_open = mock.mock_open(read_data=content)
            patch = mock.patch('__builtin__.open', mock_open)
            patch.start()
            try:
                args = args + (mock_open, )
                f(*args, **kwargs)
            finally:
                patch.stop()

        wrapper.__name__ = f.__name__
        return wrapper

    return decorator


class PatchCase(unittest.TestCase):
    mocks = {}

    def mockUp(self):
        pass

    def setUp(self):
        for name, path in self.mocks.items():
            patch = mock.patch(path)
            setattr(self, "mock_{}".format(name), patch.start())
            self.addCleanup(patch.stop)
        self.mockUp()
