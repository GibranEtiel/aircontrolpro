from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


class RolRequiredMixin(LoginRequiredMixin):
    """Restringe una vista basada en clase a ciertos roles (valores de User.Rol)."""

    roles = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if self.roles and request.user.rol not in self.roles:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def rol_required(*roles):
    """Equivalente a RolRequiredMixin para vistas basadas en función."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if roles and request.user.rol not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def ordenes_visibles(user):
    """Órdenes de trabajo que el usuario puede ver según su rol."""
    from mantenciones.models import OrdenTrabajo

    qs = OrdenTrabajo.objects.select_related('cliente', 'ubicacion', 'tecnico')
    if user.es_admin:
        return qs
    if user.es_tecnico:
        return qs.filter(tecnico=user)
    return qs.filter(cliente_id=user.cliente_id) if user.cliente_id else qs.none()


def informes_visibles(user):
    """Informes visibles: el cliente solo ve los emitidos de su empresa."""
    from mantenciones.models import Informe

    qs = Informe.objects.select_related('orden', 'orden__cliente', 'orden__ubicacion', 'tecnico')
    if user.es_admin:
        return qs
    if user.es_tecnico:
        return qs.filter(tecnico=user)
    if not user.cliente_id:
        return qs.none()
    return qs.filter(orden__cliente_id=user.cliente_id, estado=Informe.Estado.EMITIDO)
