from django.db import migrations, models


def marcar_r22(apps, schema_editor):
    """Los informes que ya existían conservan lo que decían: fuera de norma si el refrigerante era R-22."""
    InformeEquipo = apps.get_model('mantenciones', 'InformeEquipo')
    for eq in InformeEquipo.objects.select_related('activo'):
        if eq.activo.refrigerante.upper().replace('-', '').replace(' ', '') == 'R22':
            eq.fuera_de_norma = True
            eq.save(update_fields=['fuera_de_norma'])


class Migration(migrations.Migration):

    dependencies = [
        ('mantenciones', '0005_foto_paso'),
    ]

    operations = [
        migrations.AddField(
            model_name='informeequipo',
            name='fuera_de_norma',
            field=models.BooleanField(
                default=False, help_text='Lo decide el técnico en cada informe. Parte marcado si el refrigerante '
                                         'del equipo es R-22.', verbose_name='Equipo fuera de norma'),
        ),
        migrations.RunPython(marcar_r22, migrations.RunPython.noop),
    ]
