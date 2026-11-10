from django.contrib import admin

from .models import Cotizacion, CotizacionItem, Seguimiento


class ItemInline(admin.TabularInline):
    model = CotizacionItem
    extra = 0


class SeguimientoInline(admin.TabularInline):
    model = Seguimiento
    extra = 0


@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = ('numero', 'cliente', 'titulo', 'estado', 'fecha')
    list_filter = ('estado',)
    search_fields = ('numero', 'titulo', 'cliente__nombre')
    inlines = [ItemInline, SeguimientoInline]
