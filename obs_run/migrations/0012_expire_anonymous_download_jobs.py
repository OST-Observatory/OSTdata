from django.db import migrations
from django.utils import timezone


def expire_anonymous_jobs(apps, schema_editor):
    DownloadJob = apps.get_model('obs_run', 'DownloadJob')
    now = timezone.now()
    DownloadJob.objects.filter(user__isnull=True).exclude(
        status__in=('expired', 'cancelled', 'failed')
    ).update(status='expired', finished_at=now, expires_at=now, file_path='', access_token_hash='')


class Migration(migrations.Migration):

    dependencies = [
        ('obs_run', '0011_downloadjob_access_token_hash'),
    ]

    operations = [
        migrations.RunPython(expire_anonymous_jobs, migrations.RunPython.noop),
    ]
