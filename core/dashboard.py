"""Datos del dashboard del administrador, listos para serializar a JSON.

La página los incrusta al cargar y `dashboard_datos` los entrega de nuevo cuando el administrador cambia el
año o el cliente, así el dashboard se actualiza sin recargar.
"""

from datetime import timedelta

from django.db.models import Count, F, Sum
from django.db.models.functions import TruncMonth
from django.urls import reverse
from django.utils import timezone
from django.utils.timesince import timesince

from catalogo.models import Activo
from cotizaciones.models import Cotizacion, Seguimiento
from mantenciones.models import Informe, OrdenTrabajo

MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
Estado = OrdenTrabajo.Estado
COSTO = F('costo_materiales') + F('costo_mano_obra')


def _n(valor):
    return int(valor or 0)


def serie_mensual(anio, cliente_id):
    """Ingresos, costos, utilidad y por cobrar de las órdenes finalizadas de cada mes del año."""
    qs = OrdenTrabajo.objects.filter(estado=Estado.FINALIZADA, fecha_programada__year=anio)
    if cliente_id:
        qs = qs.filter(cliente_id=cliente_id)
    ing, cos, cob, n = ([0] * 12 for _ in range(4))
    for f in qs.annotate(m=TruncMonth('fecha_programada')).values('m').annotate(
            i=Sum('monto_neto'), c=Sum(COSTO), n=Count('id')):
        k = f['m'].month - 1
        ing[k], cos[k], n[k] = _n(f['i']), _n(f['c']), f['n']
    for f in (qs.filter(estado_pago=OrdenTrabajo.Pago.PENDIENTE).annotate(m=TruncMonth('fecha_programada'))
              .values('m').annotate(i=Sum('monto_neto'))):
        cob[f['m'].month - 1] = _n(f['i'])
    return {'labels': MESES, 'ingresos': ing, 'costos': cos, 'utilidad': [a - b for a, b in zip(ing, cos)],
            'por_cobrar': cob, 'ordenes': n}


def serie_dias(hoy, cliente_id, dias=30):
    """Lo mismo, día por día, de los últimos 30 días."""
    desde = hoy - timedelta(days=dias - 1)
    qs = OrdenTrabajo.objects.filter(estado=Estado.FINALIZADA, fecha_programada__range=(desde, hoy))
    if cliente_id:
        qs = qs.filter(cliente_id=cliente_id)
    fechas = [desde + timedelta(days=i) for i in range(dias)]
    pos = {f: i for i, f in enumerate(fechas)}
    ing, cos, cob, n = ([0] * dias for _ in range(4))
    for f in qs.values('fecha_programada').annotate(i=Sum('monto_neto'), c=Sum(COSTO), n=Count('id')):
        k = pos[f['fecha_programada']]
        ing[k], cos[k], n[k] = _n(f['i']), _n(f['c']), f['n']
    for f in (qs.filter(estado_pago=OrdenTrabajo.Pago.PENDIENTE).values('fecha_programada')
              .annotate(i=Sum('monto_neto'))):
        cob[pos[f['fecha_programada']]] = _n(f['i'])
    return {'labels': [f'{f.day}/{f.month}' for f in fechas], 'ingresos': ing, 'costos': cos,
            'utilidad': [a - b for a, b in zip(ing, cos)], 'por_cobrar': cob, 'ordenes': n}


def _variacion(actual, previo):
    """% de cambio respecto al período anterior (None si no hay base de comparación)."""
    if not previo:
        return None
    return round((actual - previo) / abs(previo) * 100)


def _cuando(fecha, hoy):
    dif = (fecha - hoy).days
    if dif < 0:
        return f'Atrasada {-dif} d'
    return {0: 'Hoy', 1: 'Mañana'}.get(dif, f'{fecha.day}/{fecha.month}')


def _cotizaciones(anio, cliente_id):
    cots = Cotizacion.objects.filter(fecha__year=anio).prefetch_related('items')
    if cliente_id:
        cots = cots.filter(cliente_id=cliente_id)
    cots = list(cots)
    por_estado = {e: [c for c in cots if c.estado == e] for e in Cotizacion.Estado.values}
    monto = lambda lista: sum(_n(c.neto) for c in lista)  # noqa: E731
    con_orden = [c for c in cots if c.orden_id]
    resueltas = len(por_estado['aceptada']) + len(por_estado['rechazada'])
    lista = reverse('cotizaciones')
    return {
        'enviadas': len(cots), 'pendientes': len(por_estado['pendiente']),
        'pendientes_monto': monto(por_estado['pendiente']),
        'aceptadas': len(por_estado['aceptada']), 'aceptadas_monto': monto(por_estado['aceptada']),
        'rechazadas': len(por_estado['rechazada']),
        'cierre': round(len(por_estado['aceptada']) / resueltas * 100) if resueltas else None,
        'embudo': [
            {'label': 'Enviadas', 'n': len(cots), 'monto': monto(cots), 'url': lista, 'color': '#0881c5'},
            {'label': 'Aceptadas', 'n': len(por_estado['aceptada']), 'monto': monto(por_estado['aceptada']),
             'url': f'{lista}?estado=aceptada', 'color': '#12905a'},
            {'label': 'Con orden de trabajo', 'n': len(con_orden), 'monto': monto(con_orden),
             'url': reverse('ordenes'), 'color': '#f6410f'},
        ],
    }


