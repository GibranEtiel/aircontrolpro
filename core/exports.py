"""Exportación a Excel (.xlsx) y PDF compartida por todas las pantallas.

Las vistas arman columnas y filas con valores crudos (fechas, Decimal, texto) y
este módulo se encarga del formato: pesos chilenos, fechas dd/mm/aaaa, etc.
"""

import io
from collections import namedtuple
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
EMPRESA = 'Air Control Pro'
AZUL = colors.HexColor('#075f91')
GRIS = colors.HexColor('#f1f4f9')

# fmt: 'txt' | 'clp' | 'num' | 'fecha' | 'fechahora' | 'pct'
Col = namedtuple('Col', 'titulo fmt', defaults=('txt',))

ANCHO_VERTICAL = A4[0] - 24 * mm
ANCHO_HORIZONTAL = landscape(A4)[0] - 24 * mm


MESES_ES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre',
            'Octubre', 'Noviembre', 'Diciembre']


def fecha_larga(d):
    """28 SEPTIEMBRE 2026, como se escribe en los informes."""
    return f'{d.day} {MESES_ES[d.month - 1].upper()} {d.year}'


def formato_export(request):
    """'pdf', 'xlsx' o None según el parámetro ?export= de la URL."""
    valor = request.GET.get('export')
    return valor if valor in ('pdf', 'xlsx') else None


def resolver(objeto, ruta):
    """Valor crudo de 'cliente.nombre' o 'get_tipo_display' sobre un objeto (None si falta)."""
    valor = objeto
    for parte in ruta.split('.'):
        valor = getattr(valor, parte, None)
        if callable(valor):
            valor = valor()
        if valor is None:
            return None
    return valor


def nombre_archivo(nombre, extension):
    return f'{slugify(nombre)}-{timezone.localdate():%Y%m%d}.{extension}'


def _local(valor):
    return timezone.localtime(valor) if timezone.is_aware(valor) else valor


# --- Formato de texto (PDF) ------------------------------------------------

def texto(valor, fmt='txt'):
    if valor is None or valor == '':
        return '—'
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    if fmt == 'clp':
        return '$' + f'{int(round(float(valor))):,}'.replace(',', '.')
    if fmt == 'pct':
        return f'{float(valor):.1f}%'.replace('.', ',')
    if isinstance(valor, datetime):
        return _local(valor).strftime('%d/%m/%Y %H:%M')
    if isinstance(valor, date):
        return valor.strftime('%d/%m/%Y')
    if isinstance(valor, (Decimal, float)):
        return f'{valor:.1f}'.replace('.', ',')
    return str(valor)


# --- Excel -----------------------------------------------------------------

def _valor_excel(valor):
    if valor is None:
        return ''
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    if isinstance(valor, datetime):
        return _local(valor).replace(tzinfo=None)
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (str, int, float, date)):
        return valor
    return str(valor)  # p. ej. un cliente o ubicación (instancia de modelo)


FORMATOS_EXCEL = {'clp': '"$"#,##0', 'fecha': 'DD/MM/YYYY', 'fechahora': 'DD/MM/YYYY HH:MM',
                  'num': '#,##0.0', 'pct': '0.0"%"'}


