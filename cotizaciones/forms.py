from django import forms
from django.forms import inlineformset_factory

from catalogo.models import Cliente, Ubicacion
from core.forms import BootstrapFormMixin, BootstrapModelForm

from .models import Cotizacion, CotizacionItem, Seguimiento


class UbicacionSelect(forms.Select):
    """Marca cada sucursal con su cliente para filtrarlas en el navegador."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs']['data-cliente'] = instance.cliente_id
        return option


class CotizacionForm(BootstrapModelForm):
    class Meta:
        model = Cotizacion
        fields = ['numero', 'cliente', 'ubicacion', 'titulo', 'fecha', 'validez_dias', 'descripcion',
                  'contacto_nombre', 'contacto_telefono', 'contacto_email']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'descripcion': forms.Textarea(attrs={'rows': 4}),
            'ubicacion': UbicacionSelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cliente'].queryset = Cliente.objects.filter(activo=True)
        self.fields['ubicacion'].queryset = Ubicacion.objects.filter(activa=True).select_related('cliente')
        self.fields['ubicacion'].required = False

    def clean(self):
        datos = super().clean()
        cliente, ubicacion = datos.get('cliente'), datos.get('ubicacion')
        if cliente and ubicacion and ubicacion.cliente_id != cliente.pk:
            self.add_error('ubicacion', 'Esa sucursal no pertenece al cliente elegido.')
        return datos


class ItemForm(BootstrapModelForm):
    class Meta:
        model = CotizacionItem
        fields = ['descripcion', 'cantidad', 'precio_unitario']
        widgets = {'cantidad': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
                   'precio_unitario': forms.NumberInput(attrs={'min': '0', 'step': '1'})}


ItemFormSet = inlineformset_factory(
    Cotizacion, CotizacionItem, form=ItemForm, extra=2, can_delete=True, min_num=1, validate_min=True)


class SeguimientoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Seguimiento
        fields = ['medio', 'nota']
        widgets = {'nota': forms.Textarea(attrs={
            'rows': 2, 'placeholder': 'Ej.: Lo revisa con gerencia, llamar el jueves.'})}