def _agenda(hoy, cliente_id):
    qs = (OrdenTrabajo.objects.filter(estado__in=[Estado.PENDIENTE, Estado.EN_PROCESO],
                                      fecha_programada__lte=hoy + timedelta(days=7))
          .select_related('cliente', 'ubicacion', 'tecnico').prefetch_related('activos')
          .order_by('fecha_programada', 'numero'))
    if cliente_id:
        qs = qs.filter(cliente_id=cliente_id)
    return [{
        'numero': o.numero, 'titulo': o.titulo, 'cliente': o.cliente.nombre, 'ubicacion': o.ubicacion.nombre,
        'tecnico': o.tecnico.nombre if o.tecnico else None, 'cuando': _cuando(o.fecha_programada, hoy),
        'atrasada': o.fecha_programada < hoy, 'hoy': o.fecha_programada == hoy, 'estado': o.get_estado_display(),
        'en_proceso': o.estado == Estado.EN_PROCESO, 'equipos': len(o.activos.all()), 'alta': o.prioridad == 'alta',
        'url': o.get_absolute_url(),
    } for o in qs[:8]]


def _actividad(cliente_id):
    """Los últimos movimientos del negocio: seguimientos, informes, órdenes y cotizaciones."""
    ahora = timezone.now()
    eventos = []

    def agregar(ts, icono, color, texto, url):
        if ts:
            eventos.append({'ts': ts, 'icono': icono, 'color': color, 'texto': texto, 'url': url})

    segs = Seguimiento.objects.select_related('cotizacion', 'cotizacion__cliente', 'usuario')
    cots = Cotizacion.objects.select_related('cliente')
    ords = OrdenTrabajo.objects.select_related('cliente', 'tecnico')
    infs = Informe.objects.select_related('orden', 'orden__cliente', 'tecnico')
    if cliente_id:
        segs, cots = segs.filter(cotizacion__cliente_id=cliente_id), cots.filter(cliente_id=cliente_id)
        ords, infs = ords.filter(cliente_id=cliente_id), infs.filter(orden__cliente_id=cliente_id)

    for s in segs.order_by('-creado_en')[:5]:
        agregar(s.creado_en, 'bi-telephone-fill', 'azul',
                f'{s.usuario.nombre if s.usuario else "Alguien"} registró {s.get_medio_display().lower()} · '
                f'{s.cotizacion.numero} ({s.cotizacion.cliente})', s.cotizacion.get_absolute_url())
    for c in cots.order_by('-creada_en')[:5]:
        agregar(c.creada_en, 'bi-receipt', 'naranja', f'Cotización {c.numero} creada · {c.cliente}',
                c.get_absolute_url())
    for o in ords.order_by('-creada_en')[:5]:
        agregar(o.creada_en, 'bi-clipboard2-plus', 'azul', f'Orden {o.numero} creada · {o.cliente}',
                o.get_absolute_url())
    for i in infs.filter(termino__isnull=False).order_by('-termino')[:5]:
        agregar(i.termino, 'bi-send-check', 'verde',
                f'{i.tecnico.nombre if i.tecnico else "El técnico"} envió el informe {i.numero} · '
                f'{i.orden.cliente}', reverse('informe_detalle', args=[i.pk]))
    for i in infs.filter(emitido_en__isnull=False).order_by('-emitido_en')[:3]:
        agregar(i.emitido_en, 'bi-patch-check-fill', 'verde', f'Informe {i.numero} emitido al cliente',
                reverse('informe_detalle', args=[i.pk]))
    eventos.sort(key=lambda e: e['ts'], reverse=True)
    return [{'icono': e['icono'], 'color': e['color'], 'texto': e['texto'], 'url': e['url'],
             'hace': f'hace {timesince(e["ts"], ahora).split(",")[0]}'} for e in eventos[:8]]


