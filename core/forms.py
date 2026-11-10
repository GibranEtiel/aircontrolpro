from django import forms


class BootstrapFormMixin:
    """Aplica las clases de Bootstrap a todos los campos del formulario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if isinstance(campo, forms.ModelChoiceField) and campo.empty_label is not None:
                campo.empty_label = '— Elegir —'
            w = campo.widget
            if isinstance(w, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                clase = 'form-check-input'
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                clase = 'form-select'
            else:
                clase = 'form-control'
            w.attrs['class'] = f"{w.attrs.get('class', '')} {clase}".strip()


class BootstrapModelForm(BootstrapFormMixin, forms.ModelForm):
    pass
