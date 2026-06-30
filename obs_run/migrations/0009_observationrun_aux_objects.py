from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('obs_run', '0008_datafile_re_evaluated_after_plate_solve_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='observationrun',
            name='aux_objects',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='observationrun',
            name='aux_objects_meta',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='observationrun',
            name='aux_objects_status',
            field=models.CharField(
                blank=True,
                choices=[('pending', 'Pending'), ('ready', 'Ready'), ('error', 'Error')],
                default='',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='observationrun',
            name='aux_objects_error',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='observationrun',
            name='aux_objects_computed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='observationrun',
            name='aux_objects_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
