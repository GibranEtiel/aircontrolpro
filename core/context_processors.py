from django.conf import settings

# Versión de los CSS/JS propios (fecha del archivo más nuevo). Se agrega como ?v=... para que el navegador del
# celular descargue el archivo nuevo en vez de quedarse con uno viejo guardado. Se recalcula al reiniciar la app.
V_ESTATICA = str(int(max((p.stat().st_mtime for ext in ('css', 'js')
                          for p in (settings.BASE_DIR / 'static' / ext).glob('*.' + ext)), default=0)))


def alertas(request):
    """Datos globales de las plantillas: si se ofrece recuperar la clave y, para el administrador, el aviso de
    cotizaciones por llamar del menú."""
    datos = {
        'v_estatica': V_ESTATICA,
        'recuperar_clave': settings.RECUPERAR_CLAVE,
        # En desarrollo sin servidor de correo, los correos se imprimen en la terminal en vez de enviarse.
        'correo_en_consola': settings.DEBUG and settings.EMAIL_BACKEND.endswith('console.EmailBackend'),
    }
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated and user.es_admin:
        from cotizaciones.models import Cotizacion

        datos['cotizaciones_por_llamar'] = Cotizacion.objects.por_llamar().count()
    return datos
