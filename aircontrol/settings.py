"""Configuración de Air Control Pro (producción).

Todo lo que cambia entre tu PC y el servidor se lee de variables de entorno o de un archivo `.env`
en la raíz del proyecto (ver `.env.example`). En cPanel también puedes definirlas en
«Setup Python App → Environment variables».
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env(ruta):
    """Lee un archivo .env sencillo (CLAVE=valor) sin pisar variables ya definidas."""
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding='utf-8').splitlines():
        linea = linea.strip()
        if not linea or linea.startswith('#') or '=' not in linea:
            continue
        clave, valor = linea.split('=', 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env(BASE_DIR / '.env')


def env(nombre, defecto=''):
    return os.environ.get(nombre, defecto)


def env_bool(nombre, defecto=False):
    return env(nombre, '1' if defecto else '0').strip().lower() in ('1', 'true', 'yes', 'si', 'sí')


def env_lista(nombre):
    return [x.strip() for x in env(nombre).split(',') if x.strip()]


DEBUG = env_bool('DJANGO_DEBUG', False)

SECRET_KEY = env('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            'Falta DJANGO_SECRET_KEY. Genera una con: '
            'python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"')
    SECRET_KEY = 'django-insecure-solo-para-desarrollo-local'

ALLOWED_HOSTS = env_lista('DJANGO_ALLOWED_HOSTS')
if DEBUG:
    ALLOWED_HOSTS += ['localhost', '127.0.0.1', '[::1]', 'testserver']
CSRF_TRUSTED_ORIGINS = env_lista('DJANGO_CSRF_TRUSTED_ORIGINS')  # p. ej. https://app.aircontrolpro.cl

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'catalogo',
    'mantenciones',
    'cotizaciones',
    'core',
]

AUTH_USER_MODEL = 'accounts.User'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'aircontrol.urls'

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
                'core.context_processors.alertas',
            ],
        },
    },
]

WSGI_APPLICATION = 'aircontrol.wsgi.application'

# --- Base de datos -----------------------------------------------------------
# Con DB_NAME definido se usa la base creada en cPanel (MySQL/MariaDB por defecto; con
# DB_ENGINE=postgresql, PostgreSQL). Sin DB_NAME se usa SQLite (solo desarrollo local).
if env('DB_NAME'):
    if env('DB_ENGINE', 'mysql').lower().startswith('postgres'):
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': env('DB_NAME'),
                'USER': env('DB_USER', 'postgres'),
                'PASSWORD': env('DB_PASSWORD'),
                'HOST': env('DB_HOST', 'localhost'),
                'PORT': env('DB_PORT', '5432'),
            }
        }
    else:
        try:
            import MySQLdb  # noqa: F401  (mysqlclient, si el servidor lo tiene compilado)
        except ImportError:
            # PyMySQL es 100 % Python y se instala sin compilar en cPanel.
            import pymysql
            pymysql.version_info = (2, 2, 1, 'final', 0)
            pymysql.install_as_MySQLdb()
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.mysql',
                'NAME': env('DB_NAME'),
                'USER': env('DB_USER'),
                'PASSWORD': env('DB_PASSWORD'),
                'HOST': env('DB_HOST', 'localhost'),
                'PORT': env('DB_PORT', '3306'),
                'OPTIONS': {'charset': 'utf8mb4'},
                # Las fechas se guardan en hora de Chile: así MySQL no necesita las tablas de zonas
                # horarias (que en hosting compartido suelen no estar cargadas) para filtrar por mes/año.
                'TIME_ZONE': 'America/Santiago',
                'CONN_MAX_AGE': 60,
            }
        }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': env('SQLITE_PATH') or BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

# --- Archivos estáticos y fotos ----------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

# Las fotos y firmas se sirven desde Django (core.views.media_protegida) solo a usuarios con permiso.
MEDIA_URL = 'media/'
MEDIA_ROOT = Path(env('DJANGO_MEDIA_ROOT')) if env('DJANGO_MEDIA_ROOT') else BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

# Subida de fotos desde el celular
DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024

# --- Seguridad (solo con DEBUG apagado) ----------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SSL_REDIRECT', False)  # actívalo si cPanel no redirige a HTTPS
    SECURE_HSTS_SECONDS = int(env('DJANGO_HSTS_SECONDS', '0'))  # súbelo (p. ej. 31536000) cuando HTTPS esté estable
PASSWORD_RESET_TIMEOUT = 60 * 60 * 2  # el enlace del correo para recuperar la contraseña vale 2 horas
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # los técnicos no deben reingresar a cada rato en terreno

# --- Correo (avisos de cotizaciones por llamar) ---------------------------------
if env('EMAIL_HOST'):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = env('EMAIL_HOST')
    EMAIL_PORT = int(env('EMAIL_PORT', '465'))
    EMAIL_HOST_USER = env('EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
    EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', True)
    EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', False)
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'Air Control Pro <contacto@aircontrolpro.cl>')
# Destinatarios del aviso diario; si está vacío se usa el correo de los usuarios administradores.
AVISOS_EMAIL = env_lista('AVISOS_EMAIL')

# --- Cotizaciones ------------------------------------------------------------
# Una cotización pendiente sin respuesta ni gestión hace más de estos días aparece como «por llamar».
COTIZACION_DIAS_ALERTA = int(env('COTIZACION_DIAS_ALERTA', '3'))
# Datos de la empresa para el PDF de la cotización.
EMPRESA_TELEFONO = env('EMPRESA_TELEFONO', '+56 9 3887 5867')
EMPRESA_EMAIL = env('EMPRESA_EMAIL', 'contacto@aircontrolpro.cl')
EMPRESA_WEB = env('EMPRESA_WEB', 'aircontrolpro.cl')