def excel_response(nombre, hojas):
    """hojas: [{'nombre', 'titulo', 'subtitulo', 'columnas': [Col], 'filas': [[..]], 'totales': [..]}]"""
    libro = Workbook()
    libro.remove(libro.active)
    relleno = PatternFill('solid', fgColor='075F91')
    for hoja in hojas:
        ws = libro.create_sheet(hoja['nombre'][:31])
        columnas = hoja['columnas']
        ws.append([f"{EMPRESA} · {hoja.get('titulo', hoja['nombre'])}"])
        ws['A1'].font = Font(bold=True, size=14)
        ws.append([hoja.get('subtitulo') or f'Generado el {timezone.localtime():%d/%m/%Y %H:%M}'])
        ws['A2'].font = Font(italic=True, color='666666')
        ws.append([])
        ws.append([c.titulo for c in columnas])
        for celda in ws[4]:
            celda.font = Font(bold=True, color='FFFFFF')
            celda.fill = relleno
            celda.alignment = Alignment(vertical='center', wrap_text=True)

        filas = list(hoja['filas'])
        if hoja.get('totales'):
            filas.append(hoja['totales'])
        for n, fila in enumerate(filas):
            ws.append([_valor_excel(v) for v in fila])
            es_total = hoja.get('totales') and n == len(filas) - 1
            for celda, col in zip(ws[ws.max_row], columnas):
                if col.fmt in FORMATOS_EXCEL and celda.value != '':
                    celda.number_format = FORMATOS_EXCEL[col.fmt]
                    celda.alignment = Alignment(horizontal='right')
                if es_total:
                    celda.font = Font(bold=True)

        for i, col in enumerate(columnas, start=1):
            largo = max([len(col.titulo)] + [len(str(texto(f[i - 1], col.fmt))) for f in filas[:200]] or [8])
            ws.column_dimensions[get_column_letter(i)].width = min(max(largo + 2, 10), 55)
        ws.freeze_panes = 'A5'
        if len(filas) > 1:
            ws.auto_filter.ref = f'A4:{get_column_letter(len(columnas))}{4 + len(filas)}'

    buffer = io.BytesIO()
    libro.save(buffer)
    respuesta = HttpResponse(buffer.getvalue(), content_type=XLSX_MIME)
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_archivo(nombre, "xlsx")}"'
    return respuesta


# --- PDF -------------------------------------------------------------------

_base = getSampleStyleSheet()
ESTILO_TITULO = ParagraphStyle('titulo', parent=_base['Title'], fontSize=16, alignment=0, textColor=AZUL,
                               spaceAfter=2)
ESTILO_SUB = ParagraphStyle('sub', parent=_base['Normal'], fontSize=8.5, textColor=colors.grey, spaceAfter=8)
ESTILO_H = ParagraphStyle('h', parent=_base['Heading3'], fontSize=11, textColor=AZUL, spaceBefore=8,
                          spaceAfter=4)
ESTILO_TXT = ParagraphStyle('txt', parent=_base['Normal'], fontSize=9, leading=12)
ESTILO_CELDA = ParagraphStyle('celda', parent=_base['Normal'], fontSize=7.5, leading=9)
ESTILO_CELDA_D = ParagraphStyle('celda_d', parent=ESTILO_CELDA, alignment=2)
ESTILO_CELDA_H = ParagraphStyle('celda_h', parent=ESTILO_CELDA, textColor=colors.white,
                                fontName='Helvetica-Bold')
ESTILO_CELDA_HD = ParagraphStyle('celda_hd', parent=ESTILO_CELDA_H, alignment=2)


def p(valor, estilo=ESTILO_TXT):
    """Párrafo seguro: escapa el texto del usuario y respeta los saltos de línea."""
    return Paragraph(escape(str(valor if valor not in (None, '') else '—')).replace('\n', '<br/>'), estilo)


def titulo(textos, nivel=ESTILO_H):
    return Paragraph(escape(textos), nivel)


def tabla(columnas, filas, ancho, totales=None):
    """Tabla con encabezado repetido, columnas proporcionales al contenido y números a la derecha."""
    numerica = [c.fmt in ('clp', 'num', 'pct') for c in columnas]
    datos = [[Paragraph(escape(c.titulo), ESTILO_CELDA_HD if num else ESTILO_CELDA_H)
              for c, num in zip(columnas, numerica)]]
    textos = [[texto(v, c.fmt) for v, c in zip(f, columnas)] for f in filas]
    if totales:
        textos.append([texto(v, c.fmt) for v, c in zip(totales, columnas)])
    for fila in textos:
        datos.append([Paragraph(escape(t), ESTILO_CELDA_D if num else ESTILO_CELDA)
                      for t, num in zip(fila, numerica)])

    # Montos, fechas, números y textos cortos no se parten: reciben su ancho justo; el resto reparte el espacio.
    relleno = 10
    anchos, pesos = {}, {}
    for i, c in enumerate(columnas):
        largo = max([len(t[i]) for t in textos[:100]] or [1])
        if c.fmt != 'txt' or largo <= 14:
            palabra = max((len(w) for w in c.titulo.split()), default=1)
            anchos[i] = max(largo * 4.3, palabra * 4.9) + relleno
        else:
            pesos[i] = min(max(largo, len(c.titulo), 6), 38)
    sobrante = max(ancho - sum(anchos.values()), 40 * len(pesos))
    total_pesos = sum(pesos.values()) or 1
    for i, peso in pesos.items():
        anchos[i] = sobrante * peso / total_pesos
    escala = ancho / sum(anchos.values())
    anchos = [anchos[i] * escala for i in range(len(columnas))]
    estilo = [
        ('BACKGROUND', (0, 0), (-1, 0), AZUL),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRIS]),
        ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#d5dbe6')),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    if totales:
        estilo += [('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dfe7f2')),
                   ('LINEABOVE', (0, -1), (-1, -1), 0.8, AZUL)]
    t = Table(datos, colWidths=anchos, repeatRows=1)
    t.setStyle(TableStyle(estilo))
    return t


