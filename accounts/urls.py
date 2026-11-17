from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import CambiarClaveForm, NuevaClaveForm, RestablecerClaveForm

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html',
                                                redirect_authenticated_user=True), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('clave/', auth_views.PasswordChangeView.as_view(
        template_name='registration/password_change_form.html', form_class=CambiarClaveForm,
        success_url=reverse_lazy('home'),
    ), name='cambiar_clave'),

    # Recuperar la contraseña por correo: pide el correo → llega un enlace → elige la clave nueva.
    path('recuperar/', auth_views.PasswordResetView.as_view(
        form_class=RestablecerClaveForm, success_url=reverse_lazy('password_reset_done'),
    ), name='password_reset'),
    path('recuperar/enviado/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('recuperar/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        form_class=NuevaClaveForm, success_url=reverse_lazy('password_reset_complete'),
    ), name='password_reset_confirm'),
    path('recuperar/listo/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    path('usuarios/', views.UsuarioList.as_view(), name='usuarios'),
    path('usuarios/nuevo/', views.UsuarioCreate.as_view(), name='usuario_nuevo'),
    path('usuarios/<int:pk>/editar/', views.UsuarioUpdate.as_view(), name='usuario_editar'),
    path('usuarios/<int:pk>/eliminar/', views.UsuarioEliminar.as_view(), name='usuario_eliminar'),
]
