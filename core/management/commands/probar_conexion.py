"""Comprueba la conexión a la base de datos y explica qué hacer si falla.

    python manage.py probar_conexion
"""

import re
import tempfile

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.utils import OperationalError


def _pista(error):
    """Traduce los errores más comunes de MySQL a qué revisar."""
    texto = str(error)
    if '1045' in texto or 'Access denied' in texto:
        return ('Usuario o contraseña incorrectos, o el usuario no tiene permisos sobre esta base. Revisa DB_USER y '
                'DB_PASSWORD (con el prefijo de cPanel) y que en «Bases de datos MySQL → Agregar usuario a la base '
                'de datos» el usuario esté asignado a la base con TODOS los privilegios.')
    if '1049' in texto or 'Unknown database' in texto:
        return 'La base no existe con ese nombre. Revisa DB_NAME: debe incluir el prefijo de cPanel, tal cual aparece.'
    if '2002' in texto or '2003' in texto or '2005' in texto or 'Can\'t connect' in texto or 'Name or service' in texto:
        return ('No se alcanza el servidor MySQL. Si la app corre en el mismo cPanel usa DB_HOST=localhost; si la base '
                'está en otro servidor, autoriza la conexión en cPanel → Remote MySQL.')
    return 'Revisa DB_NAME, DB_USER, DB_PASSWORD, DB_HOST y DB_PORT en el archivo .env.'


class Command(BaseCommand):
    help = 'Prueba la conexión a la base de datos configurada y muestra su estado.'

    def handle(self, *args, **opciones):
        bd = settings.DATABASES[DEFAULT_DB_ALIAS]
        conexion = connections[DEFAULT_DB_ALIAS]
        motor = conexion.vendor
        self.stdout.write(f'Motor: {motor}')
        self.stdout.write(f'Base: {bd.get("NAME")}')
        if motor != 'sqlite':
            self.stdout.write(f'Servidor: {bd.get("HOST")}:{bd.get("PORT")} · usuario: {bd.get("USER")}')

        try:
            conexion.ensure_connection()
        except OperationalError as error:
            self.stderr.write(self.style.ERROR(f'\nNO CONECTA: {error}'))
            self.stderr.write(_pista(error))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS('\nConexión correcta.'))

        with conexion.cursor() as cursor:
            if motor == 'sqlite':
                cursor.execute('SELECT sqlite_version()')
                self.stdout.write(f'Versión: SQLite {cursor.fetchone()[0]}')
            else:
                cursor.execute('SELECT VERSION()')
                version = cursor.fetchone()[0]
                self.stdout.write(f'Versión del servidor: {version}')
                self._revisar_version(version)
        tablas = conexion.introspection.table_names()
        if not tablas:
            self.stdout.write('La base está vacía: ejecuta  python manage.py migrate  para crear las tablas.')
        else:
            self.stdout.write(f'La base tiene {len(tablas)} tablas.')
        self._revisar_carpeta_de_fotos()

    def _revisar_carpeta_de_fotos(self):
        """Las fotos y firmas se guardan en MEDIA_ROOT: debe existir y poder escribirse."""
        carpeta = settings.MEDIA_ROOT
        self.stdout.write(f'\nCarpeta de fotos: {carpeta}')
        if not carpeta.exists():
            try:
                carpeta.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.stdout.write(self.style.WARNING(
                    'ADVERTENCIA: la carpeta no existe y no se pudo crear. Revisa DJANGO_MEDIA_ROOT en el .env o '
                    'créala en el Administrador de archivos de cPanel (fuera de `public_html`).'))
                return
            self.stdout.write('La carpeta no existía: se creó.')
        try:
            with tempfile.TemporaryFile(dir=carpeta):
                pass
        except OSError:
            self.stdout.write(self.style.WARNING(
                'ADVERTENCIA: la carpeta existe pero la app no puede escribir en ella (revisa los permisos).'))
            return
        self.stdout.write(self.style.SUCCESS('La carpeta existe y se puede escribir.'))

    def _revisar_version(self, version):
        """Django 6.1 necesita MariaDB 10.6+ o MySQL 8.0.11+."""
        numeros = tuple(int(x) for x in re.findall(r'\d+', version)[:3] if x) or (0,)
        if 'mariadb' in version.lower():
            if numeros < (10, 6):
                self.stdout.write(self.style.WARNING(
                    'ADVERTENCIA: Django 6.1 exige MariaDB 10.6 o superior. Pídele a tu hosting que actualice, o usa '
                    '`Django>=5.2,<5.3` en requirements.txt.'))
        elif numeros < (8, 0, 11):
            self.stdout.write(self.style.WARNING(
                'ADVERTENCIA: Django 6.1 exige MySQL 8.0.11 o superior. Pídele a tu hosting que actualice, o usa '
                '`Django>=5.2,<5.3` en requirements.txt.'))
