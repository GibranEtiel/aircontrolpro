"""Carga datos de ejemplo para probar los tres perfiles (admin, técnico y cliente)."""

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from PIL import Image, ImageDraw

from accounts.models import User
from catalogo.models import Activo, Cliente, Ubicacion
from mantenciones.models import TAREAS_CLAVES, FotoInforme, Informe, InformeEquipo, OrdenTrabajo

PASSWORD = 'aircontrol2026'  # solo para datos de demostración

EQUIPOS = [
    # n°, marca, modelo, ubicación exacta, refrigerante, BTU, presión, A total, A ventilador, T° inyección
    ('020', 'CLARK', 'CST-24HREI', 'Área común', 'R-22', 24000, '60', '8.5', '0.5', '8.7'),
    ('021', 'ANWO', 'MSE-24HR', 'Gerente general', 'R-22', 24000, '110', '3.4', '0.2', '7.3'),
    ('022', 'MIDEA', 'MSAG11B-12HRFN1-B', 'Contabilidad', 'R410A', 12000, '110', '3.2', '0.2', '6.6'),
]


def foto_demo(texto, color):
    """Imagen de relleno para ver cómo queda el informe con fotos."""
    img = Image.new('RGB', (900, 1200), color)
    d = ImageDraw.Draw(img)
    d.rectangle((60, 60, 840, 1140), outline='white', width=6)
    d.text((100, 560), f'FOTO DE DEMOSTRACION\n{texto}', fill='white')
    buffer = BytesIO()
    img.save(buffer, 'JPEG', quality=70)
    return ContentFile(buffer.getvalue())


