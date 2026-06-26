from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_is_supervisor'),
    ]

    operations = [
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS authtoken_token;',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
