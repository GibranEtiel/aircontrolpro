from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalogo.models import Cliente, Ubicacion
from mantenciones.models import OrdenTrabajo

from .models import Cotizacion, CotizacionItem


def hoy():
    return timezone.localdate()


class DatosBase:
    def setUp(self):
        self.cliente = Cliente.objects.create(nombre='Lucas Diesel', contacto='Nicolás', telefono='9 1234 5678',
                                              email='n@lucas.cl')
        self.sucursal = Ubicacion.objects.create(cliente=self.cliente, nombre='Oficinas')
        self.admin = User.objects.create_user('admin', password='x', rol=User.Rol.ADMIN, email='admin@acp.cl')
        self.tecnico = User.objects.create_user('tec', password='x', rol=User.Rol.TECNICO)
        self.usuario_cliente = User.objects.create_user('cli', password='x', rol=User.Rol.CLIENTE,
                                                        cliente=self.cliente)

    def cotizacion(self, dias, **extra):
        c = Cotizacion.objects.create(cliente=self.cliente, titulo=f'Trabajo hace {dias} d',
                                      fecha=hoy() - timedelta(days=dias), **extra)
        CotizacionItem.objects.create(cotizacion=c, descripcion='Mantención', cantidad=2, precio_unitario=50000)
        return c

    # (las pruebas siguen en CotizacionesTests)


