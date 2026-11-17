from io import BytesIO

from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from accounts.models import User
from cotizaciones.models import Cotizacion
from mantenciones.models import Informe, InformeEquipo, OrdenTrabajo

from .models import Activo, Cliente, Ubicacion


class EquiposPorEmpresaTests(TestCase):
    def setUp(self):
        self.alba = Cliente.objects.create(nombre='Alba')
        self.zeta = Cliente.objects.create(nombre='Zeta')
        sa1 = Ubicacion.objects.create(cliente=self.alba, nombre='Local 1')
        sa2 = Ubicacion.objects.create(cliente=self.alba, nombre='Local 2')
        sz = Ubicacion.objects.create(cliente=self.zeta, nombre='Oficina')
        # Se crean desordenados a propósito: la lista debe agruparlos por empresa
        Activo.objects.create(ubicacion=sz, codigo='Z-1', numero_equipo='1', nombre='Split Zeta')
        Activo.objects.create(ubicacion=sa2, codigo='A-3', numero_equipo='3', nombre='Split A3', refrigerante='R-22')
        Activo.objects.create(ubicacion=sa1, codigo='A-1', numero_equipo='1', nombre='Split A1', condicion='mala')
        Activo.objects.create(ubicacion=sa1, codigo='A-2', numero_equipo='2', nombre='Split A2')
        self.admin = User.objects.create_user('admin', password='x', rol=User.Rol.ADMIN)
        self.tecnico = User.objects.create_user('tec', password='x', rol=User.Rol.TECNICO)
        self.cli_alba = User.objects.create_user('alba', password='x', rol=User.Rol.CLIENTE, cliente=self.alba)

    def grupos(self, usuario, **params):
        self.client.force_login(usuario)
        r = self.client.get(reverse('activos'), params)
        self.assertEqual(r.status_code, 200)
        return r, r.context['grupos']

    def test_agrupa_los_equipos_por_empresa_con_sus_totales(self):
        r, grupos = self.grupos(self.admin)
        self.assertEqual([g['cliente'].nombre for g in grupos], ['Alba', 'Zeta'])
        alba = grupos[0]
        self.assertEqual([a.codigo for a in alba['activos']], ['A-1', 'A-2', 'A-3'])  # por sucursal y número
        self.assertEqual((alba['sucursales'], alba['fuera_norma'], alba['por_revisar']), (2, 1, 1))
        self.assertEqual(r.context['total'], 4)
        self.assertContains(r, 'Alba')
        self.assertContains(r, '3 equipos')

    def test_filtrar_por_empresa(self):
        _, grupos = self.grupos(self.admin, cliente=self.zeta.pk)
        self.assertEqual([g['cliente'].nombre for g in grupos], ['Zeta'])

    def test_la_busqueda_funciona_dentro_de_los_grupos(self):
        r, grupos = self.grupos(self.admin, q='A2')
        self.assertEqual([[a.codigo for a in g['activos']] for g in grupos], [['A-2']])
        self.assertTrue(r.context['abierto'])  # con búsqueda todo aparece desplegado

    def test_el_cliente_solo_ve_su_empresa_y_no_edita(self):
        r, grupos = self.grupos(self.cli_alba)
        self.assertEqual([g['cliente'].nombre for g in grupos], ['Alba'])
        self.assertEqual(r.context['clientes'], [])  # sin selector de empresas
        self.assertNotContains(r, reverse('activo_nuevo'))
        self.assertNotContains(r, 'Split Zeta')
        # aunque pida otra empresa por la URL
        _, grupos = self.grupos(self.cli_alba, cliente=self.zeta.pk)
        self.assertEqual([g['cliente'].nombre for g in grupos], ['Alba'])

    def test_el_tecnico_puede_editar(self):
        r, _ = self.grupos(self.tecnico)
        self.assertContains(r, reverse('activo_nuevo'))

    def test_la_exportacion_sale_agrupada_por_empresa(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('activos'), {'export': 'xlsx'})
        libro = load_workbook(BytesIO(r.content))
        celdas = [str(c.value) for ws in libro for fila in ws.iter_rows() for c in fila if c.value is not None]
        orden = [celdas.index(x) for x in ('Split A1', 'Split A2', 'Split A3', 'Split Zeta')]
        self.assertEqual(orden, sorted(orden))

    def test_sin_equipos_muestra_el_mensaje(self):
        Activo.objects.all().delete()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('activos')), 'Aún no hay equipos registrados')


