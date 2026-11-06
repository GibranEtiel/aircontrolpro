from django.db import models


class Cliente(models.Model):
    nombre = models.CharField('Razón social / nombre', max_length=150)
    rut = models.CharField('RUT', max_length=20, blank=True)
    giro = models.CharField(max_length=120, blank=True)
    contacto = models.CharField('Contacto', max_length=120, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField('Teléfono', max_length=30, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Ubicacion(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='ubicaciones')
    nombre = models.CharField(max_length=150)
    codigo = models.CharField('Código', max_length=30, blank=True)
    direccion = models.CharField('Dirección', max_length=200, blank=True)
    ciudad = models.CharField(max_length=80, blank=True)
    region = models.CharField('Región', max_length=80, blank=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ['cliente__nombre', 'nombre']
        verbose_name = 'ubicación'
        verbose_name_plural = 'ubicaciones'

    def __str__(self):
        return f'{self.nombre} ({self.cliente})'


class Activo(models.Model):
    class Tipo(models.TextChoices):
        SPLIT = 'split', 'Split muro'
        CASSETTE = 'cassette', 'Cassette'
        DUCTO = 'ducto', 'Ducto'
        PISO_CIELO = 'piso_cielo', 'Piso cielo'
        VRF = 'vrf', 'VRF / VRV'
        CHILLER = 'chiller', 'Chiller'
        CAMARA = 'camara', 'Cámara de frío'
        OTRO = 'otro', 'Otro'

    class Estado(models.TextChoices):
        ACTIVO = 'activo', 'Activo'
        INACTIVO = 'inactivo', 'Inactivo'
        BAJA = 'baja', 'Dado de baja'

    class Condicion(models.TextChoices):
        BUENA = 'buena', 'Buena'
        REGULAR = 'regular', 'Regular'
        MALA = 'mala', 'Mala'

    ubicacion = models.ForeignKey(Ubicacion, on_delete=models.PROTECT, related_name='activos')
    codigo = models.CharField('Código', max_length=40, unique=True)
    numero_equipo = models.CharField(
        'N° de equipo', max_length=20, blank=True, default='',
        help_text='Número con que aparece en el informe: "Equipo N°020".')
    ubicacion_exacta = models.CharField(
        'Ubicación exacta', max_length=150, blank=True, default='',
        help_text='Dónde está dentro de la sucursal: "Gerente general", "Sala de servidores"…')
    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.SPLIT)
    marca = models.CharField(max_length=60, blank=True)
    modelo = models.CharField(max_length=80, blank=True)
    numero_serie = models.CharField('N° de serie', max_length=80, blank=True)
    capacidad_btu = models.PositiveIntegerField('Capacidad (BTU)', null=True, blank=True)
    refrigerante = models.CharField(max_length=20, blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVO)
    condicion = models.CharField(max_length=10, choices=Condicion.choices, default=Condicion.BUENA)
    fecha_instalacion = models.DateField('Fecha de instalación', null=True, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ['codigo']

    @property
    def cliente(self):
        return self.ubicacion.cliente

    @property
    def etiqueta(self):
        """'Equipo N°020' como en el informe; si no tiene número usa el código."""
        return f'Equipo N°{self.numero_equipo}' if self.numero_equipo else f'Equipo {self.codigo}'

    @property
    def marca_modelo(self):
        return f'{self.marca or "-"}/{self.modelo or "-"}'

    @property
    def fuera_de_norma(self):
        """Los equipos con refrigerante R-22 se informan como fuera de norma."""
        return self.refrigerante.upper().replace('-', '').replace(' ', '') == 'R22'

    def __str__(self):
        return f'{self.codigo} · {self.nombre}'
