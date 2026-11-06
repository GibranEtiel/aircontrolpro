from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.exports import Col, exportar_tabla, formato_export
from core.permissions import RolRequiredMixin

from .forms import UsuarioCreateForm, UsuarioUpdateForm
from .models import User


class UsuarioList(RolRequiredMixin, ListView):
    roles = (User.Rol.ADMIN,)
    template_name = 'accounts/usuarios_list.html'
    context_object_name = 'usuarios'

    def get_queryset(self):
        qs = User.objects.select_related('cliente')
        rol = self.request.GET.get('rol')
        return qs.filter(rol=rol) if rol in User.Rol.values else qs

    def get(self, request, *args, **kwargs):
        formato = formato_export(request)
        if formato:
            filas = [[u.username, u.nombre, u.email, u.telefono, u.get_rol_display(), u.cliente,
                      'Activo' if u.is_active else 'Inactivo'] for u in self.get_queryset()]
            columnas = [Col(c) for c in ('Usuario', 'Nombre', 'Email', 'Teléfono', 'Rol', 'Empresa', 'Estado')]
            return exportar_tabla(formato, 'usuarios', 'Usuarios y roles', columnas, filas)
        return super().get(request, *args, **kwargs)


class UsuarioCreate(RolRequiredMixin, CreateView):
    roles = (User.Rol.ADMIN,)
    form_class = UsuarioCreateForm
    template_name = 'generic/form.html'
    success_url = reverse_lazy('usuarios')
    extra_context = {'titulo': 'Nuevo usuario', 'volver': reverse_lazy('usuarios')}

    def form_valid(self, form):
        messages.success(self.request, 'Usuario creado.')
        return super().form_valid(form)


class UsuarioUpdate(RolRequiredMixin, UpdateView):
    roles = (User.Rol.ADMIN,)
    model = User
    form_class = UsuarioUpdateForm
    template_name = 'generic/form.html'
    success_url = reverse_lazy('usuarios')
    extra_context = {'titulo': 'Editar usuario', 'volver': reverse_lazy('usuarios')}

    def form_valid(self, form):
        messages.success(self.request, 'Usuario actualizado.')
        return super().form_valid(form)
