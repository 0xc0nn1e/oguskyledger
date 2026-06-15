"""push_log 表 —— 每次 push 寫一筆，畀 /push-log/ 頁睇。

同 push_rules 一樣三路都會建（Django migration / src/init_db.py / src/push_rules.py
ensure_push_log），所以 DB 層用 idempotent CREATE TABLE IF NOT EXISTS，Django state 層
照 CreateModel。Log 表無 seed、並發 create 安全。reverse no-op：唔 drop（避免毀記錄）。
"""

from django.db import migrations, models


def create_table(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS push_log (
              id INT AUTO_INCREMENT PRIMARY KEY,
              pushed_at VARCHAR(40) NOT NULL,
              icao VARCHAR(16),
              callsign VARCHAR(32),
              registration VARCHAR(32),
              label VARCHAR(64),
              route VARCHAR(128),
              http_status INT,
              ok TINYINT(1) NOT NULL DEFAULT 0,
              KEY idx_push_log_pushed_at (pushed_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""
        )


class Migration(migrations.Migration):

    dependencies = [('notifications', '0003_alter_pushrule_callsign_prefixes_and_more')]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(create_table, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='PushLog',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('pushed_at', models.CharField(max_length=40)),
                        ('icao', models.CharField(blank=True, max_length=16, null=True)),
                        ('callsign', models.CharField(blank=True, max_length=32, null=True)),
                        ('registration', models.CharField(blank=True, max_length=32, null=True)),
                        ('label', models.CharField(blank=True, max_length=64, null=True)),
                        ('route', models.CharField(blank=True, max_length=128, null=True)),
                        ('http_status', models.IntegerField(blank=True, null=True)),
                        ('ok', models.BooleanField(default=False)),
                    ],
                    options={
                        'verbose_name': 'Push 記錄',
                        'verbose_name_plural': 'Push 記錄',
                        'db_table': 'push_log',
                    },
                ),
            ],
        ),
    ]
