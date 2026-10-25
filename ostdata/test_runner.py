"""Test runner that isolates the cache between tests."""
from django.core.cache import cache
from django.test.runner import DiscoverRunner


class CacheIsolatingResultMixin:
    """
    Clear the cache before every test. DRF throttle counters (e.g. anon 60/min) live in the shared
    cache, so without this a test gets 429 responses depending on how many requests the tests run
    before it made within the last minute.
    """

    def startTest(self, test):
        cache.clear()
        super().startTest(test)


class CacheIsolatingTestRunner(DiscoverRunner):
    def get_resultclass(self):
        # Keep the result class of --debug-sql / --pdb and only add the cache reset
        base = super().get_resultclass() or self.test_runner.resultclass
        return type(f'CacheIsolating{base.__name__}', (CacheIsolatingResultMixin, base), {})
