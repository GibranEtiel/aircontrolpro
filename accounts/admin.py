from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AirControlUserAdmin(UserAdmin):
    list_display = ('username', 'nombre', 'email', 'rol', 'cliente', 'is_active')
    list_filter = ('rol', 'is_active')
    fieldsets = UserAdmin.fieldsets + (('Air Control Pro', {'fields': ('rol', 'telefono', 'cliente')}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('Air Control Pro', {'fields': ('rol', 'telefono', 'cliente')}),)