def grafico_barras(etiquetas, series, ancho, alto=170):
    """Gráfico de barras agrupadas: series = [(nombre, [valores], color_hex)]."""
    d = Drawing(ancho, alto)
    g = VerticalBarChart()
    g.x, g.y, g.width, g.height = 50, 28, ancho - 70, alto - 55
    g.data = [s[1] for s in series]
    g.categoryAxis.categoryNames = etiquetas
    g.categoryAxis.labels.fontSize = 7
    g.valueAxis.labels.fontSize = 7
    g.valueAxis.labelTextFormat = lambda v: '$' + f'{int(v):,}'.replace(',', '.')
    g.valueAxis.valueMin = 0
    g.groupSpacing = 6
    for i, s in enumerate(series):
        g.bars[i].fillColor = colors.HexColor(s[2])
        g.bars[i].strokeColor = None
    leyenda = Legend()
    leyenda.x, leyenda.y, leyenda.fontSize = ancho / 2 - 80, alto - 4, 8
    leyenda.alignment = 'right'
    leyenda.columnMaximum = 1
    leyenda.deltax = 70
    leyenda.colorNamePairs = [(colors.HexColor(s[2]), s[0]) for s in series]
    d.add(g)
    d.add(leyenda)
    return d


def pdf_response(nombre, titulo_doc, subtitulo, story, horizontal=False):
    buffer = io.BytesIO()
    pagina = landscape(A4) if horizontal else A4
    generado = timezone.localtime()

    def pie(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawString(12 * mm, 7 * mm, f'{EMPRESA} · generado el {generado:%d/%m/%Y %H:%M}')
        canvas.drawRightString(pagina[0] - 12 * mm, 7 * mm, f'Página {doc.page}')
        canvas.setStrokeColor(AZUL)
        canvas.setLineWidth(1.5)
        canvas.line(12 * mm, pagina[1] - 9 * mm, pagina[0] - 12 * mm, pagina[1] - 9 * mm)
        canvas.setFont('Helvetica-Bold', 8)
        canvas.setFillColor(AZUL)
        canvas.drawString(12 * mm, pagina[1] - 7 * mm, EMPRESA.upper())
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=pagina, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=15 * mm, bottomMargin=14 * mm, title=f'{EMPRESA} - {titulo_doc}',
                            author=EMPRESA)
    encabezado = [Paragraph(escape(titulo_doc), ESTILO_TITULO), Paragraph(escape(subtitulo or ''), ESTILO_SUB)]
    doc.build(encabezado + list(story), onFirstPage=pie, onLaterPages=pie)
    respuesta = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_archivo(nombre, "pdf")}"'
    return respuesta


# --- Atajo para listados simples --------------------------------------------

def exportar_tabla(formato, nombre, titulo_doc, columnas, filas, subtitulo='', totales=None):
    """Devuelve la respuesta PDF/Excel de un listado de una sola tabla."""
    if formato == 'xlsx':
        return excel_response(nombre, [{'nombre': titulo_doc, 'titulo': titulo_doc, 'subtitulo': subtitulo,
                                        'columnas': columnas, 'filas': filas, 'totales': totales}])
    horizontal = len(columnas) > 5
    ancho = ANCHO_HORIZONTAL if horizontal else ANCHO_VERTICAL
    sub = subtitulo or f'{len(filas)} registro(s)'
    return pdf_response(nombre, titulo_doc, sub, [tabla(columnas, filas, ancho, totales)], horizontal)
