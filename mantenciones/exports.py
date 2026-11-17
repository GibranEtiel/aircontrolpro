"""Informe técnico de mantenimiento de aire acondicionado (PDF y Excel).

Un mismo generador sirve para la ficha de un equipo, el informe de una orden de trabajo y el
informe general del mes: todos reciben una lista de `InformeEquipo` y arman el documento con el
formato del informe de Air Control Pro (un bloque por equipo con fotos y mediciones).
"""

import io
from decimal import Decimal
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from PIL import Image as PILImage
from PIL import ImageOps
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from core.exports import EMPRESA, Col, excel_response, fecha_larga, nombre_archivo

LOGO = settings.BASE_DIR / 'static' / 'img' / 'logo.png'
ROJO = '#d00000'
GRIS_LINEA = colors.HexColor('#7a7a7a')

_base = getSampleStyleSheet()
TXT = ParagraphStyle('inf_txt', parent=_base['Normal'], fontSize=10, leading=14)
TXT_C = ParagraphStyle('inf_txt_c', parent=TXT, alignment=1)
MARCA = ParagraphStyle('inf_marca', parent=TXT_C, fontSize=13, leading=17, spaceBefore=4, spaceAfter=8)
TITULO = ParagraphStyle('inf_titulo', parent=TXT_C, fontName='Helvetica-Bold', fontSize=10.5, spaceBefore=10,
                        spaceAfter=10)
EQUIPO = ParagraphStyle('inf_equipo', parent=TXT, fontName='Helvetica-Bold', fontSize=14, leading=18,
                        spaceBefore=6, spaceAfter=6)
ACTIV = ParagraphStyle('inf_activ', parent=TXT, leftIndent=12)
CAJA = ParagraphStyle('inf_caja', parent=TXT, fontSize=9.5)
PIE_FOTO = ParagraphStyle('inf_pie_foto', parent=TXT_C, fontSize=8, leading=9.5, textColor=colors.HexColor('#444444'))
BULLET = '<font name="ZapfDingbats" size="5">n</font>&nbsp;&nbsp;'  # cuadrito ▪ del informe original


def _p(texto_, estilo=TXT):
    return Paragraph(escape(str(texto_)), estilo)


def _foto(foto, caja_w, caja_h):
    """Foto reducida para el PDF (si no, 100 fotos de celular pesarían decenas de MB)."""
    try:
        img = ImageOps.exif_transpose(PILImage.open(foto.imagen.path))
        img.thumbnail((900, 900))
        buffer = io.BytesIO()
        img.convert('RGB').save(buffer, 'JPEG', quality=72)
        buffer.seek(0)
        w, h = img.size
    except (OSError, ValueError):
        return ''
    escala = min(caja_w / w, caja_h / h)
    return Image(buffer, width=w * escala, height=h * escala)


def _grilla_fotos(fotos, ancho):
    """Fotos en 2 columnas con celdas enmarcadas y el paso al pie de cada una (1 · Aplicación del líquido…)."""
    por_fila, alto, pie = 2, 58 * mm, 8 * mm
    celdas = []
    for f in fotos:
        imagen = _foto(f, ancho / por_fila - 4 * mm, alto - pie - 4 * mm)
        celdas.append([imagen, Paragraph(escape(f.titulo), PIE_FOTO)] if imagen != '' else
                      [Paragraph(escape(f.titulo), PIE_FOTO)])
    if not celdas:
        return _p('Sin fotografías.')
    while len(celdas) % por_fila:
        celdas.append('')
    filas = [celdas[i:i + por_fila] for i in range(0, len(celdas), por_fila)]
    t = Table(filas, colWidths=[ancho / por_fila] * por_fila, rowHeights=[alto] * len(filas))
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, GRIS_LINEA), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                           ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    return t


def _bloque_equipo(eq, ancho):
    a = eq.activo
    alerta, extra = eq.observaciones_informe
    if alerta:
        obs = f'<font color="{ROJO}">{escape(alerta)}</font>' + (f', {escape(extra)}' if extra else '')
    else:
        obs = escape(extra)
    lineas_obs = [Paragraph(f'{BULLET}Observaciones: ' + obs, TXT)] if (alerta or extra) else []
    texto_equipo = [
        Paragraph(escape(a.etiqueta), EQUIPO),
        Paragraph(f'{BULLET}Marca / Modelo: ' + escape(a.marca_modelo), TXT),
        Paragraph(f'{BULLET}Ubicación exacta: ' + escape(a.ubicacion_exacta or '-'), TXT),
        Paragraph(f'{BULLET}Tipo de mantenimiento: ' + escape(eq.get_tipo_mantenimiento_display()), TXT),
        Paragraph(f'{BULLET}Actividades realizadas:', TXT),
        *[Paragraph('- ' + escape(t), ACTIV) for t in eq.tareas_labels],
        *lineas_obs,
    ]
    # Como en el original: una página con los datos y otra con las fotos y mediciones.
    bloque = [KeepTogether(texto_equipo), PageBreak(), Paragraph('Fotografías del equipo:', TXT),
              Spacer(1, 2 * mm), _grilla_fotos(eq.fotos_ordenadas, ancho)]
    mediciones = eq.mediciones  # solo las que el técnico anotó
    if mediciones:
        medidas = Table([[n, v] for n, v in mediciones], colWidths=[ancho * .45, ancho * .37], hAlign='LEFT')
        medidas.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, GRIS_LINEA), ('FONTSIZE', (0, 0), (-1, -1), 9.5),
                                     ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        bloque += [Spacer(1, 4 * mm), KeepTogether([medidas])]
    return bloque


