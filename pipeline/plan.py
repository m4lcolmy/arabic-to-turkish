#!/usr/bin/env python3
"""Plan a book's parts: whole sections grouped into parts of at most N source PDF pages (RULES.md §6).

Usage:  python3 pipeline/plan.py <book> [--max-pages N] [--dry-run]

A part is the work of one session. It holds whole sections only, so "next" never splits a section.
Parts already started (content file, part PDF or CHECK file present) are kept as they are; every part not
started yet is dropped and the remaining sections are planned again, with as few parts as possible and
their sizes kept even. A section longer than the limit becomes a part of its own (split it at a heading
by hand, in book.json, if it is far too long for one session).

--max-pages  the limit, saved in book.json as "part_max_pages" (default 12, see RULES.md §6)
--dry-run    print the plan without saving it
"""
import argparse
import functools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import content_file, load_meta, resolve_book, save_meta  # noqa: E402

DEFAULT_MAX_PAGES = 12


def started(book, part):
    return (content_file(book, part).exists() or (book / f'CHECK-part-{part}.md').exists()
            or any(book.glob(f'part-{part}_pdf-p*.pdf')) or any((book / 'docx').glob(f'part-{part}_*.docx')))


def group(sections, cap):
    """Split consecutive sections into the fewest groups of at most cap pages, sizes as even as possible."""
    size = [s['pdf'][1] - s['pdf'][0] + 1 for s in sections]
    n = len(sections)

    @functools.lru_cache(None)
    def best(i):  # (groups, unevenness, end of first group) for sections[i:]
        if i == n:
            return 0, 0.0, None
        out, total = None, 0
        for j in range(i, n):
            total += size[j]
            if total > cap and j > i:
                break
            k, d, _ = best(j + 1)
            c = (k + 1, d + (total - cap * 0.85) ** 2, j)
            if out is None or c[:2] < out[:2]:
                out = c
        return out

    groups, i = [], 0
    while i < n:
        j = best(i)[2]
        groups.append(sections[i:j + 1])
        i = j + 1
    return groups


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book')
    ap.add_argument('--max-pages', type=int)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    book = resolve_book(args.book)
    meta = load_meta(book)
    sections = meta.get('sections') or []
    if not sections:
        sys.exit(f'{book / "book.json"} has no sections yet: add them from the contents page first')
    cap = args.max_pages or meta.get('part_max_pages') or DEFAULT_MAX_PAGES

    kept = {p: r for p, r in meta.get('parts', {}).items() if started(book, p)}
    dropped = sorted(set(meta.get('parts', {})) - set(kept))
    covered = lambda r: any(a <= r[0] and r[1] <= b for a, b in kept.values())  # noqa: E731
    todo = [s for s in sections if not covered(s['pdf'])]
    last = max((b for _, b in kept.values()), default=0)
    early = [s['name'] for s in todo if s['pdf'][0] <= last]
    if early:
        sys.exit(f'sections before the last started part are not in any part: {", ".join(early)}. '
                 'Register them by hand in book.json "parts" first.')

    parts = dict(kept)
    nxt = int(max(kept, default='00')) + 1
    print(f'{book.name}: at most {cap} PDF pages per part, whole sections only')
    for p, (a, b) in sorted(kept.items()):
        print(f'  Part {p}  PDF {a}–{b}  (started, kept)')
    for g in group(todo, cap):
        p, a, b = f'{nxt:02d}', g[0]['pdf'][0], g[-1]['pdf'][1]
        parts[p] = [a, b]
        names = ' + '.join(s['name'] for s in g)
        over = '  ← over the limit: one section on its own' if b - a + 1 > cap else ''
        print(f'  Part {p}  PDF {a}–{b}  ({b - a + 1} pp)  {names}{over}')
        nxt += 1
    if dropped:
        print(f'(re-planned: unstarted part(s) {", ".join(dropped)})')

    if args.dry_run:
        print('dry run: book.json not changed')
        return
    meta['parts'] = dict(sorted(parts.items()))
    meta['part_max_pages'] = cap
    save_meta(book, meta)
    print(f'saved to {book / "book.json"}')


if __name__ == '__main__':
    main()
