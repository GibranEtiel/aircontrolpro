from django import forms
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify

from core.forms import BootstrapModelForm

from .models import Activo, Cliente, Ubicacion


class ClienteForm(BootstrapModelForm):
    class Meta:
        model = Cliente
        fields = ['nombre', 'giro', 'contacto', 'email', 'telefono', 'activo']


class _EmpresaNuevaMixin:
    """Elegir la empresa de la lista o escribir el nombre de una nueva, que se crea al guardar."""

    empresa_creada = None

    def _validar_empresa(self, datos):
        """Devuelve el nombre de la empresa nueva ('' si se eligió una existente)."""
        cliente, nueva = datos.get('cliente'), (datos.get('empresa_nueva') or '').strip()
        if nueva:
            if cliente:
                self.add_error('empresa_nueva', 'Elige una empresa de la lista o escribe una nueva, no las dos.')
            elif Cliente.objects.filter(nombre__iexact=nueva).exists():
                self.add_error('empresa_nueva', 'Ya existe una empresa con ese nombre: elígela en la lista.')
        elif not cliente:
            self.add_error('cliente', 'Elige la empresa o escribe el nombre de una nueva.')
        return nueva

    def _empresa_para_guardar(self):
        nueva = (self.cleaned_data.get('empresa_nueva') or '').strip()
        if nueva:
            self.empresa_creada = Cliente.objects.create(nombre=nueva)
            return self.empresa_creada
        return self.cleaned_data['cliente']


class UbicacionForm(_EmpresaNuevaMixin, BootstrapModelForm):
    empresa_nueva = forms.CharField(label='Empresa nueva', max_length=150, required=False)
    field_order = ['cliente', 'empresa_nueva', 'nombre', 'codigo', 'direccion', 'ciudad', 'region', 'activa']

    class Meta:
        model = Ubicacion
        fields = ['cliente', 'nombre', 'codigo', 'direccion', 'ciudad', 'region', 'activa']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cliente'].label = 'Empresa'
        self.fields['cliente'].required = False
        self.fields['empresa_nueva'].help_text = 'Si la empresa aún no existe, escribe aquí su nombre y se crea al guardar.'

    def clean(self):
        datos = super().clean()
        self._validar_empresa(datos)
        return datos

    @property
    def mensaje_extra(self):
        return f' Empresa «{self.empresa_creada.nombre}» creada.' if self.empresa_creada else ''

    def save(self, commit=True):
        sucursal = super().save(commit=False)
        with transaction.atomic():
            sucursal.cliente = self._empresa_para_guardar()
            if commit:
                sucursal.save()
                self.save_m2m()
        return sucursal


