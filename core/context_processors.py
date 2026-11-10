def alertas(request):
    """Número de cotizaciones por llamar, para el aviso del menú (solo administradores)."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated or not user.es_admin:
        return {}
    from cotizaciones.models import Cotizacion

    return {'cotizaciones_por_llamar': Cotizacion.objects.por_llamar().count()}
