from django import forms
from django.db import transaction
from django.contrib.auth.forms import (PasswordChangeForm, PasswordResetForm, SetPasswordForm,
                                       UserCreationForm)

from catalogo.models import Cliente
from core.forms import BootstrapFormMixin

from .models import User


class _CorreoUnicoMixin:
    """El correo es obligatorio (sirve para recuperar la contraseña) y no se repite entre usuarios."""

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        repetido = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError('Ya hay un usuario con este correo.')
        return email


class _EmpresaMixin:
    """Un usuario cliente pertenece a una empresa: se elige una existente o se escribe el nombre de una nueva
    (se crea al guardar, con los datos del propio usuario como contacto)."""

    empresa_creada = None

    def _preparar_empresa(self):
        self.fields['cliente'].label = 'Empresa'
        self.fields['cliente'].help_text = 'Solo para usuarios con rol Cliente.'
        self.fields['empresa_nueva'].help_text = 'Si la empresa aún no existe, escribe aquí su nombre y se crea al guardar.'

    def _validar_empresa(self, data):
        if data.get('rol') != User.Rol.CLIENTE:
            data['empresa_nueva'] = ''
            return
        nueva = (data.get('empresa_nueva') or '').strip()
        if nueva:
            if data.get('cliente'):
                self.add_error('empresa_nueva', 'Elige una empresa de la lista o escribe una nueva, no las dos.')
            elif Cliente.objects.filter(nombre__iexact=nueva).exists():
                self.add_error('empresa_nueva', 'Ya existe una empresa con ese nombre: elígela en la lista.')
        elif not data.get('cliente'):
            self.add_error('cliente', 'Un usuario cliente debe estar asociado a una empresa.')

    def save(self, commit=True):
        usuario = super().save(commit=False)
        nueva = (self.cleaned_data.get('empresa_nueva') or '').strip()
        with transaction.atomic():
            if usuario.rol == User.Rol.CLIENTE and nueva:
                self.empresa_creada = Cliente.objects.create(
                    nombre=nueva, contacto=usuario.get_full_name(), email=usuario.email, telefono=usuario.telefono)
                usuario.cliente = self.empresa_creada
            if commit:
                usuario.save()
                self.save_m2m()
        return usuario


class UsuarioCreateForm(_EmpresaMixin, _CorreoUnicoMixin, BootstrapFormMixin, UserCreationForm):
    empresa_nueva = forms.CharField(label='Empresa nueva', max_length=150, required=False)
    field_order = ['username', 'first_name', 'last_name', 'email', 'telefono', 'rol', 'cliente', 'empresa_nueva',
                   'password1', 'password2']

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'telefono', 'rol', 'cliente']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['email'].help_text = 'Se usa para que la persona recupere su contraseña por correo.'
        self._preparar_empresa()

    def clean(self):
        data = super().clean()
        self._validar_empresa(data)
        return data


class UsuarioUpdateForm(_EmpresaMixin, _CorreoUnicoMixin, BootstrapFormMixin, forms.ModelForm):
    empresa_nueva = forms.CharField(label='Empresa nueva', max_length=150, required=False)
    field_order = ['first_name', 'last_name', 'email', 'telefono', 'rol', 'cliente', 'empresa_nueva', 'is_active']

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'telefono', 'rol', 'cliente', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['email'].help_text = 'Se usa para que la persona recupere su contraseña por correo.'
        self._preparar_empresa()

    def clean(self):
        data = super().clean()
        self._validar_empresa(data)
        return data


# --- Contraseñas ---------------------------------------------------------------

class CambiarClaveForm(BootstrapFormMixin, PasswordChangeForm):
    pass


class RestablecerClaveForm(BootstrapFormMixin, PasswordResetForm):
    """Pide el correo; si existe un usuario activo con ese correo se le envía el enlace."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({'autocomplete': 'email', 'autofocus': True})


class NuevaClaveForm(BootstrapFormMixin, SetPasswordForm):
    pass
