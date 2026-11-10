from django import template

from core.exports import resolver

register = template.Library()

BADGES = {
    # órdenes
    'pendiente': 'secondary', 'en_proceso': 'info', 'en_revision': 'warning',
    'finalizada': 'success', 'cancelada': 'danger',
    # informes
    'borrador': 'secondary', 'enviado': 'warning', 'emitido': 'success',
    # pagos
    'pagado': 'success',
    # equipos
    'activo': 'success', 'inactivo': 'secondary', 'baja': 'danger',
    'buena': 'success', 'regular': 'warning', 'mala': 'danger',
    'operativo': 'success', 'observaciones': 'warning', 'fuera_servicio': 'danger',
    # prioridad
    'media': 'info', 'alta': 'danger',
    # cotizaciones
    'aceptada': 'success', 'rechazada': 'danger',
}


@register.filter
def wa(telefono):
    """Número para wa.me: '9 3887 5867' o '+56 9 3887 5867' -> '56938875867' ('' si no parece un celular)."""
    digitos = ''.join(c for c in str(telefono or '') if c.isdigit())
    if digitos.startswith('56') and len(digitos) == 11:
        return digitos
    if len(digitos) == 9 and digitos[0] == '9':
        return '56' + digitos
    if len(digitos) == 8:
        return '569' + digitos
    return ''


@register.filter
def tel(telefono):
    """Valor para un enlace tel: (solo dígitos y +)."""
    return ''.join(c for c in str(telefono or '') if c.isdigit() or c == '+')


@register.filter
def badge(valor):
    """Color de Bootstrap para un estado (`{{ orden.estado|badge }}`)."""
    return BADGES.get(valor, 'secondary')


@register.filter
def clp(valor):
    """Formatea un monto como pesos chilenos: 1234567 -> $1.234.567."""
    try:
        return '$' + f'{int(round(float(valor))):,}'.replace(',', '.')
    except (TypeError, ValueError):
        return '—'


@register.filter
def attr(objeto, ruta):
    """Resuelve 'cliente.nombre' o 'get_tipo_display' sobre un objeto, para tablas genéricas."""
    valor = resolver(objeto, ruta)
    if valor is None:
        return '—'
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    return valor if valor != '' else '—'