def _cabecera(equipos):
    """Datos del encabezado, reunidos a partir de las órdenes e informes de los equipos."""
    ordenes, vistos = [], set()
    for e in equipos:
        if e.informe.orden_id not in vistos:
            vistos.add(e.informe.orden_id)
            ordenes.append(e.informe.orden)

    def unicos(valores):
        return list(dict.fromkeys(v for v in valores if v))

    return {
        'ots': ', '.join(unicos(o.numero for o in ordenes)),
        'clientes': ', '.join(unicos(str(o.cliente) for o in ordenes)),
        'atencion': ', '.join(unicos((o.atencion or o.cliente.contacto) for o in ordenes)),
        'ubicaciones': ', '.join(unicos([o.ubicacion.nombre for o in ordenes]
                                        + [e.activo.ubicacion.nombre for e in equipos])),
        'tecnicos': ', '.join(unicos(str(e.informe.tecnico) for e in equipos if e.informe.tecnico)),
    }


def _firmas(equipos, cab, ancho):
    """Bloque final con las firmas: 'Recibe conforme' (con la firma del cliente si la dibujó en el celular) y el técnico
    responsable, con su línea para firmar. Como en la hoja del informe en pantalla."""
    informes = list({e.informe_id: e.informe for e in equipos}.values())
    informe = informes[0] if len(informes) == 1 else None  # la firma del cliente es de un informe concreto

    def imagen_firma(campo):
        archivo = getattr(informe, campo) if informe is not None else None
        if not archivo:
            return ''
        try:
            with PILImage.open(archivo.path) as im:
                w, h = im.size
            escala = min(55 * mm / w, 20 * mm / h)
            return Image(archivo.path, width=w * escala, height=h * escala)
        except (OSError, ValueError):
            return ''

    firma, firma_tecnico = imagen_firma('firma'), imagen_firma('firma_tecnico')
    recibe = 'Recibe conforme' + (f': {informe.recibido_por}' if informe is not None and informe.recibido_por else '')
    tecnico = f'Técnico: {cab["tecnicos"] or "-"}'
    t = Table([[firma, '', firma_tecnico], [Paragraph(escape(recibe), TXT_C), '', Paragraph(escape(tecnico), TXT_C)]],
              colWidths=[ancho * .42, ancho * .16, ancho * .42], rowHeights=[24 * mm, None])
    t.setStyle(TableStyle([('LINEABOVE', (0, 1), (0, 1), 0.7, colors.black),
                           ('LINEABOVE', (2, 1), (2, 1), 0.7, colors.black),
                           ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'), ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                           ('ALIGN', (2, 0), (2, 0), 'CENTER'),
                           ('VALIGN', (0, 1), (-1, 1), 'TOP')]))
    return KeepTogether([Spacer(1, 12 * mm), t])


