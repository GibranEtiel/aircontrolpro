from django import forms

from core.forms import BootstrapModelForm

from .models import Activo, Cliente, Ubicacion


class ClienteForm(BootstrapModelForm):
    class Meta:
        model = Cliente
        fields = ['nombre', 'rut', 'giro', 'contacto', 'email', 'telefono', 'activo']


class UbicacionForm(BootstrapModelForm):
    class Meta:
        model = Ubicacion
        fields = ['cliente', 'nombre', 'codigo', 'direccion', 'ciudad', 'region',
                  'latitud', 'longitud', 'activa']


class ActivoForm(BootstrapModelForm):
    class Meta:
        model = Activo
        fields = ['ubicacion', 'codigo', 'numero_equipo', 'ubicacion_exacta', 'nombre', 'tipo', 'marca',
                  'modelo', 'numero_serie',
                  'capacidad_btu', 'refrigerante', 'estado', 'condicion', 'fecha_instalacion',
                  'observaciones']
        widgets = {
            'fecha_instalacion': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'observaciones': forms.Textarea(attrs={'rows': 3}),
        }