class EquipoConEmpresaTests(TestCase):
    """Un equipo se crea eligiendo su empresa; así el cliente lo ve en su portal."""

    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', rol=User.Rol.ADMIN)
        self.tecnico = User.objects.create_user('tec', password='x', rol=User.Rol.TECNICO)
        self.con_sucursal = Cliente.objects.create(nombre='Lucas Diesel')
        self.sucursal = Ubicacion.objects.create(cliente=self.con_sucursal, nombre='Oficinas')
        self.otra = Ubicacion.objects.create(cliente=Cliente.objects.create(nombre='Otra'), nombre='Bodega')
        self.nueva = Cliente.objects.create(nombre='Empresa Etiel SpA')  # recién creada: sin sucursales
        self.usuario_nueva = User.objects.create_user('etiel', password='x', rol=User.Rol.CLIENTE, cliente=self.nueva)
        self.client.force_login(self.admin)

    def datos(self, **extra):
        return {'cliente': self.nueva.pk, 'ubicacion': '', 'ubicacion_nueva': '', 'numero_equipo': '020',
                'nombre': 'Split oficina', 'tipo': 'split', 'estado': 'activo', 'condicion': 'buena', 'codigo': '',
                **extra}

    def test_el_formulario_pide_la_empresa_primero_y_filtra_las_sucursales(self):
        r = self.client.get(reverse('activo_nuevo'))
        self.assertContains(r, 'id_cliente')
        self.assertContains(r, 'Empresa')
        self.assertContains(r, f'data-cliente="{self.sucursal.cliente_id}"')  # cada sucursal sabe de qué empresa es
        self.assertContains(r, 'empresa_sucursal.js')
        self.assertContains(r, 'id_empresa_nueva')

    def test_una_empresa_sin_sucursales_recibe_una_al_crear_su_primer_equipo(self):
        r = self.client.post(reverse('activo_nuevo'), self.datos(), follow=True)
        self.assertRedirects(r, reverse('activos'))
        self.assertContains(r, 'Sucursal «Sucursal principal» creada')
        equipo = Activo.objects.get()
        self.assertEqual((equipo.ubicacion.cliente, equipo.ubicacion.nombre), (self.nueva, 'Sucursal principal'))
        self.assertEqual(equipo.codigo, 'EMPRESA-020')  # código automático
        # y el cliente de esa empresa ya ve su equipo
        self.client.force_login(self.usuario_nueva)
        self.assertContains(self.client.get(reverse('activos')), 'Split muro')  # el nombre sale del tipo

    def test_se_puede_escribir_el_nombre_de_la_sucursal_nueva(self):
        self.client.post(reverse('activo_nuevo'), self.datos(cliente=self.con_sucursal.pk, ubicacion_nueva='Sucursal Maipú'))
        equipo = Activo.objects.get()
        self.assertEqual((equipo.ubicacion.nombre, equipo.ubicacion.cliente), ('Sucursal Maipú', self.con_sucursal))
        self.assertEqual(Ubicacion.objects.filter(cliente=self.con_sucursal).count(), 2)

    def test_con_sucursales_hay_que_elegir_una_o_crearla(self):
        r = self.client.post(reverse('activo_nuevo'), self.datos(cliente=self.con_sucursal.pk))
        self.assertContains(r, 'Elige la sucursal o escribe el nombre de una nueva')
        r = self.client.post(reverse('activo_nuevo'), self.datos(cliente=self.con_sucursal.pk, ubicacion=self.sucursal.pk))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Activo.objects.get().ubicacion, self.sucursal)

    def test_rechaza_sucursales_de_otra_empresa_dobles_y_repetidas(self):
        r = self.client.post(reverse('activo_nuevo'), self.datos(cliente=self.con_sucursal.pk, ubicacion=self.otra.pk))
        self.assertContains(r, 'no pertenece a la empresa elegida')
        r = self.client.post(reverse('activo_nuevo'), self.datos(
            cliente=self.con_sucursal.pk, ubicacion=self.sucursal.pk, ubicacion_nueva='Otra más'))
        self.assertContains(r, 'no las dos')
        r = self.client.post(reverse('activo_nuevo'), self.datos(cliente=self.con_sucursal.pk, ubicacion_nueva='oficinas'))
        self.assertContains(r, 'Ya existe una sucursal con ese nombre')
        self.assertFalse(Activo.objects.exists())

    def test_la_empresa_es_obligatoria(self):
        r = self.client.post(reverse('activo_nuevo'), self.datos(cliente=''))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Activo.objects.exists())

    def test_los_codigos_automaticos_no_se_repiten_y_el_escrito_se_respeta(self):
        self.client.post(reverse('activo_nuevo'), self.datos())  # crea «Sucursal principal» en la empresa
        principal = Ubicacion.objects.get(cliente=self.nueva).pk
        self.client.post(reverse('activo_nuevo'), self.datos(nombre='Segundo', ubicacion=principal))
        self.client.post(reverse('activo_nuevo'), self.datos(nombre='Tercero', codigo='MI-CODIGO', ubicacion=principal))
        self.assertEqual(sorted(Activo.objects.values_list('codigo', flat=True)),
                         ['EMPRESA-020', 'EMPRESA-020-2', 'MI-CODIGO'])

    def test_si_algo_falla_no_queda_una_sucursal_huerfana(self):
        self.client.post(reverse('activo_nuevo'), self.datos(numero_equipo='X' * 30))  # N° de equipo demasiado largo
        self.assertFalse(Ubicacion.objects.filter(cliente=self.nueva).exists())

    def test_al_editar_aparece_la_empresa_y_se_puede_mover_el_equipo(self):
        equipo = Activo.objects.create(ubicacion=self.sucursal, codigo='L-1', nombre='Split', numero_equipo='1')
        r = self.client.get(reverse('activo_editar', args=[equipo.pk]))
        self.assertEqual(r.context['form'].fields['cliente'].initial, self.con_sucursal.pk)
        self.client.post(reverse('activo_editar', args=[equipo.pk]), self.datos(
            cliente=self.nueva.pk, codigo='L-1', nombre='Split', numero_equipo='1'))
        equipo.refresh_from_db()
        self.assertEqual(equipo.ubicacion.cliente, self.nueva)

    def test_el_tecnico_tambien_puede_crear_equipos_y_el_cliente_no(self):
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.post(reverse('activo_nuevo'), self.datos()).status_code, 302)
        self.client.force_login(self.usuario_nueva)
        self.assertEqual(self.client.get(reverse('activo_nuevo')).status_code, 403)


