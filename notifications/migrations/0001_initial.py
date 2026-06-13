"""push_rules 初始 migration。

呢張表三條路都可能建：Django migration、src/init_db.py、同 src 兩個 script
嘅 runtime guard（src/push_rules.py）。所以 DB 層用 idempotent RunPython
（表已存在就唔重建），Django state 層照 CreateModel。Seed 一條 HK Express
（HKE,UO，預設開），等舊行為原封不動。reverse no-op：唔 drop 已有 rule。
"""

from django.db import migrations, models

TABLE = 'push_rules'


def _table_exists(schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
            [TABLE],
        )
        return cur.fetchone()[0] > 0


def create_and_seed(apps, schema_editor):
    # Migration 係 seed 嘅唯一 owner：一次性、serial（manage.py migrate 唔會
    # 同自己並發），所以喺度做 seed-if-empty 安全——涵蓋「migrate 行先」同
    # 「runtime guard / init_db 已建空表先」兩種次序，又因為只跑一次，唔會
    # 喺用戶刪晒 rule 之後翻生。runtime guard（每 cycle 並發）就只建表唔 seed。
    with schema_editor.connection.cursor() as cur:
        if not _table_exists(schema_editor):
            cur.execute(
                f"""CREATE TABLE {TABLE} (
                  id INT AUTO_INCREMENT PRIMARY KEY,
                  label VARCHAR(64) NOT NULL,
                  callsign_prefixes VARCHAR(128) NOT NULL,
                  enabled TINYINT(1) NOT NULL DEFAULT 1
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""
            )
        cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
        if cur.fetchone()[0] == 0:
            cur.execute(
                f"INSERT INTO {TABLE} (label, callsign_prefixes, enabled) VALUES (%s, %s, %s)",
                ['HK Express', 'HKE,UO', 1],
            )


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(create_and_seed, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='PushRule',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('label', models.CharField(help_text='operator 顯示名，會用喺 push message 開頭', max_length=64)),
                        ('callsign_prefixes', models.CharField(help_text='逗號分隔嘅 callsign 前綴，例如 HKE,UO', max_length=128)),
                        ('enabled', models.BooleanField(default=True)),
                    ],
                    options={
                        'verbose_name': 'Push 規則',
                        'verbose_name_plural': 'Push 規則',
                        'db_table': 'push_rules',
                    },
                ),
            ],
        ),
    ]