class CotizacionesTests(DatosBase, TestCase):
    def test_numeracion_y_montos(self):
        c = self.cotizacion(0)
        self.assertEqual(c.numero, f'COT-{hoy().year}-0001')
        self.assertEqual(self.cotizacion(0).numero, f'COT-{hoy().year}-0002')
        self.assertEqual((c.neto, c.iva, c.total), (Decimal(100000), Decimal(19000), Decimal(119000)))

    def test_alerta_solo_pasados_los_tres_dias(self):
        reciente, limite, vieja = self.cotizacion(2), self.cotizacion(3), self.cotizacion(4)
        self.assertEqual(set(Cotizacion.objects.por_llamar()), {vieja})
        self.assertTrue(vieja.por_llamar)
        self.assertFalse(limite.por_llamar)
        self.assertFalse(reciente.por_llamar)

    def test_solo_las_pendientes_se_alertan(self):
        self.cotizacion(10, estado=Cotizacion.Estado.ACEPTADA)
        self.cotizacion(10, estado=Cotizacion.Estado.RECHAZADA)
        self.assertFalse(Cotizacion.objects.por_llamar().exists())

    def test_registrar_llamada_la_saca_de_la_alerta_unos_dias(self):
        c = self.cotizacion(10)
        self.client.force_login(self.admin)
        r = self.client.post(reverse('seguimiento_agregar', args=[c.pk]),
                             {'medio': 'llamada', 'nota': 'Lo ve el jueves'})
        self.assertRedirects(r, c.get_absolute_url())
        c.refresh_from_db()
        self.assertEqual(c.ultimo_contacto, hoy())
        self.assertFalse(Cotizacion.objects.por_llamar().exists())
        # pasados más de 3 días desde la llamada vuelve a avisar
        Cotizacion.objects.filter(pk=c.pk).update(ultimo_contacto=hoy() - timedelta(days=4))
        self.assertEqual(list(Cotizacion.objects.por_llamar()), [c])

    def test_dashboard_y_menu_avisan_con_datos_de_contacto(self):
        self.cotizacion(5)
        self.client.force_login(self.admin)
        html = self.client.get(reverse('home')).content.decode()
        self.assertIn('Cotizaciones por llamar', html)
        self.assertIn('tel:912345678', html)
        self.assertIn('wa.me/56912345678', html)
        self.assertIn('nav-pill', html)

    def test_solo_el_administrador_accede(self):
        c = self.cotizacion(0)
        for usuario in (self.tecnico, self.usuario_cliente):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('cotizaciones')).status_code, 403)
            self.assertEqual(self.client.get(c.get_absolute_url()).status_code, 403)
            self.assertEqual(
                self.client.post(reverse('cotizacion_estado', args=[c.pk]), {'accion': 'aceptar'}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('cotizaciones')).status_code, 302)

    def test_crear_con_items_desde_el_formulario(self):
        self.client.force_login(self.admin)
        datos = {
            'cliente': self.cliente.pk, 'ubicacion': self.sucursal.pk, 'titulo': 'Instalación split',
            'fecha': hoy().isoformat(), 'validez_dias': 15, 'descripcion': '', 'contacto_nombre': '',
            'contacto_telefono': '', 'contacto_email': '',
            'items-TOTAL_FORMS': 3, 'items-INITIAL_FORMS': 0, 'items-MIN_NUM_FORMS': 1, 'items-MAX_NUM_FORMS': 1000,
            'items-0-descripcion': 'Split 12000 BTU', 'items-0-cantidad': '1', 'items-0-precio_unitario': '350000',
            'items-1-descripcion': 'Instalación', 'items-1-cantidad': '1', 'items-1-precio_unitario': '80000',
            'items-2-descripcion': '', 'items-2-cantidad': '1', 'items-2-precio_unitario': '0',
        }
        r = self.client.post(reverse('cotizacion_nueva'), datos)
        cot = Cotizacion.objects.get()
        self.assertRedirects(r, cot.get_absolute_url())
        self.assertEqual(cot.items.count(), 2)
        self.assertEqual(cot.neto, 430000)
        self.assertEqual(cot.creada_por, self.admin)

    def test_sin_items_no_se_guarda(self):
        self.client.force_login(self.admin)
        datos = {'cliente': self.cliente.pk, 'titulo': 'Vacía', 'fecha': hoy().isoformat(), 'validez_dias': 15,
                 'items-TOTAL_FORMS': 1, 'items-INITIAL_FORMS': 0, 'items-MIN_NUM_FORMS': 1,
                 'items-MAX_NUM_FORMS': 1000}
        r = self.client.post(reverse('cotizacion_nueva'), datos)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Cotizacion.objects.exists())

    def test_aceptar_y_generar_orden_de_trabajo(self):
        c = self.cotizacion(1, ubicacion=self.sucursal)
        self.client.force_login(self.admin)
        self.client.post(reverse('cotizacion_estado', args=[c.pk]), {'accion': 'aceptar'})
        c.refresh_from_db()
        self.assertEqual((c.estado, c.fecha_respuesta), ('aceptada', hoy()))

        url = f"{reverse('orden_nueva')}?cotizacion={c.pk}"
        formulario = self.client.get(url)
        self.assertContains(formulario, c.numero)
        self.assertEqual(formulario.context['form'].initial['monto_neto'], c.neto)
        r = self.client.post(url, {
            'titulo': c.titulo, 'tipo': 'instalacion', 'prioridad': 'media', 'estado': 'pendiente',
            'ubicacion': self.sucursal.pk, 'tecnico': self.tecnico.pk, 'fecha_programada': hoy().isoformat(),
            'monto_neto': '100000', 'costo_materiales': 0, 'costo_mano_obra': 0, 'estado_pago': 'pendiente'})
        orden = OrdenTrabajo.objects.get()
        self.assertRedirects(r, orden.get_absolute_url())
        c.refresh_from_db()
        self.assertEqual(c.orden, orden)
        # ya tiene orden: no se ofrece generar otra
        self.assertNotContains(self.client.get(c.get_absolute_url()), 'Generar orden de trabajo')

    def test_pdf_y_exportacion(self):
        c = self.cotizacion(1)
        self.client.force_login(self.admin)
        r = self.client.get(reverse('cotizacion_pdf', args=[c.pk]))
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))
        for formato in ('pdf', 'xlsx'):
            self.assertEqual(self.client.get(reverse('cotizaciones'), {'export': formato}).status_code, 200)

    def test_aviso_por_correo(self):
        self.cotizacion(6)
        self.cotizacion(1)
        salida = StringIO()
        call_command('avisar_cotizaciones', '--dry-run', stdout=salida)
        self.assertIn('9 1234 5678', salida.getvalue())
        self.assertEqual(len(mail.outbox), 0)
        call_command('avisar_cotizaciones', stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['admin@acp.cl'])
        self.assertIn('Nicolás', mail.outbox[0].body)
        self.assertNotIn('Trabajo hace 1 d', mail.outbox[0].body)

    @override_settings(AVISOS_EMAIL=['yo@aircontrolpro.cl'])
    def test_sin_por_llamar_no_envia_correo(self):
        self.cotizacion(1)
        call_command('avisar_cotizaciones', stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)


