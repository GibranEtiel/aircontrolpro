import base64
import binascii
from collections import OrderedDict
from datetime import date

from django.contrib import messages
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, UpdateView
from PIL import Image

from accounts.models import User
from catalogo.models import Activo, Cliente, Ubicacion
from core.exports import EMPRESA, MESES_ES, Col, exportar_tabla, formato_export
from core.permissions import (RolRequiredMixin, informes_visibles, ordenes_visibles,
                              rol_required)

from .exports import equipos_a_excel, ficha_a_pdf, informe_a_excel, informe_a_pdf, reporte_pdf
from .forms import EquipoNuevoForm, InformeEquipoForm, InformeForm, InformeNuevoForm, OrdenForm
from .models import (PASO_NOMBRE, TAREAS_CLAVES, FotoInforme, Informe, InformeEquipo,
                     OrdenTrabajo)

ADMIN, TECNICO, CLIENTE = User.Rol.ADMIN, User.Rol.TECNICO, User.Rol.CLIENTE
TIPO_POR_ORDEN = {
    OrdenTrabajo.Tipo.CORRECTIVO: InformeEquipo.Tipo.CORRECTIVO,
    OrdenTrabajo.Tipo.EMERGENCIA: InformeEquipo.Tipo.CORRECTIVO,
}


def _puede_editar(user, informe):
    """El administrador edita siempre; el técnico su informe mientras no esté emitido al cliente."""
    if user.es_admin:
        return True
    return (user.es_tecnico and informe.tecnico_id == user.pk
            and informe.estado in (Informe.Estado.BORRADOR, Informe.Estado.ENVIADO))


# --- Órdenes de trabajo ---------------------------------------------------

@rol_required(ADMIN, TECNICO, CLIENTE)
def orden_lista(request):
    qs = ordenes_visibles(request.user)
    estado = request.GET.get('estado', '')
    tipo = request.GET.get('tipo', '')
    mes = request.GET.get('mes', '')
    q = request.GET.get('q', '').strip()
    if estado in OrdenTrabajo.Estado.values:
        qs = qs.filter(estado=estado)
    if tipo in OrdenTrabajo.Tipo.values:
        qs = qs.filter(tipo=tipo)
    if len(mes) == 7 and mes[4] == '-' and mes[:4].isdigit() and mes[5:].isdigit():
        qs = qs.filter(fecha_programada__year=int(mes[:4]), fecha_programada__month=int(mes[5:]))
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(titulo__icontains=q) |
                       Q(cliente__nombre__icontains=q) | Q(ubicacion__nombre__icontains=q))
    formato = formato_export(request)
    if formato:
        return _exportar_ordenes(request.user, qs, formato)
    return render(request, 'mantenciones/ordenes_list.html', {
        'ordenes': qs[:300], 'estado': estado, 'tipo': tipo, 'mes': mes, 'q': q,
        'estados': OrdenTrabajo.Estado.choices, 'tipos': OrdenTrabajo.Tipo.choices,
    })


def _exportar_ordenes(user, qs, formato):
    columnas = [Col('N° OT'), Col('Título'), Col('Cliente'), Col('Ubicación'), Col('Tipo'), Col('Prioridad'),
                Col('Técnico'), Col('Fecha programada', 'fecha'), Col('Estado')]
    if user.es_admin:  # las finanzas solo las ve el administrador
        columnas += [Col('Monto neto', 'clp'), Col('Costos', 'clp'), Col('Utilidad', 'clp'), Col('Pago')]
    filas = []
    for o in qs:
        fila = [o.numero, o.titulo, o.cliente, o.ubicacion.nombre, o.get_tipo_display(),
                o.get_prioridad_display(), o.tecnico, o.fecha_programada, o.get_estado_display()]
        if user.es_admin:
            fila += [o.monto_neto, o.costo_total, o.utilidad, o.get_estado_pago_display()]
        filas.append(fila)
    return exportar_tabla(formato, 'ordenes-de-trabajo', 'Órdenes de trabajo', columnas, filas)


