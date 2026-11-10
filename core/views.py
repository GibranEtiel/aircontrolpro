from django.contrib.auth.views import redirect_to_login
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncMonth
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.static import serve

from accounts.models import User
from catalogo.models import Activo, Cliente
from cotizaciones.models import Cotizacion
from mantenciones.models import FotoInforme, Informe, InformeEquipo, OrdenTrabajo

from . import dashboard
from .exports import (ANCHO_VERTICAL, Col, excel_response, exportar_tabla, formato_export, grafico_barras,
                      pdf_response, tabla, texto, titulo)
from .permissions import informes_visibles, ordenes_visibles, rol_required

MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
Estado = OrdenTrabajo.Estado


def _cero(valor):
    return valor or 0


def _anios_disponibles():
    anios = {d.year for d in OrdenTrabajo.objects.dates('fecha_programada', 'year')}
    anios.add(timezone.localdate().year)
    return sorted(anios, reverse=True)


@rol_required(User.Rol.ADMIN, User.Rol.TECNICO, User.Rol.CLIENTE)
def home(request):
    user = request.user
    if user.es_admin:
        return _dashboard_admin(request)
    if user.es_tecnico:
        return _dashboard_tecnico(request)
    return _dashboard_cliente(request)


def _dashboard_admin(request):
    hoy = timezone.localdate()
    try:
        anio = int(request.GET.get('anio', hoy.year))
    except ValueError:
        anio = hoy.year
    cliente_id = request.GET.get('cliente', '')

    ordenes = OrdenTrabajo.objects.filter(fecha_programada__year=anio)
    if cliente_id.isdigit():
        ordenes = ordenes.filter(cliente_id=cliente_id)
    finalizadas = ordenes.filter(estado=Estado.FINALIZADA)
    costo = F('costo_materiales') + F('costo_mano_obra')

    # Ingresos, costos y utilidad por mes
    ingresos_mes, costos_mes = [0] * 12, [0] * 12
    for fila in (finalizadas.annotate(m=TruncMonth('fecha_programada')).values('m')
                 .annotate(ing=Sum('monto_neto'), cos=Sum(costo))):
        ingresos_mes[fila['m'].month - 1] = int(_cero(fila['ing']))
        costos_mes[fila['m'].month - 1] = int(_cero(fila['cos']))
    utilidad_mes = [i - c for i, c in zip(ingresos_mes, costos_mes)]

    ingresos, costos = sum(ingresos_mes), sum(costos_mes)
    utilidad = ingresos - costos
    mes_actual = hoy.month - 1 if anio == hoy.year else None

    por_cobrar = OrdenTrabajo.objects.filter(estado=Estado.FINALIZADA, estado_pago=OrdenTrabajo.Pago.PENDIENTE)
    if cliente_id.isdigit():
        por_cobrar = por_cobrar.filter(cliente_id=cliente_id)
    por_cobrar_total = por_cobrar.aggregate(t=Sum('monto_neto'), n=Count('id'))

    conteo = {e['estado']: e['n'] for e in ordenes.values('estado').annotate(n=Count('id'))}
    estados = [(valor, etiqueta, conteo.get(valor, 0)) for valor, etiqueta in Estado.choices]
    activas = sum(conteo.get(e, 0) for e in (Estado.PENDIENTE, Estado.EN_PROCESO,
                                             Estado.EN_REVISION, Estado.FINALIZADA))
    cumplimiento = round(conteo.get(Estado.FINALIZADA, 0) / activas * 100) if activas else 0

    por_cliente = list(finalizadas.values('cliente__nombre').annotate(ing=Sum('monto_neto'))
                       .order_by('-ing')[:8])
    por_tipo = {t['tipo']: t['n'] for t in ordenes.exclude(estado=Estado.CANCELADA)
                .values('tipo').annotate(n=Count('id'))}
    por_tecnico = list(finalizadas.exclude(tecnico=None).values('tecnico__first_name', 'tecnico__last_name',
                                                               'tecnico__username')
                       .annotate(n=Count('id'), ing=Sum('monto_neto'), cos=Sum(costo)).order_by('-ing'))
    for t in por_tecnico:
        t['nombre'] = f"{t['tecnico__first_name']} {t['tecnico__last_name']}".strip() or t['tecnico__username']
        t['utilidad'] = int(_cero(t['ing'])) - int(_cero(t['cos']))

    charts = {
        'meses': MESES, 'ingresos': ingresos_mes, 'costos': costos_mes, 'utilidad': utilidad_mes,
        'estados': {'labels': [e[1] for e in estados], 'data': [e[2] for e in estados]},
        'clientes': {'labels': [c['cliente__nombre'] for c in por_cliente],
                     'data': [int(c['ing']) for c in por_cliente]},
        'tipos': {'labels': [label for _, label in OrdenTrabajo.Tipo.choices],
                  'data': [por_tipo.get(v, 0) for v, _ in OrdenTrabajo.Tipo.choices]},
    }
    contexto = {
        'anio': anio, 'anios': _anios_disponibles(), 'cliente_id': cliente_id,
        'clientes': Cliente.objects.filter(activo=True),
        'kpis': {
            'ingresos': ingresos, 'costos': costos, 'utilidad': utilidad,
            'margen': round(utilidad / ingresos * 100, 1) if ingresos else 0,
            'ingresos_mes': ingresos_mes[mes_actual] if mes_actual is not None else None,
            'utilidad_mes': utilidad_mes[mes_actual] if mes_actual is not None else None,
            'por_cobrar': int(_cero(por_cobrar_total['t'])), 'por_cobrar_n': por_cobrar_total['n'],
            'cumplimiento': cumplimiento,
        },
        'estados': estados, 'por_tecnico': por_tecnico, 'charts': charts,
        'en_revision': Informe.objects.filter(estado=Informe.Estado.ENVIADO)
                       .select_related('orden', 'orden__cliente', 'tecnico')[:8],
        'equipos_total': Activo.objects.filter(estado=Activo.Estado.ACTIVO).count(),
        'cot_por_llamar': list(Cotizacion.objects.por_llamar().select_related('cliente')
                               .prefetch_related('items').order_by('fecha')[:10]),
        'cot_pendientes': [(c.neto) for c in Cotizacion.objects.pendientes().prefetch_related('items')],
    }
    contexto['cot_pendientes_n'] = len(contexto['cot_pendientes'])
    contexto['cot_pendientes_monto'] = sum(contexto['cot_pendientes'], 0)
    formato = formato_export(request)
    if formato:
        return _exportar_dashboard(formato, contexto)
    hora = timezone.localtime().hour
    contexto.update(
        datos=dashboard.payload(anio, cliente_id, hoy), hoy=hoy,
        saludo='Buenos días' if hora < 12 else 'Buenas tardes' if hora < 20 else 'Buenas noches',
        n_por_iniciar=OrdenTrabajo.objects.filter(estado=Estado.PENDIENTE).count(),
        n_por_revisar=Informe.objects.filter(estado=Informe.Estado.ENVIADO).count(),
        n_por_llamar=Cotizacion.objects.por_llamar().count(),
    )
    return render(request, 'core/dashboard_admin.html', contexto)


