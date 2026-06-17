import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
from celery.schedules import crontab
import django.utils.translation
from my_site.core.logging_config import get_logging_config
django.utils.translation.ugettext_lazy = django.utils.translation.gettext_lazy
django.utils.translation.ugettext = django.utils.translation.gettext

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG') == 'True'

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']


import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn=os.getenv('SENTRY_DSN'),
    integrations=[
        DjangoIntegration(),
    ],
    traces_sample_rate=1.0,
    send_default_pii=True,
)

LOGGING = get_logging_config(BASE_DIR)


# ------------------------------------------------------------------ #
#  Installed apps                                                      #
# ------------------------------------------------------------------ #

INSTALLED_APPS = [
    'django_prometheus',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'django_celery_results',
    'apps.products',
    'apps.orders',
    'apps.users',
    'apps.carts',
    'health_check',  
    
                              

]

# ------------------------------------------------------------------ #
#  Middleware                                                          #
# ------------------------------------------------------------------ #

MIDDLEWARE = [

    'django_prometheus.middleware.PrometheusBeforeMiddleware',

    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'my_site.core.middlewares.CapacityControlMiddleware', 
    'my_site.core.middlewares.GlobalExceptionHandlerMiddleware',
    'my_site.core.middlewares.RequestMonitoringMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

ROOT_URLCONF = 'my_site.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'my_site.wsgi.application'

# ------------------------------------------------------------------ #
#  Database                                                            #
# ------------------------------------------------------------------ #

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME':     os.getenv('POSTGRES_DB',       'my_django_project'),
        'USER':     os.getenv('POSTGRES_USER',     'postgres'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'postgres'),
        'HOST':     os.getenv('POSTGRES_HOST',     '127.0.0.1'),
        'PORT':     os.getenv('POSTGRES_PORT',     '5432'),
        'CONN_MAX_AGE': 60,
    }
}

AUTH_USER_MODEL = 'users.User'

# ------------------------------------------------------------------ #
#  Caching — Redis (Requirement 6)                                    #
# ------------------------------------------------------------------ #

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'IGNORE_EXCEPTIONS': True,   
            'SOCKET_CONNECT_TIMEOUT': 2,
            'SOCKET_TIMEOUT': 2,
        },
    }
}

# ------------------------------------------------------------------ #
#  Celery — Async tasks (Req 3) & Scheduled batch jobs (Req 4)        #
# ------------------------------------------------------------------ #

CELERY_BROKER_URL        = os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND    = 'django-db'
CELERY_ACCEPT_CONTENT    = ['json']
CELERY_TASK_SERIALIZER   = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE          = 'UTC'

CELERY_BEAT_SCHEDULE = {
  
    'daily-batch-sales': {
        'task': 'apps.common.tasks.daily_sales_batch_processing',
        'schedule': crontab(hour=0, minute=0),
    },
    'weekly-full-report': {
        'task': 'apps.common.tasks.generate_weekly_report',
        'schedule': crontab(day_of_week=1, hour=0, minute=0),
    },
}

# ------------------------------------------------------------------ #
#  Django REST Framework                                               #
# ------------------------------------------------------------------ #

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100000000/day',
        'user': '100000000/day',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(weeks=1),
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ------------------------------------------------------------------ #
#  Email                                                               #
# ------------------------------------------------------------------ #


EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = 'smtp.gmail.com'
EMAIL_PORT          = 587
EMAIL_USE_TLS       = True
EMAIL_HOST_USER     = os.getenv('EMAIL_HOST_USER',     'your_email@gmail.com')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', 'your_app_password')
DEFAULT_FROM_EMAIL  = EMAIL_HOST_USER

# ------------------------------------------------------------------ #
#  Auth / i18n / static                                                #
# ------------------------------------------------------------------ #

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'UTC'
USE_I18N      = True
USE_TZ        = True

STATIC_URL  = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'