def _equipos(cliente_id):
    qs = Activo.objects.filter(estado=Activo.Estado.ACTIVO)
    if cliente_id:
        qs = qs.filter(ubicacion__cliente_id=cliente_id)
    cond = {c['condicion']: c['n'] for c in qs.values('condicion').annotate(n=Count('id'))}
    fuera = sum(1 for r in qs.values_list('refrigerante', flat=True)
                if r.upper().replace('-', '').replace(' ', '') == 'R22')
    return {'total': sum(cond.values()), 'fuera_norma': fuera,
            'condiciones': [{'label': label, 'n': cond.get(v, 0)} for v, label in Activo.Condicion.choices]}


def payload(anio, cliente_id, hoy=None):
    hoy = hoy or timezone.localdate()
    cliente_id = cliente_id if str(cliente_id).isdigit() else ''
    meses, previo = serie_mensual(anio, cliente_id), serie_mensual(anio - 1, cliente_id)
    hasta = hoy.month if anio == hoy.year else 12  # año en curso: se compara contra los mismos meses del anterior
    comparacion = {}
    for clave in ('ingresos', 'costos', 'utilidad'):
        comparacion[clave] = _variacion(sum(meses[clave][:hasta]), sum(previo[clave][:hasta]))

    ordenes = OrdenTrabajo.objects.filter(fecha_programada__year=anio)
    por_cobrar = OrdenTrabajo.objects.filter(estado=Estado.FINALIZADA, estado_pago=OrdenTrabajo.Pago.PENDIENTE)
    if cliente_id:
        ordenes, por_cobrar = ordenes.filter(cliente_id=cliente_id), por_cobrar.filter(cliente_id=cliente_id)
    conteo = {e['estado']: e['n'] for e in ordenes.values('estado').annotate(n=Count('id'))}
    activas = sum(conteo.get(e, 0) for e in (Estado.PENDIENTE, Estado.EN_PROCESO, Estado.EN_REVISION,
                                             Estado.FINALIZADA))
    ing, cos = sum(meses['ingresos']), sum(meses['costos'])
    tot_cobrar = por_cobrar.aggregate(t=Sum('monto_neto'), n=Count('id'))
    ordenes_url = reverse('ordenes')

    finalizadas = ordenes.filter(estado=Estado.FINALIZADA)
    por_cliente = list(finalizadas.values('cliente_id', 'cliente__nombre').annotate(ing=Sum('monto_neto'))
                       .order_by('-ing')[:6])
    por_tecnico = []
    for t in (finalizadas.exclude(tecnico=None)
              .values('tecnico__first_name', 'tecnico__last_name', 'tecnico__username')
              .annotate(n=Count('id'), ing=Sum('monto_neto'), cos=Sum(COSTO)).order_by('-ing')[:6]):
        nombre = f"{t['tecnico__first_name']} {t['tecnico__last_name']}".strip() or t['tecnico__username']
        por_tecnico.append({'nombre': nombre, 'n': t['n'], 'ingresos': _n(t['ing']),
                            'utilidad': _n(t['ing']) - _n(t['cos'])})
    por_tipo = {t['tipo']: t['n'] for t in ordenes.exclude(estado=Estado.CANCELADA).values('tipo')
                .annotate(n=Count('id'))}

    return {
        'anio': anio, 'cliente': cliente_id, 'hoy': hoy.isoformat(),
        'kpis': {
            'ingresos': ing, 'costos': cos, 'utilidad': ing - cos,
            'margen': round((ing - cos) / ing * 100, 1) if ing else 0,
            'por_cobrar': _n(tot_cobrar['t']), 'por_cobrar_n': tot_cobrar['n'],
            'cumplimiento': round(conteo.get(Estado.FINALIZADA, 0) / activas * 100) if activas else 0,
            'comparacion': comparacion, 'comparado_con': f'{MESES[hasta - 1]} {anio - 1}' if hasta < 12
            else str(anio - 1),
        },
        'meses': meses, 'meses_previo': previo, 'dias': serie_dias(hoy, cliente_id),
        'estados': [{'valor': v, 'label': label, 'n': conteo.get(v, 0), 'url': f'{ordenes_url}?estado={v}'}
                    for v, label in Estado.choices],
        'tipos': [{'label': label, 'n': por_tipo.get(v, 0)} for v, label in OrdenTrabajo.Tipo.choices],
        'clientes': [{'id': c['cliente_id'], 'nombre': c['cliente__nombre'], 'ingresos': _n(c['ing'])}
                     for c in por_cliente],
        'tecnicos': por_tecnico,
        'cotizaciones': _cotizaciones(anio, cliente_id),
        'agenda': _agenda(hoy, cliente_id),
        'actividad': _actividad(cliente_id),
        'equipos': _equipos(cliente_id),
    }
