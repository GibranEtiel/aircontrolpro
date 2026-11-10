from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageOps

IVA = Decimal('0.19')

# "Actividades realizadas" del informe técnico de Air Control Pro.
TAREAS_MANTENCION = [
    ('filtros', 'Limpieza de filtros'),
    ('serpentines', 'Limpieza de serpentines'),
    ('presiones', 'Verificación de presiones'),
    ('tarjetas', 'Revisión de tarjetas electrónicas'),
    ('sensores', 'Revisión de sensores'),
    ('estado_general', 'Estado general del equipo'),
]
TAREAS_CLAVES = [clave for clave, _ in TAREAS_MANTENCION]

# Fotos que el técnico saca de cada equipo, en el orden del trabajo: (clave, nombre, obligatoria).
# Las obligatorias que falten se avisan al técnico, que puede agregarlas después; las opcionales no.
PASOS_FOTO = [
    ('liquido', 'Aplicación del líquido', True),
    ('hidrolavadora', 'Lavado con hidrolavadora', True),
    ('soplador', 'Secado con soplador', True),
    ('desarmado', 'Equipo desarmado', True),
    ('condensadora', 'Condensadora', False),
    ('terminado', 'Equipo armado y funcionando', True),
]
PASOS_CLAVES = [clave for clave, _, _ in PASOS_FOTO]
PASO_NOMBRE = {clave: nombre for clave, nombre, _ in PASOS_FOTO}


def _siguiente_numero(modelo, prefijo, anio):
    base = f'{prefijo}-{anio}-'
    ultimo = modelo.objects.filter(numero__startswith=base).order_by('-numero').first()
    n = int(ultimo.numero.rsplit('-', 1)[1]) + 1 if ultimo else 1
    return f'{base}{n:04d}'


def siguiente_numero_ot(anio):
    """Próxima OT del año con el formato de Air Control Pro: 456/26 (número/año).

    Continúa desde la OT más alta del año, incluidas las que se escribieron a mano,
    así que basta con ingresar la primera (por ejemplo 456/26) para seguir con 457/26.
    """
    sufijo = f'/{anio % 100:02d}'
    mayor = 0
    for numero in OrdenTrabajo.objects.filter(numero__endswith=sufijo).values_list('numero', flat=True):
        if numero[:-3].isdigit():
            mayor = max(mayor, int(numero[:-3]))
    return f'{mayor + 1}{sufijo}'


class OrdenTrabajo(models.Model):
    class Tipo(models.TextChoices):
        PREVENTIVO = 'preventivo', 'Mantención preventiva'
        CORRECTIVO = 'correctivo', 'Mantención correctiva'
        EMERGENCIA = 'emergencia', 'Visita de emergencia'
        INSTALACION = 'instalacion', 'Instalación'

    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        EN_PROCESO = 'en_proceso', 'En proceso'
        EN_REVISION = 'en_revision', 'En revisión'
        FINALIZADA = 'finalizada', 'Finalizada'
        CANCELADA = 'cancelada', 'Cancelada'

    class Prioridad(models.TextChoices):
        BAJA = 'baja', 'Baja'
        MEDIA = 'media', 'Media'
        ALTA = 'alta', 'Alta'

    class Pago(models.TextChoices):
        PENDIENTE = 'pendiente', 'Por cobrar'
        PAGADO = 'pagado', 'Pagado'

    numero = models.CharField(
        'N° OT', max_length=20, unique=True, blank=True,
        help_text='Déjalo vacío para numerar automáticamente (456/26, 457/26…) o escribe uno.')
    atencion = models.CharField(
        'A.t (atención de)', max_length=120, blank=True, default='',
        help_text='Persona del cliente a quien va dirigido el informe.')
    titulo = models.CharField('Título', max_length=200)
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.PREVENTIVO)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    prioridad = models.CharField(max_length=6, choices=Prioridad.choices, default=Prioridad.MEDIA)
    cliente = models.ForeignKey('catalogo.Cliente', on_delete=models.PROTECT, related_name='ordenes')
    ubicacion = models.ForeignKey('catalogo.Ubicacion', on_delete=models.PROTECT, related_name='ordenes')
    activos = models.ManyToManyField('catalogo.Activo', blank=True, related_name='ordenes')
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='ordenes_asignadas', limit_choices_to={'rol': 'tecnico'},
    )
    fecha_programada = models.DateField('Fecha programada', default=timezone.localdate)
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_termino = models.DateTimeField(null=True, blank=True)
    descripcion = models.TextField('Descripción', blank=True)

    # Finanzas (valores netos en CLP)
    monto_neto = models.DecimalField('Monto cobrado (neto)', max_digits=12, decimal_places=0, default=0)
    costo_materiales = models.DecimalField('Costo materiales', max_digits=12, decimal_places=0, default=0)
    costo_mano_obra = models.DecimalField('Costo mano de obra', max_digits=12, decimal_places=0, default=0)
    estado_pago = models.CharField(max_length=10, choices=Pago.choices, default=Pago.PENDIENTE)
    fecha_pago = models.DateField(null=True, blank=True)

    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_programada', '-numero']
        verbose_name = 'orden de trabajo'
        verbose_name_plural = 'órdenes de trabajo'

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = siguiente_numero_ot(self.fecha_programada.year)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('orden_detalle', args=[self.pk])

    @property
    def costo_total(self):
        return (self.costo_materiales or 0) + (self.costo_mano_obra or 0)

    @property
    def utilidad(self):
        return (self.monto_neto or 0) - self.costo_total

    @property
    def margen(self):
        return round(self.utilidad / self.monto_neto * 100, 1) if self.monto_neto else 0

    @property
    def iva(self):
        return (self.monto_neto * IVA).quantize(Decimal('1'))

    @property
    def total_con_iva(self):
        return self.monto_neto + self.iva

    def __str__(self):
        return f'{self.numero} · {self.titulo}'


