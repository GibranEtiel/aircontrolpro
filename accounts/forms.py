from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class UsuarioCreateForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'telefono', 'rol', 'cliente']

    def clean(self):
        data = super().clean()
        if data.get('rol') == User.Rol.CLIENTE and not data.get('cliente'):
            self.add_error('cliente', 'Un usuario cliente debe estar asociado a una empresa.')
        return data


class UsuarioUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'telefono', 'rol', 'cliente', 'is_active']

    def clean(self):
        data = super().clean()
        if data.get('rol') == User.Rol.CLIENTE and not data.get('cliente'):
            self.add_error('cliente', 'Un usuario cliente debe estar asociado a una empresa.')
        return data
