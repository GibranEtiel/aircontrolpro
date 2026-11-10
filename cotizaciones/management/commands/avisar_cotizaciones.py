"""Envía por correo las cotizaciones pendientes que hay que llamar. Pensado para un cron diario en cPanel.

    python manage.py avisar_cotizaciones            # envía el aviso
    python manage.py avisar_cotizaciones --dry-run  # solo muestra el texto
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from accounts.models import User
from cotizaciones.models import Cotizacion


def _linea(c):
    partes = [f'• {c.numero} · {c.cliente.nombre} — {c.titulo}',
              f'  Neto ${int(c.neto):,}'.replace(',', '.') + f' · enviada el {c.fecha:%d/%m/%Y} '
              f'({c.dias_desde_envio} días)' + (f' · último seguimiento {c.ultimo_contacto:%d/%m/%Y}'
                                                  if c.ultimo_contacto else '')]
    contacto = ' · '.join(x for x in (c.contacto, c.telefono, c.email) if x)
    partes.append(f'  Llamar a: {contacto or "sin datos de contacto"}')
    return '\n'.join(partes)


class Command(BaseCommand):
    help = 'Avisa por correo de las cotizaciones pendientes que superan los días de alerta.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Muestra el aviso sin enviarlo.')

    def handle(self, *args, **options):
        cotizaciones = list(Cotizacion.objects.por_llamar().select_related('cliente').prefetch_related('items')
                            .order_by('fecha'))
        if not cotizaciones:
            self.stdout.write('No hay cotizaciones por llamar.')
            return
        dias = settings.COTIZACION_DIAS_ALERTA
        cuerpo = (f'Hay {len(cotizaciones)} cotización(es) pendientes hace más de {dias} días sin respuesta.\n'
                  'Llámalas y registra el seguimiento en el portal para sacarlas de esta lista:\n\n'
                  + '\n\n'.join(_linea(c) for c in cotizaciones))
        asunto = f'Air Control Pro: {len(cotizaciones)} cotización(es) por llamar'
        if options['dry_run']:
            self.stdout.write(f'{asunto}\n\n{cuerpo}')
            return
        destinatarios = settings.AVISOS_EMAIL or list(
            User.objects.filter(rol=User.Rol.ADMIN, is_active=True).exclude(email='')
            .values_list('email', flat=True))
        if not destinatarios:
            self.stderr.write('Sin destinatarios: define AVISOS_EMAIL o el correo de un usuario administrador.')
            return
        send_mail(asunto, cuerpo, settings.DEFAULT_FROM_EMAIL, destinatarios)
        self.stdout.write(self.style.SUCCESS(f'Aviso enviado a {", ".join(destinatarios)}.'))