class SucursalSelect(forms.Select):
    """Marca cada sucursal con su empresa para mostrar solo las de la empresa elegida."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs']['data-cliente'] = instance.cliente_id
        return option


def _codigo_automatico(cliente_nombre, cliente, numero, excluir_pk=None):
    """EMPRESA-N° (p. ej. LUCAS-020); si ya existe, EMPRESA-N°-2, -3…"""
    prefijo = slugify(cliente_nombre.split()[0]).upper()[:8] or 'EQ'
    if numero:
        numero = slugify(numero).upper()
    else:
        numero = str(Activo.objects.filter(ubicacion__cliente=cliente).count() + 1) if cliente else '1'
    base = f'{prefijo}-{numero}'
    codigo, n = base, 1
    while Activo.objects.filter(codigo=codigo).exclude(pk=excluir_pk).exists():
        n += 1
        codigo = f'{base}-{n}'
    return codigo


class ActivoForm(_EmpresaNuevaMixin, BootstrapModelForm):
    """Equipo: primero la empresa a la que pertenece (así el cliente lo ve), luego su sucursal.

    La empresa y la sucursal pueden ser nuevas: se crean al guardar. Si la empresa no tiene sucursales, el equipo
    queda en «Sucursal principal» (o el nombre que escribas).
    """

    cliente = forms.ModelChoiceField(queryset=Cliente.objects.none(), label='Empresa', required=False)
    empresa_nueva = forms.CharField(label='Empresa nueva', max_length=150, required=False)
    ubicacion_nueva = forms.CharField(label='Sucursal nueva', max_length=150, required=False)
    sucursal_creada = None

    field_order = ['cliente', 'empresa_nueva', 'ubicacion', 'ubicacion_nueva', 'numero_equipo', 'ubicacion_exacta',
                   'tipo', 'marca', 'modelo', 'numero_serie', 'capacidad_btu', 'refrigerante', 'estado',
                   'condicion', 'fecha_instalacion', 'codigo', 'observaciones']

    class Meta:
        model = Activo
        fields = ['ubicacion', 'codigo', 'numero_equipo', 'ubicacion_exacta', 'tipo', 'marca',
                  'modelo', 'numero_serie',
                  'capacidad_btu', 'refrigerante', 'estado', 'condicion', 'fecha_instalacion',
                  'observaciones']
        widgets = {
            'fecha_instalacion': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'observaciones': forms.Textarea(attrs={'rows': 3}),
            'ubicacion': SucursalSelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        actual = self.instance.ubicacion if self.instance.pk else None
        self.fields['cliente'].queryset = Cliente.objects.filter(
            Q(activo=True) | Q(pk=actual.cliente_id if actual else None))
        if actual:
            self.fields['cliente'].initial = actual.cliente_id
        self.fields['cliente'].help_text = 'El equipo aparece en el portal de esta empresa.'
        self.fields['empresa_nueva'].help_text = 'Si la empresa aún no existe, escribe aquí su nombre y se crea al guardar.'
        ubicacion = self.fields['ubicacion']
        ubicacion.label = 'Sucursal'
        ubicacion.required = False
        ubicacion.queryset = Ubicacion.objects.filter(Q(activa=True) | Q(pk=actual.pk if actual else None)
                                                      ).select_related('cliente')
        self.fields['ubicacion_nueva'].help_text = 'Se crea al guardar y queda en la lista de la empresa.'
        self.fields['codigo'].required = False
        self.fields['codigo'].help_text = 'Opcional: si lo dejas vacío se genera solo (EMPRESA-N° de equipo).'

    def clean(self):
        datos = super().clean()
        cliente, ubicacion = datos.get('cliente'), datos.get('ubicacion')
        sucursal_nueva = (datos.get('ubicacion_nueva') or '').strip()
        empresa_nueva = self._validar_empresa(datos)
        if not (cliente or empresa_nueva) or self.errors:
            return datos
        if empresa_nueva:
            if ubicacion:
                self.add_error('ubicacion', 'Con una empresa nueva la sucursal también es nueva: no elijas una de la lista.')
        elif ubicacion and sucursal_nueva:
            self.add_error('ubicacion_nueva', 'Elige una sucursal de la lista o escribe una nueva, no las dos.')
        elif ubicacion:
            if ubicacion.cliente_id != cliente.pk:
                self.add_error('ubicacion', 'Esa sucursal no pertenece a la empresa elegida.')
        elif sucursal_nueva:
            if Ubicacion.objects.filter(cliente=cliente, nombre__iexact=sucursal_nueva).exists():
                self.add_error('ubicacion_nueva', 'Ya existe una sucursal con ese nombre: elígela en la lista.')
        elif Ubicacion.objects.filter(cliente=cliente).exists():
            self.add_error('ubicacion', 'Elige la sucursal o escribe el nombre de una nueva.')
        if not self.errors and not (datos.get('codigo') or '').strip():
            datos['codigo'] = _codigo_automatico(
                empresa_nueva or cliente.nombre, cliente, datos.get('numero_equipo'), self.instance.pk)
        return datos

    @property
    def mensaje_extra(self):
        partes = []
        if self.empresa_creada:
            partes.append(f'Empresa «{self.empresa_creada.nombre}» creada.')
        if self.sucursal_creada:
            partes.append(f'Sucursal «{self.sucursal_creada.nombre}» creada.')
        return (' ' + ' '.join(partes)) if partes else ''

    def save(self, commit=True):
        activo = super().save(commit=False)
        activo.nombre = activo.get_tipo_display()  # el nombre ya no se pide: marca, modelo y empresa lo describen
        nueva = (self.cleaned_data.get('ubicacion_nueva') or '').strip()
        with transaction.atomic():
            empresa = self._empresa_para_guardar()
            if not self.cleaned_data.get('ubicacion'):
                self.sucursal_creada = Ubicacion.objects.create(cliente=empresa, nombre=nueva or 'Sucursal principal')
                activo.ubicacion = self.sucursal_creada
            if commit:
                activo.save()
                self.save_m2m()
        return activo
