from itertools import groupby

from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View

from accounts.models import User
from core.exports import Col, exportar_tabla, formato_export, resolver
from core.permissions import RolRequiredMixin

from . import eliminar as borrado
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
    eliminar_name = None  # nombre de la URL que confirma la eliminación (solo en las pantallas de edición)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(titulo=self.titulo, volver=self.success_url)
        objeto = getattr(self, 'object', None)
        if self.eliminar_name and objeto is not None and objeto.pk and self.request.user.es_admin:
            ctx['eliminar_url'] = reverse(self.eliminar_name, args=[objeto.pk])
        return ctx

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        messages.success(self.request, self.mensaje + getattr(form, 'mensaje_extra', ''))
        return respuesta


# --- Clientes -------------------------------------------------------------

class ClienteList(CatalogoList):
    roles = ADMIN
    model = Cliente
    titulo = 'Clientes'
    columnas = [('Cliente', 'nombre'), ('Contacto', 'contacto'),
                ('Email', 'email'), ('Teléfono', 'telefono'), ('Activo', 'activo')]
    nuevo_url = 'cliente_nuevo'
    editar_url = 'cliente_editar'
    busqueda = ('nombre', 'contacto')


class ClienteCreate(CatalogoForm, RolRequiredMixin, CreateView):
    roles = ADMIN
    form_class = ClienteForm
    titulo = 'Nuevo cliente'
    success_url = reverse_lazy('clientes')


class ClienteUpdate(CatalogoForm, RolRequiredMixin, UpdateView):
    eliminar_name = 'cliente_eliminar'
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
    template_name = 'catalogo/ubicacion_form.html'
    roles = ADMIN
    form_class = UbicacionForm
    titulo = 'Nueva ubicación'
    success_url = reverse_lazy('ubicaciones')


class UbicacionUpdate(CatalogoForm, RolRequiredMixin, UpdateView):
    eliminar_name = 'ubicacion_eliminar'
    template_name = 'catalogo/ubicacion_form.html'
    roles = ADMIN
    model = Ubicacion
    form_class = UbicacionForm
    titulo = 'Editar ubicación'
    success_url = reverse_lazy('ubicaciones')


# --- Activos (equipos) ----------------------------------------------------

class ActivoList(CatalogoList):
    """Equipos agrupados por empresa: una tarjeta plegable por cliente, con sus equipos adentro."""

    template_name = 'catalogo/activos_list.html'
    paginate_by = None
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

    def get_queryset(self):
        qs = super().get_queryset()
        cliente = self.request.GET.get('cliente', '')
        if cliente.isdigit() and not self.request.user.es_cliente:
            qs = qs.filter(ubicacion__cliente_id=cliente)
        # Por empresa, luego sucursal y número de equipo (también ordena la exportación)
        return qs.order_by('ubicacion__cliente__nombre', 'ubicacion__cliente_id', 'ubicacion__nombre',
                           'numero_equipo', 'codigo')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        if user.es_cliente:
            ctx['titulo'] = 'Mis equipos'
        grupos = []
        for cliente, items in groupby(ctx['object_list'], key=lambda a: a.ubicacion.cliente):
            items = list(items)
            grupos.append({
                'cliente': cliente, 'activos': items,
                'fuera_norma': sum(1 for a in items if a.fuera_de_norma),
                'por_revisar': sum(1 for a in items if a.condicion != Activo.Condicion.BUENA),
                'sucursales': len({a.ubicacion_id for a in items}),
            })
        ctx.update(
            grupos=grupos, total=sum(len(g['activos']) for g in grupos),
            clientes=[] if user.es_cliente else Cliente.objects.filter(activo=True),
            cliente_id=self.request.GET.get('cliente', ''),
            # Con pocos equipos o una búsqueda activa se muestra todo abierto; con muchos, plegado.
            abierto=bool(self.request.GET.get('q') or self.request.GET.get('cliente'))
            or sum(len(g['activos']) for g in grupos) <= 30 or len(grupos) == 1)
        return ctx


class ActivoCreate(CatalogoForm, RolRequiredMixin, CreateView):
    template_name = 'catalogo/activo_form.html'
    roles = EDITAN_EQUIPOS
    form_class = ActivoForm
    titulo = 'Nuevo equipo'
    success_url = reverse_lazy('activos')


class ActivoUpdate(CatalogoForm, RolRequiredMixin, UpdateView):
    eliminar_name = 'activo_eliminar'
    template_name = 'catalogo/activo_form.html'
    roles = EDITAN_EQUIPOS
    model = Activo
    form_class = ActivoForm
    titulo = 'Editar equipo'
    success_url = reverse_lazy('activos')


# --- Eliminar ---------------------------------------------------------------

class EliminarView(RolRequiredMixin, View):
    """Confirma y elimina. Solo el administrador. Lo que tiene historial se ofrece desactivar en vez de borrar."""

    roles = ADMIN
    modelo = None
    editar_name = ''
    lista_name = ''

    def protegido(self, request, objeto):
        """Razones que impiden eliminar Y desactivar (p. ej. tu propia cuenta). Por defecto ninguna."""
        return []

    def get(self, request, pk):
        objeto = get_object_or_404(self.modelo, pk=pk)
        protegido = self.protegido(request, objeto)
        bloqueos, arrastra = borrado.analizar(objeto)
        return render(request, 'catalogo/eliminar.html', {
            'objeto': objeto, 'nombre': borrado.nombre_objeto(objeto), 'que': borrado.etiqueta(objeto),
            'bloqueos': protegido + bloqueos, 'arrastra': arrastra,
            'puede_desactivar': borrado.esta_activo(objeto) and not protegido,
            'volver': reverse(self.editar_name, args=[objeto.pk]),
        })

    def post(self, request, pk):
        objeto = get_object_or_404(self.modelo, pk=pk)
        nombre = borrado.nombre_objeto(objeto)
        protegido = self.protegido(request, objeto)
        if request.POST.get('accion') == 'desactivar':
            if protegido:
                messages.error(request, f'«{nombre}» no se puede desactivar: {protegido[0]}')
                return redirect(request.path)
            borrado.desactivar(objeto)
            messages.success(request, f'«{nombre}» quedó desactivado: ya no aparece para elegir, pero su historial se conserva.')
            return redirect(self.lista_name)
        bloqueos, _ = borrado.analizar(objeto)
        if protegido or bloqueos:
            messages.error(request, f'«{nombre}» no se puede eliminar.' + (f' {protegido[0]}' if protegido else ' Tiene historial.'))
            return redirect(request.path)
        try:
            borrado.eliminar(objeto)
        except ProtectedError:
            messages.error(request, f'«{nombre}» está en uso y no se puede eliminar.')
            return redirect(request.path)
        masculino = borrado.etiqueta(objeto).startswith('el ')
        messages.success(request, f'{borrado.etiqueta(objeto).capitalize()} «{nombre}» eliminad{"o" if masculino else "a"}.')
        return redirect(self.lista_name)


class ClienteEliminar(EliminarView):
    modelo, editar_name, lista_name = Cliente, 'cliente_editar', 'clientes'


class UbicacionEliminar(EliminarView):
    modelo, editar_name, lista_name = Ubicacion, 'ubicacion_editar', 'ubicaciones'


class ActivoEliminar(EliminarView):
    modelo, editar_name, lista_name = Activo, 'activo_editar', 'activos'
