#!/usr/bin/env python3
"""Where a book stands, and what comes next.

Usage:  python3 pipeline/status.py [book] [--next]

The book can be any of its names, even inside a longer phrase ("next premise ten premises").
Without a book, or when the words name none ("next"), the most recently worked-on book is shown.

"Next" is the first planned part (book.json "parts", made by plan.py) that is not done yet: whole
sections, never a split one. --next prints only that, for scripts: "NN A B" (part, PDF range),
"DONE" when every part is done, or "NOPLAN" when sections are left that no part covers.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import books, content_file, load_meta, pdf_pages, resolve_book, source_pdf  # noqa: E402


def state(book, part):
    docx = any((book / 'docx').glob(f'part-{part}_*.docx'))
    check = (book / f'CHECK-part-{part}.md').exists()
    return 'done' if docx and check else 'in progress' if content_file(book, part).exists() else 'planned'


def main():
    args = [a for a in sys.argv[1:] if a != '--next']
    book = resolve_book(' '.join(args), latest_if_unnamed=True)
    meta = load_meta(book)
    parts = {p: tuple(r) for p, r in sorted(meta.get('parts', {}).items(), key=lambda x: x[1][0])}
    sections = meta.get('sections', [])
    covered = lambda r: any(a <= r[0] and r[1] <= b for a, b in parts.values())  # noqa: E731
    open_parts = [p for p in parts if state(book, p) != 'done']
    uncovered = [s for s in sections if not covered(s['pdf'])]
    if '--next' in sys.argv[1:]:
        print(f'{open_parts[0]} {parts[open_parts[0]][0]} {parts[open_parts[0]][1]}' if open_parts
              else 'NOPLAN' if uncovered or not sections else 'DONE')
        return
    names = ' · '.join(x for x in (meta.get('title_tr'), meta.get('title_en')) if x)
    print(f'{book.name}{f" ({names})" if names else ""}, {pdf_pages(source_pdf(book))} PDF pages')
    if not meta:
        print('  book.json is missing: this book has not been set up yet (see pipeline/README.md)')
        return

    print('\nParts:')
    for p, (a, b) in parts.items():
        names = '; '.join(s['name'] for s in sections if a <= s['pdf'][0] and s['pdf'][1] <= b)
        rng = f'{a}–{b}'
        print(f'  Part {p}  PDF {rng:<9} {state(book, p):<12} {names}')
    if not parts:
        print('  (none yet)')

    if not sections:
        print('\nNo sections in book.json yet: add them from the contents page to use "next".')
        return
    if uncovered:
        print('\nSections in no part yet:')
        for s in uncovered:
            print(f'  {s["name"]:<40} PDF {s["pdf"][0]}–{s["pdf"][1]}')
    if open_parts:
        p = open_parts[0]
        a, b = parts[p]
        names = ' + '.join(s['name'] for s in sections if a <= s['pdf'][0] and s['pdf'][1] <= b)
        print(f'\nNext: Part {p} = {names}, PDF pages {a}–{b} ({b - a + 1} pages; {state(book, p)})')
    elif uncovered:
        print(f'\nNext: plan the parts first, python3 pipeline/plan.py "{book.name}"')
    else:
        print(f'\nEvery part is done. Next step: the combined PDF, python3 pipeline/make_pdf.py "{book.name}" (RULES.md §6).')
    others = [b.name for b in books() if b != book]
    if others:
        print(f'Other books: {", ".join(others)}')


if __name__ == '__main__':
    main()