@rol_required(ADMIN, TECNICO, CLIENTE)
def orden_detalle(request, pk):
    orden = get_object_or_404(ordenes_visibles(request.user), pk=pk)
    informe = getattr(orden, 'informe', None)
    if request.user.es_cliente and (informe is None or informe.estado != Informe.Estado.EMITIDO):
        informe = None
    por_activo = {}
    if informe is not None:
        por_activo = {e.activo_id: e for e in informe.equipos.prefetch_related('fotos')}
    activos = list(orden.activos.select_related('ubicacion'))
    return render(request, 'mantenciones/orden_detalle.html', {
        'orden': orden, 'informe': informe, 'activos': activos,
        'filas_equipos': [(a, por_activo.get(a.pk)) for a in activos],
        'puede_iniciar': request.user.es_tecnico and orden.estado in (
            OrdenTrabajo.Estado.PENDIENTE, OrdenTrabajo.Estado.EN_PROCESO),
    })


class OrdenCreate(RolRequiredMixin, CreateView):
    roles = (ADMIN,)
    form_class = OrdenForm
    template_name = 'mantenciones/orden_form.html'
    extra_context = {'titulo': 'Nueva orden de trabajo'}

    def _cotizacion(self):
        """Cotización aceptada desde la que se genera la orden (?cotizacion=<id>), si no tiene orden aún."""
        from cotizaciones.models import Cotizacion

        pk = self.request.GET.get('cotizacion', '')
        if not pk.isdigit():
            return None
        return Cotizacion.objects.filter(pk=pk, orden__isnull=True).select_related('cliente').first()

    def get_initial(self):
        initial = super().get_initial()
        cot = self._cotizacion()
        if cot:
            initial.update(titulo=cot.titulo, descripcion=cot.descripcion, monto_neto=cot.neto,
                           atencion=cot.contacto, ubicacion=cot.ubicacion_id)
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cotizacion'] = self._cotizacion()
        return ctx

    def form_valid(self, form):
        form.instance.creada_por = self.request.user
        response = super().form_valid(form)
        cot = self._cotizacion()
        if cot:
            cot.orden = self.object
            cot.save(update_fields=['orden'])
        messages.success(self.request, 'Orden de trabajo creada.')
        return response

    def get_success_url(self):
        return self.object.get_absolute_url()


class OrdenUpdate(RolRequiredMixin, UpdateView):
    roles = (ADMIN,)
    model = OrdenTrabajo
    form_class = OrdenForm
    template_name = 'mantenciones/orden_form.html'
    extra_context = {'titulo': 'Editar orden de trabajo'}

    def form_valid(self, form):
        messages.success(self.request, 'Orden de trabajo actualizada.')
        return super().form_valid(form)

    def get_success_url(self):
        return self.object.get_absolute_url()


@require_POST
@rol_required(ADMIN)
def orden_pago(request, pk):
    orden = get_object_or_404(OrdenTrabajo, pk=pk)
    if orden.estado_pago == OrdenTrabajo.Pago.PAGADO:
        orden.estado_pago, orden.fecha_pago = OrdenTrabajo.Pago.PENDIENTE, None
    else:
        orden.estado_pago, orden.fecha_pago = OrdenTrabajo.Pago.PAGADO, timezone.localdate()
    orden.save(update_fields=['estado_pago', 'fecha_pago'])
    messages.success(request, f'{orden.numero}: {orden.get_estado_pago_display().lower()}.')
    return redirect(request.POST.get('next') or 'finanzas')


