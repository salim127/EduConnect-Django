"""Natural-flow PDF fallback for hosts without a Chromium browser."""
from html import escape
from io import BytesIO
import re

from bs4 import NavigableString
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, Preformatted

from .document_export import rich_blocks, points, css
from . import export_layout as assets


def inline(node):
    if isinstance(node, NavigableString):
        return escape(re.sub(r'\s+', ' ', str(node)))
    if node.name == 'br':
        return '<br/>'
    value = ''.join(inline(child) for child in node.children)
    if node.name in ('b', 'strong', 'em', 'i', 'u', 'sub', 'sup'):
        tag = {'strong': 'b', 'em': 'i'}.get(node.name, node.name)
        value = f'<{tag}>{value}</{tag}>'
    properties = css(node)
    font = []
    size = points(properties.get('font-size'))
    if size:
        font.append(f'size="{min(size, 96)}"')
    color = properties.get('color', node.get('color', ''))
    if re.fullmatch(r'#[0-9a-fA-F]{6}|[a-zA-Z]{1,20}', color):
        try:
            colors.toColor(color)
            font.append(f'color="{color}"')
        except ValueError:
            pass
    if font:
        value = '<font ' + ' '.join(font) + '>' + value + '</font>'
    return value


def pdf_document(course, output):
    normal = ParagraphStyle('Normal', fontName='Helvetica', fontSize=12, leading=20.4, spaceAfter=12)
    heading = ParagraphStyle('Heading', parent=normal, fontName='Helvetica-Bold', fontSize=19, leading=24,
                             spaceBefore=12, spaceAfter=8, keepWithNext=True, textColor=colors.HexColor('#493b96'))
    story = [Paragraph(escape(course.titre), heading)]
    if course.description.strip():
        story.append(Paragraph(escape(course.description), normal))
    for title, content in [('Introduction', course.contenu)] + [(c['titre'], c['contenu']) for c in course.chapitres]:
        story.append(Paragraph(escape(title), heading))
        for kind, node, prefix, properties in rich_blocks(content):
            if kind == 'img':
                raw = assets.image_data(node.get('src', ''))
                if raw:
                    width, height = assets.fit_image(raw, 480, 600)
                    story.append(Image(BytesIO(raw), width=width, height=height))
                    story.append(Spacer(1, 8))
                elif node.get('alt'):
                    story.append(Paragraph(escape(node['alt']), normal))
            elif kind == 'table':
                rows = [[Paragraph(''.join(inline(child) for child in cell.children), normal) for cell in row.find_all(['td', 'th'], recursive=False)] for row in node.find_all('tr')]
                columns = max((len(row) for row in rows), default=0)
                if not columns:
                    continue
                table = Table([row + [''] * (columns - len(row)) for row in rows], colWidths=[480 / columns] * columns)
                table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), .5, colors.HexColor('#dcd8ed')), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('PADDING', (0, 0), (-1, -1), 6)]))
                story.extend([table, Spacer(1, 8)])
            elif kind == 'pre':
                story.append(Preformatted(node.get_text(), ParagraphStyle('Code', parent=normal, fontName='Courier', fontSize=10, leading=13), maxLineLength=80))
            else:
                base = heading if re.fullmatch(r'h[1-6]', kind) else normal
                size = points(properties.get('font-size')) or base.fontSize
                line = properties.get('line-height', '')
                leading = size * float(line) if re.fullmatch(r'[0-9.]+', line) else points(line) or size * 1.4
                style = ParagraphStyle('Content', parent=base, fontSize=size, leading=leading,
                    alignment={'left': TA_LEFT, 'center': TA_CENTER, 'right': TA_RIGHT, 'justify': TA_JUSTIFY}.get(properties.get('text-align'), TA_LEFT))
                markup = (escape(prefix) + ' ' if prefix else '') + ''.join(inline(child) for child in node.children)
                story.append(Paragraph(markup, style) if markup.strip() else Spacer(1, 8))
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=54, leftMargin=54, topMargin=50, bottomMargin=50, title=course.titre)
    document.build(story)