class EmpresaYSucursalNuevasEnLosFormulariosTests(TestCase):
    """Si la empresa o la sucursal no existen, se crean en el mismo formulario."""

    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', rol=User.Rol.ADMIN)
        self.lucas = Cliente.objects.create(nombre='Lucas Diesel')
        self.client.force_login(self.admin)

    def equipo(self, **extra):
        return {'cliente': '', 'empresa_nueva': '', 'ubicacion': '', 'ubicacion_nueva': '', 'numero_equipo': '1',
                'nombre': 'Split', 'tipo': 'split', 'estado': 'activo', 'condicion': 'buena', 'codigo': '', **extra}

    def test_un_equipo_puede_crear_su_empresa_y_su_sucursal_de_una_vez(self):
        r = self.client.post(reverse('activo_nuevo'), self.equipo(empresa_nueva='Transportes Rivera', ubicacion_nueva='Bodega'),
                             follow=True)
        self.assertContains(r, 'Empresa «Transportes Rivera» creada')
        self.assertContains(r, 'Sucursal «Bodega» creada')
        activo = Activo.objects.get()
        self.assertEqual((activo.ubicacion.cliente.nombre, activo.ubicacion.nombre, activo.codigo),
                         ('Transportes Rivera', 'Bodega', 'TRANSPOR-1'))

    def test_empresa_nueva_sin_sucursal_usa_la_principal(self):
        self.client.post(reverse('activo_nuevo'), self.equipo(empresa_nueva='Nueva SpA'))
        self.assertEqual(Activo.objects.get().ubicacion.nombre, 'Sucursal principal')

    def test_el_equipo_pide_empresa_y_valida_las_dos_formas(self):
        r = self.client.post(reverse('activo_nuevo'), self.equipo())
        self.assertContains(r, 'Elige la empresa o escribe el nombre de una nueva')
        r = self.client.post(reverse('activo_nuevo'), self.equipo(cliente=self.lucas.pk, empresa_nueva='Otra'))
        self.assertContains(r, 'no las dos')
        r = self.client.post(reverse('activo_nuevo'), self.equipo(empresa_nueva='lucas diesel'))
        self.assertContains(r, 'Ya existe una empresa con ese nombre')
        sucursal = Ubicacion.objects.create(cliente=self.lucas, nombre='Oficinas')
        r = self.client.post(reverse('activo_nuevo'), self.equipo(empresa_nueva='Nueva', ubicacion=sucursal.pk))
        self.assertContains(r, 'la sucursal también es nueva')
        self.assertFalse(Activo.objects.exists())
        self.assertEqual(Cliente.objects.count(), 1)  # no quedaron empresas a medias

    # --- formulario de ubicaciones ---
    def sucursal(self, **extra):
        return {'cliente': '', 'empresa_nueva': '', 'nombre': 'Casa matriz', 'codigo': '', 'direccion': '', 'ciudad': '',
                'region': '', 'activa': 'on', **extra}

    def test_la_ubicacion_puede_crear_la_empresa_en_el_mismo_formulario(self):
        r = self.client.post(reverse('ubicacion_nueva'), self.sucursal(empresa_nueva='Panadería Sol'), follow=True)
        self.assertRedirects(r, reverse('ubicaciones'))
        self.assertContains(r, 'Empresa «Panadería Sol» creada')
        sucursal = Ubicacion.objects.get()
        self.assertEqual((sucursal.cliente.nombre, sucursal.nombre), ('Panadería Sol', 'Casa matriz'))

    def test_la_ubicacion_con_empresa_existente_y_las_validaciones(self):
        self.client.post(reverse('ubicacion_nueva'), self.sucursal(cliente=self.lucas.pk))
        self.assertEqual(Ubicacion.objects.get().cliente, self.lucas)
        self.assertContains(self.client.post(reverse('ubicacion_nueva'), self.sucursal()),
                            'Elige la empresa o escribe el nombre de una nueva')
        self.assertContains(self.client.post(reverse('ubicacion_nueva'), self.sucursal(empresa_nueva='LUCAS DIESEL')),
                            'Ya existe una empresa con ese nombre')
        self.assertEqual(Ubicacion.objects.count(), 1)
        self.assertEqual(Cliente.objects.count(), 1)

    def test_la_pantalla_de_ubicacion_ofrece_crear_la_empresa(self):
        r = self.client.get(reverse('ubicacion_nueva'))
        self.assertContains(r, 'id_empresa_nueva')
        self.assertContains(r, 'empresa_sucursal.js')
        sucursal = Ubicacion.objects.create(cliente=self.lucas, nombre='Oficinas')
        r = self.client.get(reverse('ubicacion_editar', args=[sucursal.pk]))
        self.assertEqual(r.status_code, 200)
        for campo in ('latitud', 'longitud'):  # ya no se piden
            self.assertNotContains(r, f'id_{campo}')


class NombreDelEquipoYRutTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', rol=User.Rol.ADMIN)
        self.client.force_login(self.admin)

    def test_el_equipo_ya_no_pide_nombre_y_se_genera_del_tipo(self):
        r = self.client.get(reverse('activo_nuevo'))
        self.assertNotContains(r, 'id_nombre')
        self.client.post(reverse('activo_nuevo'), {
            'cliente': '', 'empresa_nueva': 'Nueva SpA', 'ubicacion': '', 'ubicacion_nueva': '', 'numero_equipo': '5',
            'tipo': 'cassette', 'marca': 'MIDEA', 'modelo': 'X1', 'estado': 'activo', 'condicion': 'buena', 'codigo': ''})
        self.assertEqual(Activo.objects.get().nombre, 'Cassette')

    def test_el_cliente_ya_no_guarda_rut_ni_razon_social(self):
        r = self.client.get(reverse('cliente_nuevo'))
        self.assertNotContains(r, 'id_rut')
        self.assertNotContains(r, 'RUT')
        self.assertContains(r, 'Nombre de la empresa')
        self.assertFalse(hasattr(Cliente(), 'rut'))
        self.client.post(reverse('cliente_nuevo'), {'nombre': 'Lucas Diesel', 'giro': '', 'contacto': 'Nicolás',
                                                    'email': '', 'telefono': '', 'activo': 'on'})
        self.assertEqual(Cliente.objects.get().nombre, 'Lucas Diesel')

    def test_la_cotizacion_en_pdf_no_muestra_rut(self):
        from cotizaciones.models import CotizacionItem

        cliente = Cliente.objects.create(nombre='Lucas Diesel')
        cot = Cotizacion.objects.create(cliente=cliente, titulo='Servicio')
        CotizacionItem.objects.create(cotizacion=cot, descripcion='Servicio', cantidad=1, precio_unitario=1000)
        r = self.client.get(reverse('cotizacion_pdf', args=[cot.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b'%PDF'))


class EliminarTests(TestCase):
    """Eliminar empresas, sucursales y equipos; lo que tiene historial se desactiva en vez de borrarse."""

    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', rol=User.Rol.ADMIN)
        self.tecnico = User.objects.create_user('tec', password='x', rol=User.Rol.TECNICO)
        self.empresa = Cliente.objects.create(nombre='Lucas Diesel')
        self.sucursal = Ubicacion.objects.create(cliente=self.empresa, nombre='Oficinas')
        self.equipo = Activo.objects.create(ubicacion=self.sucursal, codigo='L-1', nombre='Split', numero_equipo='1')
        self.client.force_login(self.admin)

    def con_historial(self):
        orden = OrdenTrabajo.objects.create(titulo='OT', cliente=self.empresa, ubicacion=self.sucursal)
        orden.activos.add(self.equipo)
        informe = Informe.objects.create(orden=orden)
        InformeEquipo.objects.create(informe=informe, activo=self.equipo)

    # --- botón en la pantalla de editar ---
    def test_editar_muestra_el_boton_eliminar_solo_al_administrador(self):
        for nombre, objeto in (('cliente_editar', self.empresa), ('ubicacion_editar', self.sucursal),
                               ('activo_editar', self.equipo)):
            r = self.client.get(reverse(nombre, args=[objeto.pk]))
            self.assertContains(r, 'Eliminar', msg_prefix=nombre)
        self.client.force_login(self.tecnico)  # el técnico edita equipos, pero no los elimina
        self.assertNotContains(self.client.get(reverse('activo_editar', args=[self.equipo.pk])), 'Eliminar')
        for nombre, objeto in (('cliente_eliminar', self.empresa), ('ubicacion_eliminar', self.sucursal),
                               ('activo_eliminar', self.equipo)):
            self.assertEqual(self.client.get(reverse(nombre, args=[objeto.pk])).status_code, 403, nombre)
            self.assertEqual(self.client.post(reverse(nombre, args=[objeto.pk])).status_code, 403, nombre)
        self.assertTrue(Activo.objects.filter(pk=self.equipo.pk).exists())

    # --- equipo ---
    def test_elimina_un_equipo_sin_historial_previa_confirmacion(self):
        r = self.client.get(reverse('activo_eliminar', args=[self.equipo.pk]))
        self.assertContains(r, 'no se puede deshacer')
        self.assertTrue(Activo.objects.exists())  # mirar la confirmación no borra nada
        r = self.client.post(reverse('activo_eliminar', args=[self.equipo.pk]), follow=True)
        self.assertRedirects(r, reverse('activos'))
        self.assertContains(r, 'eliminado')
        self.assertFalse(Activo.objects.exists())

    def test_un_equipo_con_historial_no_se_elimina_y_se_puede_dar_de_baja(self):
        self.con_historial()
        r = self.client.get(reverse('activo_eliminar', args=[self.equipo.pk]))
        self.assertContains(r, 'No se puede eliminar porque tiene historial')
        self.assertContains(r, '1 informe técnico')
        self.assertNotContains(r, 'Sí, eliminar definitivamente')
        self.client.post(reverse('activo_eliminar', args=[self.equipo.pk]))  # aunque fuerce el envío
        self.assertTrue(Activo.objects.filter(pk=self.equipo.pk).exists())
        self.client.post(reverse('activo_eliminar', args=[self.equipo.pk]), {'accion': 'desactivar'})
        self.equipo.refresh_from_db()
        self.assertEqual(self.equipo.estado, Activo.Estado.BAJA)

    # --- sucursal ---
    def test_elimina_una_sucursal_junto_con_sus_equipos_si_no_tienen_historial(self):
        r = self.client.get(reverse('ubicacion_eliminar', args=[self.sucursal.pk]))
        self.assertContains(r, '1 equipo')
        self.client.post(reverse('ubicacion_eliminar', args=[self.sucursal.pk]))
        self.assertFalse(Ubicacion.objects.exists())
        self.assertFalse(Activo.objects.exists())
        self.assertTrue(Cliente.objects.exists())  # la empresa sigue

    def test_una_sucursal_con_ordenes_no_se_elimina_y_se_desactiva(self):
        self.con_historial()
        r = self.client.get(reverse('ubicacion_eliminar', args=[self.sucursal.pk]))
        self.assertContains(r, 'orden de trabajo en esta sucursal')
        self.client.post(reverse('ubicacion_eliminar', args=[self.sucursal.pk]))
        self.assertTrue(Ubicacion.objects.exists())
        self.client.post(reverse('ubicacion_eliminar', args=[self.sucursal.pk]), {'accion': 'desactivar'})
        self.sucursal.refresh_from_db()
        self.assertFalse(self.sucursal.activa)

    # --- empresa ---
    def test_elimina_una_empresa_con_sus_sucursales_y_equipos_si_no_tiene_historial(self):
        r = self.client.get(reverse('cliente_eliminar', args=[self.empresa.pk]))
        self.assertContains(r, '1 sucursal')
        self.assertContains(r, '1 equipo')
        self.client.post(reverse('cliente_eliminar', args=[self.empresa.pk]))
        self.assertFalse(Cliente.objects.exists() or Ubicacion.objects.exists() or Activo.objects.exists())

    def test_una_empresa_con_ordenes_cotizaciones_o_usuarios_no_se_elimina(self):
        self.con_historial()
        Cotizacion.objects.create(cliente=self.empresa, titulo='C')
        User.objects.create_user('cli', password='x', rol=User.Rol.CLIENTE, cliente=self.empresa, email='c@x.cl')
        r = self.client.get(reverse('cliente_eliminar', args=[self.empresa.pk]))
        for texto in ('1 orden de trabajo', '1 cotización', '1 usuario cliente asociado'):
            self.assertContains(r, texto)
        self.client.post(reverse('cliente_eliminar', args=[self.empresa.pk]))
        self.assertTrue(Cliente.objects.filter(pk=self.empresa.pk).exists())
        self.client.post(reverse('cliente_eliminar', args=[self.empresa.pk]), {'accion': 'desactivar'})
        self.empresa.refresh_from_db()
        self.assertFalse(self.empresa.activo)
        # una empresa desactivada ya no se ofrece al crear equipos nuevos
        r = self.client.get(reverse('activo_nuevo'))
        self.assertNotIn(self.empresa, list(r.context['form'].fields['cliente'].queryset))
