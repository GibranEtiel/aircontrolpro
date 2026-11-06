from django.contrib import admin

from .models import Activo, Cliente, Ubicacion


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'rut', 'contacto', 'activo')
    search_fields = ('nombre', 'rut')


@admin.register(Ubicacion)
class UbicacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'cliente', 'ciudad', 'activa')
    list_filter = ('cliente',)
    search_fields = ('nombre', 'direccion')


@admin.register(Activo)
class ActivoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'ubicacion', 'tipo', 'estado', 'condicion')
    list_filter = ('tipo', 'estado', 'condicion', 'ubicacion__cliente')
    search_fields = ('codigo', 'nombre', 'marca', 'modelo', 'numero_serie')
