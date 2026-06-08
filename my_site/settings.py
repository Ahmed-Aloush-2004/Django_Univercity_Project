import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
from celery.schedules import crontab

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG') == 'True'

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

# ------------------------------------------------------------------ #
#  Installed apps                                                      #
# ------------------------------------------------------------------ #

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'django_celery_results',
    # Project apps
    'apps.products',
    'apps.orders',
    'apps.users',
    'apps.carts',
]

# ------------------------------------------------------------------ #
#  Middleware                                                          #
# ------------------------------------------------------------------ #

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Requirement 2: caps simultaneous requests at MAX_CONCURRENT_REQUESTS (50)
    'my_site.middlewares.CapacityControlMiddleware',
    # Catches unhandled exceptions and returns a structured JSON 500 response
    'my_site.middlewares.GlobalExceptionHandlerMiddleware',
    # Requirement 10: per-second request-rate counter (stored in Redis)
    'my_site.middlewares.RequestRateMonitorMiddleware',
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
        # Requirement 10 (Bottleneck fix): reuse DB connections for up to 60 s.
        # Before: CONN_MAX_AGE=0 → a new TCP handshake on every request (~5 ms overhead).
        # After : CONN_MAX_AGE=60 → connection reused → overhead drops to ~0.1 ms.
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
            'IGNORE_EXCEPTIONS': True,   # degrade gracefully if Redis is down
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
    # Requirement 4a: daily sales batch — runs every day at midnight.
    # Task lives in my_site/tasks.py → module path: my_site.tasks
    'daily-batch-sales': {
        'task': 'my_site.tasks.daily_sales_batch_processing',
        'schedule': crontab(hour=0, minute=0),
    },
    # Requirement 4b: weekly full report — runs every Monday at midnight.
    'weekly-full-report': {
        'task': 'my_site.tasks.generate_weekly_report',
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
    # Requirement 2: per-user and per-IP rate throttle (second capacity layer)
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day',
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

EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = 'smtp.gmail.com'
EMAIL_PORT          = 587
EMAIL_USE_TLS       = True
EMAIL_HOST_USER     = os.getenv('EMAIL_USER',     'your_email@gmail.com')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_PASSWORD', 'your_app_password')
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