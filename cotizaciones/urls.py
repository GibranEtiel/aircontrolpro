from django.urls import path

from . import views

urlpatterns = [
    path('cotizaciones/', views.cotizacion_lista, name='cotizaciones'),
    path('cotizaciones/nueva/', views.cotizacion_nueva, name='cotizacion_nueva'),
    path('cotizaciones/<int:pk>/', views.cotizacion_detalle, name='cotizacion_detalle'),
    path('cotizaciones/<int:pk>/editar/', views.cotizacion_editar, name='cotizacion_editar'),
    path('cotizaciones/<int:pk>/pdf/', views.cotizacion_pdf, name='cotizacion_pdf'),
    path('cotizaciones/<int:pk>/seguimiento/', views.seguimiento_agregar, name='seguimiento_agregar'),
    path('cotizaciones/<int:pk>/estado/', views.cotizacion_estado, name='cotizacion_estado'),
]
