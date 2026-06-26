from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('objects', '0006_historicalobject_exclude_from_orphan_cleanup_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='identifier',
            index=models.Index(fields=['name'], name='objects_identifier_name_idx'),
        ),
    ]