class Command(BaseCommand):
    help = 'Crea usuarios y datos de demostración (admin, tecnico, cliente).'

    def handle(self, *args, **options):
        admin = self._usuario('admin', 'Benjamín', 'Quiroz', User.Rol.ADMIN, is_staff=True, is_superuser=True)
        tecnico = self._usuario('tecnico', 'Daniel', 'Bustos Gómez', User.Rol.TECNICO, telefono='+56947854105')

        cliente, _ = Cliente.objects.get_or_create(
            nombre='LUCAS DIESEL',
            defaults={'rut': '99.595.100-2', 'giro': 'Comercio', 'contacto': 'Nicolas Gonzales'})
        sucursal, _ = Ubicacion.objects.get_or_create(
            cliente=cliente, nombre='Oficinas Administrativas 2do piso',
            defaults={'codigo': '995951002', 'direccion': 'Av. Presidente Eduardo Frei Montalva 5325',
                      'ciudad': 'Conchalí', 'region': 'Metropolitana', 'latitud': Decimal('-33.384900'),
                      'longitud': Decimal('-70.675600')})
        self._usuario('cliente', 'Nicolas', 'Gonzales', User.Rol.CLIENTE, cliente=cliente)

        equipos = []
        for numero, marca, modelo, donde, refrigerante, btu, *_ in EQUIPOS:
            a, _ = Activo.objects.get_or_create(
                codigo=f'LUCAS-{numero}',
                defaults={'ubicacion': sucursal, 'nombre': f'Split {donde.lower()}', 'numero_equipo': numero,
                          'ubicacion_exacta': donde, 'marca': marca, 'modelo': modelo, 'capacidad_btu': btu,
                          'refrigerante': refrigerante, 'tipo': Activo.Tipo.SPLIT})
            equipos.append(a)

        if OrdenTrabajo.objects.exists():
            self.stdout.write('Ya hay órdenes; no se crean más datos de ejemplo.')
        else:
            self._ordenes(admin, tecnico, cliente, sucursal, equipos)

        self.stdout.write(self.style.SUCCESS(
            f'Listo. Usuarios admin / tecnico / cliente — contraseña de demo: {PASSWORD}'))

    def _ordenes(self, admin, tecnico, cliente, sucursal, equipos):
        hoy = timezone.localdate()
        colores = ['#3d6f8e', '#8e5a3d', '#4d8e5a']
        for atras, (tipo, neto, mat, mo) in enumerate([
            (OrdenTrabajo.Tipo.PREVENTIVO, 180000, 25000, 60000),
            (OrdenTrabajo.Tipo.CORRECTIVO, 240000, 90000, 70000),
            (OrdenTrabajo.Tipo.PREVENTIVO, 180000, 20000, 60000),
            (OrdenTrabajo.Tipo.EMERGENCIA, 150000, 30000, 50000),
        ]):
            fecha = hoy.replace(day=15) - timedelta(days=30 * atras)
            termino = timezone.now() - timedelta(days=30 * atras)
            orden = OrdenTrabajo.objects.create(
                numero='456/26' if atras == 0 else '',  # las siguientes continúan: 457/26, 458/26…
                titulo=f'{OrdenTrabajo.Tipo(tipo).label} A/A - {sucursal.nombre}', tipo=tipo,
                estado=OrdenTrabajo.Estado.FINALIZADA, cliente=cliente, ubicacion=sucursal, tecnico=tecnico,
                atencion='Nicolas Gonzales', fecha_programada=fecha, monto_neto=neto, costo_materiales=mat,
                costo_mano_obra=mo, estado_pago=OrdenTrabajo.Pago.PAGADO if atras else OrdenTrabajo.Pago.PENDIENTE,
                fecha_pago=fecha if atras else None, creada_por=admin, fecha_inicio=termino, fecha_termino=termino)
            orden.activos.set(equipos)
            inf = Informe.objects.create(
                orden=orden, tecnico=tecnico, estado=Informe.Estado.EMITIDO, inicio=termino, termino=termino,
                emitido_en=termino, emitido_por=admin, latitud_inicio=sucursal.latitud,
                longitud_inicio=sucursal.longitud, precision_inicio=12, recibido_por='Nicolas Gonzales')
            for activo, datos in zip(equipos, EQUIPOS):
                _, _, _, _, _, _, presion, total, ventilador, inyeccion = datos
                eq = InformeEquipo.objects.create(
                    informe=inf, activo=activo, tareas=TAREAS_CLAVES, presion=Decimal(presion),
                    tipo_mantenimiento=(InformeEquipo.Tipo.CORRECTIVO if tipo == OrdenTrabajo.Tipo.CORRECTIVO
                                        else InformeEquipo.Tipo.PREVENTIVO),
                    consumo_total=Decimal(total), consumo_ventilador=Decimal(ventilador),
                    temp_inyeccion=Decimal(inyeccion), finalizado=True, completado_en=termino,
                    observaciones='Problemas receptor de señal display, cambio por tarjeta universal.'
                    if activo.numero_equipo == '021' else '')
                for n in range(3):
                    foto = FotoInforme(informe=inf, equipo=eq, etapa=FotoInforme.Etapa.OTRO)
                    foto.imagen.save(f'demo-{inf.pk}-{activo.numero_equipo}-{n}.jpg',
                                     foto_demo(f'{activo.etiqueta} · {n + 1}', colores[n]), save=False)
                    foto.save()

        OrdenTrabajo.objects.create(
            titulo=f'Mantención preventiva A/A - {sucursal.nombre}', cliente=cliente, ubicacion=sucursal,
            tecnico=tecnico, atencion='Nicolas Gonzales', fecha_programada=hoy, monto_neto=180000,
            creada_por=admin).activos.set(equipos[:2])
        OrdenTrabajo.objects.create(
            titulo='Visita de revisión por falta de frío', tipo=OrdenTrabajo.Tipo.CORRECTIVO,
            cliente=cliente, ubicacion=sucursal, tecnico=tecnico, fecha_programada=hoy + timedelta(days=5),
            monto_neto=95000, creada_por=admin).activos.set(equipos[2:])

    def _usuario(self, username, nombre, apellido, rol, **extra):
        usuario, creado = User.objects.get_or_create(
            username=username, defaults={'first_name': nombre, 'last_name': apellido, 'rol': rol, **extra})
        if creado:
            usuario.set_password(PASSWORD)
            usuario.save()
        return usuario
