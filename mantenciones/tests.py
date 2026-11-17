import shutil
import tempfile
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from PIL import Image

from accounts.models import User
from catalogo.models import Activo, Cliente, Ubicacion

from .models import TAREAS_CLAVES, FotoInforme, Informe, OrdenTrabajo

MEDIA_TMP = tempfile.mkdtemp()


def imagen_de_prueba():
    buf = BytesIO()
    Image.new('RGB', (2400, 1800), 'steelblue').save(buf, 'JPEG')
    return SimpleUploadedFile('foto.jpg', buf.getvalue(), content_type='image/jpeg')


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class FlujoMantencionTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TMP, ignore_errors=True)

    def setUp(self):
        self.cli_a = Cliente.objects.create(nombre='Cliente A')
        self.cli_b = Cliente.objects.create(nombre='Cliente B')
        self.ub_a = Ubicacion.objects.create(cliente=self.cli_a, nombre='Sucursal A')
        self.ub_b = Ubicacion.objects.create(cliente=self.cli_b, nombre='Sucursal B')
        self.equipo = Activo.objects.create(ubicacion=self.ub_a, codigo='A-1', nombre='Split')
        self.admin = User.objects.create_user('admin', password='x', rol=User.Rol.ADMIN)
        self.tecnico = User.objects.create_user('tec', password='x', rol=User.Rol.TECNICO)
        self.otro_tecnico = User.objects.create_user('tec2', password='x', rol=User.Rol.TECNICO)
        self.user_a = User.objects.create_user('ca', password='x', rol=User.Rol.CLIENTE, cliente=self.cli_a)
        self.user_b = User.objects.create_user('cb', password='x', rol=User.Rol.CLIENTE, cliente=self.cli_b)
        self.orden = OrdenTrabajo.objects.create(
            titulo='Preventivo', cliente=self.cli_a, ubicacion=self.ub_a, tecnico=self.tecnico,
            monto_neto=100000, costo_materiales=20000, costo_mano_obra=30000)
        self.orden.activos.add(self.equipo)

    def test_numeracion_y_finanzas(self):
        self.assertEqual(self.orden.numero, f'1/{self.orden.fecha_programada.year % 100:02d}')
        self.assertEqual(self.orden.utilidad, 50000)
        self.assertEqual(self.orden.iva, 19000)

    def test_numeracion_continua_desde_la_ultima_escrita_a_mano(self):
        anio = self.orden.fecha_programada.year
        sufijo = f'/{anio % 100:02d}'
        base = dict(titulo='X', cliente=self.cli_a, ubicacion=self.ub_a)
        OrdenTrabajo.objects.create(numero=f'456{sufijo}', **base)
        self.assertEqual(OrdenTrabajo.objects.create(**base).numero, f'457{sufijo}')
        self.assertEqual(OrdenTrabajo.objects.create(**base).numero, f'458{sufijo}')
        # Otro año arranca de 1 y los números con otro formato no interfieren
        OrdenTrabajo.objects.create(numero='OT-2020-0099', **base)
        otro = OrdenTrabajo.objects.create(fecha_programada=self.orden.fecha_programada.replace(year=anio + 1),
                                           **base)
        self.assertEqual(otro.numero, f'1/{(anio + 1) % 100:02d}')

    def test_formulario_de_orden_acepta_numero_manual(self):
        self.client.force_login(self.admin)
        datos = {'numero': '456/26', 'titulo': 'Preventivo', 'atencion': 'Nicolas', 'tipo': 'preventivo',
                 'prioridad': 'media', 'estado': 'pendiente', 'ubicacion': self.ub_a.pk,
                 'activos': [self.equipo.pk], 'fecha_programada': '2026-10-01', 'monto_neto': 0,
                 'costo_materiales': 0, 'costo_mano_obra': 0, 'estado_pago': 'pendiente'}
        self.client.post(reverse('orden_nueva'), datos)
        self.assertTrue(OrdenTrabajo.objects.filter(numero='456/26', atencion='Nicolas').exists())
        self.client.post(reverse('orden_nueva'), {**datos, 'numero': ''})
        self.assertTrue(OrdenTrabajo.objects.filter(numero='457/26').exists())
        self.assertContains(self.client.get(reverse('orden_nueva')), 'Automático: 458/26')

    def test_flujo_completo(self):
        c = self.client
        c.force_login(self.tecnico)

        r = c.post(reverse('orden_iniciar', args=[self.orden.pk]))
        informe = Informe.objects.get(orden=self.orden)
        self.assertRedirects(r, reverse('informe_editar', args=[informe.pk]))
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, OrdenTrabajo.Estado.EN_PROCESO)
        self.assertEqual(informe.equipos.count(), 1)

        # Sin terminar los equipos no se puede enviar, y sin fotos no se puede terminar un equipo
        eq = informe.equipos.get()
        self.assertEqual(eq.tareas, TAREAS_CLAVES)  # parte con las 6 actividades marcadas
        datos = {f'eq{eq.pk}-estado_equipo': 'operativo', f'eq{eq.pk}-tipo_mantenimiento': 'preventivo',
                 f'eq{eq.pk}-tareas': ['filtros', 'presiones'], f'eq{eq.pk}-presion': '60',
                 f'eq{eq.pk}-consumo_total': '8.5', f'eq{eq.pk}-consumo_ventilador': '0.5',
                 f'eq{eq.pk}-temp_inyeccion': '8.7', f'eq{eq.pk}-modo': 'frio', 'diagnostico': 'ok'}
        c.post(reverse('informe_editar', args=[informe.pk]), {**datos, 'accion': 'enviar'})
        informe.refresh_from_db()
        self.assertEqual(informe.estado, Informe.Estado.BORRADOR)
        c.post(reverse('informe_editar', args=[informe.pk]), {**datos, 'accion': f'terminar_{eq.pk}'})
        eq.refresh_from_db()
        self.assertFalse(eq.finalizado)
        self.assertEqual(c.get(reverse('equipo_pdf', args=[eq.pk])).status_code, 404)

        # Subir foto con coordenadas
        r = c.post(reverse('foto_subir', args=[informe.pk]),
                   {'imagen': imagen_de_prueba(), 'etapa': 'antes', 'equipo': eq.pk})
        self.assertEqual(r.status_code, 200, r.content)
        foto = FotoInforme.objects.get()
        self.assertEqual(foto.equipo, eq)
        self.assertLessEqual(max(Image.open(foto.imagen).size), 1600)

        # Un archivo que no es imagen se rechaza
        r = c.post(reverse('foto_subir', args=[informe.pk]),
                   {'imagen': SimpleUploadedFile('x.jpg', b'no soy imagen', content_type='image/jpeg')})
        self.assertEqual(r.status_code, 400)

        # Con foto, el equipo se termina y su ficha PDF queda disponible al instante
        c.post(reverse('informe_editar', args=[informe.pk]), {**datos, 'accion': f'terminar_{eq.pk}'})
        eq.refresh_from_db()
        self.assertTrue(eq.finalizado)
        self.assertIsNotNone(eq.completado_en)
        ficha = c.get(reverse('equipo_pdf', args=[eq.pk]))
        self.assertEqual(ficha.status_code, 200)
        self.assertTrue(ficha.content.startswith(b'%PDF'))

        # Ahora sí se envía el informe
        c.post(reverse('informe_editar', args=[informe.pk]), {**datos, 'accion': 'enviar'})
        informe.refresh_from_db()
        eq.refresh_from_db()
        self.assertEqual(informe.estado, Informe.Estado.ENVIADO)
        self.assertEqual(eq.tareas, ['filtros', 'presiones'])
        self.assertEqual(str(eq.consumo_total), '8.5')
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, OrdenTrabajo.Estado.EN_REVISION)

        # En revisión el técnico aún puede corregir; el cliente todavía no ve el informe
        self.assertEqual(c.get(reverse('informe_editar', args=[informe.pk])).status_code, 200)
        c.force_login(self.user_a)
        self.assertEqual(c.get(reverse('informe_detalle', args=[informe.pk])).status_code, 404)
        self.assertEqual(c.get(reverse('equipo_pdf', args=[eq.pk])).status_code, 404)

        # El admin emite y el cliente lo ve ordenado por mes
        c.force_login(self.admin)
        c.post(reverse('informe_emitir', args=[informe.pk]))
        self.orden.refresh_from_db()
        informe.refresh_from_db()
        self.assertEqual(self.orden.estado, OrdenTrabajo.Estado.FINALIZADA)
        self.assertEqual(informe.emitido_por, self.admin)
        c.force_login(self.user_a)
        r = c.get(reverse('informes'))
        self.assertContains(r, informe.numero)
        self.assertEqual(c.get(reverse('informe_detalle', args=[informe.pk])).status_code, 200)
        self.assertEqual(c.get(reverse('equipo_pdf', args=[eq.pk])).status_code, 200)

        # Emitido: el técnico ya no lo edita, el admin sí y el informe sigue emitido
        c.force_login(self.tecnico)
        self.assertRedirects(c.get(reverse('informe_editar', args=[informe.pk])),
                             reverse('informe_detalle', args=[informe.pk]))
        c.force_login(self.admin)
        r = c.post(reverse('informe_editar', args=[informe.pk]),
                   {**datos, 'diagnostico': 'corregido', 'accion': 'guardar'}, follow=True)
        informe.refresh_from_db()
        self.assertEqual((informe.diagnostico, informe.estado), ('corregido', Informe.Estado.EMITIDO))
        self.assertContains(r, 'Cambios guardados')

    # --- 6 fotos por equipo ----------------------------------------------------------

    def _informe_iniciado(self):
        c = self.client
        c.force_login(self.tecnico)
        c.post(reverse('orden_iniciar', args=[self.orden.pk]))
        informe = Informe.objects.get(orden=self.orden)
        c.get(reverse('informe_editar', args=[informe.pk]))  # al abrir el editor se crea la ficha de cada equipo
        return informe, informe.equipos.get()

    def _foto(self, informe, eq, paso):
        return self.client.post(reverse('foto_subir', args=[informe.pk]),
                                {'imagen': imagen_de_prueba(), 'equipo': eq.pk, 'paso': paso})

    def test_las_seis_fotos_por_equipo_y_la_condensadora_es_opcional(self):
        from .models import PASOS_FOTO

        self.assertEqual([p[0] for p in PASOS_FOTO],
                         ['liquido', 'hidrolavadora', 'soplador', 'desarmado', 'condensadora', 'terminado'])
        self.assertEqual([p[0] for p in PASOS_FOTO if not p[2]], ['condensadora'])
        informe, eq = self._informe_iniciado()
        self.assertEqual(len(eq.pasos_pendientes), 5)  # todas menos la opcional
        for paso in ('liquido', 'hidrolavadora', 'soplador', 'desarmado', 'terminado'):
            r = self._foto(informe, eq, paso)
            self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['faltan'], [])  # sin la condensadora ya está completo
        eq = informe.equipos.prefetch_related('fotos').get()
        self.assertEqual(eq.pasos_pendientes, [])
        self.assertEqual(eq.fotos.count(), 5)

    def test_volver_a_tomar_un_paso_reemplaza_la_foto(self):
        informe, eq = self._informe_iniciado()
        primera = self._foto(informe, eq, 'liquido').json()
        segunda = self._foto(informe, eq, 'liquido').json()
        self.assertNotEqual(primera['id'], segunda['id'])
        self.assertEqual(FotoInforme.objects.filter(equipo=eq, paso='liquido').count(), 1)
        self.assertEqual(segunda['titulo'], '1 · Aplicación del líquido')

    def test_paso_invalido_o_sin_equipo_se_rechaza(self):
        informe, eq = self._informe_iniciado()
        self.assertEqual(self._foto(informe, eq, 'inventado').status_code, 400)
        r = self.client.post(reverse('foto_subir', args=[informe.pk]), {'imagen': imagen_de_prueba(), 'paso': 'liquido'})
        self.assertEqual(r.status_code, 400)

    def test_se_puede_terminar_con_fotos_faltantes_y_agregarlas_despues(self):
        informe, eq = self._informe_iniciado()
        c = self.client
        self._foto(informe, eq, 'liquido')
        datos = {**self._base(informe), 'accion': f'terminar_{eq.pk}'}
        r = c.post(reverse('informe_editar', args=[informe.pk]), datos, follow=True)
        eq.refresh_from_db()
        self.assertTrue(eq.finalizado)
        self.assertContains(r, 'Faltan fotos')
        self.assertContains(r, 'Lavado con hidrolavadora')

        # El técnico ve el recordatorio en su jornada, con enlace directo al equipo
        r = c.get(reverse('home'))
        self.assertContains(r, 'Fotos pendientes')
        self.assertContains(r, f'#eq-{eq.pk}')
        self.assertEqual([e.pk for e in r.context['fotos_pendientes']], [eq.pk])

        # Se envía a revisión igual (con aviso) y puede completarlas mientras está en revisión
        c.post(reverse('informe_editar', args=[informe.pk]), {**self._base(informe), 'accion': 'enviar'}, follow=True)
        informe.refresh_from_db()
        self.assertEqual(informe.estado, Informe.Estado.ENVIADO)
        for paso in ('hidrolavadora', 'soplador', 'desarmado', 'terminado'):
            self.assertEqual(self._foto(informe, eq, paso).status_code, 200)
        self.assertEqual(c.get(reverse('home')).context['fotos_pendientes'], [])

    def test_el_administrador_ve_las_fotos_pendientes_en_el_informe(self):
        informe, eq = self._informe_iniciado()
        self.client.post(reverse('informe_editar', args=[informe.pk]),
                         {**self._base(informe), 'accion': f'terminar_{eq.pk}'})  # sin fotos: no termina
        self._foto(informe, eq, 'liquido')
        self.client.post(reverse('informe_editar', args=[informe.pk]), {**self._base(informe), 'accion': f'terminar_{eq.pk}'})
        self.client.force_login(self.admin)
        r = self.client.get(reverse('informe_detalle', args=[informe.pk]))
        self.assertContains(r, 'Fotos pendientes')
        self.assertContains(r, '1 · Aplicación del líquido')  # la foto lleva su paso al pie
        r = self.client.get(reverse('orden_detalle', args=[self.orden.pk]))
        self.assertContains(r, 'Faltan 4 fotos')

    def test_informe_individual_y_general_incluyen_los_pasos(self):
        informe, eq = self._informe_iniciado()
        for paso in ('liquido', 'hidrolavadora', 'soplador', 'desarmado', 'condensadora', 'terminado'):
            self._foto(informe, eq, paso)
        self.client.post(reverse('informe_editar', args=[informe.pk]),
                         {**self._base(informe), 'accion': f'terminar_{eq.pk}'})
        eq = informe.equipos.prefetch_related('fotos').get()
        self.assertEqual([f.paso for f in eq.fotos_ordenadas],
                         ['liquido', 'hidrolavadora', 'soplador', 'desarmado', 'condensadora', 'terminado'])
        individual = self.client.get(reverse('equipo_pdf', args=[eq.pk]))
        general = self.client.get(reverse('informe_pdf', args=[informe.pk]))
        for r in (individual, general):
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.content.startswith(b'%PDF'))
        self.assertGreater(len(general.content), 10000)  # 6 fotos con su pie
        celdas = self._celdas(self.client.get(reverse('informe_excel', args=[informe.pk])))
        self.assertIn('—', celdas)  # sin fotos pendientes
        # La orden ofrece ambos informes
        r = self.client.get(reverse('orden_detalle', args=[self.orden.pk]))
        self.assertContains(r, reverse('informe_pdf', args=[informe.pk]))
        self.assertContains(r, reverse('equipo_pdf', args=[eq.pk]))

    # --- mediciones y observaciones opcionales ---------------------------------------------

    def test_lo_que_el_tecnico_no_anota_no_sale_en_el_informe(self):
        informe, eq = self._informe_iniciado()
        self._foto(informe, eq, 'liquido')
        self.client.post(reverse('informe_editar', args=[informe.pk]),
                         {**self._base(informe), 'accion': f'terminar_{eq.pk}'})
        eq = informe.equipos.select_related('activo').prefetch_related('fotos').get()
        self.assertTrue(eq.finalizado)  # terminó sin ninguna medición ni observación
        self.assertEqual((eq.mediciones, eq.observaciones_informe), ([], ('', '')))

        self.client.force_login(self.admin)
        html = self.client.get(reverse('informe_detalle', args=[informe.pk])).content.decode()
        for ausente in ('SIN OBS', 'Presión de funcionamiento', 'Consumo eléctrico', 'Temperatura de inyección',
                        'Observaciones:'):
            self.assertNotIn(ausente, html)
        for url in (reverse('equipo_pdf', args=[eq.pk]), reverse('informe_pdf', args=[informe.pk])):
            self.assertTrue(self.client.get(url).content.startswith(b'%PDF'))

    def test_solo_salen_las_mediciones_con_valor(self):
        informe, eq = self._informe_iniciado()
        eq.presion, eq.temp_inyeccion, eq.modo, eq.observaciones = Decimal('60'), Decimal('8.7'), 'calor', 'Filtro roto'
        eq.save()
        eq = informe.equipos.select_related('activo').prefetch_related('fotos').get()
        self.assertEqual(eq.mediciones, [('Presión de funcionamiento', '60 PSI'),
                                         ('Temperatura de inyección (CALOR)', '8.7°C')])
        self.assertEqual(eq.observaciones_informe, ('', 'Filtro roto'))
        eq.temp_inyeccion = None  # sin temperatura, el modo frío/calor tampoco aparece
        self.assertEqual([n for n, _ in eq.mediciones], ['Presión de funcionamiento'])

    # --- interruptor «equipo fuera de norma» -------------------------------------------------

    def test_fuera_de_norma_parte_segun_el_refrigerante_y_el_tecnico_lo_decide(self):
        self.equipo.refrigerante = 'R-22'
        self.equipo.save()
        informe, eq = self._informe_iniciado()
        self.assertTrue(eq.fuera_de_norma)  # R-22: parte activado
        self.assertEqual(eq.observaciones_informe[0], 'EQUIPO FUERA DE NORMA (REFRIGERANTE R-22)')
        self.assertContains(self.client.get(reverse('informe_editar', args=[informe.pk])), 'role="switch"')

        # El técnico lo apaga (el interruptor apagado no envía nada) y deja de salir en el informe
        self.client.post(reverse('informe_editar', args=[informe.pk]), {**self._base(informe), 'accion': 'guardar'})
        eq.refresh_from_db()
        self.assertFalse(eq.fuera_de_norma)
        self.assertEqual(eq.observaciones_informe, ('', ''))
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get(reverse('informe_detalle', args=[informe.pk])), 'FUERA DE NORMA')

    def test_el_tecnico_puede_marcar_fuera_de_norma_un_equipo_que_no_es_r22(self):
        self.equipo.refrigerante = 'R410A'
        self.equipo.save()
        informe, eq = self._informe_iniciado()
        self.assertFalse(eq.fuera_de_norma)
        self.client.post(reverse('informe_editar', args=[informe.pk]), {
            **self._base(informe), f'eq{eq.pk}-fuera_de_norma': 'on', f'eq{eq.pk}-observaciones': 'Gas dañado',
            'accion': 'guardar'})
        eq = informe.equipos.select_related('activo').get()
        self.assertTrue(eq.fuera_de_norma)
        self.assertEqual(eq.observaciones_informe, ('EQUIPO FUERA DE NORMA', 'Gas dañado'))  # sin «R-22»
        self.client.force_login(self.admin)
        html = self.client.get(reverse('informe_detalle', args=[informe.pk])).content.decode()
        self.assertIn('EQUIPO FUERA DE NORMA', html)
        self.assertNotIn('REFRIGERANTE R-22', html)

    # --- firma del técnico -----------------------------------------------------------------

    def test_el_tecnico_firma_en_el_informe_y_sale_en_la_pantalla_y_en_el_pdf(self):
        import base64

        buf = BytesIO()
        Image.new('RGBA', (300, 120), (0, 0, 0, 0)).save(buf, 'PNG')
        firma = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
        informe, eq = self._informe_iniciado()
        html = self.client.get(reverse('informe_editar', args=[informe.pk])).content.decode()
        self.assertIn('id="firma-tecnico"', html)  # además de la firma del cliente
        self.client.post(reverse('informe_editar', args=[informe.pk]),
                         {**self._base(informe), 'firma_tecnico_data': firma, 'accion': 'guardar'})
        informe.refresh_from_db()
        self.assertTrue(informe.firma_tecnico)
        self.assertFalse(informe.firma)  # la del cliente no se tocó
        self.client.post(reverse('informe_editar', args=[informe.pk]),
                         {**self._base(informe), 'accion': f'terminar_{eq.pk}'})
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('informe_detalle', args=[informe.pk])), 'Firma técnico')
        pdf = self.client.get(reverse('informe_pdf', args=[informe.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        # la imagen se sirve con sesión
        self.assertEqual(self.client.get(informe.firma_tecnico.url).status_code, 200)

    # --- eliminar un informe creado sin querer -----------------------------------------------

    def test_eliminar_solo_el_informe_borra_fotos_y_archivos_y_deja_la_orden_pendiente(self):
        informe, eq = self._informe_iniciado()
        self._foto(informe, eq, 'liquido')
        ruta = informe.fotos.get().imagen.path
        r = self.client.get(reverse('informe_eliminar', args=[informe.pk]))
        self.assertContains(r, 'no se puede deshacer')
        self.assertNotContains(r, 'y la orden')  # esta orden tiene cobro: no se ofrece borrarla
        self.assertTrue(Informe.objects.filter(pk=informe.pk).exists())  # mirar la confirmación no borra
        r = self.client.post(reverse('informe_eliminar', args=[informe.pk]), {'accion': 'con_orden'}, follow=True)
        self.assertRedirects(r, reverse('informes'))
        self.assertFalse(Informe.objects.exists() or FotoInforme.objects.exists())
        self.assertFalse(__import__('os').path.exists(ruta))
        self.orden.refresh_from_db()  # la orden con cobro se conserva aunque se pida borrarla
        self.assertEqual(self.orden.estado, OrdenTrabajo.Estado.PENDIENTE)
        self.assertIsNone(self.orden.fecha_inicio)

    def test_el_tecnico_elimina_un_informe_en_terreno_con_su_orden_creada_sin_querer(self):
        self.client.force_login(self.tecnico)
        self.client.post(reverse('informe_nuevo'), {'cliente': self.cli_a.pk, 'ubicacion': self.ub_a.pk,
                                                    'tipo': 'preventivo', 'titulo': '', 'atencion': ''})
        informe = Informe.objects.exclude(orden=self.orden).get()
        self.assertContains(self.client.get(reverse('informes')), reverse('informe_eliminar', args=[informe.pk]))
        self.assertContains(self.client.get(reverse('informe_eliminar', args=[informe.pk])), 'y la orden')
        self.client.post(reverse('informe_eliminar', args=[informe.pk]), {'accion': 'con_orden'})
        self.assertFalse(Informe.objects.exclude(orden=self.orden).exists())
        self.assertEqual(OrdenTrabajo.objects.count(), 1)  # solo queda la orden del administrador

    def test_quien_puede_eliminar_un_informe(self):
        informe, eq = self._informe_iniciado()
        url = reverse('informe_eliminar', args=[informe.pk])
        self.client.force_login(self.otro_tecnico)  # un técnico ajeno ni siquiera lo ve
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.force_login(self.user_a)  # el cliente no elimina
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.tecnico)  # ya enviado a revisión, el técnico no puede borrarlo
        Informe.objects.filter(pk=informe.pk).update(estado=Informe.Estado.ENVIADO)
        self.client.post(url)
        self.assertTrue(Informe.objects.filter(pk=informe.pk).exists())
        self.assertNotContains(self.client.get(reverse('informe_detalle', args=[informe.pk])), url)
        self.client.force_login(self.admin)  # el administrador sí, y le avisa si ya se emitió
        self.assertContains(self.client.get(reverse('informe_detalle', args=[informe.pk])), url)
        self.client.post(url)
        self.assertFalse(Informe.objects.exists())

    # --- cámara o galería, y quitar una foto equivocada --------------------------------------

    def test_cada_casilla_ofrece_camara_y_galeria_y_se_puede_quitar_una_foto_equivocada(self):
        informe, eq = self._informe_iniciado()
        html = self.client.get(reverse('informe_editar', args=[informe.pk])).content.decode()
        # 6 pasos: cada uno con un selector con cámara y otro sin `capture` (galería)
        camara = html.count('capture="environment" class="js-slot"')
        galeria = html.count('<input type="file" accept="image/*" class="js-slot"')
        self.assertEqual((camara, galeria), (6, 6))
        self.assertIn('Galería', html)

        # Foto equivocada: se quita y el paso vuelve a quedar pendiente
        foto = self._foto(informe, eq, 'soplador').json()
        eq = informe.equipos.prefetch_related('fotos').get()
        self.assertNotIn('Secado con soplador', [p['nombre'] for p in eq.pasos_pendientes])
        r = self.client.post(foto['eliminar'])
        self.assertEqual(r.status_code, 200)
        self.assertIn('Secado con soplador', r.json()['faltan'])
        self.assertFalse(FotoInforme.objects.filter(pk=foto['id']).exists())

        # Una foto de la galería (cualquier imagen) reemplaza a la anterior del mismo paso
        self._foto(informe, eq, 'soplador')
        segunda = self._foto(informe, eq, 'soplador').json()
        self.assertEqual(list(FotoInforme.objects.filter(equipo=eq, paso='soplador').values_list('pk', flat=True)),
                         [segunda['id']])

    def test_otro_tecnico_no_puede_quitar_fotos_ajenas(self):
        informe, eq = self._informe_iniciado()
        foto = self._foto(informe, eq, 'liquido').json()
        self.client.force_login(self.otro_tecnico)
        self.assertEqual(self.client.post(foto['eliminar']).status_code, 404)
        self.assertTrue(FotoInforme.objects.filter(pk=foto['id']).exists())

    def _base(self, informe):
        """Datos mínimos de los equipos del informe, como los enviaría el navegador."""
        datos = {}
        for eq in informe.equipos.all():
            datos.update({f'eq{eq.pk}-tipo_mantenimiento': 'preventivo', f'eq{eq.pk}-estado_equipo': 'operativo',
                          f'eq{eq.pk}-modo': 'frio'})
        return datos

    def test_agregar_crear_y_quitar_equipos_del_informe(self):
        otro = Activo.objects.create(ubicacion=self.ub_a, codigo='A-2', nombre='Otro', numero_equipo='021')
        ajeno = Activo.objects.create(ubicacion=self.ub_b, codigo='B-1', nombre='Ajeno', numero_equipo='001')
        c = self.client
        c.force_login(self.tecnico)
        c.post(reverse('orden_iniciar', args=[self.orden.pk]))
        informe = Informe.objects.get(orden=self.orden)
        url = reverse('informe_editar', args=[informe.pk])
        self.assertContains(c.get(url), 'Agregar equipos de Cliente A')

        # Se agregan equipos de la misma empresa (el de otro cliente se ignora)
        c.post(url, {**self._base(informe), 'accion': 'agregar', 'agregar_activos': [otro.pk, ajeno.pk]})
        self.assertEqual(sorted(informe.equipos.values_list('activo__codigo', flat=True)), ['A-1', 'A-2'])
        self.assertIn(otro, self.orden.activos.all())
        self.assertNotIn(ajeno, self.orden.activos.all())

        # Equipo que no estaba en el catálogo: se crea, queda del cliente y como fuera de norma por el R-22
        nuevo = {'nuevo-numero_equipo': '099', 'nuevo-marca': 'LG', 'nuevo-modelo': 'X1',
                 'nuevo-refrigerante': 'R-22', 'nuevo-ubicacion_exacta': 'Bodega', 'nuevo-ubicacion': self.ub_a.pk}
        c.post(url, {**self._base(informe), 'accion': 'nuevo', **nuevo})
        creado = Activo.objects.get(numero_equipo='099')
        self.assertEqual((creado.ubicacion, creado.fuera_de_norma, creado.etiqueta),
                         (self.ub_a, True, 'Equipo N°099'))
        self.assertTrue(informe.equipos.filter(activo=creado).exists())
        c.post(url, {**self._base(informe), 'accion': 'nuevo', **nuevo})  # repetido: se rechaza
        self.assertEqual(Activo.objects.filter(numero_equipo='099').count(), 1)

        # Quitar un equipo lo saca del informe y de la orden
        eq_otro = informe.equipos.get(activo=otro)
        c.post(url, {**self._base(informe), 'accion': f'quitar_{eq_otro.pk}'})
        self.assertFalse(informe.equipos.filter(activo=otro).exists())
        self.assertNotIn(otro, self.orden.activos.all())
        # vuelve a estar disponible en la lista para agregar
        self.assertContains(c.get(url), f'name="agregar_activos" value="{otro.pk}"')

    def test_tecnico_crea_un_informe_en_terreno_sin_orden_previa(self):
        c = self.client
        c.force_login(self.tecnico)
        pagina = c.get(reverse('informe_nuevo'))
        self.assertContains(pagina, 'Cliente B')
        antes = OrdenTrabajo.objects.count()
        datos = {'cliente': self.cli_a.pk, 'ubicacion': self.ub_a.pk, 'tipo': 'correctivo', 'atencion': 'Nicolas'}

        # Una sucursal de otro cliente se rechaza
        r = c.post(reverse('informe_nuevo'), {**datos, 'ubicacion': self.ub_b.pk})
        self.assertContains(r, 'no pertenece al cliente elegido')
        self.assertEqual(OrdenTrabajo.objects.count(), antes)

        r = c.post(reverse('informe_nuevo'), datos)
        orden = OrdenTrabajo.objects.exclude(pk=self.orden.pk).get()
        informe = orden.informe
        self.assertRedirects(r, reverse('informe_editar', args=[informe.pk]))
        self.assertEqual((orden.tecnico, orden.estado, orden.creada_por, orden.cliente, orden.atencion),
                         (self.tecnico, OrdenTrabajo.Estado.EN_PROCESO, self.tecnico, self.cli_a, 'Nicolas'))
        self.assertIn('correctiva', orden.titulo)
        self.assertEqual(informe.tecnico, self.tecnico)
        # Puede agregar los equipos del cliente dentro del informe recién creado
        self.assertContains(c.get(reverse('informe_editar', args=[informe.pk])), 'Agregar equipos de Cliente A')

        # Solo el técnico crea informes desde cero
        for usuario in (self.admin, self.user_a):
            c.force_login(usuario)
            self.assertEqual(c.get(reverse('informe_nuevo')).status_code, 403)

    def test_tecnico_da_de_alta_equipos_en_terreno(self):
        datos = {'cliente': self.cli_a.pk, 'ubicacion': self.ub_a.pk, 'codigo': 'A-77', 'numero_equipo': '077', 'nombre': 'Split nuevo',
                 'tipo': 'split', 'estado': 'activo', 'condicion': 'buena', 'refrigerante': 'R-22'}
        self.client.force_login(self.tecnico)
        self.assertContains(self.client.get(reverse('activos')), reverse('activo_nuevo'))
        self.client.post(reverse('activo_nuevo'), datos)
        creado = Activo.objects.get(codigo='A-77')
        self.assertTrue(creado.fuera_de_norma)
        self.assertEqual(self.client.post(reverse('activo_editar', args=[creado.pk]),
                                          {**datos, 'ubicacion_exacta': 'Bodega'}).status_code, 302)
        creado.refresh_from_db()
        self.assertEqual(creado.ubicacion_exacta, 'Bodega')
        # El técnico no administra clientes ni usuarios; el cliente no crea equipos
        for url in ('clientes', 'usuarios', 'ubicacion_nueva'):
            self.assertEqual(self.client.get(reverse(url)).status_code, 403, url)
        self.client.force_login(self.user_a)
        self.assertEqual(self.client.get(reverse('activo_nuevo')).status_code, 403)
        self.assertNotContains(self.client.get(reverse('activos')), reverse('activo_nuevo'))

    def test_aislamiento_entre_clientes_y_roles(self):
        informe = Informe.objects.create(orden=self.orden, tecnico=self.tecnico, estado=Informe.Estado.EMITIDO)
        c = self.client
        c.force_login(self.user_b)
        self.assertEqual(c.get(reverse('orden_detalle', args=[self.orden.pk])).status_code, 404)
        self.assertEqual(c.get(reverse('informe_detalle', args=[informe.pk])).status_code, 404)
        self.assertNotContains(c.get(reverse('ordenes')), self.orden.numero)
        for url in ('finanzas', 'usuarios', 'clientes', 'orden_nueva'):
            self.assertEqual(c.get(reverse(url)).status_code, 403, url)

        c.force_login(self.otro_tecnico)
        self.assertEqual(c.get(reverse('orden_detalle', args=[self.orden.pk])).status_code, 404)
        self.assertEqual(c.post(reverse('orden_iniciar', args=[self.orden.pk])).status_code, 404)
        self.assertEqual(c.get(reverse('finanzas')).status_code, 403)

    def test_dashboards_por_rol(self):
        self.orden.estado = OrdenTrabajo.Estado.FINALIZADA
        self.orden.save()
        for usuario in (self.admin, self.tecnico, self.user_a):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('home')).status_code, 200, usuario.rol)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('home')), '$50.000')
        self.assertEqual(self.client.get(reverse('finanzas')).status_code, 200)
        for url in ('ordenes', 'informes', 'activos', 'ubicaciones', 'clientes', 'usuarios',
                    'orden_nueva', 'activo_nuevo'):
            self.assertEqual(self.client.get(reverse(url)).status_code, 200, url)

    def _celdas(self, respuesta):
        """Todos los textos de un .xlsx devuelto por una vista."""
        libro = load_workbook(BytesIO(respuesta.content))
        return [str(c.value) for ws in libro for fila in ws.iter_rows() for c in fila if c.value is not None]

    def test_exportaciones_pdf_y_excel(self):
        informe = Informe.objects.create(orden=self.orden, tecnico=self.tecnico, estado=Informe.Estado.EMITIDO,
                                         diagnostico='Filtros sucios')
        eq = informe.equipos.create(activo=self.equipo, tareas=['filtros'], presion='60', finalizado=True,
                                    completado_en=timezone.now())
        foto = FotoInforme(informe=informe, equipo=eq, imagen=imagen_de_prueba(), etapa='antes')
        foto.save()
        self.orden.estado = OrdenTrabajo.Estado.FINALIZADA
        self.orden.save()

        self.client.force_login(self.admin)
        urls = [reverse(n) for n in ('home', 'finanzas', 'ordenes', 'informes', 'activos', 'ubicaciones',
                                     'clientes', 'usuarios')]
        for url in urls:
            for formato, tipo in (('pdf', 'application/pdf'), ('xlsx', 'spreadsheetml')):
                r = self.client.get(url, {'export': formato})
                self.assertEqual(r.status_code, 200, (url, formato))
                self.assertIn(tipo, r['Content-Type'])
                if formato == 'pdf':
                    self.assertTrue(r.content.startswith(b'%PDF'), url)

        r = self.client.get(reverse('informe_pdf', args=[informe.pk]))
        self.assertTrue(r.content.startswith(b'%PDF'))
        self.assertGreater(len(r.content), 5000)  # incluye la foto
        celdas = self._celdas(self.client.get(reverse('informe_excel', args=[informe.pk])))
        self.assertIn(self.orden.numero, celdas)
        self.assertIn('A-1', celdas)
        self.assertIn('Limpieza de filtros', ' '.join(celdas))
        celdas = self._celdas(self.client.get(reverse('finanzas'), {'export': 'xlsx'}))
        self.assertIn(self.orden.numero, celdas)

        # El cliente exporta solo lo suyo y sin columnas financieras
        self.client.force_login(self.user_a)
        celdas = self._celdas(self.client.get(reverse('ordenes'), {'export': 'xlsx'}))
        self.assertIn(self.orden.numero, celdas)
        self.assertNotIn('Monto neto', celdas)
        self.assertEqual(self.client.get(reverse('finanzas'), {'export': 'xlsx'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('informe_pdf', args=[informe.pk])).status_code, 200)
        self.client.force_login(self.user_b)
        self.assertEqual(self.client.get(reverse('informe_pdf', args=[informe.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('informe_excel', args=[informe.pk])).status_code, 404)
        self.assertNotIn(self.orden.numero, self._celdas(self.client.get(reverse('ordenes'), {'export': 'xlsx'})))

    def test_fuera_de_norma_por_refrigerante(self):
        for valor, esperado in (('R-22', True), ('r22', True), (' R 22 ', True), ('R410A', False), ('', False)):
            self.equipo.refrigerante = valor
            self.assertEqual(self.equipo.fuera_de_norma, esperado, valor)

    def test_informe_mensual(self):
        self.equipo.refrigerante, self.equipo.numero_equipo = 'R-22', '020'
        self.equipo.save()
        informe = Informe.objects.create(orden=self.orden, tecnico=self.tecnico, estado=Informe.Estado.ENVIADO)
        eq = informe.equipos.create(activo=self.equipo, tareas=TAREAS_CLAVES, finalizado=True, fuera_de_norma=True,
                                    completado_en=timezone.now(), observaciones='Cambio de tarjeta')
        FotoInforme(informe=informe, equipo=eq, imagen=imagen_de_prueba()).save()
        mes = timezone.localdate().strftime('%Y-%m')
        url = reverse('informe_mensual')
        c = self.client

        # El admin ve los equipos enviados a revisión del cliente elegido y los exporta
        c.force_login(self.admin)
        r = c.get(url, {'cliente': self.cli_a.pk, 'mes': mes})
        self.assertContains(r, 'Cambio de tarjeta')
        self.assertEqual(len(r.context['equipos']), 1)
        self.assertEqual(len(c.get(url, {'cliente': self.cli_b.pk, 'mes': mes}).context['equipos']), 0)
        pdf = c.get(url, {'cliente': self.cli_a.pk, 'mes': mes, 'export': 'pdf'})
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        celdas = self._celdas(c.get(url, {'cliente': self.cli_a.pk, 'mes': mes, 'export': 'xlsx'}))
        self.assertIn('EQUIPO FUERA DE NORMA (REFRIGERANTE R-22) · Cambio de tarjeta', celdas)
        self.assertIn(self.orden.numero, celdas)

        # Un mes sin equipos no genera archivo
        r = c.get(url, {'cliente': self.cli_a.pk, 'mes': '2020-01', 'export': 'pdf'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'No hay equipos terminados')

        # Equipos de informes aún en borrador: ocultos por defecto
        informe.estado = Informe.Estado.BORRADOR
        informe.save()
        self.assertEqual(len(c.get(url, {'cliente': self.cli_a.pk, 'mes': mes}).context['equipos']), 0)
        self.assertEqual(len(c.get(url, {'cliente': self.cli_a.pk, 'mes': mes, 'borradores': '1'}).context['equipos']), 1)

        # El cliente solo ve lo emitido y solo de su empresa, aunque pida otro cliente por URL
        informe.estado = Informe.Estado.ENVIADO
        informe.save()
        c.force_login(self.user_a)
        self.assertEqual(len(c.get(url, {'mes': mes}).context['equipos']), 0)
        informe.estado = Informe.Estado.EMITIDO
        informe.save()
        self.assertEqual(len(c.get(url, {'mes': mes}).context['equipos']), 1)
        c.force_login(self.user_b)
        self.assertEqual(len(c.get(url, {'mes': mes, 'cliente': self.cli_a.pk}).context['equipos']), 0)

        c.force_login(self.tecnico)
        self.assertEqual(c.get(url).status_code, 403)

    def test_orden_form_valida_equipos_de_la_ubicacion(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('orden_nueva'), {
            'titulo': 'X', 'tipo': 'preventivo', 'prioridad': 'media', 'estado': 'pendiente',
            'ubicacion': self.ub_b.pk, 'activos': [self.equipo.pk], 'fecha_programada': '2026-10-01',
            'monto_neto': 0, 'costo_materiales': 0, 'costo_mano_obra': 0, 'estado_pago': 'pendiente'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'no pertenecen al cliente')
