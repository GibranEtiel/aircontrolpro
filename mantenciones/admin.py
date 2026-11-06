from django.contrib import admin

from .models import FotoInforme, Informe, InformeEquipo, OrdenTrabajo


@admin.register(OrdenTrabajo)
class OrdenTrabajoAdmin(admin.ModelAdmin):
    list_display = ('numero', 'titulo', 'cliente', 'tipo', 'estado', 'tecnico', 'fecha_programada',
                    'monto_neto', 'estado_pago')
    list_filter = ('estado', 'tipo', 'estado_pago', 'cliente')
    search_fields = ('numero', 'titulo')
    filter_horizontal = ('activos',)


class InformeEquipoInline(admin.TabularInline):
    model = InformeEquipo
    extra = 0


@admin.register(Informe)
class InformeAdmin(admin.ModelAdmin):
    list_display = ('numero', 'orden', 'tecnico', 'estado', 'inicio', 'termino')
    list_filter = ('estado',)
    inlines = [InformeEquipoInline]


@admin.register(FotoInforme)
class FotoInformeAdmin(admin.ModelAdmin):
    list_display = ('id', 'informe', 'etapa', 'latitud', 'longitud', 'tomada_en')