class Informe(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'borrador', 'Borrador'
        ENVIADO = 'enviado', 'En revisión'
        EMITIDO = 'emitido', 'Emitido'

    numero = models.CharField('N° informe', max_length=20, unique=True, blank=True)
    orden = models.OneToOneField(OrdenTrabajo, on_delete=models.CASCADE, related_name='informe')
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='informes',
    )
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.BORRADOR)

    inicio = models.DateTimeField('Inicio', default=timezone.now)
    termino = models.DateTimeField('Término', null=True, blank=True)
    latitud_inicio = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud_inicio = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    precision_inicio = models.PositiveIntegerField('Precisión GPS (m)', null=True, blank=True)
    latitud_fin = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud_fin = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    diagnostico = models.TextField('Diagnóstico / hallazgos', blank=True)
    trabajos_realizados = models.TextField('Trabajos realizados', blank=True)
    recomendaciones = models.TextField('Recomendaciones', blank=True)
    recibido_por = models.CharField('Recibido por (cliente)', max_length=120, blank=True)
    firma = models.ImageField('Firma del cliente', upload_to='firmas/%Y/%m/', null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    emitido_en = models.DateTimeField(null=True, blank=True)
    emitido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    class Meta:
        ordering = ['-inicio']

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = _siguiente_numero(Informe, 'INF', timezone.localdate().year)
        super().save(*args, **kwargs)

    @property
    def fecha_referencia(self):
        return self.emitido_en or self.termino or self.inicio

    @property
    def tiene_ubicacion(self):
        return self.latitud_inicio is not None

    def __str__(self):
        return f'{self.numero} · {self.orden.numero}'


class InformeEquipo(models.Model):
    class Estado(models.TextChoices):
        OPERATIVO = 'operativo', 'Operativo'
        OBSERVACIONES = 'observaciones', 'Operativo con observaciones'
        FUERA_SERVICIO = 'fuera_servicio', 'Fuera de servicio'

    class Tipo(models.TextChoices):
        PREVENTIVO = 'preventivo', 'Preventivo'
        CORRECTIVO = 'correctivo', 'Correctivo'
        AMBOS = 'ambos', 'Preventivo / Correctivo'

    class Modo(models.TextChoices):
        FRIO = 'frio', 'Frío'
        CALOR = 'calor', 'Calor'

    informe = models.ForeignKey(Informe, on_delete=models.CASCADE, related_name='equipos')
    activo = models.ForeignKey('catalogo.Activo', on_delete=models.PROTECT, related_name='+')
    estado_equipo = models.CharField(max_length=15, choices=Estado.choices, default=Estado.OPERATIVO)
    tipo_mantenimiento = models.CharField('Tipo de mantenimiento', max_length=10, choices=Tipo.choices,
                                          default=Tipo.PREVENTIVO)
    tareas = models.JSONField(default=list, blank=True)
    presion = models.DecimalField('Presión de funcionamiento (PSI)', max_digits=6, decimal_places=1,
                                  null=True, blank=True)
    consumo_total = models.DecimalField('Consumo eléctrico total (A)', max_digits=6, decimal_places=1,
                                        null=True, blank=True)
    consumo_ventilador = models.DecimalField('Consumo ventilador (A)', max_digits=6, decimal_places=1,
                                             null=True, blank=True)
    temp_inyeccion = models.DecimalField('Temperatura de inyección (°C)', max_digits=5, decimal_places=1,
                                         null=True, blank=True)
    modo = models.CharField('Modo de la medición', max_length=5, choices=Modo.choices, default=Modo.FRIO)
    observaciones = models.TextField(blank=True)
    fuera_de_norma = models.BooleanField(
        'Equipo fuera de norma', default=False,
        help_text='Lo decide el técnico en cada informe. Parte marcado si el refrigerante del equipo es R-22.')
    finalizado = models.BooleanField('Equipo terminado', default=False)
    completado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['activo__numero_equipo', 'activo__codigo']
        unique_together = [('informe', 'activo')]

    @property
    def pasos(self):
        """Las fotos del procedimiento, en orden: [{clave, nombre, obligatoria, numero, foto|None}]."""
        por_paso = {f.paso: f for f in self.fotos.all() if f.paso}
        return [{'clave': c, 'nombre': n, 'obligatoria': o, 'numero': i, 'foto': por_paso.get(c)}
                for i, (c, n, o) in enumerate(PASOS_FOTO, start=1)]

    @property
    def pasos_pendientes(self):
        """Fotos obligatorias que aún no se han subido."""
        return [p for p in self.pasos if p['obligatoria'] and p['foto'] is None]

    @property
    def pendientes_texto(self):
        return ', '.join(p['nombre'] for p in self.pasos_pendientes)

    @property
    def fotos_extra(self):
        """Fotos adicionales que no corresponden a un paso."""
        return [f for f in self.fotos.all() if not f.paso]

    @property
    def fotos_ordenadas(self):
        """Primero las fotos de cada paso, en el orden del trabajo; después las adicionales."""
        orden = {c: i for i, c in enumerate(PASOS_CLAVES)}
        return sorted(self.fotos.all(), key=lambda f: (orden.get(f.paso, len(orden)), f.tomada_en))

    @property
    def tareas_labels(self):
        nombres = dict(TAREAS_MANTENCION)
        return [nombres.get(t, t) for t in self.tareas]

    @property
    def fecha(self):
        return self.completado_en or self.informe.inicio

    @property
    def observaciones_informe(self):
        """(fuera_de_norma, texto): la alerta de R-22 va aparte para mostrarla en rojo.

        Si el técnico no escribe nada (y el equipo no es R-22) no hay observaciones y la línea no sale en el informe.
        """
        extra = self.observaciones.strip()
        if self.fuera_de_norma:
            motivo = ' (REFRIGERANTE R-22)' if self.activo.fuera_de_norma else ''
            return f'EQUIPO FUERA DE NORMA{motivo}', extra
        return '', extra

    @property
    def mediciones(self):
        """Solo las mediciones que el técnico anotó: [(nombre, 'valor unidad')]. Lo vacío no sale en el informe."""
        def fmt(valor, unidad):
            return f'{format(valor.normalize(), "f")}{unidad}'

        filas = []
        if self.presion is not None:
            filas.append(('Presión de funcionamiento', fmt(self.presion, ' PSI')))
        if self.consumo_total is not None:
            filas.append(('Consumo eléctrico total', fmt(self.consumo_total, ' A')))
        if self.consumo_ventilador is not None:
            filas.append(('Consumo ventilador', fmt(self.consumo_ventilador, ' A')))
        if self.temp_inyeccion is not None:  # el modo (frío/calor) solo importa si hay temperatura
            filas.append((f'Temperatura de inyección ({self.get_modo_display().upper()})',
                          fmt(self.temp_inyeccion, '°C')))
        return filas

    def __str__(self):
        return f'{self.informe.numero} · {self.activo.codigo}'


class FotoInforme(models.Model):
    class Etapa(models.TextChoices):
        ANTES = 'antes', 'Antes'
        DURANTE = 'durante', 'Durante'
        DESPUES = 'despues', 'Después'
        OTRO = 'otro', 'Otra'

    informe = models.ForeignKey(Informe, on_delete=models.CASCADE, related_name='fotos')
    equipo = models.ForeignKey(
        InformeEquipo, null=True, blank=True, on_delete=models.CASCADE, related_name='fotos',
    )
    imagen = models.ImageField(upload_to='informes/%Y/%m/')
    paso = models.CharField('Paso del procedimiento', max_length=15, blank=True, default='')
    etapa = models.CharField(max_length=8, choices=Etapa.choices, default=Etapa.OTRO)
    descripcion = models.CharField(max_length=200, blank=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    tomada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['tomada_en']

    def save(self, *args, **kwargs):
        # Las fotos de celular pesan varios MB: se corrigen y reducen al guardarlas.
        if self._state.adding and self.imagen and not getattr(self.imagen, '_committed', True):
            try:
                img = ImageOps.exif_transpose(Image.open(self.imagen))
                img.thumbnail((1600, 1600))
                buffer = BytesIO()
                img.convert('RGB').save(buffer, 'JPEG', quality=82, optimize=True)
                nombre = self.imagen.name.rsplit('.', 1)[0] + '.jpg'
                self.imagen.save(nombre, ContentFile(buffer.getvalue()), save=False)
            except OSError:
                pass
        super().save(*args, **kwargs)

    @property
    def titulo(self):
        """Texto al pie de la foto en el informe: «1 · Aplicación del líquido» o «Foto adicional»."""
        if self.paso in PASO_NOMBRE:
            return f'{PASOS_CLAVES.index(self.paso) + 1} · {PASO_NOMBRE[self.paso]}'
        return self.descripcion or 'Foto adicional'

    def __str__(self):
        return f'Foto {self.pk} · {self.informe.numero}'