def reporte_pdf(equipos, nombre, fecha_texto, generado_por):
    """PDF con el formato del informe técnico: encabezado y un bloque por equipo."""
    equipos = list(equipos)
    cab = _cabecera(equipos)
    ancho = A4[0] - 24 * mm
    generado = timezone.localtime()

    def pagina(canvas, doc):
        canvas.saveState()
        if LOGO.exists():
            canvas.drawImage(str(LOGO), 12 * mm, A4[1] - 31 * mm, width=36 * mm, height=36 * mm * 313 / 516,
                             mask='auto')
        canvas.setFont('Helvetica', 9)
        canvas.setFillColor(colors.black)
        canvas.drawRightString(A4[0] - 12 * mm, A4[1] - 14 * mm, f'N° DE OTS: {cab["ots"]}'[:70])
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawString(12 * mm, 7 * mm, f'{EMPRESA} · generado el {generado:%d/%m/%Y %H:%M}')
        canvas.drawRightString(A4[0] - 12 * mm, 7 * mm, f'Página {doc.page}')
        canvas.restoreState()

    caja = Table([[Paragraph(f'<b>EMITIDO POR</b>: {escape(generado_por)}', CAJA),
                   Paragraph(f'<b>RESPONSABLE TÉCNICO</b>: {escape(cab["tecnicos"] or "-")}', CAJA)]],
                 colWidths=[ancho * .45, ancho * .55], rowHeights=[13 * mm])
    caja.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.5, GRIS_LINEA), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))

    story = [
        Paragraph('AIRCONTROLPRO CLIMATIZACIÓN', MARCA), caja,
        Paragraph('INFORME TÉCNICO DE MANTENIMIENTO DE AIRE ACONDICIONADO', TITULO),
        _p(f'Fecha: {fecha_texto}'), _p(f'Cliente: {cab["clientes"]}'), _p(f'Dirigido a: {cab["atencion"] or "-"}'),
        _p(f'Ubicación: {cab["ubicaciones"]}'), Spacer(1, 4 * mm),
    ]
    for i, eq in enumerate(equipos):
        if i:
            story.append(PageBreak())
        story += _bloque_equipo(eq, ancho)
    if equipos:
        story.append(_firmas(equipos, cab, ancho))
    if not equipos:
        story.append(_p('No hay equipos intervenidos en este período.'))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=34 * mm,
                            bottomMargin=14 * mm, title=f'Informe técnico {cab["ots"]}', author=EMPRESA)
    doc.build(story, onFirstPage=pagina, onLaterPages=pagina)
    respuesta = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_archivo(nombre, "pdf")}"'
    return respuesta


def equipos_a_excel(nombre, titulo, equipos, fecha_texto, generado_por):
    equipos = list(equipos)
    cab = _cabecera(equipos)
    resumen = [
        ('N° de OTs', cab['ots']), ('Fecha', fecha_texto), ('Cliente', cab['clientes']),
        ('Dirigido a', cab['atencion']), ('Ubicación', cab['ubicaciones']), ('Emitido por', generado_por),
        ('Responsable técnico', cab['tecnicos']), ('Equipos intervenidos', len(equipos)),
        ('Equipos fuera de norma', sum(1 for e in equipos if e.fuera_de_norma)),
    ]
    filas = []
    for e in equipos:
        a = e.activo
        alerta, extra = e.observaciones_informe
        filas.append([
            a.numero_equipo or a.codigo, a.marca_modelo, a.ubicacion_exacta, e.get_tipo_mantenimiento_display(),
            '; '.join(e.tareas_labels), ' · '.join(x for x in (alerta, extra) if x), e.presion, e.consumo_total,
            e.consumo_ventilador, e.temp_inyeccion, e.get_modo_display(), e.informe.orden.numero,
            str(e.informe.tecnico or ''), e.fecha, e.fotos.count(), e.pendientes_texto or '—'])
    columnas = [Col('N° equipo'), Col('Marca / modelo'), Col('Ubicación exacta'), Col('Tipo de mantenimiento'),
                Col('Actividades realizadas'), Col('Observaciones'), Col('Presión (PSI)', 'num'),
                Col('Consumo total (A)', 'num'), Col('Consumo ventilador (A)', 'num'),
                Col('T° inyección (°C)', 'num'), Col('Modo'), Col('N° OT'), Col('Técnico'),
                Col('Fecha', 'fechahora'), Col('Fotos'), Col('Fotos pendientes')]
    return excel_response(nombre, [
        {'nombre': 'Resumen', 'titulo': titulo, 'subtitulo': f'Informe técnico de mantenimiento · {fecha_texto}',
         'columnas': [Col('Campo'), Col('Valor')], 'filas': [list(r) for r in resumen]},
        {'nombre': 'Equipos', 'titulo': titulo, 'subtitulo': f'{len(equipos)} equipo(s) intervenido(s)',
         'columnas': columnas, 'filas': filas},
    ])


# --- Atajos ----------------------------------------------------------------

def _fecha_informe(informe):
    return fecha_larga(timezone.localtime(informe.inicio).date())


def equipos_terminados(informe):
    return informe.equipos.filter(finalizado=True).select_related(
        'activo', 'activo__ubicacion', 'informe', 'informe__orden', 'informe__orden__cliente', 'informe__orden__ubicacion',
        'informe__tecnico').prefetch_related('fotos')


def informe_a_pdf(informe, generado_por):
    return reporte_pdf(equipos_terminados(informe), f'informe-{informe.numero}', _fecha_informe(informe),
                       generado_por)


def informe_a_excel(informe, generado_por):
    return equipos_a_excel(f'informe-{informe.numero}', f'Informe {informe.numero}', equipos_terminados(informe),
                           _fecha_informe(informe), generado_por)


def ficha_a_pdf(equipo, generado_por):
    return reporte_pdf([equipo], f'ficha-{equipo.activo.codigo}', fecha_larga(timezone.localtime(equipo.fecha).date()),
                       generado_por)