@rol_required(User.Rol.ADMIN)
def dashboard_datos(request):
    """JSON del dashboard para un año y cliente: lo usa la página para actualizarse sin recargar."""
    from django.http import JsonResponse

    hoy = timezone.localdate()
    try:
        anio = int(request.GET.get('anio', hoy.year))
    except ValueError:
        anio = hoy.year
    return JsonResponse(dashboard.payload(anio, request.GET.get('cliente', ''), hoy))


def _exportar_dashboard(formato, ctx):
    anio, k, charts = ctx['anio'], ctx['kpis'], ctx['charts']
    cliente = next((c.nombre for c in ctx['clientes'] if str(c.pk) == ctx['cliente_id']), 'Todos los clientes')
    subtitulo = f'Año {anio} · {cliente}'
    resumen = [
        ('Ingresos netos', texto(k['ingresos'], 'clp')), ('Costos', texto(k['costos'], 'clp')),
        ('Utilidad', texto(k['utilidad'], 'clp')), ('Margen', texto(k['margen'], 'pct')),
        ('Por cobrar', f"{texto(k['por_cobrar'], 'clp')} ({k['por_cobrar_n']} OT)"),
        ('Cumplimiento de OT', f"{k['cumplimiento']}%"),
    ]
    mensual = [[mes, i, c, u] for mes, i, c, u in zip(MESES, charts['ingresos'], charts['costos'],
                                                    charts['utilidad'])]
    mensual_tot = ['Total', k['ingresos'], k['costos'], k['utilidad']]
    cols_mes = [Col('Mes'), Col('Ingresos', 'clp'), Col('Costos', 'clp'), Col('Utilidad', 'clp')]
    estados = [[label, n] for _, label, n in ctx['estados']]
    clientes = list(zip(charts['clientes']['labels'], charts['clientes']['data']))
    tecnicos = [[t['nombre'], t['n'], int(_cero(t['ing'])), t['utilidad']] for t in ctx['por_tecnico']]
    cols_tec = [Col('Técnico'), Col('OT finalizadas'), Col('Ingresos', 'clp'), Col('Utilidad', 'clp')]

    if formato == 'xlsx':
        return excel_response('dashboard', [
            {'nombre': 'Resumen', 'titulo': 'Resumen financiero', 'subtitulo': subtitulo,
             'columnas': [Col('Indicador'), Col('Valor')], 'filas': [list(r) for r in resumen]},
            {'nombre': 'Por mes', 'titulo': 'Ingresos, costos y utilidad por mes', 'subtitulo': subtitulo,
             'columnas': cols_mes, 'filas': mensual, 'totales': mensual_tot},
            {'nombre': 'Por cliente', 'titulo': 'Ingresos por cliente', 'subtitulo': subtitulo,
             'columnas': [Col('Cliente'), Col('Ingresos', 'clp')], 'filas': [list(c) for c in clientes]},
            {'nombre': 'Por técnico', 'titulo': 'Rendimiento por técnico', 'subtitulo': subtitulo,
             'columnas': cols_tec, 'filas': tecnicos},
            {'nombre': 'Órdenes por estado', 'titulo': 'Órdenes de trabajo por estado', 'subtitulo': subtitulo,
             'columnas': [Col('Estado'), Col('Cantidad')], 'filas': estados},
        ])

    ancho = ANCHO_VERTICAL
    story = [
        titulo('Resumen'),
        tabla([Col('Indicador'), Col('Valor')], [list(r) for r in resumen], ancho),
        titulo('Ingresos, costos y utilidad por mes'),
        grafico_barras(MESES, [('Ingresos', charts['ingresos'], '#0881c5'), ('Costos', charts['costos'], '#f6410f')],
                       ancho),
        tabla(cols_mes, mensual, ancho, mensual_tot),
        titulo('Ingresos por cliente'),
        tabla([Col('Cliente'), Col('Ingresos', 'clp')], [list(c) for c in clientes] or [['—', None]], ancho),
        titulo('Rendimiento por técnico'),
        tabla(cols_tec, tecnicos or [['—', None, None, None]], ancho),
        titulo('Órdenes de trabajo por estado'),
        tabla([Col('Estado'), Col('Cantidad')], estados, ancho),
    ]
    return pdf_response('dashboard', 'Dashboard financiero', subtitulo, story)