@rol_required(TECNICO)
def informe_nuevo(request):
    """El técnico abre un informe en terreno: se crea la orden (a su nombre) y el informe."""
    form = InformeNuevoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        ahora = timezone.now()
        orden = OrdenTrabajo.objects.create(
            titulo=d['titulo'] or f'{OrdenTrabajo.Tipo(d["tipo"]).label} A/A - {d["ubicacion"].nombre}',
            tipo=d['tipo'], estado=OrdenTrabajo.Estado.EN_PROCESO, cliente=d['ubicacion'].cliente,
            ubicacion=d['ubicacion'], tecnico=request.user, atencion=d['atencion'],
            fecha_inicio=ahora, creada_por=request.user)
        informe = Informe.objects.create(orden=orden, tecnico=request.user, inicio=ahora)
        messages.success(request, f'Orden {orden.numero} creada. Agrega los equipos que vas a intervenir.')
        return redirect('informe_editar', pk=informe.pk)
    return render(request, 'mantenciones/informe_nuevo.html', {'form': form})


@require_POST
@rol_required(TECNICO)
def orden_iniciar(request, pk):
    """El técnico inicia el trabajo: la orden pasa a «en proceso» y se abre el informe."""
    orden = get_object_or_404(ordenes_visibles(request.user), pk=pk)
    if orden.estado not in (OrdenTrabajo.Estado.PENDIENTE, OrdenTrabajo.Estado.EN_PROCESO):
        messages.error(request, 'Esta orden ya no se puede iniciar.')
        return redirect('orden_detalle', pk=orden.pk)

    informe, _ = Informe.objects.get_or_create(orden=orden, defaults={'tecnico': request.user})
    if orden.estado == OrdenTrabajo.Estado.PENDIENTE:
        orden.estado = OrdenTrabajo.Estado.EN_PROCESO
        orden.fecha_inicio = timezone.now()
        orden.save(update_fields=['estado', 'fecha_inicio'])
    return redirect('informe_editar', pk=informe.pk)


# --- Informes técnicos ----------------------------------------------------

@rol_required(ADMIN, TECNICO, CLIENTE)
def informe_lista(request):
    qs = informes_visibles(request.user)
    q = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '')
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(orden__numero__icontains=q) |
                       Q(orden__titulo__icontains=q) | Q(orden__ubicacion__nombre__icontains=q) |
                       Q(orden__cliente__nombre__icontains=q))
    if estado in Informe.Estado.values and not request.user.es_cliente:
        qs = qs.filter(estado=estado)

    informes = sorted(qs, key=lambda i: i.fecha_referencia, reverse=True)
    meses = OrderedDict()
    for inf in informes:
        ref = timezone.localtime(inf.fecha_referencia)
        meses.setdefault(date(ref.year, ref.month, 1), []).append(inf)
    formato = formato_export(request)
    if formato:
        return _exportar_informes(request.user, meses, formato)
    return render(request, 'mantenciones/informes_list.html', {
        'meses': list(meses.items()), 'total': len(informes), 'q': q, 'estado': estado,
        'estados': Informe.Estado.choices,
    })


def _exportar_informes(user, meses, formato):
    columnas = [Col('Mes'), Col('N° informe'), Col('N° OT'), Col('Trabajo'), Col('Cliente'),
                Col('Ubicación'), Col('Técnico'), Col('Fecha', 'fecha')]
    if not user.es_cliente:
        columnas.append(Col('Estado'))
    filas = []
    for mes, informes in meses.items():
        for i in informes:
            fila = [f'{MESES_ES[mes.month - 1]} {mes.year}', i.numero, i.orden.numero, i.orden.titulo,
                    i.orden.cliente, i.orden.ubicacion.nombre, i.tecnico,
                    timezone.localtime(i.fecha_referencia).date()]
            if not user.es_cliente:
                fila.append(i.get_estado_display())
            filas.append(fila)
    return exportar_tabla(formato, 'informes-tecnicos', 'Informes técnicos por mes', columnas, filas)


