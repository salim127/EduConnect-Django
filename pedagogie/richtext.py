"""Restricted formatting for course content, including pasted HTML."""
import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit


class CourseHTML(HTMLParser):
    tags = {'p', 'div', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li', 'blockquote', 'span', 'font', 'a', 'img', 'table', 'thead', 'tbody', 'tfoot',
            'tr', 'td', 'th', 'caption', 'colgroup', 'col', 'hr', 'pre', 'code', 'sub', 'sup', 'del', 'ins', 'address'}
    void_tags = {'br', 'hr', 'img', 'col'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.tags:
            return
        attrs = dict(attrs)
        styles = []
        for key, value in (part.split(':', 1) for part in attrs.get('style', '').split(';') if ':' in part):
            key, value = key.strip().lower(), value.strip()
            rules = {
                'color': r'#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,20}|rgba?\([0-9.,% ]+\)',
                'background-color': r'#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,20}|rgba?\([0-9.,% ]+\)',
                'text-align': r'left|right|center|justify',
                'font-family': r"[a-zA-Z0-9 ,\-'\"]{1,150}",
                'font-size': r'[0-9.]{1,6}(?:px|pt|em|rem|%)',
                'font-weight': r'normal|bold|[1-9]00',
                'font-style': r'normal|italic',
                'text-decoration': r'(?:none|underline|line-through|overline)(?: (?:underline|line-through|overline))*',
                'line-height': r'[0-9.]{1,6}(?:px|pt|em|rem|%)?',
                'border-collapse': r'collapse|separate',
                'border-style': r'none|solid|dashed|dotted|double',
                'vertical-align': r'top|middle|bottom|baseline',
                'list-style-type': r'disc|circle|square|decimal|lower-alpha|upper-alpha|lower-roman|upper-roman',
                'float': r'left|right|none',
            }
            for dimension in ('width', 'height', 'max-width', 'min-width', 'padding', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom', 'margin-left', 'margin-right', 'border-width'):
                rules[dimension] = r'(?:[0-9.]{1,6}(?:px|pt|em|rem|%)|auto)'
            if key in rules and re.fullmatch(rules[key], value):
                styles.append(key.strip().lower() + ':' + value.strip())
        color = attrs.get('color', '')
        if tag == 'font' and re.fullmatch(r'#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,20}', color):
            styles.append('color:' + color)
        style = ' style="' + escape(';'.join(styles), quote=True) + '"' if styles else ''
        safe_attrs = []
        for name in ('title', 'alt'):
            if name in attrs:
                safe_attrs.append(f'{name}="{escape(attrs[name] or "", quote=True)}"')
        for name in ('colspan', 'rowspan', 'width', 'height', 'start', 'span', 'border', 'cellpadding', 'cellspacing'):
            if re.fullmatch(r'[0-9]{1,4}%?', attrs.get(name, '')):
                safe_attrs.append(f'{name}="{attrs[name]}"')
        if attrs.get('dir') in ('ltr', 'rtl'):
            safe_attrs.append(f'dir="{attrs["dir"]}"')
        url_attr = 'href' if tag == 'a' else 'src' if tag == 'img' else None
        if url_attr and attrs.get(url_attr):
            url = attrs[url_attr].strip()
            try:
                scheme = urlsplit(url).scheme.lower()
                valid = scheme in ('http', 'https') or (tag == 'a' and scheme == 'mailto') or not scheme
                valid = valid and not re.search(r'[\x00-\x20\x7f]', url) and not url.startswith('\\')
            except ValueError:
                valid = False
            if valid:
                safe_attrs.append(f'{url_attr}="{escape(url, quote=True)}"')
        if tag == 'a':
            safe_attrs.append('rel="noopener noreferrer"')
        extra = (' ' + ' '.join(safe_attrs)) if safe_attrs else ''
        self.parts.append('<' + tag + style + extra + '>')

    def handle_endtag(self, tag):
        if tag in self.tags and tag not in self.void_tags:
            self.parts.append('</' + tag + '>')

    def handle_data(self, data):
        self.parts.append(escape(data))


def clean_content(value):
    parser = CourseHTML()
    parser.feed(value or '')
    parser.close()
    return ''.join(parser.parts)