def _dashboard_tecnico(request):
    hoy = timezone.localdate()
    mias = ordenes_visibles(request.user).prefetch_related('activos')
    # Equipos ya terminados a los que les faltan fotos del procedimiento: se pueden completar mientras el informe
    # no esté emitido.
    terminados = (InformeEquipo.objects.filter(
        informe__tecnico=request.user, finalizado=True,
        informe__estado__in=[Informe.Estado.BORRADOR, Informe.Estado.ENVIADO])
        .select_related('activo', 'informe', 'informe__orden', 'informe__orden__cliente')
        .prefetch_related('fotos').order_by('-completado_en'))
    fotos_pendientes = [e for e in terminados if e.pasos_pendientes]
    return render(request, 'core/dashboard_tecnico.html', {
        'fotos_pendientes': fotos_pendientes,
        'en_proceso': mias.filter(estado=Estado.EN_PROCESO),
        'pendientes': mias.filter(estado=Estado.PENDIENTE).order_by('fecha_programada', 'numero'),
        'en_revision': mias.filter(estado=Estado.EN_REVISION).count(),
        'finalizadas_mes': mias.filter(estado=Estado.FINALIZADA, fecha_programada__year=hoy.year,
                                       fecha_programada__month=hoy.month).count(),
        'hoy': hoy,
    })


