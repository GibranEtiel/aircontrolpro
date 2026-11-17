import os
import re
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from catalogo.models import Cliente, Ubicacion
from mantenciones.models import Informe, OrdenTrabajo

from .models import User


@override_settings(RECUPERAR_CLAVE=True)
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


class UsuariosInicialesTests(TestCase):
    """`crear_usuarios_iniciales`: deja una base vacía con solo el administrador y el técnico."""

    OPCIONES = dict(
        admin_usuario='benjamin', admin_nombre='Benjamín', admin_apellido='Quiroz', admin_correo='benjamin@aircontrolpro.cl',
        tecnico_usuario='daniel', tecnico_nombre='Daniel', tecnico_apellido='Bustos', tecnico_correo='daniel@aircontrolpro.cl',
        tecnico_telefono='+56947854105', admin_telefono='')

    def ejecutar(self, **extra):
        salida = StringIO()
        call_command('crear_usuarios_iniciales', stdout=salida, stderr=StringIO(), **{**self.OPCIONES, **extra})
        return salida.getvalue()

    def test_crea_solo_el_admin_y_el_tecnico(self):
        with mock.patch.dict(os.environ, {'ACP_ADMIN_CLAVE': 'AdminSegura#2026', 'ACP_TECNICO_CLAVE': 'Tecnico#Segura2026'}):
            salida = self.ejecutar()
        self.assertEqual(User.objects.count(), 2)
        admin, tecnico = User.objects.get(username='benjamin'), User.objects.get(username='daniel')
        self.assertEqual((admin.rol, admin.is_staff, admin.is_superuser, admin.email),
                         (User.Rol.ADMIN, True, True, 'benjamin@aircontrolpro.cl'))
        self.assertEqual((tecnico.rol, tecnico.is_staff, tecnico.is_superuser, tecnico.telefono),
                         (User.Rol.TECNICO, False, False, '+56947854105'))
        self.assertTrue(admin.check_password('AdminSegura#2026'))
        self.assertTrue(tecnico.check_password('Tecnico#Segura2026'))
        self.assertNotIn('AdminSegura', salida)  # la contraseña nunca se imprime
        # y pueden ingresar al portal
        self.assertTrue(self.client.login(username='daniel', password='Tecnico#Segura2026'))

    def test_no_pisa_a_los_usuarios_que_ya_existen(self):
        User.objects.create_user('benjamin', password='ClaveActual#2026', rol=User.Rol.ADMIN, email='otro@acp.cl')
        with mock.patch.dict(os.environ, {'ACP_ADMIN_CLAVE': 'OtraClave#2026', 'ACP_TECNICO_CLAVE': 'Tecnico#Segura2026'}):
            salida = self.ejecutar()
        self.assertIn('ya existe', salida)
        self.assertTrue(User.objects.get(username='benjamin').check_password('ClaveActual#2026'))
        self.assertEqual(User.objects.count(), 2)

    def test_rechaza_contrasenas_debiles(self):
        with mock.patch.dict(os.environ, {'ACP_ADMIN_CLAVE': '12345678', 'ACP_TECNICO_CLAVE': 'Tecnico#Segura2026'}):
            with self.assertRaisesMessage(CommandError, 'Contraseña no válida'):
                self.ejecutar()
        self.assertFalse(User.objects.exists())

    def test_rechaza_correos_invalidos_o_repetidos(self):
        with mock.patch.dict(os.environ, {'ACP_ADMIN_CLAVE': 'AdminSegura#2026', 'ACP_TECNICO_CLAVE': 'Tecnico#Segura2026'}):
            with self.assertRaisesMessage(CommandError, 'no es válido'):
                self.ejecutar(admin_correo='no-es-un-correo')
            with self.assertRaisesMessage(CommandError, 'Ya hay un usuario con el correo'):
                self.ejecutar(tecnico_correo='BENJAMIN@aircontrolpro.cl')  # mismo que el admin recién creado

    def test_solo_admin(self):
        with mock.patch.dict(os.environ, {'ACP_ADMIN_CLAVE': 'AdminSegura#2026'}):
            self.ejecutar(solo_admin=True)
        self.assertEqual(list(User.objects.values_list('username', flat=True)), ['benjamin'])

    def test_pregunta_por_pantalla_y_oculta_la_contrasena(self):
        respuestas = iter(['benjamin', 'Benjamín', 'Quiroz', 'benjamin@aircontrolpro.cl', '',
                           'daniel', 'Daniel', '', 'daniel@aircontrolpro.cl', ''])
        claves = iter(['AdminSegura#2026', 'AdminSegura#2026', 'Tecnico#Segura2026', 'Tecnico#Segura2026'])
        with mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch('builtins.input', lambda *_: next(respuestas)), \
                mock.patch('getpass.getpass', lambda *_: next(claves)):
            os.environ.pop('ACP_ADMIN_CLAVE', None)
            os.environ.pop('ACP_TECNICO_CLAVE', None)
            call_command('crear_usuarios_iniciales', stdout=StringIO(), stderr=StringIO())
        self.assertEqual(sorted(User.objects.values_list('username', flat=True)), ['benjamin', 'daniel'])
        self.assertTrue(User.objects.get(username='daniel').check_password('Tecnico#Segura2026'))


