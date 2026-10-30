"""Test runner that isolates the cache between tests and keeps tests away from a developer's Redis."""
from django.core.cache import cache
from django.test.runner import DiscoverRunner
from django.test.utils import override_settings


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
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        # Redis helpers (download quotas, health/watchdog status, admin toggles) use the Celery broker
        # when it is redis://. A local development Redis would make tests depend on (and fill) its
        # counters, e.g. the anonymous download limit after a few test runs; CI has no Redis.
        self._no_redis = override_settings(CELERY_BROKER_URL='memory://')
        self._no_redis.enable()

    def teardown_test_environment(self, **kwargs):
        self._no_redis.disable()
        super().teardown_test_environment(**kwargs)

    def get_resultclass(self):
        # Keep the result class of --debug-sql / --pdb and only add the cache reset
        base = super().get_resultclass() or self.test_runner.resultclass
        return type(f'CacheIsolating{base.__name__}', (CacheIsolatingResultMixin, base), {})
