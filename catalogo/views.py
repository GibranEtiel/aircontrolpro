from django.contrib import messages
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from accounts.models import User
from core.exports import Col, exportar_tabla, formato_export, resolver
from core.permissions import RolRequiredMixin

from .forms import ActivoForm, ClienteForm, UbicacionForm
from .models import Activo, Cliente, Ubicacion

ADMIN = (User.Rol.ADMIN,)
TODOS = (User.Rol.ADMIN, User.Rol.TECNICO, User.Rol.CLIENTE)
EDITAN_EQUIPOS = (User.Rol.ADMIN, User.Rol.TECNICO)  # el técnico da de alta equipos en terreno


class CatalogoList(RolRequiredMixin, ListView):
    """Listado genérico: la plantilla dibuja `columnas` = [(encabezado, 'ruta.atributo')]."""

    template_name = 'generic/list.html'
    titulo = ''
    columnas = []
    nuevo_url = None
    editar_url = None
    roles_edicion = (User.Rol.ADMIN,)  # quiénes ven los botones Nuevo y Editar
    busqueda = ()
    paginate_by = 25

    def filtrar_por_rol(self, qs):
        return qs

    def get_queryset(self):
        qs = self.filtrar_por_rol(super().get_queryset())
        q = self.request.GET.get('q', '').strip()
        if q and self.busqueda:
            filtro = Q()
            for campo in self.busqueda:
                filtro |= Q(**{f'{campo}__icontains': q})
            qs = qs.filter(filtro)
        return qs

    def get(self, request, *args, **kwargs):
        formato = formato_export(request)
        if formato:
            filas = [[resolver(obj, ruta) for _, ruta in self.columnas] for obj in self.get_queryset()]
            return exportar_tabla(formato, self.titulo, self.titulo,
                                  [Col(titulo) for titulo, _ in self.columnas], filas)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        puede_editar = self.request.user.rol in self.roles_edicion
        ctx.update(
            titulo=self.titulo, columnas=self.columnas, q=self.request.GET.get('q', ''),
            nuevo_url=self.nuevo_url if puede_editar else None,
            editar_url=self.editar_url if puede_editar else None,
        )
        return ctx


class CatalogoForm:
    template_name = 'generic/form.html'
    titulo = ''
    mensaje = 'Guardado correctamente.'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(titulo=self.titulo, volver=self.success_url)
        return ctx

    def form_valid(self, form):
        messages.success(self.request, self.mensaje)
        return super().form_valid(form)


# --- Clientes -------------------------------------------------------------

class ClienteList(CatalogoList):
    roles = ADMIN
    model = Cliente
    titulo = 'Clientes'
    columnas = [('Cliente', 'nombre'), ('RUT', 'rut'), ('Contacto', 'contacto'),
                ('Email', 'email'), ('Teléfono', 'telefono'), ('Activo', 'activo')]
    nuevo_url = 'cliente_nuevo'
    editar_url = 'cliente_editar'
    busqueda = ('nombre', 'rut', 'contacto')


class ClienteCreate(CatalogoForm, RolRequiredMixin, CreateView):
    roles = ADMIN
    form_class = ClienteForm
    titulo = 'Nuevo cliente'
    success_url = reverse_lazy('clientes')


class ClienteUpdate(CatalogoForm, RolRequiredMixin, UpdateView):
    roles = ADMIN
    model = Cliente
    form_class = ClienteForm
    titulo = 'Editar cliente'
    success_url = reverse_lazy('clientes')


# --- Ubicaciones ----------------------------------------------------------

class UbicacionList(CatalogoList):
    roles = TODOS
    model = Ubicacion
    titulo = 'Ubicaciones'
    columnas = [('Ubicación', 'nombre'), ('Cliente', 'cliente'), ('Código', 'codigo'),
                ('Dirección', 'direccion'), ('Ciudad', 'ciudad'), ('Activa', 'activa')]
    nuevo_url = 'ubicacion_nueva'
    editar_url = 'ubicacion_editar'
    busqueda = ('nombre', 'codigo', 'direccion', 'cliente__nombre')

    def filtrar_por_rol(self, qs):
        qs = qs.select_related('cliente')
        user = self.request.user
        if user.es_cliente:
            return qs.filter(cliente_id=user.cliente_id)
        return qs


class UbicacionCreate(CatalogoForm, RolRequiredMixin, CreateView):
    roles = ADMIN
    form_class = UbicacionForm
    titulo = 'Nueva ubicación'
    success_url = reverse_lazy('ubicaciones')


class UbicacionUpdate(CatalogoForm, RolRequiredMixin, UpdateView):
    roles = ADMIN
    model = Ubicacion
    form_class = UbicacionForm
    titulo = 'Editar ubicación'
    success_url = reverse_lazy('ubicaciones')


# --- Activos (equipos) ----------------------------------------------------

class ActivoList(CatalogoList):
    roles = TODOS
    model = Activo
    titulo = 'Equipos'
    columnas = [('N°', 'numero_equipo'), ('Código', 'codigo'), ('Equipo', 'nombre'),
                ('Marca / modelo', 'marca_modelo'), ('Ubicación exacta', 'ubicacion_exacta'),
                ('Sucursal', 'ubicacion'), ('Refrigerante', 'refrigerante'),
                ('Estado', 'get_estado_display'), ('Condición', 'get_condicion_display')]
    nuevo_url = 'activo_nuevo'
    editar_url = 'activo_editar'
    roles_edicion = EDITAN_EQUIPOS
    busqueda = ('codigo', 'numero_equipo', 'nombre', 'marca', 'modelo', 'numero_serie',
                'ubicacion_exacta', 'ubicacion__nombre')

    def filtrar_por_rol(self, qs):
        qs = qs.select_related('ubicacion', 'ubicacion__cliente')
        user = self.request.user
        if user.es_cliente:
            return qs.filter(ubicacion__cliente_id=user.cliente_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.user.es_cliente:
            ctx['titulo'] = 'Mis equipos'
        return ctx


class ActivoCreate(CatalogoForm, RolRequiredMixin, CreateView):
    roles = EDITAN_EQUIPOS
    form_class = ActivoForm
    titulo = 'Nuevo equipo'
    success_url = reverse_lazy('activos')


class ActivoUpdate(CatalogoForm, RolRequiredMixin, UpdateView):
    roles = EDITAN_EQUIPOS
    model = Activo
    form_class = ActivoForm
    titulo = 'Editar equipo'
    success_url = reverse_lazy('activos')