def _quien_genero(user, informe=None):
    """Nombre que va en 'GENERÓ': quien emitió el informe o, si no, quien lo descarga."""
    if informe is not None and informe.emitido_por_id:
        return informe.emitido_por.nombre
    return EMPRESA if user.es_cliente else user.nombre


@rol_required(ADMIN, TECNICO, CLIENTE)
def informe_pdf(request, pk):
    informe = get_object_or_404(informes_visibles(request.user), pk=pk)
    return informe_a_pdf(informe, _quien_genero(request.user, informe))


@rol_required(ADMIN, TECNICO, CLIENTE)
def informe_excel(request, pk):
    informe = get_object_or_404(informes_visibles(request.user), pk=pk)
    return informe_a_excel(informe, _quien_genero(request.user, informe))


@rol_required(ADMIN, TECNICO, CLIENTE)
def equipo_pdf(request, pk):
    """Ficha de un equipo en el formato del informe, disponible apenas el técnico lo termina."""
    equipo = get_object_or_404(
        InformeEquipo.objects.filter(informe__in=informes_visibles(request.user), finalizado=True)
        .select_related('activo', 'activo__ubicacion', 'informe', 'informe__orden', 'informe__orden__cliente',
                        'informe__orden__ubicacion', 'informe__tecnico', 'informe__emitido_por')
        .prefetch_related('fotos'), pk=pk)
    return ficha_a_pdf(equipo, _quien_genero(request.user, equipo.informe))


# --- Informe general del mes --------------------------------------------------

def _anio_mes(valor):
    try:
        anio, mes = (int(x) for x in valor.split('-'))
        date(anio, mes, 1)
        return anio, mes
    except (AttributeError, ValueError):
        hoy = timezone.localdate()
        return hoy.year, hoy.month


def _equipos_del_mes(user, cliente, ubicacion_id, anio, mes, incluir_borradores):
    qs = (InformeEquipo.objects
          .filter(finalizado=True, informe__orden__cliente=cliente,
                  completado_en__year=anio, completado_en__month=mes)
          .select_related('activo', 'activo__ubicacion', 'informe', 'informe__orden', 'informe__orden__cliente',
                          'informe__orden__ubicacion', 'informe__tecnico')
          .prefetch_related('fotos')
          .order_by('activo__numero_equipo', 'activo__codigo'))
    if str(ubicacion_id).isdigit():
        qs = qs.filter(informe__orden__ubicacion_id=ubicacion_id)
    if user.es_cliente:
        qs = qs.filter(informe__estado=Informe.Estado.EMITIDO)
    elif not incluir_borradores:
        qs = qs.filter(informe__estado__in=[Informe.Estado.ENVIADO, Informe.Estado.EMITIDO])
    return qs


@rol_required(ADMIN, CLIENTE)
def informe_mensual(request):
    """Informe general con todos los equipos intervenidos en el mes para un cliente."""
    user = request.user
    anio, mes = _anio_mes(request.GET.get('mes'))
    if user.es_cliente:
        cliente, clientes = user.cliente, None
    else:
        clientes = list(Cliente.objects.filter(activo=True))
        elegido = request.GET.get('cliente') or (str(clientes[0].pk) if len(clientes) == 1 else '')
        cliente = next((c for c in clientes if str(c.pk) == elegido), None)
    ubicaciones = Ubicacion.objects.filter(cliente=cliente) if cliente else Ubicacion.objects.none()
    ubicacion_id = request.GET.get('ubicacion', '')
    borradores = user.es_admin and request.GET.get('borradores') == '1'
    equipos = list(_equipos_del_mes(user, cliente, ubicacion_id, anio, mes, borradores)) if cliente else []

    formato = formato_export(request)
    if formato and equipos:
        fecha_texto = f'{MESES_ES[mes - 1].upper()} {anio}'
        nombre = f'informe-mensual-{cliente}-{anio}-{mes:02d}'
        quien = _quien_genero(user)
        if formato == 'pdf':
            return reporte_pdf(equipos, nombre, fecha_texto, quien)
        return equipos_a_excel(nombre, f'Informe mensual {fecha_texto}', equipos, fecha_texto, quien)
    if formato:
        messages.warning(request, 'No hay equipos intervenidos para exportar con esos filtros.')

    sin_revisar = 0
    if user.es_admin and cliente and not borradores:
        sin_revisar = (_equipos_del_mes(user, cliente, ubicacion_id, anio, mes, True).count() - len(equipos))
    return render(request, 'mantenciones/informe_mensual.html', {
        'cliente': cliente, 'clientes': clientes, 'ubicaciones': ubicaciones, 'ubicacion_id': ubicacion_id,
        'mes_valor': f'{anio}-{mes:02d}', 'mes_nombre': f'{MESES_ES[mes - 1]} {anio}', 'equipos': equipos,
        'borradores': borradores, 'sin_revisar': sin_revisar,
        'resumen': {
            'ordenes': len({e.informe.orden_id for e in equipos}),
            'fuera_norma': sum(1 for e in equipos if e.fuera_de_norma),
            'con_observaciones': sum(1 for e in equipos if e.observaciones.strip()),
            'fotos': sum(len(e.fotos.all()) for e in equipos),
        },
    })


