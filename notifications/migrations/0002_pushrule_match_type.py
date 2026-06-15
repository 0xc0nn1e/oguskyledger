"""push_rules 加 match_type 欄。

同 0001 一樣三路都可能改到呢個 schema（Django migration / src/init_db.py /
src/push_rules.py runtime guard），所以 DB 層 idempotent（欄已存在就唔再 ALTER），
Django state 層照 AddField。舊 row 冇 match_type → DEFAULT 'callsign'，行為原封不動。
reverse no-op：唔 drop 欄（避免毀資料）。
"""

from django.db import migrations, models

TABLE = 'push_rules'
COLUMN = 'match_type'


def _column_exists(schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
            [TABLE, COLUMN],
        )
        return cur.fetchone()[0] > 0


def add_column(apps, schema_editor):
    if not _column_exists(schema_editor):
        with schema_editor.connection.cursor() as cur:
            cur.execute(
                f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} "
                "VARCHAR(16) NOT NULL DEFAULT 'callsign'"
            )


class Migration(migrations.Migration):

    dependencies = [('notifications', '0001_initial')]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(add_column, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='pushrule',
                    name='match_type',
                    field=models.CharField(
                        default='callsign', max_length=16,
                        help_text='match 邊個欄：callsign / icao / registration / type / route / country',
                    ),
                ),
            ],
        ),
    ]
