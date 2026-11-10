import shutil
import tempfile
from io import BytesIO

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
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
