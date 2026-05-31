"""
Django settings for planehistory project.

Plane-history ADS-B 接收記錄器：原本純 stdlib（http.server + pymysql），
而家 migrate 緊去 Django（learning project）。設定保留原本 src/config.json
（mysql + push secret + receiver info），SECRET_KEY / DEBUG / ALLOWED_HOSTS
則由 .env 經 django-environ 讀。
"""

import json
from pathlib import Path

import environ
import pymysql

# Django 預設 mysqlclient driver；用 PyMySQL 取代避免裝 mysql-connector C ext
pymysql.install_as_MySQLdb()

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ['127.0.0.1', 'localhost']),
)
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env('ALLOWED_HOSTS')

# plane-history domain config（tar1090 URL、push.secret、receiver info）由 config.json load
# 唔放 .env 因為係 nested structured config。code 用：
#   from django.conf import settings
#   settings.PLANE_HISTORY['push']['secret']
with open(BASE_DIR / 'src' / 'config.json', encoding='utf-8') as _f:
    PLANE_HISTORY = json.load(_f)


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # 3rd party
    'rest_framework',
    'django_filters',
    # local apps
    'tracking',
    'enrichment',
    'web',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'planehistory.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
            ],
        },
    },
]

WSGI_APPLICATION = 'planehistory.wsgi.application'

# Database：用 src/config.json 入面 mysql block
_mysql = PLANE_HISTORY['mysql']
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': _mysql['database'],
        'USER': _mysql['user'],
        'PASSWORD': _mysql['password'],
        'HOST': _mysql['host'],
        'PORT': str(_mysql['port']),
        'OPTIONS': {'charset': 'utf8mb4'},
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# i18n / l10n：3 套語言，cookie name 用 Django default `django_language`
LANGUAGE_CODE = 'zh-hant'
TIME_ZONE = 'UTC'   # ingest 寫 UTC ISO；display 時轉 JST
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('zh-hant', '繁體中文'),
    ('ja', '日本語'),
    ('en', 'English'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']


# Static files（whitenoise serve）
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# DRF
REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        # DEBUG 時保留 Browsable API；prod 可以剔走
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}


# Auth：login 跳 `/`（首頁），logout 都跳返首頁
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
