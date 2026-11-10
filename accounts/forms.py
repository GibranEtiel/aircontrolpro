from django import forms
from django.contrib.auth.forms import (PasswordChangeForm, PasswordResetForm, SetPasswordForm,
                                       UserCreationForm)

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


class UsuarioCreateForm(_CorreoUnicoMixin, BootstrapFormMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'telefono', 'rol', 'cliente']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['email'].help_text = 'Se usa para que la persona recupere su contraseña por correo.'

    def clean(self):
        data = super().clean()
        if data.get('rol') == User.Rol.CLIENTE and not data.get('cliente'):
            self.add_error('cliente', 'Un usuario cliente debe estar asociado a una empresa.')
        return data


class UsuarioUpdateForm(_CorreoUnicoMixin, BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'telefono', 'rol', 'cliente', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['email'].help_text = 'Se usa para que la persona recupere su contraseña por correo.'

    def clean(self):
        data = super().clean()
        if data.get('rol') == User.Rol.CLIENTE and not data.get('cliente'):
            self.add_error('cliente', 'Un usuario cliente debe estar asociado a una empresa.')
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
