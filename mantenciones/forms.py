from django import forms
from django.utils import timezone

from accounts.models import User
from catalogo.models import Activo, Cliente, Ubicacion
from core.forms import BootstrapFormMixin, BootstrapModelForm

from .models import TAREAS_MANTENCION, Informe, InformeEquipo, OrdenTrabajo, siguiente_numero_ot


class ActivosCheckbox(forms.CheckboxSelectMultiple):
    """Marca cada opción con su ubicación para filtrarlas en el navegador."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs']['data-ubicacion'] = instance.ubicacion_id
        return option


class OrdenForm(BootstrapModelForm):
    class Meta:
        model = OrdenTrabajo
        fields = ['numero', 'titulo', 'atencion', 'tipo', 'prioridad', 'estado', 'ubicacion', 'activos',
                  'tecnico', 'fecha_programada', 'descripcion', 'monto_neto', 'costo_materiales',
                  'costo_mano_obra', 'estado_pago', 'fecha_pago']
        widgets = {
            'activos': ActivosCheckbox,
            'fecha_programada': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'fecha_pago': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'descripcion': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ubicacion'].queryset = Ubicacion.objects.select_related('cliente')
        self.fields['activos'].queryset = Activo.objects.select_related('ubicacion')
        self.fields['tecnico'].queryset = User.objects.filter(rol=User.Rol.TECNICO, is_active=True)
        if not self.instance.pk:
            self.fields['numero'].widget.attrs['placeholder'] = (
                f'Automático: {siguiente_numero_ot(timezone.localdate().year)}')

    def clean(self):
        data = super().clean()
        ubicacion = data.get('ubicacion')
        activos = data.get('activos')
        if ubicacion and activos:
            ajenos = [a.codigo for a in activos if a.ubicacion.cliente_id != ubicacion.cliente_id]
            if ajenos:
                self.add_error('activos', f'Estos equipos no pertenecen al cliente de la ubicación: {", ".join(ajenos)}')
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.cliente = obj.ubicacion.cliente
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class InformeForm(BootstrapModelForm):
    """Textos generales del informe."""

    class Meta:
        model = Informe
        fields = ['diagnostico', 'trabajos_realizados', 'recomendaciones', 'recibido_por']
        widgets = {
            'diagnostico': forms.Textarea(attrs={'rows': 3}),
            'trabajos_realizados': forms.Textarea(attrs={'rows': 3}),
            'recomendaciones': forms.Textarea(attrs={'rows': 3}),
        }


class ClienteSelect(forms.Select):
    """Select de sucursales que marca cada opción con su cliente para filtrarlas en el navegador."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs']['data-cliente'] = instance.cliente_id
        return option


class InformeNuevoForm(BootstrapFormMixin, forms.Form):
    """El técnico abre un informe en terreno sin que exista una orden previa."""

    cliente = forms.ModelChoiceField(queryset=Cliente.objects.filter(activo=True), label='Cliente')
    ubicacion = forms.ModelChoiceField(queryset=Ubicacion.objects.filter(activa=True), label='Sucursal',
                                       widget=ClienteSelect)
    tipo = forms.ChoiceField(label='Tipo de trabajo', choices=OrdenTrabajo.Tipo.choices,
                             initial=OrdenTrabajo.Tipo.PREVENTIVO)
    titulo = forms.CharField(label='Título (opcional)', max_length=200, required=False)
    atencion = forms.CharField(label='A.t (opcional)', max_length=120, required=False,
                               help_text='Si lo dejas vacío se usa el contacto del cliente.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ubicacion'].queryset = Ubicacion.objects.filter(activa=True).select_related('cliente')

    def clean(self):
        datos = super().clean()
        cliente, ubicacion = datos.get('cliente'), datos.get('ubicacion')
        if cliente and ubicacion and ubicacion.cliente_id != cliente.pk:
            self.add_error('ubicacion', 'Esa sucursal no pertenece al cliente elegido.')
        return datos


class EquipoNuevoForm(BootstrapFormMixin, forms.Form):
    """Alta rápida de un equipo que el técnico encuentra en terreno y aún no está en el catálogo."""

    numero_equipo = forms.CharField(label='N° de equipo', max_length=20)
    marca = forms.CharField(max_length=60, required=False)
    modelo = forms.CharField(max_length=80, required=False)
    ubicacion_exacta = forms.CharField(label='Ubicación exacta', max_length=150, required=False)
    refrigerante = forms.CharField(max_length=20, required=False)
    ubicacion = forms.ModelChoiceField(label='Sucursal', queryset=Ubicacion.objects.none())

    def __init__(self, *args, ubicaciones, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ubicacion'].queryset = ubicaciones
        self.fields['ubicacion'].empty_label = None
        self.cliente_id = ubicaciones[0].cliente_id if ubicaciones else None

    def clean_numero_equipo(self):
        numero = self.cleaned_data['numero_equipo'].strip()
        if Activo.objects.filter(ubicacion__cliente_id=self.cliente_id, numero_equipo=numero).exists():
            raise forms.ValidationError(f'El cliente ya tiene un equipo N°{numero}: agrégalo desde la lista.')
        return numero


class InformeEquipoForm(BootstrapFormMixin, forms.ModelForm):
    tareas = forms.MultipleChoiceField(
        choices=TAREAS_MANTENCION, required=False, widget=forms.CheckboxSelectMultiple,
        label='Tareas realizadas',
    )

    class Meta:
        model = InformeEquipo
        fields = ['tipo_mantenimiento', 'tareas', 'observaciones', 'fuera_de_norma', 'presion', 'consumo_total',
                  'consumo_ventilador', 'temp_inyeccion', 'modo', 'estado_equipo']
        widgets = {'observaciones': forms.Textarea(attrs={'rows': 2}),
                   'fuera_de_norma': forms.CheckboxInput(attrs={'role': 'switch'})}
