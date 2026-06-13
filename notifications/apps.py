from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    # 同 codebase 其他表一致用 INT PK（init_db.py / src guard 都係 INT AUTO_INCREMENT）
    default_auto_field = 'django.db.models.AutoField'
    name = 'notifications'
    verbose_name = '推送通知'
