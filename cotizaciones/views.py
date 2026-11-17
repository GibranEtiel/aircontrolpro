from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib.units import mm
from reportlab.platypus import Spacer, Table, TableStyle

from accounts.models import User
from core.exports import (ANCHO_VERTICAL, AZUL, ESTILO_CELDA, Col, exportar_tabla, formato_export, p,
                          pdf_response, tabla, texto)
from core.permissions import rol_required

from .forms import CotizacionForm, ItemFormSet, SeguimientoForm
from .models import Cotizacion

ADMIN = User.Rol.ADMIN
Estado = Cotizacion.Estado


def _queryset():
    return Cotizacion.objects.select_related('cliente', 'ubicacion').prefetch_related('items')


@rol_required(ADMIN)
def cotizacion_lista(request):
    qs = _queryset()
    estado = request.GET.get('estado', '')
    q = request.GET.get('q', '').strip()
    if estado == 'por_llamar':
        qs = qs.filter(pk__in=Cotizacion.objects.por_llamar().values('pk'))
    elif estado in Estado.values:
        qs = qs.filter(estado=estado)
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(titulo__icontains=q) | Q(cliente__nombre__icontains=q) |
                       Q(contacto_nombre__icontains=q))

    formato = formato_export(request)
    if formato:
        columnas = [Col('N° cotización'), Col('Fecha', 'fecha'), Col('Cliente'), Col('Título'), Col('Contacto'),
                    Col('Teléfono'), Col('Correo'), Col('Neto', 'clp'), Col('Total con IVA', 'clp'),
                    Col('Estado'), Col('Días sin gestión')]
        filas = [[c.numero, c.fecha, c.cliente, c.titulo, c.contacto, c.telefono, c.email, c.neto, c.total,
                  c.get_estado_display(), c.dias_sin_gestion if c.estado == Estado.PENDIENTE else None]
                 for c in qs]
        return exportar_tabla(formato, 'cotizaciones', 'Cotizaciones', columnas, filas)

    todas = list(_queryset())
    pendientes = [c for c in todas if c.estado == Estado.PENDIENTE]
    anio = timezone.localdate().year
    del_anio = [c for c in todas if c.fecha.year == anio]
    aceptadas = [c for c in del_anio if c.estado == Estado.ACEPTADA]
    resueltas = [c for c in del_anio if c.estado != Estado.PENDIENTE]
    resumen = {
        'pendientes': len(pendientes), 'pendientes_monto': sum((c.neto for c in pendientes), Decimal('0')),
        'por_llamar': sum(1 for c in pendientes if c.por_llamar),
        'aceptadas_monto': sum((c.neto for c in aceptadas), Decimal('0')), 'aceptadas': len(aceptadas),
        'cierre': round(len(aceptadas) / len(resueltas) * 100) if resueltas else None, 'anio': anio,
    }
    vista = 'tablero' if request.GET.get('vista') == 'tablero' else 'lista'
    contexto = {
        'cotizaciones': list(qs[:300]), 'estado': estado, 'q': q, 'resumen': resumen, 'vista': vista,
        'estados': Estado.choices, 'dias_alerta': settings.COTIZACION_DIAS_ALERTA,
    }
    if vista == 'tablero':
        # El tablero muestra las tres columnas a la vez: el filtro de estado no aplica, la búsqueda sí.
        base = _queryset()
        if q:
            base = base.filter(Q(numero__icontains=q) | Q(titulo__icontains=q) | Q(cliente__nombre__icontains=q) |
                               Q(contacto_nombre__icontains=q))
        tarjetas = list(base.order_by('-fecha', '-numero')[:300])
        contexto['columnas'] = [
            {'estado': valor, 'label': etiqueta, 'tarjetas': [c for c in tarjetas if c.estado == valor]}
            for valor, etiqueta in Estado.choices]
        for col in contexto['columnas']:
            col['monto'] = sum((c.neto for c in col['tarjetas']), Decimal('0'))
    return render(request, 'cotizaciones/lista.html', contexto)


@rol_required(ADMIN)
def cotizacion_detalle(request, pk):
    cot = get_object_or_404(_queryset().prefetch_related('seguimientos__usuario'), pk=pk)
    return render(request, 'cotizaciones/detalle.html', {
        'cot': cot, 'items': cot.items.all(), 'seguimientos': cot.seguimientos.all(),
        'form_seguimiento': SeguimientoForm(), 'dias_alerta': settings.COTIZACION_DIAS_ALERTA,
    })