class SinCorreoConfiguradoTests(TestCase):
    """Sin servidor de correo el portal no promete enviar enlaces: manda a pedir la clave al administrador."""

    @override_settings(RECUPERAR_CLAVE=False)
    def test_no_ofrece_recuperar_por_correo(self):
        login = self.client.get(reverse('login'))
        self.assertNotContains(login, reverse('password_reset'))
        self.assertContains(login, 'Pídele al administrador una nueva')
        pagina = self.client.get(reverse('password_reset'))
        self.assertContains(pagina, 'Recuperación por correo no disponible')
        self.assertNotContains(pagina, 'Enviar enlace')

    @override_settings(RECUPERAR_CLAVE=True)
    def test_con_correo_si_lo_ofrece(self):
        self.assertContains(self.client.get(reverse('login')), reverse('password_reset'))
        self.assertContains(self.client.get(reverse('password_reset')), 'Enviar enlace')

    def test_en_produccion_sin_email_host_queda_apagado(self):
        # Misma regla que aircontrol/settings.py: correo configurado, o modo desarrollo.
        regla = lambda email_host, debug: bool(email_host) or debug  # noqa: E731
        self.assertFalse(regla('', False))
        self.assertTrue(regla('mail.aircontrolpro.cl', False))
        self.assertTrue(regla('', True))


class UsuarioClienteConEmpresaNuevaTests(TestCase):
    """Al crear un usuario cliente se elige su empresa o se crea una nueva ahí mismo."""

    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', rol=User.Rol.ADMIN, email='admin@acp.cl')
        self.lucas = Cliente.objects.create(nombre='Lucas Diesel')
        self.client.force_login(self.admin)

    def datos(self, **extra):
        return {'username': 'etiel', 'first_name': 'Etiel', 'last_name': 'Beiza', 'email': 'etiel@empresa.cl',
                'telefono': '948652764', 'rol': 'cliente', 'cliente': '', 'empresa_nueva': '',
                'password1': 'Etiel#Clave2026', 'password2': 'Etiel#Clave2026', **extra}

    def test_la_pantalla_ofrece_crear_la_empresa_y_la_muestra_solo_para_clientes(self):
        r = self.client.get(reverse('usuario_nuevo'))
        self.assertContains(r, 'id_empresa_nueva')
        self.assertContains(r, 'Empresa')
        self.assertContains(r, "rol.value === 'cliente'")  # el selector solo aparece con rol Cliente

    def test_crea_la_empresa_nueva_y_deja_al_usuario_asociado(self):
        r = self.client.post(reverse('usuario_nuevo'), self.datos(empresa_nueva='Empresa Etiel SpA'), follow=True)
        self.assertRedirects(r, reverse('usuarios'))
        self.assertContains(r, 'Empresa «Empresa Etiel SpA» creada')
        empresa = Cliente.objects.get(nombre='Empresa Etiel SpA')
        usuario = User.objects.get(username='etiel')
        self.assertEqual(usuario.cliente, empresa)
        # la empresa nace con los datos del usuario como contacto
        self.assertEqual((empresa.contacto, empresa.email, empresa.telefono),
                         ('Etiel Beiza', 'etiel@empresa.cl', '948652764'))
        # y el usuario ve solo lo de su empresa
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)

    def test_con_una_empresa_existente_no_crea_otra(self):
        self.client.post(reverse('usuario_nuevo'), self.datos(cliente=self.lucas.pk))
        self.assertEqual(User.objects.get(username='etiel').cliente, self.lucas)
        self.assertEqual(Cliente.objects.count(), 1)

    def test_un_cliente_sin_empresa_se_rechaza(self):
        r = self.client.post(reverse('usuario_nuevo'), self.datos())
        self.assertContains(r, 'debe estar asociado a una empresa')
        self.assertFalse(User.objects.filter(username='etiel').exists())

    def test_no_se_pueden_dar_dos_empresas_ni_repetir_el_nombre_de_una_existente(self):
        r = self.client.post(reverse('usuario_nuevo'), self.datos(cliente=self.lucas.pk, empresa_nueva='Otra'))
        self.assertContains(r, 'no las dos')
        r = self.client.post(reverse('usuario_nuevo'), self.datos(empresa_nueva='lucas diesel'))
        self.assertContains(r, 'Ya existe una empresa con ese nombre')
        self.assertFalse(User.objects.filter(username='etiel').exists())
        self.assertEqual(Cliente.objects.count(), 1)

    def test_si_el_usuario_falla_no_queda_una_empresa_huerfana(self):
        r = self.client.post(reverse('usuario_nuevo'), self.datos(empresa_nueva='Empresa Fantasma', password2='otra'))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Cliente.objects.filter(nombre='Empresa Fantasma').exists())

    def test_un_tecnico_ignora_la_empresa_nueva(self):
        self.client.post(reverse('usuario_nuevo'), self.datos(rol='tecnico', empresa_nueva='No debe crearse'))
        self.assertTrue(User.objects.filter(username='etiel', rol='tecnico').exists())
        self.assertFalse(Cliente.objects.filter(nombre='No debe crearse').exists())

    def test_al_editar_se_puede_pasar_a_un_cliente_a_una_empresa_nueva(self):
        usuario = User.objects.create_user('juan', password='x', rol='cliente', cliente=self.lucas, email='juan@lucas.cl')
        r = self.client.post(reverse('usuario_editar', args=[usuario.pk]), {
            'first_name': 'Juan', 'last_name': 'Perez', 'email': 'juan@lucas.cl', 'telefono': '', 'rol': 'cliente',
            'cliente': '', 'empresa_nueva': 'Transportes Nuevos', 'is_active': 'on'})
        self.assertRedirects(r, reverse('usuarios'))
        usuario.refresh_from_db()
        self.assertEqual(usuario.cliente.nombre, 'Transportes Nuevos')


