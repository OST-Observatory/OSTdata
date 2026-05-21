from django.apps import AppConfig


class AdminopsConfig(AppConfig):
    name = 'adminops'
    verbose_name = 'Admin Operations'

    def ready(self):
        import adminops.signals  # noqa: F401




