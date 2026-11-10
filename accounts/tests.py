import re

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from catalogo.models import Cliente

from .models import User


class RecuperarContrasenaTests(TestCase):
    def setUp(self):
        self.tecnico = User.objects.create_user('daniel', password='ClaveVieja#2026', rol=User.Rol.TECNICO,
                                                email='daniel@aircontrolpro.cl', first_name='Daniel')

    def pedir(self, email):
        return self.client.post(reverse('password_reset'), {'email': email})

    def enlace(self):
        return re.search(r'https?://\S+/recuperar/\S+/\S+/', mail.outbox[0].body).group(0)

    def test_el_login_ofrece_recuperar_la_contrasena(self):
        self.assertContains(self.client.get(reverse('login')), reverse('password_reset'))

    def test_llega_un_correo_con_un_enlace_que_permite_elegir_una_clave_nueva(self):
        r = self.pedir('daniel@aircontrolpro.cl')
        self.assertRedirects(r, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, ['daniel@aircontrolpro.cl'])
        self.assertIn('restablece tu contraseña', correo.subject)
        self.assertIn('daniel', correo.body)
        self.assertNotIn('ClaveVieja', correo.body)

        enlace = self.enlace().replace('http://testserver', '')
        r = self.client.get(enlace, follow=True)  # Django guarda el token en la sesión y redirige
        self.assertContains(r, 'Elige tu nueva contraseña')
        url_clave = r.redirect_chain[-1][0]

        # Una clave débil se rechaza; una buena la cambia
        r = self.client.post(url_clave, {'new_password1': '12345678', 'new_password2': '12345678'})
        self.assertEqual(r.status_code, 200)
        r = self.client.post(url_clave, {'new_password1': 'NuevaClave#2026', 'new_password2': 'NuevaClave#2026'})
        self.assertRedirects(r, reverse('password_reset_complete'))
        self.assertTrue(self.client.login(username='daniel', password='NuevaClave#2026'))
        self.client.logout()
        self.assertFalse(self.client.login(username='daniel', password='ClaveVieja#2026'))

        # El enlace sirve una sola vez
        r = self.client.get(enlace, follow=True)
        self.assertContains(r, 'Este enlace ya no sirve')

    def test_correo_desconocido_no_revela_nada_ni_envia(self):
        r = self.pedir('nadie@ejemplo.cl')
        self.assertRedirects(r, reverse('password_reset_done'))  # misma respuesta que con un correo válido
        self.assertEqual(len(mail.outbox), 0)

    def test_usuario_inactivo_no_recibe_enlace(self):
        User.objects.filter(pk=self.tecnico.pk).update(is_active=False)
        self.pedir('daniel@aircontrolpro.cl')
        self.assertEqual(len(mail.outbox), 0)

    def test_enlace_manipulado_no_sirve(self):
        self.pedir('daniel@aircontrolpro.cl')
        enlace = self.enlace().replace('http://testserver', '')
        r = self.client.get(enlace[:-3] + 'xx/', follow=True)
        self.assertContains(r, 'Este enlace ya no sirve')

    def test_cambiar_contrasena_con_sesion_iniciada(self):
        self.client.force_login(self.tecnico)
        pagina = self.client.get(reverse('cambiar_clave'))
        self.assertContains(pagina, 'form-control')  # campos con el estilo del portal
        self.assertContains(pagina, '¿Olvidaste tu contraseña actual?')
        r = self.client.post(reverse('cambiar_clave'), {
            'old_password': 'ClaveVieja#2026', 'new_password1': 'Otra#Clave2027', 'new_password2': 'Otra#Clave2027'})
        self.assertRedirects(r, reverse('home'), fetch_redirect_response=False)
        self.tecnico.refresh_from_db()
        self.assertTrue(self.tecnico.check_password('Otra#Clave2027'))


class CorreoDeUsuariosTests(TestCase):
    """Sin correo no hay recuperación: el administrador debe registrarlo, y sin repetirse."""

    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', rol=User.Rol.ADMIN, email='admin@aircontrolpro.cl')
        self.cliente = Cliente.objects.create(nombre='Lucas')
        self.client.force_login(self.admin)

    def datos(self, **extra):
        return {'username': 'camila', 'first_name': 'Camila', 'last_name': 'Rojas', 'email': 'camila@acp.cl',
                'telefono': '', 'rol': 'tecnico', 'cliente': '', 'password1': 'Camila#Clave2026',
                'password2': 'Camila#Clave2026', **extra}

    def test_el_correo_es_obligatorio_al_crear_un_usuario(self):
        r = self.client.post(reverse('usuario_nuevo'), self.datos(email=''))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username='camila').exists())
        r = self.client.post(reverse('usuario_nuevo'), self.datos())
        self.assertRedirects(r, reverse('usuarios'))
        self.assertEqual(User.objects.get(username='camila').email, 'camila@acp.cl')

    def test_no_se_repite_el_correo_entre_usuarios(self):
        r = self.client.post(reverse('usuario_nuevo'), self.datos(email='ADMIN@aircontrolpro.cl'))
        self.assertContains(r, 'Ya hay un usuario con este correo')
        self.assertFalse(User.objects.filter(username='camila').exists())

    def test_editar_un_usuario_conserva_su_propio_correo(self):
        r = self.client.post(reverse('usuario_editar', args=[self.admin.pk]), {
            'first_name': 'Beni', 'last_name': '', 'email': 'admin@aircontrolpro.cl', 'telefono': '', 'rol': 'admin',
            'cliente': '', 'is_active': 'on'})
        self.assertRedirects(r, reverse('usuarios'))