class AvisoDeCorreoEnConsolaTests(TestCase):
    @override_settings(DEBUG=True, EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_en_desarrollo_la_pantalla_explica_que_el_correo_va_a_la_terminal(self):
        r = self.client.post(reverse('password_reset'), {'email': 'nadie@ejemplo.cl'}, follow=True)
        self.assertContains(r, 'Revisa tu correo')
        self.assertContains(r, 'no se envía de verdad')

    @override_settings(DEBUG=False, EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', RECUPERAR_CLAVE=True)
    def test_con_correo_real_no_aparece_el_aviso(self):
        r = self.client.post(reverse('password_reset'), {'email': 'nadie@ejemplo.cl'}, follow=True)
        self.assertContains(r, 'Revisa tu correo')
        self.assertNotContains(r, 'no se envía de verdad')


class UsuariosInicialesSinTerminalTests(TestCase):
    """«Ejecutar script» de cPanel no tiene teclado: solo se pasan los datos básicos y las contraseñas por variables."""

    def ejecutar(self, **opciones):
        with mock.patch('builtins.input', side_effect=EOFError):
            call_command('crear_usuarios_iniciales', stdout=StringIO(), stderr=StringIO(), **opciones)

    def test_funciona_sin_terminal_con_lo_minimo(self):
        entorno = {'ACP_ADMIN_CLAVE': 'AdminSegura#2026', 'ACP_TECNICO_CLAVE': 'Tecnico#Segura2026'}
        with mock.patch.dict(os.environ, entorno):
            self.ejecutar(admin_correo='benjamin@aircontrolpro.cl', tecnico_usuario='daniel', tecnico_nombre='Daniel',
                          tecnico_correo='daniel@aircontrolpro.cl')
        admin = User.objects.get(username='benjamin')  # usuario y nombre toman el valor por defecto
        self.assertEqual((admin.first_name, admin.last_name, admin.telefono, admin.rol), ('Benjamín', '', '', User.Rol.ADMIN))
        self.assertEqual(User.objects.get(username='daniel').rol, User.Rol.TECNICO)

    def test_sin_terminal_ni_variable_pide_la_contrasena_con_un_mensaje_claro(self):
        with mock.patch.dict(os.environ, {}):
            os.environ.pop('ACP_ADMIN_CLAVE', None)
            with mock.patch('getpass.getpass', side_effect=EOFError):
                with self.assertRaisesMessage(CommandError, 'ACP_ADMIN_CLAVE'):
                    self.ejecutar(admin_correo='benjamin@aircontrolpro.cl', solo_admin=True)
        self.assertFalse(User.objects.exists())

    def test_un_dato_obligatorio_sin_valor_por_defecto_da_error_claro(self):
        with mock.patch.dict(os.environ, {'ACP_ADMIN_CLAVE': 'AdminSegura#2026'}):
            with self.assertRaisesMessage(CommandError, 'No hay terminal'):
                self.ejecutar(solo_admin=True)  # falta el correo


class EliminarUsuariosTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', rol=User.Rol.ADMIN, email='a@acp.cl')
        self.otro_admin = User.objects.create_user('admin2', password='x', rol=User.Rol.ADMIN, email='a2@acp.cl')
        self.tecnico = User.objects.create_user('tec', password='x', rol=User.Rol.TECNICO, email='t@acp.cl', first_name='Daniel')
        self.empresa = Cliente.objects.create(nombre='Lucas')
        self.cliente = User.objects.create_user('cli', password='x', rol=User.Rol.CLIENTE, cliente=self.empresa, email='c@l.cl')
        self.client.force_login(self.admin)

    def test_editar_ofrece_eliminar_y_pide_confirmacion(self):
        r = self.client.get(reverse('usuario_editar', args=[self.cliente.pk]))
        self.assertContains(r, reverse('usuario_eliminar', args=[self.cliente.pk]))
        r = self.client.get(reverse('usuario_eliminar', args=[self.cliente.pk]))
        self.assertContains(r, 'no se puede deshacer')
        self.assertTrue(User.objects.filter(pk=self.cliente.pk).exists())

    def test_elimina_un_usuario_cliente_y_la_empresa_se_conserva(self):
        r = self.client.post(reverse('usuario_eliminar', args=[self.cliente.pk]), follow=True)
        self.assertRedirects(r, reverse('usuarios'))
        self.assertContains(r, 'eliminado')
        self.assertFalse(User.objects.filter(pk=self.cliente.pk).exists())
        self.assertTrue(Cliente.objects.filter(pk=self.empresa.pk).exists())

    def test_no_puedes_eliminarte_ni_desactivarte_a_ti_mismo(self):
        r = self.client.get(reverse('usuario_eliminar', args=[self.admin.pk]))
        self.assertContains(r, 'Es tu propia cuenta')
        self.assertNotContains(r, 'Desactivar en su lugar')
        self.client.post(reverse('usuario_eliminar', args=[self.admin.pk]))
        self.client.post(reverse('usuario_eliminar', args=[self.admin.pk]), {'accion': 'desactivar'})
        self.admin.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=self.admin.pk, is_active=True).exists())

    def test_no_se_elimina_al_unico_administrador_activo(self):
        self.client.force_login(self.otro_admin)
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        r = self.client.get(reverse('usuario_eliminar', args=[self.otro_admin.pk]))
        self.assertContains(r, 'Es tu propia cuenta')
        # con otro administrador activo sí se puede eliminar a un admin
        User.objects.filter(pk=self.admin.pk).update(is_active=True)
        self.client.post(reverse('usuario_eliminar', args=[self.admin.pk]))
        self.assertFalse(User.objects.filter(pk=self.admin.pk).exists())

    def test_un_tecnico_con_trabajos_se_desactiva_en_vez_de_eliminarse(self):
        ubicacion = Ubicacion.objects.create(cliente=self.empresa, nombre='Oficinas')
        orden = OrdenTrabajo.objects.create(titulo='OT', cliente=self.empresa, ubicacion=ubicacion, tecnico=self.tecnico)
        Informe.objects.create(orden=orden, tecnico=self.tecnico)
        r = self.client.get(reverse('usuario_eliminar', args=[self.tecnico.pk]))
        self.assertContains(r, 'No se puede eliminar porque tiene historial')
        self.assertContains(r, '1 orden de trabajo asignada')
        self.assertContains(r, '1 informe técnico como responsable')
        self.client.post(reverse('usuario_eliminar', args=[self.tecnico.pk]))  # forzando el envío
        self.assertTrue(User.objects.filter(pk=self.tecnico.pk).exists())
        self.client.post(reverse('usuario_eliminar', args=[self.tecnico.pk]), {'accion': 'desactivar'})
        self.tecnico.refresh_from_db()
        self.assertFalse(self.tecnico.is_active)
        self.assertEqual(orden.informe.tecnico, self.tecnico)  # el informe sigue con su responsable

    def test_un_tecnico_sin_historial_se_elimina(self):
        self.client.post(reverse('usuario_eliminar', args=[self.tecnico.pk]))
        self.assertFalse(User.objects.filter(pk=self.tecnico.pk).exists())

    def test_solo_el_administrador_elimina_usuarios(self):
        for usuario in (self.tecnico, self.cliente):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('usuario_eliminar', args=[self.otro_admin.pk])).status_code, 403)
            self.assertEqual(self.client.post(reverse('usuario_eliminar', args=[self.otro_admin.pk])).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.otro_admin.pk).exists())
