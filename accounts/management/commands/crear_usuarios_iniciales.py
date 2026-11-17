"""Crea los dos primeros usuarios de una base vacía: el administrador y un técnico.

    python manage.py crear_usuarios_iniciales

Pregunta cada dato por pantalla; las contraseñas se escriben ocultas y no se guardan en ningún archivo.
Si el hosting no da terminal interactivo (p. ej. el botón «Run Python script» de cPanel), los datos se pueden
pasar con opciones (--admin-usuario, --admin-correo…) y las contraseñas con las variables de entorno
ACP_ADMIN_CLAVE y ACP_TECNICO_CLAVE (bórralas del panel apenas termine).

No pisa nada: si un usuario ya existe lo deja como está.
"""

import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from accounts.models import User

ROLES = {
    'admin': dict(etiqueta='ADMINISTRADOR', rol=User.Rol.ADMIN, entorno='ACP_ADMIN_CLAVE',
                  usuario='benjamin', nombre='Benjamín'),
    'tecnico': dict(etiqueta='TÉCNICO', rol=User.Rol.TECNICO, entorno='ACP_TECNICO_CLAVE', usuario='', nombre=''),
}


class Command(BaseCommand):
    help = 'Crea el usuario administrador y el técnico iniciales en una base de datos vacía.'

    def add_arguments(self, parser):
        for clave in ROLES:
            for campo in ('usuario', 'nombre', 'apellido', 'correo', 'telefono'):
                parser.add_argument(f'--{clave}-{campo}', default=None)
        parser.add_argument('--solo-admin', action='store_true', help='No crea el técnico.')

    # --- entrada de datos ---------------------------------------------------------
    def _pedir(self, texto, defecto='', requerido=True):
        while True:
            sufijo = f' [{defecto}]' if defecto else ''
            try:
                valor = input(f'  {texto}{sufijo}: ').strip() or defecto
            except EOFError:
                # Sin terminal (p. ej. «Ejecutar script» de cPanel): se usa el valor por defecto o se deja vacío
                if defecto or not requerido:
                    return defecto
                raise CommandError(
                    'No hay terminal para preguntar «' + texto + '». Ejecuta el comando en el terminal de cPanel o '
                    'pasa los datos como opciones (--admin-usuario, --admin-correo, --tecnico-usuario…).')
            if valor or not requerido:
                return valor
            self.stderr.write('    Este dato es obligatorio.')

    def _dato(self, opciones, clave, campo, texto, defecto='', requerido=True):
        valor = opciones.get(f'{clave}_{campo}')
        # Una opción indicada (aunque sea vacía, p. ej. --admin-telefono "") no se vuelve a preguntar
        return valor.strip() if valor is not None else self._pedir(texto, defecto, requerido)

    def _clave(self, config, usuario):
        env = os.environ.get(config['entorno'])
        if env:
            return env
        while True:
            try:
                uno = getpass.getpass(f'  Contraseña para «{usuario}»: ')
                dos = getpass.getpass('  Repite la contraseña: ')
            except EOFError:
                raise CommandError(
                    f'No hay terminal para pedir la contraseña de «{usuario}». Define la variable de entorno '
                    f'{config["entorno"]} (bórrala apenas termine) o usa el terminal de cPanel.')
            if uno != dos:
                self.stderr.write('    Las contraseñas no coinciden, intenta de nuevo.')
                continue
            return uno

    # --- creación -----------------------------------------------------------------
    def _crear(self, clave, opciones):
        config = ROLES[clave]
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n{config["etiqueta"]}'))
        usuario = self._dato(opciones, clave, 'usuario', 'Nombre de usuario (para ingresar)', config['usuario'])
        if User.objects.filter(username=usuario).exists():
            self.stdout.write(self.style.WARNING(f'  «{usuario}» ya existe: se deja como está.'))
            return
        nombre = self._dato(opciones, clave, 'nombre', 'Nombre', config['nombre'])
        apellido = self._dato(opciones, clave, 'apellido', 'Apellido', requerido=False)
        correo = self._dato(opciones, clave, 'correo', 'Correo (sirve para recuperar la contraseña)')
        telefono = self._dato(opciones, clave, 'telefono', 'Teléfono (opcional)', requerido=False)
        try:
            validate_email(correo)
        except ValidationError:
            raise CommandError(f'El correo «{correo}» no es válido.')
        if User.objects.filter(email__iexact=correo).exists():
            raise CommandError(f'Ya hay un usuario con el correo «{correo}».')

        clave_usuario = self._clave(config, usuario)
        candidato = User(username=usuario, first_name=nombre, last_name=apellido, email=correo)
        try:
            validate_password(clave_usuario, candidato)  # mismas reglas que el portal
        except ValidationError as error:
            raise CommandError('Contraseña no válida: ' + ' '.join(error.messages))

        extra = {'is_staff': True, 'is_superuser': True} if config['rol'] == User.Rol.ADMIN else {}
        User.objects.create_user(username=usuario, password=clave_usuario, first_name=nombre, last_name=apellido,
                                 email=correo, telefono=telefono, rol=config['rol'], **extra)
        self.stdout.write(self.style.SUCCESS(f'  Usuario «{usuario}» creado ({config["etiqueta"].lower()}).'))

    def handle(self, *args, **opciones):
        existentes = User.objects.count()
        self.stdout.write(f'Usuarios actuales en la base de datos: {existentes}.')
        self._crear('admin', opciones)
        if not opciones['solo_admin']:
            self._crear('tecnico', opciones)
        self.stdout.write(self.style.SUCCESS(
            '\nListo. Ingresa en /login/ con esos usuarios. Los clientes y el resto del equipo se crean desde '
            '«Usuarios y roles».'))
