#!/usr/bin/env python3
"""Assemble the public GitHub Pages site from the generated reports.

    python scripts/build_site.py [--out site]

Only these reports are published. Everything else in the repo stays out of
the site, even though the repo itself is public.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / 'reports'
# (source report, page file, menu label)
PAGES = (
    ('latest.md', 'index.md', 'Daily brief'),
    ('calibration.md', 'calibration.md', 'Is it right? (backtest)'),
    ('prediction-log.md', 'prediction-log.md', 'Live prediction log'),
    ('catalog-comparison.md', 'catalog-comparison.md', 'Hand-picked vs UCDP list'),
)
REPO = 'https://github.com/Kaiju77/huginn-muninn'
FOOTER = ('_Huginn & Muninn reports what prices did after comparable past events, with n, '
          f'a 95% CI, a range and a normal-period baseline. Not a forecast or advice. [Source code]({REPO})._')


def menu(current):
    def link(page, label):
        if page == current:
            return f'**{label}**'
        return f'[{label}](./)' if page == 'index.md' else f'[{label}]({page[:-3]}.html)'
    return ' · '.join(link(page, label) for _, page, label in PAGES)


def no_liquid(body):
    """The report as literal text for Liquid: nothing in it is run as a tag."""
    body = re.sub(r'\{%-?\s*endraw\s*-?%\}', '', body)
    return '{% raw %}\n' + body + '\n{% endraw %}'


def build(out, reports=REPORTS):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / '_config.yml').write_text('title: Huginn & Muninn\ntheme: jekyll-theme-minimal\n',
                                     encoding='utf-8')
    written = []
    for src, page, _ in PAGES:
        path = Path(reports) / src
        body = path.read_text(encoding='utf-8') if path.exists() else '# Not generated yet\n'
        text = f'{menu(page)}\n\n{no_liquid(body.rstrip())}\n\n---\n\n{FOOTER}\n'
        (out / page).write_text(text, encoding='utf-8')
        written.append(page)
    return written


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--out', default=str(ROOT / 'site'))
    a = p.parse_args(argv)
    print('\n'.join(build(a.out)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
