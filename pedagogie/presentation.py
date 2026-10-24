"""Turn editor HTML into bounded reading pages shared by the reader and exports."""
from html import escape
import math
import re
import textwrap

from bs4 import BeautifulSoup, NavigableString
from .richtext import clean_content


def normalized_text(value):
    value = re.sub(r'_x000[dDaA]_', '\n', value or '')
    return value.replace('\r\n', '\n').replace('\r', '\n').replace('\xa0', ' ')


def content_blocks(value):
    soup = BeautifulSoup(clean_content(normalized_text(value)), 'html.parser')
    result = []
    containers = {'div', 'ul', 'ol', 'li', 'blockquote', 'section', 'article'}
    boundaries = containers | {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'img', 'pre', 'hr'}

    def text_block(parts, kind='paragraph', level=0):
        html = ''.join(str(p) if not isinstance(p, NavigableString) else escape(str(p)) for p in parts)
        fragment = BeautifulSoup(html, 'html.parser')
        for br in fragment.find_all('br'):
            br.replace_with('\n')
        text = normalized_text(fragment.get_text()).strip()
        # Ignore empty pasted paragraphs and decorative bullets, not course text.
        if not text or not text.strip(' \n\t·•'):
            return
        chunks = textwrap.wrap(text, width=650, break_long_words=True, replace_whitespace=False) if len(text) > 650 else [text]
        for chunk in chunks:
            rendered = html if len(chunks) == 1 else escape(chunk)
            result.append({'kind': kind, 'text': chunk, 'html': rendered, 'level': level,
                           'units': 3 if kind == 'heading' else max(1.5, math.ceil(len(chunk) / 82) * 1.15 + .7)})

    def walk(node, kind='paragraph'):
        pending = []

        def flush():
            if pending:
                text_block(pending, kind)
                pending.clear()

        for child in node.children:
            if isinstance(child, NavigableString):
                pending.append(child)
                continue
            tag = child.name
            if tag not in boundaries:
                # Inline wrappers can contain block HTML pasted from Word.
                if child.find(list(boundaries)):
                    flush()
                    walk(child, kind)
                else:
                    pending.append(child)
                continue
            flush()
            if tag == 'img':
                if child.get('src'):
                    result.append({'kind': 'image', 'src': child['src'], 'alt': child.get('alt', ''),
                                   'html': str(child), 'text': child.get('alt', ''), 'units': 10})
            elif tag == 'table':
                rows = []
                for row in child.find_all('tr'):
                    cells = [normalized_text(cell.get_text(' ', strip=True)) for cell in row.find_all(['td', 'th'], recursive=False)]
                    if cells:
                        rows.append(cells)
                # Bound wide tables and long cells while retaining every cell's text.
                for offset in range(0, len(rows), 5):
                    group = rows[offset:offset + 5]
                    rendered = '<table><tbody>' + ''.join('<tr>' + ''.join('<td>' + escape(cell) + '</td>' for cell in row) + '</tr>' for row in group) + '</tbody></table>'
                    result.append({'kind': 'table', 'rows': group, 'html': rendered,
                                   'text': '\n'.join(' | '.join(row) for row in group), 'units': min(14, 2 + len(group) * 2)})
            elif re.fullmatch(r'h[1-6]', tag):
                text_block(list(child.children), 'heading', int(tag[1]))
            elif tag == 'pre':
                text_block(list(child.children), 'code')
            elif tag == 'hr':
                continue
            else:
                walk(child, 'bullet' if tag == 'li' else 'paragraph' if tag == 'p' else kind)
        flush()

    walk(soup)
    return result


def reading_pages(value, capacity=22):
    pages, current, units = [], [], 0
    for block in content_blocks(value):
        if current and units + block['units'] > capacity:
            # Keep a heading with the following paragraph/image where possible.
            carry = current.pop() if current[-1]['kind'] == 'heading' and len(current) > 1 else None
            if current:
                pages.append(current)
            current = [carry] if carry else []
            units = carry['units'] if carry else 0
        current.append(block)
        units += block['units']
    if current:
        pages.append(current)
    return pages or [[]]
