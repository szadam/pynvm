import os

def load_tests(*args):
    if not len(args):
        # Avoid conflict between nose and unittest (nose thinks this is a test).
        return
    loader, standard_tests, pattern = args[0], args[1], args[2]
    this_dir = os.path.dirname(__file__)
    if pattern is None:
        pattern = "test*"
    package_tests = loader.discover(start_dir=this_dir, pattern=pattern)
    standard_tests.addTests(package_tests)
    return standard_tests
