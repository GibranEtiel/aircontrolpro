from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Rol(models.TextChoices):
        ADMIN = 'admin', 'Administrador'
        TECNICO = 'tecnico', 'Técnico'
        CLIENTE = 'cliente', 'Cliente'

    rol = models.CharField(max_length=10, choices=Rol.choices, default=Rol.CLIENTE)
    telefono = models.CharField(max_length=30, blank=True)
    cliente = models.ForeignKey(
        'catalogo.Cliente', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='usuarios', help_text='Solo para usuarios con rol Cliente.',
    )

    class Meta:
        ordering = ['first_name', 'last_name', 'username']

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.rol = self.Rol.ADMIN
        super().save(*args, **kwargs)

    @property
    def es_admin(self):
        return self.rol == self.Rol.ADMIN

    @property
    def es_tecnico(self):
        return self.rol == self.Rol.TECNICO

    @property
    def es_cliente(self):
        return self.rol == self.Rol.CLIENTE

    @property
    def nombre(self):
        return self.get_full_name() or self.username

    def __str__(self):
        return self.nombre
