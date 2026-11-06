from django.urls import path

from . import views

urlpatterns = [
    path('clientes/', views.ClienteList.as_view(), name='clientes'),
    path('clientes/nuevo/', views.ClienteCreate.as_view(), name='cliente_nuevo'),
    path('clientes/<int:pk>/editar/', views.ClienteUpdate.as_view(), name='cliente_editar'),
    path('ubicaciones/', views.UbicacionList.as_view(), name='ubicaciones'),
    path('ubicaciones/nueva/', views.UbicacionCreate.as_view(), name='ubicacion_nueva'),
    path('ubicaciones/<int:pk>/editar/', views.UbicacionUpdate.as_view(), name='ubicacion_editar'),
    path('equipos/', views.ActivoList.as_view(), name='activos'),
    path('equipos/nuevo/', views.ActivoCreate.as_view(), name='activo_nuevo'),
    path('equipos/<int:pk>/editar/', views.ActivoUpdate.as_view(), name='activo_editar'),
]
