import os
import shutil
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import OutputWrapper
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from accounts.models import User
from catalogo.models import Cliente, Ubicacion
from mantenciones.models import FotoInforme, Informe, OrdenTrabajo

MEDIA_TMP = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class MediaProtegidaTests(TestCase):
    """Las fotos de un informe solo las ve quien puede ver ese informe."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TMP, ignore_errors=True)

    def setUp(self):
        self.cli_a, self.cli_b = Cliente.objects.create(nombre='A'), Cliente.objects.create(nombre='B')
        ubicacion = Ubicacion.objects.create(cliente=self.cli_a, nombre='Sucursal')
        self.admin = User.objects.create_user('admin', password='x', rol=User.Rol.ADMIN)
        self.tecnico = User.objects.create_user('tec', password='x', rol=User.Rol.TECNICO)
        self.otro_tecnico = User.objects.create_user('tec2', password='x', rol=User.Rol.TECNICO)
        self.user_a = User.objects.create_user('ca', password='x', rol=User.Rol.CLIENTE, cliente=self.cli_a)
        self.user_b = User.objects.create_user('cb', password='x', rol=User.Rol.CLIENTE, cliente=self.cli_b)
        orden = OrdenTrabajo.objects.create(titulo='OT', cliente=self.cli_a, ubicacion=ubicacion,
                                            tecnico=self.tecnico)
        self.informe = Informe.objects.create(orden=orden, tecnico=self.tecnico)
        buf = BytesIO()
        Image.new('RGB', (50, 50), 'red').save(buf, 'JPEG')
        self.foto = FotoInforme(informe=self.informe)
        self.foto.imagen.save('f.jpg', ContentFile(buf.getvalue()), save=False)
        self.foto.save()
        self.url = '/' + self.foto.imagen.url.lstrip('/')

    def pedir(self, usuario=None):
        self.client.logout()
        if usuario:
            self.client.force_login(usuario)
        return self.client.get(self.url)

    def test_sin_sesion_va_al_login(self):
        r = self.pedir()
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login/', r['Location'])

    def test_admin_y_tecnico_del_informe(self):
        self.assertEqual(self.pedir(self.admin).status_code, 200)
        self.assertEqual(self.pedir(self.tecnico).status_code, 200)
        self.assertEqual(self.pedir(self.otro_tecnico).status_code, 404)

    def test_cliente_solo_ve_informes_emitidos_de_su_empresa(self):
        self.assertEqual(self.pedir(self.user_a).status_code, 404)  # aún en borrador
        Informe.objects.filter(pk=self.informe.pk).update(estado=Informe.Estado.EMITIDO)
        self.assertEqual(self.pedir(self.user_a).status_code, 200)
        self.assertEqual(self.pedir(self.user_b).status_code, 404)


class ConfiguracionDeProduccionTests(SimpleTestCase):
    def test_un_env_con_datos_sin_completar_impide_arrancar_y_dice_cuales(self):
        from aircontrol import settings as ajustes

        with tempfile.TemporaryDirectory() as carpeta:
            env = Path(carpeta) / '.env'
            env.write_text('DB_NAME=mi_base\nDB_USER=PEGA_AQUI_usuario\nDB_PASSWORD=PEGA_AQUI_clave\n', encoding='utf-8')
            with mock.patch.dict(os.environ, {}, clear=False):
                with self.assertRaises(ImproperlyConfigured) as caso:
                    ajustes._cargar_env(env)
                os.environ.pop('DB_NAME', None)
        mensaje = str(caso.exception)
        self.assertIn('DB_USER', mensaje)
        self.assertIn('DB_PASSWORD', mensaje)
        self.assertNotIn('DB_NAME', mensaje)

    def test_un_env_completo_se_carga_y_acepta_simbolos_en_los_valores(self):
        from aircontrol import settings as ajustes

        with tempfile.TemporaryDirectory() as carpeta:
            env = Path(carpeta) / '.env'
            env.write_text('# comentario\nACP_PRUEBA_CLAVE=ab#cd$ef*gh?ij=kl\n', encoding='utf-8')
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop('ACP_PRUEBA_CLAVE', None)
                ajustes._cargar_env(env)
                self.assertEqual(os.environ['ACP_PRUEBA_CLAVE'], 'ab#cd$ef*gh?ij=kl')
                os.environ.pop('ACP_PRUEBA_CLAVE', None)


class ProbarConexionTests(TestCase):
    def ejecutar(self):
        salida = StringIO()
        call_command('probar_conexion', stdout=salida, stderr=StringIO())
        return salida.getvalue()

    def test_informa_que_conecta_y_el_estado_de_la_base(self):
        texto = self.ejecutar()
        self.assertIn('Conexión correcta', texto)
        self.assertIn('Motor: sqlite', texto)
        self.assertIn('tablas', texto)  # la base de pruebas ya tiene las tablas

    def test_las_pistas_orientan_segun_el_error(self):
        from core.management.commands.probar_conexion import _pista

        self.assertIn('TODOS los privilegios', _pista(Exception("(1045, \"Access denied for user 'x'@'localhost'\")")))
        self.assertIn('prefijo de cPanel', _pista(Exception("(1049, \"Unknown database 'x'\")")))
        self.assertIn('localhost', _pista(Exception("(2002, \"Can't connect to server\")")))

    def test_advierte_si_el_servidor_es_muy_antiguo(self):
        from core.management.commands.probar_conexion import Command

        comando = Command(stdout=OutputWrapper(StringIO()))
        for version, avisa in (('10.5.22-MariaDB', True), ('10.6.18-MariaDB', False), ('11.4.2-MariaDB', False),
                               ('5.7.44', True), ('8.0.36', False)):
            salida = StringIO()
            comando.stdout = OutputWrapper(salida)
            comando._revisar_version(version)
            self.assertEqual('ADVERTENCIA' in salida.getvalue(), avisa, version)


class CarpetaDeFotosTests(TestCase):
    def ejecutar(self):
        salida = StringIO()
        call_command('probar_conexion', stdout=salida, stderr=StringIO())
        return salida.getvalue()

    def test_crea_la_carpeta_de_fotos_si_no_existe(self):
        with tempfile.TemporaryDirectory() as base:
            destino = Path(base) / 'aircontrolpro_media'
            with override_settings(MEDIA_ROOT=destino):
                texto = self.ejecutar()
            self.assertTrue(destino.is_dir())
        self.assertIn('se creó', texto)
        self.assertIn('se puede escribir', texto)

    def test_avisa_si_la_carpeta_no_se_puede_crear(self):
        with tempfile.TemporaryDirectory() as base:
            archivo = Path(base) / 'es_un_archivo'
            archivo.write_text('x')
            with override_settings(MEDIA_ROOT=archivo / 'media'):  # bajo un archivo no se puede crear una carpeta
                texto = self.ejecutar()
        self.assertIn('no se pudo crear', texto)

    def test_la_ruta_con_tilde_se_resuelve_a_la_carpeta_personal(self):
        resuelta = Path('~/aircontrolpro_media').expanduser()
        self.assertTrue(resuelta.is_absolute())
        self.assertEqual(resuelta.name, 'aircontrolpro_media')
        self.assertNotIn('~', str(resuelta))

    def test_confirma_si_la_carpeta_existe_y_se_puede_escribir(self):
        with tempfile.TemporaryDirectory() as base:
            with override_settings(MEDIA_ROOT=Path(base)):
                texto = self.ejecutar()
        self.assertIn('se puede escribir', texto)
