#!/usr/bin/env python3
"""Where a book stands, and what comes next.

Usage:  python3 pipeline/status.py [book]

The book can be any of its names, even inside a longer phrase ("next premise ten premises").
Without a book, or when the words name none ("next"), the most recently worked-on book is shown.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import books, content_file, load_meta, pdf_pages, resolve_book, source_pdf  # noqa: E402


def main():
    book = resolve_book(' '.join(sys.argv[1:]), latest_if_unnamed=True)
    meta = load_meta(book)
    names = ' · '.join(x for x in (meta.get('title_tr'), meta.get('title_en')) if x)
    print(f'{book.name}{f" ({names})" if names else ""}, {pdf_pages(source_pdf(book))} PDF pages')
    if not meta:
        print('  book.json is missing: this book has not been set up yet (see pipeline/README.md)')
        return

    parts = {p: tuple(r) for p, r in sorted(meta.get('parts', {}).items())}
    sections = meta.get('sections', [])
    covered = lambda r: any(a <= r[0] and r[1] <= b for a, b in parts.values())  # noqa: E731

    print('\nParts:')
    for p, (a, b) in parts.items():
        docx = any((book / 'docx').glob(f'part-{p}_*.docx'))
        check = (book / f'CHECK-part-{p}.md').exists()
        state = 'done' if docx and check else 'in progress' if content_file(book, p).exists() else 'registered'
        names = '; '.join(s['name'] for s in sections if a <= s['pdf'][0] and s['pdf'][1] <= b)
        rng = f'{a}–{b}'
        print(f'  Part {p}  PDF {rng:<7} {state:<12} {names}')
    if not parts:
        print('  (none yet)')

    if not sections:
        print('\nNo sections in book.json yet: add them from the contents page to use "next".')
        return
    print('\nSections still to translate:')
    todo = [s for s in sections if not covered(s['pdf'])]
    for s in todo:
        print(f'  {s["name"]:<40} PDF {s["pdf"][0]}–{s["pdf"][1]}')
    if not todo:
        print(f'  none: every section is translated. Next step: the combined PDF, python3 pipeline/make_pdf.py "{book.name}" (RULES.md §6).')
        return
    nxt = int(max(parts, default='00')) + 1
    s = todo[0]
    print(f'\nNext: Part {nxt:02d} = {s["name"]}, PDF pages {s["pdf"][0]}–{s["pdf"][1]}')
    others = [b.name for b in books() if b != book]
    if others:
        print(f'Other books: {", ".join(others)}')


if __name__ == '__main__':
    main()
