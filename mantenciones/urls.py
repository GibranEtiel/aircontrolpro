from django.urls import path

from . import views

urlpatterns = [
    path('ordenes/', views.orden_lista, name='ordenes'),
    path('ordenes/nueva/', views.OrdenCreate.as_view(), name='orden_nueva'),
    path('ordenes/<int:pk>/', views.orden_detalle, name='orden_detalle'),
    path('ordenes/<int:pk>/editar/', views.OrdenUpdate.as_view(), name='orden_editar'),
    path('ordenes/<int:pk>/iniciar/', views.orden_iniciar, name='orden_iniciar'),
    path('ordenes/<int:pk>/pago/', views.orden_pago, name='orden_pago'),
    path('informes/', views.informe_lista, name='informes'),
    path('informes/nuevo/', views.informe_nuevo, name='informe_nuevo'),
    path('informes/mensual/', views.informe_mensual, name='informe_mensual'),
    path('informes/<int:pk>/', views.informe_detalle, name='informe_detalle'),
    path('equipos-informe/<int:pk>/pdf/', views.equipo_pdf, name='equipo_pdf'),
    path('informes/<int:pk>/pdf/', views.informe_pdf, name='informe_pdf'),
    path('informes/<int:pk>/excel/', views.informe_excel, name='informe_excel'),
    path('informes/<int:pk>/editar/', views.informe_editar, name='informe_editar'),
    path('informes/<int:pk>/foto/', views.foto_subir, name='foto_subir'),
    path('informes/<int:pk>/eliminar/', views.informe_eliminar, name='informe_eliminar'),
    path('informes/<int:pk>/emitir/', views.informe_emitir, name='informe_emitir'),
    path('informes/<int:pk>/devolver/', views.informe_devolver, name='informe_devolver'),
    path('fotos/<int:pk>/eliminar/', views.foto_eliminar, name='foto_eliminar'),
]
