from django.contrib import admin
from django.urls import include, path, re_path

from core.views import media_protegida

admin.site.site_header = 'Air Control Pro'
admin.site.site_title = 'Air Control Pro'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('', include('catalogo.urls')),
    path('', include('mantenciones.urls')),
    path('', include('cotizaciones.urls')),
    path('', include('core.urls')),
    # Fotos y firmas: solo con sesión y permiso sobre el informe (ver core.views.media_protegida).
    re_path(r'^media/(?P<path>.*)$', media_protegida, name='media'),
]
