from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

IVA = Decimal('0.19')


def _hoy():
    return timezone.localdate()


class CotizacionQuerySet(models.QuerySet):
    def pendientes(self):
        return self.filter(estado=Cotizacion.Estado.PENDIENTE)

    def por_llamar(self, hoy=None):
        """Pendientes a las que hace más de `COTIZACION_DIAS_ALERTA` días no se les da respuesta ni gestión.

        Cuenta desde la fecha de envío o, si ya se llamó al cliente, desde ese último seguimiento:
        al registrar una llamada la cotización sale de la alerta hasta que vuelvan a pasar los días.
        """
        limite = (hoy or _hoy()) - timedelta(days=settings.COTIZACION_DIAS_ALERTA)
        return (self.pendientes().filter(fecha__lt=limite)
                .filter(Q(ultimo_contacto__isnull=True) | Q(ultimo_contacto__lt=limite)))


class Cotizacion(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        ACEPTADA = 'aceptada', 'Aceptada'
        RECHAZADA = 'rechazada', 'Rechazada'

    numero = models.CharField('N° cotización', max_length=20, unique=True, blank=True,
                              help_text='Déjalo vacío para numerar automáticamente (COT-2026-0001).')
    cliente = models.ForeignKey('catalogo.Cliente', on_delete=models.PROTECT, related_name='cotizaciones')
    ubicacion = models.ForeignKey('catalogo.Ubicacion', null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name='cotizaciones', verbose_name='Sucursal')
    titulo = models.CharField('Título', max_length=200)
    descripcion = models.TextField('Alcance / condiciones', blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    fecha = models.DateField('Fecha de envío', default=_hoy)
    validez_dias = models.PositiveSmallIntegerField('Validez (días)', default=15)

    # Si la persona que decide no es el contacto del cliente, se anota aquí a quién llamar.
    contacto_nombre = models.CharField('Contacto', max_length=120, blank=True,
                                       help_text='Vacío = contacto registrado en el cliente.')
    contacto_telefono = models.CharField('Teléfono', max_length=30, blank=True)
    contacto_email = models.EmailField('Correo', blank=True)

    ultimo_contacto = models.DateField('Último seguimiento', null=True, blank=True)
    fecha_respuesta = models.DateField(null=True, blank=True)
    orden = models.OneToOneField('mantenciones.OrdenTrabajo', null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='cotizacion')

    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    creada_en = models.DateTimeField(auto_now_add=True)

    objects = CotizacionQuerySet.as_manager()

    class Meta:
        ordering = ['-fecha', '-numero']
        verbose_name = 'cotización'
        verbose_name_plural = 'cotizaciones'

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = self._siguiente_numero()
        super().save(*args, **kwargs)

    def _siguiente_numero(self):
        base = f'COT-{self.fecha.year}-'
        mayor = 0
        for numero in Cotizacion.objects.filter(numero__startswith=base).values_list('numero', flat=True):
            sufijo = numero[len(base):]
            if sufijo.isdigit():
                mayor = max(mayor, int(sufijo))
        return f'{base}{mayor + 1:04d}'

    def get_absolute_url(self):
        return reverse('cotizacion_detalle', args=[self.pk])

    # --- Datos de contacto (los de la cotización mandan sobre los del cliente) ---
    @property
    def contacto(self):
        return self.contacto_nombre or self.cliente.contacto

    @property
    def telefono(self):
        return self.contacto_telefono or self.cliente.telefono

    @property
    def email(self):
        return self.contacto_email or self.cliente.email

    # --- Montos ---
    @property
    def neto(self):
        return sum((i.subtotal for i in self.items.all()), Decimal('0'))

    @property
    def iva(self):
        return (self.neto * IVA).quantize(Decimal('1'))

    @property
    def total(self):
        return self.neto + self.iva

    # --- Seguimiento ---
    @property
    def dias_desde_envio(self):
        return (_hoy() - self.fecha).days

    @property
    def fecha_gestion(self):
        """Último movimiento: el envío o el último seguimiento, el que sea más reciente."""
        return max(self.fecha, self.ultimo_contacto) if self.ultimo_contacto else self.fecha

    @property
    def dias_sin_gestion(self):
        return (_hoy() - self.fecha_gestion).days

    @property
    def vence(self):
        return self.fecha + timedelta(days=self.validez_dias)

    @property
    def por_llamar(self):
        return (self.estado == self.Estado.PENDIENTE
                and self.dias_desde_envio > settings.COTIZACION_DIAS_ALERTA
                and self.dias_sin_gestion > settings.COTIZACION_DIAS_ALERTA)

    def __str__(self):
        return f'{self.numero} · {self.titulo}'


class CotizacionItem(models.Model):
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.CASCADE, related_name='items')
    descripcion = models.CharField('Descripción', max_length=250)
    cantidad = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    precio_unitario = models.DecimalField('Precio unitario (neto)', max_digits=12, decimal_places=0, default=0)

    class Meta:
        ordering = ['pk']

    @property
    def subtotal(self):
        return (self.cantidad * self.precio_unitario).quantize(Decimal('1'))

    def __str__(self):
        return self.descripcion


class Seguimiento(models.Model):
    """Registro de cada gestión con el cliente: llamada, WhatsApp, correo…"""

    class Medio(models.TextChoices):
        LLAMADA = 'llamada', 'Llamada'
        WHATSAPP = 'whatsapp', 'WhatsApp'
        CORREO = 'correo', 'Correo'
        VISITA = 'visita', 'Visita'

    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.CASCADE, related_name='seguimientos')
    medio = models.CharField(max_length=10, choices=Medio.choices, default=Medio.LLAMADA)
    nota = models.TextField('Qué se conversó', blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='+')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado_en']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        Cotizacion.objects.filter(pk=self.cotizacion_id).update(ultimo_contacto=timezone.localdate())
