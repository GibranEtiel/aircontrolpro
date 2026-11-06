from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html',
                                                redirect_authenticated_user=True), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('clave/', auth_views.PasswordChangeView.as_view(
        template_name='generic/form.html',
        success_url=reverse_lazy('home'),
        extra_context={'titulo': 'Cambiar contraseña', 'volver': reverse_lazy('home')},
    ), name='cambiar_clave'),
    path('usuarios/', views.UsuarioList.as_view(), name='usuarios'),
    path('usuarios/nuevo/', views.UsuarioCreate.as_view(), name='usuario_nuevo'),
    path('usuarios/<int:pk>/editar/', views.UsuarioUpdate.as_view(), name='usuario_editar'),
]