@rol_required(ADMIN, TECNICO, CLIENTE)
def informe_detalle(request, pk):
    informe = get_object_or_404(informes_visibles(request.user), pk=pk)
    equipos = informe.equipos.select_related('activo').prefetch_related('fotos')
    return render(request, 'mantenciones/informe_detalle.html', {
        'informe': informe, 'orden': informe.orden, 'equipos': equipos,
        'fotos_generales': informe.fotos.filter(equipo__isnull=True),
        'puede_editar': _puede_editar(request.user, informe),
        'puede_emitir': request.user.es_admin and informe.estado == Informe.Estado.ENVIADO,
    })


@rol_required(ADMIN, TECNICO)
def informe_editar(request, pk):
    informe = get_object_or_404(informes_visibles(request.user), pk=pk)
    if not _puede_editar(request.user, informe):
        messages.info(request, 'Este informe ya no se puede editar.')
        return redirect('informe_detalle', pk=informe.pk)

    for activo in informe.orden.activos.all():
        _nuevo_informe_equipo(informe, activo)
    equipos = list(informe.equipos.select_related('activo').prefetch_related('fotos'))

    if request.method == 'POST':
        form = InformeForm(request.POST, instance=informe)
        forms_eq = [InformeEquipoForm(request.POST, instance=eq, prefix=f'eq{eq.pk}') for eq in equipos]
        if form.is_valid() and all(f.is_valid() for f in forms_eq):
            form.save()
            for f in forms_eq:
                eq = f.save(commit=False)
                eq.tareas = f.cleaned_data['tareas']
                eq.save()
            _guardar_firma(informe, request.POST.get('firma_data', ''))
            accion = request.POST.get('accion', 'guardar')
            if accion == 'enviar' and informe.estado == Informe.Estado.BORRADOR:
                return _enviar_informe(request, informe)
            if accion.startswith('terminar_'):
                return _terminar_equipo(request, informe, accion.split('_', 1)[1])
            if accion == 'agregar':
                return _agregar_equipos(request, informe)
            if accion == 'nuevo':
                return _equipo_nuevo(request, informe)
            if accion.startswith('quitar_'):
                return _quitar_equipo(request, informe, accion.split('_', 1)[1])
            messages.success(request, 'Borrador guardado.' if informe.estado == Informe.Estado.BORRADOR
                             else 'Cambios guardados.')
            return redirect('informe_editar', pk=informe.pk)
        messages.error(request, 'Revisa los campos marcados.')
    else:
        form = InformeForm(instance=informe)
        forms_eq = [InformeEquipoForm(instance=eq, prefix=f'eq{eq.pk}') for eq in equipos]

    orden = informe.orden
    disponibles = (Activo.objects.filter(ubicacion__cliente=orden.cliente, estado=Activo.Estado.ACTIVO)
                   .exclude(pk__in=[e.activo_id for e in equipos]).select_related('ubicacion')
                   .order_by('numero_equipo', 'codigo'))
    ubicaciones = Ubicacion.objects.filter(cliente=orden.cliente)
    return render(request, 'mantenciones/informe_form.html', {
        'informe': informe, 'orden': orden, 'form': form,
        'bloques': list(zip(equipos, forms_eq)),
        'fotos_generales': informe.fotos.filter(equipo__isnull=True),
        'etapas': FotoInforme.Etapa.choices, 'disponibles': disponibles,
        'nuevo_form': EquipoNuevoForm(prefix='nuevo', ubicaciones=ubicaciones,
                                      initial={'ubicacion': orden.ubicacion_id}),
        'es_borrador': informe.estado == Informe.Estado.BORRADOR,
        'hay_terminados': any(e.finalizado for e in equipos),
        'faltan_fotos': [e for e in equipos if e.finalizado and e.pasos_pendientes],
    })