def _dashboard_cliente(request):
    user = request.user
    hoy = timezone.localdate()
    ordenes = ordenes_visibles(user)
    activos = Activo.objects.filter(ubicacion__cliente_id=user.cliente_id) if user.cliente_id \
        else Activo.objects.none()
    condiciones = {c['condicion']: c['n'] for c in activos.values('condicion').annotate(n=Count('id'))}
    return render(request, 'core/dashboard_cliente.html', {
        'cliente': user.cliente,
        'equipos': activos.count(),
        'condiciones': [(label, condiciones.get(v, 0)) for v, label in Activo.Condicion.choices],
        'proximas': ordenes.filter(estado__in=[Estado.PENDIENTE, Estado.EN_PROCESO],
                                   ).order_by('fecha_programada')[:6],
        'realizadas_anio': ordenes.filter(estado=Estado.FINALIZADA, fecha_programada__year=hoy.year).count(),
        'ultimos_informes': sorted(informes_visibles(user)[:20], key=lambda i: i.fecha_referencia,
                                   reverse=True)[:5],
    })


@rol_required(User.Rol.ADMIN)
def finanzas(request):
    hoy = timezone.localdate()
    try:
        anio = int(request.GET.get('anio', hoy.year))
    except ValueError:
        anio = hoy.year
    pago = request.GET.get('pago', '')
    ordenes = (OrdenTrabajo.objects.filter(estado=Estado.FINALIZADA, fecha_programada__year=anio)
               .select_related('cliente', 'tecnico').order_by('-fecha_programada'))
    if pago in OrdenTrabajo.Pago.values:
        ordenes = ordenes.filter(estado_pago=pago)
    ordenes = list(ordenes)
    formato = formato_export(request)
    if formato:
        columnas = [Col('N° OT'), Col('Título'), Col('Cliente'), Col('Técnico'), Col('Fecha', 'fecha'),
                    Col('Neto', 'clp'), Col('Materiales', 'clp'), Col('Mano de obra', 'clp'),
                    Col('Utilidad', 'clp'), Col('Margen', 'pct'), Col('IVA 19%', 'clp'),
                    Col('Total con IVA', 'clp'), Col('Pago'), Col('Fecha de pago', 'fecha')]
        filas = [[o.numero, o.titulo, o.cliente, o.tecnico, o.fecha_programada, o.monto_neto,
                  o.costo_materiales, o.costo_mano_obra, o.utilidad, o.margen, o.iva, o.total_con_iva,
                  o.get_estado_pago_display(), o.fecha_pago] for o in ordenes]
        suma = lambda campo: sum(getattr(o, campo) for o in ordenes)  # noqa: E731
        totales = ['Totales', '', '', '', None, suma('monto_neto'), suma('costo_materiales'),
                   suma('costo_mano_obra'), suma('utilidad'), None, suma('iva'), suma('total_con_iva'), '', None]
        return exportar_tabla(formato, 'finanzas', f'Finanzas {anio}', columnas, filas,
                              subtitulo=f'Órdenes finalizadas {anio} · montos netos en CLP', totales=totales)
    totales = {
        'neto': sum(o.monto_neto for o in ordenes),
        'costos': sum(o.costo_total for o in ordenes),
        'utilidad': sum(o.utilidad for o in ordenes),
        'iva': sum(o.iva for o in ordenes),
        'total': sum(o.total_con_iva for o in ordenes),
    }
    return render(request, 'core/finanzas.html', {
        'ordenes': ordenes, 'totales': totales, 'anio': anio, 'anios': _anios_disponibles(),
        'pago': pago, 'pagos': OrdenTrabajo.Pago.choices,
    })


def media_protegida(request, path):
    """Sirve fotos y firmas solo a quien puede ver el informe al que pertenecen.

    El administrador ve todo; el técnico, sus informes; el cliente, los informes emitidos de su empresa.
    """
    from django.conf import settings

    user = request.user
    if not user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if not user.es_admin:
        visibles = informes_visibles(user).values('pk')
        permitido = (FotoInforme.objects.filter(imagen=path, informe__in=visibles).exists()
                     or Informe.objects.filter(firma=path, pk__in=visibles).exists())
        if not permitido:
            raise Http404
    respuesta = serve(request, path, document_root=settings.MEDIA_ROOT)
    respuesta['Cache-Control'] = 'private, max-age=3600'
    return respuesta
