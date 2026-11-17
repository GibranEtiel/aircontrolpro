"""Eliminar empresas, sucursales y equipos sin perder el historial.

Lo que tiene órdenes de trabajo, informes o cotizaciones NO se borra (son el respaldo del trabajo hecho y de los cobros):
se ofrece desactivarlo, y deja de aparecer en las listas para elegir. Lo que no tiene historial se elimina de verdad.
"""

from django.db import transaction

from accounts.models import User
from mantenciones.models import Informe, InformeEquipo, OrdenTrabajo

from .models import Activo, Cliente, Ubicacion


def _n(cantidad, uno, varios):
    return f'{cantidad} {uno if cantidad == 1 else varios}'


def nombre_objeto(objeto):
    if isinstance(objeto, Activo):
        return objeto.etiqueta
    if isinstance(objeto, User):
        return f'{objeto.nombre} ({objeto.username})' if objeto.get_full_name() else objeto.username
    return objeto.nombre


def etiqueta(objeto):
    return {Cliente: 'la empresa', Ubicacion: 'la sucursal', Activo: 'el equipo', User: 'el usuario'}[type(objeto)]


def analizar(objeto):
    """(bloqueos, arrastra): lo que impide eliminarlo y lo que se eliminaría junto con él."""
    bloqueos, arrastra = [], []
    if isinstance(objeto, Cliente):
        for cant, uno, varios in ((objeto.ordenes.count(), 'orden de trabajo', 'órdenes de trabajo'),
                                  (objeto.cotizaciones.count(), 'cotización', 'cotizaciones')):
            if cant:
                bloqueos.append(_n(cant, uno, varios))
        usuarios = objeto.usuarios.count()
        if usuarios:
            bloqueos.append(_n(usuarios, 'usuario cliente asociado', 'usuarios cliente asociados')
                            + ' (cámbialos de empresa en «Usuarios y roles»)')
        sucursales = objeto.ubicaciones.count()
        equipos = Activo.objects.filter(ubicacion__cliente=objeto).count()
    elif isinstance(objeto, Ubicacion):
        ordenes = objeto.ordenes.count()
        if ordenes:
            bloqueos.append(_n(ordenes, 'orden de trabajo en esta sucursal', 'órdenes de trabajo en esta sucursal'))
        con_equipos = OrdenTrabajo.objects.filter(activos__ubicacion=objeto).exclude(ubicacion=objeto).distinct().count()
        if con_equipos:
            bloqueos.append(_n(con_equipos, 'orden que incluye sus equipos', 'órdenes que incluyen sus equipos'))
        informes = InformeEquipo.objects.filter(activo__ubicacion=objeto).count()
        if informes:
            bloqueos.append(_n(informes, 'informe de sus equipos', 'informes de sus equipos'))
        sucursales, equipos = 0, objeto.activos.count()
    elif isinstance(objeto, User):
        # Un técnico firma los informes que hizo y un administrador los que emitió: sin él quedarían sin responsable.
        asignadas = objeto.ordenes_asignadas.count()
        if asignadas:
            bloqueos.append(_n(asignadas, 'orden de trabajo asignada', 'órdenes de trabajo asignadas'))
        informes = objeto.informes.count()
        if informes:
            bloqueos.append(_n(informes, 'informe técnico como responsable', 'informes técnicos como responsable'))
        emitidos = Informe.objects.filter(emitido_por=objeto).count()
        if emitidos:
            bloqueos.append(_n(emitidos, 'informe emitido por este usuario', 'informes emitidos por este usuario'))
        sucursales, equipos = 0, 0
    else:  # equipo
        ordenes = objeto.ordenes.count()
        if ordenes:
            bloqueos.append(_n(ordenes, 'orden de trabajo', 'órdenes de trabajo'))
        informes = InformeEquipo.objects.filter(activo=objeto).count()
        if informes:
            bloqueos.append(_n(informes, 'informe técnico', 'informes técnicos'))
        sucursales, equipos = 0, 0
    if sucursales:
        arrastra.append(_n(sucursales, 'sucursal', 'sucursales'))
    if equipos:
        arrastra.append(_n(equipos, 'equipo', 'equipos'))
    return bloqueos, arrastra


def esta_activo(objeto):
    if isinstance(objeto, Cliente):
        return objeto.activo
    if isinstance(objeto, Ubicacion):
        return objeto.activa
    if isinstance(objeto, User):
        return objeto.is_active
    return objeto.estado == Activo.Estado.ACTIVO


def desactivar(objeto):
    if isinstance(objeto, Cliente):
        objeto.activo = False
        objeto.save(update_fields=['activo'])
    elif isinstance(objeto, Ubicacion):
        objeto.activa = False
        objeto.save(update_fields=['activa'])
    elif isinstance(objeto, User):
        objeto.is_active = False
        objeto.save(update_fields=['is_active'])
    else:
        objeto.estado = Activo.Estado.BAJA
        objeto.save(update_fields=['estado'])


def eliminar(objeto):
    with transaction.atomic():
        if isinstance(objeto, Cliente):
            Activo.objects.filter(ubicacion__cliente=objeto).delete()
            objeto.ubicaciones.all().delete()
        elif isinstance(objeto, Ubicacion):
            objeto.activos.all().delete()
        objeto.delete()