def _guardar(request, instancia, titulo_pagina):
    form = CotizacionForm(request.POST or None, instance=instancia)
    items = ItemFormSet(request.POST or None, instance=instancia)
    if request.method == 'POST' and form.is_valid() and items.is_valid():
        with transaction.atomic():
            cot = form.save(commit=False)
            if cot.pk is None:
                cot.creada_por = request.user
            cot.save()
            items.instance = cot
            items.save()
        messages.success(request, f'Cotización {cot.numero} guardada.')
        return redirect(cot)
    return render(request, 'cotizaciones/form.html', {'form': form, 'items': items, 'titulo': titulo_pagina})


@rol_required(ADMIN)
def cotizacion_nueva(request):
    return _guardar(request, None, 'Nueva cotización')


@rol_required(ADMIN)
def cotizacion_editar(request, pk):
    cot = get_object_or_404(Cotizacion, pk=pk)
    return _guardar(request, cot, f'Editar {cot.numero}')


@require_POST
@rol_required(ADMIN)
def seguimiento_agregar(request, pk):
    cot = get_object_or_404(Cotizacion, pk=pk)
    form = SeguimientoForm(request.POST)
    if form.is_valid():
        seg = form.save(commit=False)
        seg.cotizacion, seg.usuario = cot, request.user
        seg.save()
        messages.success(request, 'Seguimiento registrado: la cotización sale de la alerta por unos días.')
    else:
        messages.error(request, 'No se pudo guardar el seguimiento.')
    return redirect(cot)


@require_POST
@rol_required(ADMIN)
def cotizacion_estado(request, pk):
    cot = get_object_or_404(Cotizacion, pk=pk)
    accion = request.POST.get('accion')
    nuevo = {'aceptar': Estado.ACEPTADA, 'rechazar': Estado.RECHAZADA, 'reabrir': Estado.PENDIENTE}.get(accion)
    desde_tablero = request.headers.get('X-Requested-With') == 'fetch'  # el tablero arrastrable pide JSON
    if nuevo is None:
        if desde_tablero:
            return JsonResponse({'ok': False, 'error': 'Acción no válida.'}, status=400)
        return redirect(cot)
    cot.estado = nuevo
    cot.fecha_respuesta = None if nuevo == Estado.PENDIENTE else timezone.localdate()
    cot.save(update_fields=['estado', 'fecha_respuesta'])
    if desde_tablero:
        generar = nuevo == Estado.ACEPTADA and cot.orden_id is None
        return JsonResponse({
            'ok': True, 'estado': cot.estado, 'etiqueta': cot.get_estado_display(), 'numero': cot.numero,
            'orden_url': f"{reverse('orden_nueva')}?cotizacion={cot.pk}" if generar else None,
        })
    messages.success(request, f'{cot.numero}: {cot.get_estado_display().lower()}.')
    return redirect(cot)


@rol_required(ADMIN)
def cotizacion_pdf(request, pk):
    """Cotización lista para enviar al cliente."""
    cot = get_object_or_404(_queryset(), pk=pk)
    items = list(cot.items.all())
    cols = [Col('Descripción'), Col('Cant.'), Col('Precio unitario', 'clp'), Col('Subtotal', 'clp')]
    filas = [[i.descripcion, format(i.cantidad.normalize(), 'f'), i.precio_unitario, i.subtotal] for i in items]

    totales = Table([
        ['Neto', texto(cot.neto, 'clp')], ['IVA 19%', texto(cot.iva, 'clp')], ['TOTAL', texto(cot.total, 'clp')],
    ], colWidths=[30 * mm, 35 * mm], hAlign='RIGHT')
    totales.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'), ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'), ('LINEABOVE', (0, -1), (-1, -1), 0.8, AZUL),
        ('TEXTCOLOR', (0, -1), (-1, -1), AZUL), ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))

    datos_cliente = [f'Cliente: {cot.cliente.nombre}']
    if cot.contacto:
        datos_cliente.append(f'Dirigido a: {cot.contacto}')
    if cot.ubicacion:
        datos_cliente.append(f'Sucursal: {cot.ubicacion.nombre}')
    datos_cliente.append(f'Fecha: {cot.fecha:%d/%m/%Y} · Válida hasta el {cot.vence:%d/%m/%Y}')

    story = [p('\n'.join(datos_cliente)), Spacer(1, 5 * mm)]
    if cot.descripcion:
        story += [p(cot.descripcion), Spacer(1, 4 * mm)]
    story += [tabla(cols, filas, ANCHO_VERTICAL), Spacer(1, 4 * mm), totales, Spacer(1, 8 * mm),
              p(f'Valores netos en pesos chilenos. Consultas: {settings.EMPRESA_TELEFONO} · '
                f'{settings.EMPRESA_EMAIL} · {settings.EMPRESA_WEB}', ESTILO_CELDA)]
    return pdf_response(f'cotizacion-{cot.numero}', f'Cotización {cot.numero}', cot.titulo, story)
