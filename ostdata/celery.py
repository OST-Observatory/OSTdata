from __future__ import absolute_import, unicode_literals

import os

from celery import Celery


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ostdata.settings')

app = Celery('ostdata')

# Read config from Django settings, using CELERY_ namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks across installed apps
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    return {'request_id': self.request.id}




