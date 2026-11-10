from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/datos/', views.dashboard_datos, name='dashboard_datos'),
    path('finanzas/', views.finanzas, name='finanzas'),
]