def _nuevo_informe_equipo(informe, activo):
    return InformeEquipo.objects.get_or_create(
        informe=informe, activo=activo,
        defaults={'tareas': TAREAS_CLAVES, 'fuera_de_norma': activo.fuera_de_norma,
                  'tipo_mantenimiento': TIPO_POR_ORDEN.get(informe.orden.tipo, InformeEquipo.Tipo.PREVENTIVO)})[0]


def _agregar_equipos(request, informe):
    """Suma al informe equipos de la misma empresa que no estaban en la orden."""
    orden = informe.orden
    activos = Activo.objects.filter(pk__in=[p for p in request.POST.getlist('agregar_activos') if p.isdigit()],
                                    ubicacion__cliente=orden.cliente)
    ultimo = None
    for activo in activos:
        orden.activos.add(activo)
        ultimo = _nuevo_informe_equipo(informe, activo)
    if ultimo is None:
        messages.warning(request, 'Marca al menos un equipo de la lista para agregarlo.')
        return redirect('informe_editar', pk=informe.pk)
    messages.success(request, f'{len(activos)} equipo(s) agregado(s) al informe.')
    return redirect(f"{reverse('informe_editar', args=[informe.pk])}#eq-{ultimo.pk}")


def _equipo_nuevo(request, informe):
    """Crea un equipo nuevo del cliente (no estaba en el catálogo) y lo agrega al informe."""
    orden = informe.orden
    form = EquipoNuevoForm(request.POST, prefix='nuevo',
                           ubicaciones=Ubicacion.objects.filter(cliente=orden.cliente))
    if not form.is_valid():
        errores = '; '.join(e for lista in form.errors.values() for e in lista)
        messages.error(request, f'No se pudo crear el equipo: {errores}')
        return redirect(f"{reverse('informe_editar', args=[informe.pk])}#nuevo-equipo")
    d = form.cleaned_data
    prefijo = slugify(orden.cliente.nombre.split()[0]).upper()[:8] or 'EQ'
    codigo, n = f'{prefijo}-{d["numero_equipo"]}', 1
    while Activo.objects.filter(codigo=codigo).exists():
        n += 1
        codigo = f'{prefijo}-{d["numero_equipo"]}-{n}'
    activo = Activo.objects.create(
        ubicacion=d['ubicacion'], codigo=codigo, numero_equipo=d['numero_equipo'],
        nombre=f'{d["marca"]} {d["modelo"]}'.strip() or f'Equipo {d["numero_equipo"]}', marca=d['marca'],
        modelo=d['modelo'], ubicacion_exacta=d['ubicacion_exacta'], refrigerante=d['refrigerante'])
    orden.activos.add(activo)
    eq = _nuevo_informe_equipo(informe, activo)
    messages.success(request, f'{activo.etiqueta} creado y agregado al informe.')
    return redirect(f"{reverse('informe_editar', args=[informe.pk])}#eq-{eq.pk}")


