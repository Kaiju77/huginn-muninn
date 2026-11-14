"""Escaping for untrusted text (headlines, model output, catalog titles) that is
written into markdown reports. The reports are shown on GitHub and published
through Jekyll (kramdown + Liquid), so raw HTML, kramdown attribute lists
(``{: ...}``) and Liquid tags (``{{ }}``, ``{% %}``) must all be neutralised."""

import re

_ENTITIES = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '{': '&#123;', '}': '&#125;',
             '|': '&#124;', '%': '&#37;'}


def md(text):
    """One line of plain text, safe inside a link label, a list item or a table cell."""
    text = re.sub(r'\s+', ' ', str(text)).strip()
    text = text.replace('[', '(').replace(']', ')').replace('`', "'").replace('\\', '/')
    return ''.join(_ENTITIES.get(c, c) for c in text)


def url(text):
    """An http(s) link target, or '' for anything else."""
    text = str(text).strip()
    if not re.match(r'https?://', text):
        return ''
    return re.sub(r'[^A-Za-z0-9\-._~:/?#@!$&\'*+,;=%]',
                  lambda m: ''.join(f'%{b:02X}' for b in m.group().encode('utf-8')), text)