class TableroYDashboardTests(DatosBase, TestCase):

    def test_tablero_muestra_tres_columnas_con_totales(self):
        self.cotizacion(5)
        self.cotizacion(1, estado=Cotizacion.Estado.ACEPTADA)
        self.client.force_login(self.admin)
        r = self.client.get(reverse('cotizaciones'), {'vista': 'tablero'})
        self.assertEqual([c['estado'] for c in r.context['columnas']], ['pendiente', 'aceptada', 'rechazada'])
        self.assertEqual([len(c['tarjetas']) for c in r.context['columnas']], [1, 1, 0])
        self.assertContains(r, 'draggable="true"')
        self.assertContains(r, 'Generar orden')  # la aceptada sin orden

    def test_cambio_de_estado_desde_el_tablero_responde_json(self):
        c = self.cotizacion(5)
        self.client.force_login(self.admin)
        url = reverse('cotizacion_estado', args=[c.pk])
        r = self.client.post(url, {'accion': 'aceptar'}, headers={'X-Requested-With': 'fetch'})
        self.assertEqual(r.status_code, 200)
        datos = r.json()
        self.assertEqual((datos['ok'], datos['estado']), (True, 'aceptada'))
        self.assertIn(f'cotizacion={c.pk}', datos['orden_url'])
        c.refresh_from_db()
        self.assertEqual(c.estado, 'aceptada')
        self.assertEqual(self.client.post(url, {'accion': 'volar'}, headers={'X-Requested-With': 'fetch'}).status_code, 400)
        r = self.client.post(url, {'accion': 'reabrir'}, headers={'X-Requested-With': 'fetch'})
        self.assertEqual(r.json()['estado'], 'pendiente')

    def test_datos_del_dashboard_solo_para_admin_y_filtrables(self):
        otro = Cliente.objects.create(nombre='Otro')
        self.cotizacion(5)
        Cotizacion.objects.create(cliente=otro, titulo='Ajena', fecha=hoy())
        for usuario in (self.tecnico, self.usuario_cliente):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('dashboard_datos')).status_code, 403)
        self.client.force_login(self.admin)
        d = self.client.get(reverse('dashboard_datos')).json()
        self.assertEqual(d['cotizaciones']['enviadas'], 2)
        self.assertEqual(len(d['meses']['ingresos']), 12)
        self.assertEqual(len(d['dias']['ingresos']), 30)
        self.assertEqual([p['label'] for p in d['cotizaciones']['embudo']],
                         ['Enviadas', 'Aceptadas', 'Con orden de trabajo'])
        filtrado = self.client.get(reverse('dashboard_datos'), {'cliente': self.cliente.pk}).json()
        self.assertEqual(filtrado['cotizaciones']['enviadas'], 1)
        self.assertEqual(self.client.get(reverse('dashboard_datos'), {'anio': 'x'}).status_code, 200)

    def test_series_del_dashboard_suman_las_ordenes_finalizadas(self):
        OrdenTrabajo.objects.create(titulo='A', cliente=self.cliente, ubicacion=self.sucursal, estado='finalizada',
                                    fecha_programada=hoy(), monto_neto=200000, costo_materiales=50000,
                                    costo_mano_obra=30000, estado_pago='pendiente')
        OrdenTrabajo.objects.create(titulo='B', cliente=self.cliente, ubicacion=self.sucursal, estado='pendiente',
                                    fecha_programada=hoy(), monto_neto=999000)
        self.client.force_login(self.admin)
        d = self.client.get(reverse('dashboard_datos')).json()
        mes = hoy().month - 1
        self.assertEqual(d['meses']['ingresos'][mes], 200000)
        self.assertEqual(d['meses']['utilidad'][mes], 120000)
        self.assertEqual(d['meses']['por_cobrar'][mes], 200000)
        self.assertEqual(d['dias']['ingresos'][-1], 200000)  # hoy es el último de los 30 días
        self.assertEqual(d['kpis']['por_cobrar'], 200000)
        self.assertEqual([a['numero'] for a in d['agenda']], [OrdenTrabajo.objects.get(titulo='B').numero])