def _quitar_equipo(request, informe, equipo_pk):
    """Saca un equipo del informe (y de la orden), con sus fotos."""
    eq = informe.equipos.select_related('activo').filter(pk=equipo_pk).first()
    if eq is not None:
        for foto in eq.fotos.all():
            foto.imagen.delete(save=False)
        informe.orden.activos.remove(eq.activo)
        etiqueta = eq.activo.etiqueta
        eq.delete()
        messages.info(request, f'{etiqueta} quitado del informe.')
    return redirect('informe_editar', pk=informe.pk)


def _guardar_firma(informe, data_url):
    if not data_url.startswith('data:image/png;base64,'):
        return
    try:
        contenido = base64.b64decode(data_url.split(',', 1)[1])
    except (binascii.Error, ValueError):
        return
    informe.firma.save(f'{informe.numero}.png', ContentFile(contenido), save=True)


def _terminar_equipo(request, informe, equipo_pk):
    """Marca un equipo como terminado: desde ese momento su ficha PDF está disponible."""
    volver = reverse('informe_editar', args=[informe.pk])
    eq = informe.equipos.select_related('activo').filter(pk=equipo_pk).first()
    if eq is None:
        return redirect(volver)
    if not eq.fotos.exists():
        messages.error(request, f'Sube al menos una foto del {eq.activo.etiqueta} antes de terminarlo.')
        return redirect(f'{volver}#eq-{eq.pk}')
    if not eq.finalizado:
        eq.finalizado, eq.completado_en = True, timezone.now()
        eq.save(update_fields=['finalizado', 'completado_en'])
    messages.success(request, f'{eq.activo.etiqueta} terminado. Su informe PDF ya está disponible.')
    if eq.pasos_pendientes:
        messages.warning(request, f'Faltan fotos del {eq.activo.etiqueta}: {eq.pendientes_texto}. '
                                  'Puedes agregarlas después desde este mismo informe.')
    return redirect(f'{volver}#eq-{eq.pk}')


def _enviar_informe(request, informe):
    pendientes = [e.activo.etiqueta for e in informe.equipos.select_related('activo') if not e.finalizado]
    if pendientes:
        messages.error(request, 'Antes de enviar, termina: ' + ', '.join(pendientes) + '.')
        return redirect('informe_editar', pk=informe.pk)
    if not informe.equipos.exists() and not informe.fotos.exists():
        messages.error(request, 'Agrega al menos una foto antes de enviar el informe.')
        return redirect('informe_editar', pk=informe.pk)
    informe.estado = Informe.Estado.ENVIADO
    informe.termino = timezone.now()
    informe.save()
    orden = informe.orden
    orden.estado = OrdenTrabajo.Estado.EN_REVISION
    orden.fecha_termino = informe.termino
    orden.save(update_fields=['estado', 'fecha_termino'])
    messages.success(request, 'Informe enviado a revisión.')
    con_faltas = [e for e in informe.equipos.select_related('activo').prefetch_related('fotos') if e.pasos_pendientes]
    if con_faltas:
        messages.warning(request, 'Aún faltan fotos en: ' + '; '.join(
            f'{e.activo.etiqueta} ({e.pendientes_texto})' for e in con_faltas)
            + '. Puedes completarlas editando el informe mientras esté en revisión.')
    return redirect('informe_detalle', pk=informe.pk)


@require_POST
@rol_required(ADMIN, TECNICO)
def foto_subir(request, pk):
    informe = get_object_or_404(informes_visibles(request.user), pk=pk)
    if not _puede_editar(request.user, informe):
        return JsonResponse({'error': 'El informe no se puede editar.'}, status=403)
    archivo = request.FILES.get('imagen')
    if archivo is None:
        return JsonResponse({'error': 'Falta la imagen.'}, status=400)
    try:
        Image.open(archivo).verify()
        archivo.seek(0)
    except Exception:
        return JsonResponse({'error': 'El archivo no es una imagen válida.'}, status=400)

    equipo = None
    if request.POST.get('equipo'):
        equipo = informe.equipos.filter(pk=request.POST['equipo']).first()
    etapa = request.POST.get('etapa')
    paso = request.POST.get('paso', '')
    if paso and (paso not in PASO_NOMBRE or equipo is None):
        return JsonResponse({'error': 'Paso de foto no válido.'}, status=400)
    if paso:  # cada paso tiene una sola foto: volver a tomarla reemplaza la anterior
        for anterior in FotoInforme.objects.filter(equipo=equipo, paso=paso):
            anterior.imagen.delete(save=False)
            anterior.delete()
    foto = FotoInforme(
        informe=informe, equipo=equipo, imagen=archivo, paso=paso,
        etapa=etapa if etapa in FotoInforme.Etapa.values else FotoInforme.Etapa.OTRO,
        descripcion=request.POST.get('descripcion', '')[:200],
    )
    foto.save()
    respuesta = {
        'id': foto.pk, 'url': foto.imagen.url, 'etapa': foto.get_etapa_display(), 'paso': foto.paso,
        'titulo': foto.titulo, 'eliminar': reverse('foto_eliminar', args=[foto.pk]),
    }
    if equipo is not None:
        equipo = InformeEquipo.objects.prefetch_related('fotos').get(pk=equipo.pk)
        respuesta['faltan'] = [p['nombre'] for p in equipo.pasos_pendientes]
    return JsonResponse(respuesta)


@require_POST
@rol_required(ADMIN, TECNICO)
def foto_eliminar(request, pk):
    foto = get_object_or_404(FotoInforme.objects.select_related('informe'), pk=pk)
    informe = get_object_or_404(informes_visibles(request.user), pk=foto.informe_id)
    if not _puede_editar(request.user, informe):
        return JsonResponse({'error': 'No se puede editar.'}, status=403)
    equipo_id = foto.equipo_id
    foto.imagen.delete(save=False)
    foto.delete()
    respuesta = {'ok': True}
    if equipo_id:
        equipo = InformeEquipo.objects.prefetch_related('fotos').get(pk=equipo_id)
        respuesta['faltan'] = [p['nombre'] for p in equipo.pasos_pendientes]
    return JsonResponse(respuesta)


@require_POST
@rol_required(ADMIN)
def informe_emitir(request, pk):
    informe = get_object_or_404(Informe, pk=pk, estado=Informe.Estado.ENVIADO)
    informe.estado = Informe.Estado.EMITIDO
    informe.emitido_en = timezone.now()
    informe.emitido_por = request.user
    informe.save(update_fields=['estado', 'emitido_en', 'emitido_por'])
    orden = informe.orden
    orden.estado = OrdenTrabajo.Estado.FINALIZADA
    orden.fecha_termino = orden.fecha_termino or informe.emitido_en
    orden.save(update_fields=['estado', 'fecha_termino'])
    messages.success(request, f'Informe {informe.numero} emitido: el cliente ya puede verlo.')
    return redirect('informe_detalle', pk=informe.pk)


@require_POST
@rol_required(ADMIN)
def informe_devolver(request, pk):
    informe = get_object_or_404(Informe, pk=pk, estado=Informe.Estado.ENVIADO)
    informe.estado = Informe.Estado.BORRADOR
    informe.save(update_fields=['estado'])
    orden = informe.orden
    orden.estado = OrdenTrabajo.Estado.EN_PROCESO
    orden.save(update_fields=['estado'])
    messages.info(request, 'Informe devuelto al técnico para correcciones.')
    return redirect('informe_detalle', pk=informe.pk)
