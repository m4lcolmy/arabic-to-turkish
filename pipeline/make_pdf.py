#!/usr/bin/env python3
"""Combine a book's reviewed part PDFs into the final PDF (RULES.md §6, step 10).

Usage:  python3 pipeline/make_pdf.py <book> [--draft]

Nothing is retranslated: each part PDF (<book>/part-NN_pdf-pA-B.pdf, written by build.py) is merged as it was
reviewed. Before merging, the script stops if the parts in book.json leave a source page out or overlap, a part
PDF or CHECK file is missing, or a part PDF is out of date: its content file, make.js or assets changed after
it was built (book.json "built"; rebuild it with build.py and review it again).
Each part PDF is then checked: page count, every font embedded and no fallback font (a missing glyph), and
the printed page number on every page. The parts are merged, the entries of the contents page become PDF
bookmarks, and each entry is checked to land on the page that carries its title.

Flow books (book.json "layout": "flow", RULES.md §2): a part may have more or fewer pages than its source
range. Page numbers must run on without a gap from part to part, and the contents numbers are the printed
pages where build.py found each title. A part whose text is unchanged but whose page numbers or contents
numbers are out of date (a part before it changed length, later titles were placed) is rebuilt here.

--draft  uses the parts that exist so far: gaps, out-of-date part PDFs and missing CHECK files
         become warnings. The result goes to work/final/, never to output/.

Output:  <book>/output/<Turkish title>.pdf         (with --draft: work/final/<title> - DRAFT.pdf)
         <book>/work/final/report.txt, contact-sheet.png (every page at a glance)
Exit code 1 when a check fails; the final PDF is then not written.
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (PIPELINE, build_inputs, build_numbers, content_file, die, first_position, fold, front_pages, is_flow, load_content, load_meta,  # noqa: E402
                    page_label, page_text, part_pdf, pdf_pages, plain, resolve_book, source_pdf, toc_titles)



class Report:
    """Collects findings; with draft=True, 'soft' errors (book not finished yet) are only warnings."""

    def __init__(self, draft):
        self.draft, self.lines, self.errors, self.warnings = draft, [], 0, 0

    def say(self, msg):
        self.lines.append(msg)
        print(msg)

    def error(self, msg, soft=False):
        if soft and self.draft:
            return self.warn(msg)
        self.errors += 1
        self.say(f'ERROR  {msg}')

    def warn(self, msg):
        self.warnings += 1
        self.say(f'WARN   {msg}')

    def ok(self, msg):
        self.say(f'ok     {msg}')


# ── Before converting ───────────────────────────────────────────────────────
def check_coverage(parts, total, rep, omit=()):
    """Parts must cover PDF pages 1..total once each, in order. book.json "omit" ranges (e.g. an index
    that points to the source's page numbers) are left out of the Turkish edition on purpose."""
    nxt = 1
    for p, (a, b) in sorted(list(parts) + [('omit', tuple(r)) for r in omit], key=lambda x: x[1]):
        if a < nxt:
            rep.error(f'Part {p} (PDF {a}–{b}) overlaps the part before it')
        elif a > nxt:
            rep.error(f'PDF pages {nxt}–{a - 1} belong to no part', soft=True)
        nxt = max(nxt, b + 1)
    if nxt <= total:
        rep.error(f'PDF pages {nxt}–{total} belong to no part (not translated yet)', soft=True)
    elif nxt - 1 > total:
        rep.error(f'parts in book.json go up to PDF page {nxt - 1}, but the source has {total} pages')


# ── Checking a converted PDF ────────────────────────────────────────────────
def squash(name):
    return re.sub(r'[\s_-]', '', name).lower()


def pdf_fonts(pdf):
    """[(font name without subset prefix, embedded?)] from pdffonts."""
    out = subprocess.run(['pdffonts', str(pdf)], capture_output=True, text=True).stdout.splitlines()
    fonts = []
    for line in out[2:]:
        cols = line.split()
        if len(cols) >= 7:
            fonts.append((re.sub(r'^[A-Z]{6}\+', '', cols[0]), cols[-5] == 'yes'))
    return fonts


def check_fonts(pdf, wanted, label, rep):
    families = [squash(f) for f in wanted]
    bad = False
    for name, embedded in pdf_fonts(pdf):
        if not embedded:
            rep.error(f'{label}: font {name} is not embedded')
            bad = True
        if not any(squash(name.split(',')[0]).startswith(f) for f in families):
            rep.error(f'{label}: fallback font {name} was used (the document asks only for {", ".join(sorted(wanted))}): '
                      'a character the font lacks, e.g. ﷺ, or a font that is not installed')
            bad = True
    return not bad


def page_words(pdf, page):
    """[(yMax, xMin, word)] of one page."""
    out = subprocess.run(['pdftotext', '-f', str(page), '-l', str(page), '-bbox', str(pdf), '-'],
                         capture_output=True, text=True).stdout
    return [(float(y), float(x), html.unescape(w)) for x, y, w in
            re.findall(r'<word xMin="([\d.]+)" yMin="[\d.]+" xMax="[\d.]+" yMax="([\d.]+)">([^<]*)</word>', out)]


def footer_text(pdf, page, at_top=False):
    """The lowest line of text on the page: the page number in the footer. at_top (book.json
    "page_number": "header"): the page number at either end of the running head, like "12 | TITLE" or
    "TITLE | 13"; a page without one (a section opener) falls back to the footer."""
    words = page_words(pdf, page)
    if not words:
        return ''
    if at_top:
        top = min(y for y, _, _ in words)
        line = [w for y, x, w in sorted(words, key=lambda t: t[1]) if y - top < 2]
        folio = re.compile(r'^(\d+|[ivxlc]+)$')
        if '|' in line:
            for w in (line[0], line[-1]):
                if folio.match(w):
                    return w
    bottom = max(y for y, _, _ in words)
    foot = ' '.join(w for y, x, w in sorted(words, key=lambda t: t[1]) if bottom - y < 2)
    if at_top and not re.fullmatch(r'\d+|[ivxlc]+', foot):
        return ''  # a page without a number (half title, copyright page): its last line is text, not a folio
    return foot


# ── Steps ───────────────────────────────────────────────────────────────────
def contents_entries(book, parts, offset):
    """[(title, source PDF page)] from the contents page ('toc' block) of the part files."""
    entries = []
    for p, _ in parts:
        if content_file(book, p).exists():
            for pg in load_content(book, p):
                for b in pg.get('blocks', []):
                    if b.get('type') == 'toc':
                        entries += [(t, int(n) + offset) for t, n in b['entries']]
    return entries


def contact_sheet(pdf, labels, out, rep):
    if not shutil.which('montage'):
        rep.warn('ImageMagick "montage" not found: no contact sheet')
        return
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(['pdftoppm', '-r', '30', '-png', str(pdf), f'{d}/t'], check=True)
        thumbs = sorted(Path(d).glob('t-*.png'), key=lambda f: int(f.stem.split('-')[1]))
        args = [a for label, t in zip(labels, thumbs) for a in ('-label', label, str(t))]
        subprocess.run(['montage', *args, '-tile', '8x', '-geometry', '+6+6', '-pointsize', '11',
                        '-background', '#d8d8d8', str(out)], check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book')
    ap.add_argument('--draft', action='store_true', help='build from the parts that exist so far, into work/final/')
    args = ap.parse_args()

    book = resolve_book(args.book)
    meta = load_meta(book)
    if not meta.get('parts'):
        die(f'{book / "book.json"} lists no parts yet')
    total = pdf_pages(source_pdf(book))
    flow = is_flow(meta)
    offset = front_pages(meta) if flow else meta.get('page_offset') or 0  # flow: Turkish pages before printed page 1
    at_top = meta.get('page_number') == 'header'
    title = meta.get('title_tr') or book.name
    parts = sorted(((p, tuple(r)) for p, r in meta['parts'].items()), key=lambda x: x[1])
    final = book / 'work' / 'final'
    shutil.rmtree(final, ignore_errors=True)
    final.mkdir(parents=True)
    rep = Report(args.draft)
    rep.say(f'{book.name}: {title}, {total} source pages, {len(parts)} part(s)'
            f'{", flow layout" if flow else ""}{" (DRAFT)" if args.draft else ""}\n')

    # 1. Before converting
    check_coverage(parts, total, rep, meta.get('omit', []))
    if flow:
        titles, _ = toc_titles(book, meta)
        unplaced = [t for t in titles if t not in meta.get('toc_pages', {})]
        if unplaced:
            rep.error(f'contents: no page found yet for {len(unplaced)} title(s), e.g. "{unplaced[0]}"; build the '
                      'parts that hold them (the title in the text must match the contents entry)', soft=True)
    todo, fonts, stale = [], set(), 0
    for p, (a, b) in parts:
        if not (book / f'CHECK-part-{p}.md').exists():
            rep.error(f'Part {p}: CHECK-part-{p}.md is missing (completeness check not done)', soft=True)
        if not content_file(book, p).exists():
            rep.error(f'Part {p}: {content_file(book, p).relative_to(book)} is missing', soft=True)
            continue
        pdf, built = part_pdf(book, p, meta), load_meta(book).get('built', {}).get(p)
        if not pdf.exists() or not built:
            rep.error(f'Part {p}: {pdf.name} is missing; build it with build.py', soft=True)
            continue
        if built['inputs'] != build_inputs(book, p):
            stale += 1
            rep.error(f'Part {p}: {pdf.name} is out of date: its content file, make.js or assets changed after it was '
                      f'built. Rebuild with build.py "{book.name}" {p}, review it, and run this again', soft=True)
        elif flow and built['numbers'] != build_numbers(book, load_meta(book), p):
            # Same text, only the page numbers or contents numbers moved: rebuilding changes nothing else
            r = subprocess.run([sys.executable, str(PIPELINE / 'build.py'), str(book), p], capture_output=True, text=True)
            if r.returncode:
                rep.error(f'Part {p}: rebuilding it with the final page and contents numbers failed: {r.stdout}{r.stderr}')
            else:
                rep.ok(f'Part {p}: rebuilt with the final page and contents numbers (nothing else changed)')
            built = load_meta(book)['built'][p]
        fonts |= set(built.get('fonts', []))
        todo.append((p, a, b, pdf))
    if not todo:
        rep.error('no part PDF to merge')
    if rep.errors:
        return finish(rep, final, 'Stopped before merging.')
    fresh = 'up to date' if not stale else f'{len(todo) - stale} up to date, {stale} out of date (draft)'
    rep.ok(f'{len(todo)} part PDF(s) to merge, {fresh}')

    # 2. Check each part
    part_pdfs, positions, labels = [], [], []
    meta = load_meta(book)  # rebuilds above may have moved page counts
    for p, a, b, src in todo:
        label = f'Part {p}'
        pdf = final / f'part-{p}.pdf'
        shutil.copy(src, pdf)
        n, want = pdf_pages(pdf), b - a + 1
        content = load_content(book, p) if content_file(book, p).exists() else []
        if flow:
            # Page numbers run on from the real last page of the part before; cover and blank pages carry none
            first = first_position(load_meta(book), p)
            good = meta.get('layout_pages', {}).get(p) == n and first is not None
            if not good:
                rep.error(f'{label}: {n} page(s), but book.json records {meta.get("layout_pages", {}).get(p)}, or a part '
                          f'before it was never built; rebuild the parts from here on with build.py, in order')
                first = first or 1
            pos = list(range(first, first + n))
            unnumbered = sum(pg.get('type') in ('cover', 'blank') for pg in content)
        else:
            good = n == want
            if not good:
                rep.error(f'{label}: {n} page(s), source range {a}–{b} has {want}')
            pos = list(range(a, a + n))
        good &= check_fonts(pdf, fonts, label, rep)
        numbered = []
        for i in range(1, n + 1):
            at = pos[i - 1]
            got, expect = footer_text(pdf, i, at_top), str(at - offset)
            if flow and at - offset < 1:
                want_front = page_label(meta, at)
                if got.isdigit() or (want_front and got and got != want_front):
                    rep.error(f'Page {at}: front matter (before printed page 1) shows page number {got}'
                              f'{f", expected {want_front} or none" if want_front else ""}')
                    good = False
                continue  # front matter before printed page 1 (book.json front_pages): none, or roman numbers
            if flow and not got and unnumbered:
                unnumbered -= 1  # a cover or blank page
                continue
            if not flow and i <= len(content) and content[i - 1].get('type') in ('cover', 'blank'):
                continue  # full-page image or empty page, no footer
            numbered.append(expect)
            if got != expect:
                rep.error(f'{"Page" if flow else "PDF page"} {at}: printed page number is "{got or "none"}", expected {expect}')
                good = False
        if good:
            nums = f', page numbers {numbered[0]}–{numbered[-1]}' if numbered else ''
            rep.ok(f'{label}: {"source " if flow else ""}PDF pages {a}–{b}, {n} page(s), fonts embedded{nums}')
        part_pdfs.append(pdf)
        positions += pos
        labels += [(f'p. {x - offset}' if x > offset else 'front') if flow else f'PDF p. {x}' for x in pos]
    if rep.errors:
        return finish(rep, final, 'Part PDFs have problems; no book PDF written.')

    # 3. Merge, add document info and bookmarks
    merged = final / 'merged.pdf'
    if len(part_pdfs) == 1:
        shutil.copy(part_pdfs[0], merged)
    else:
        subprocess.run(['pdfunite', *map(str, part_pdfs), str(merged)], check=True)
    # where: page position (source PDF page, or Turkish book page in flow books) → page in the merged PDF
    where = {x: i + 1 for i, x in enumerate(positions)}
    if flow:
        toc = load_meta(book).get('toc_pages', {})
        pos = load_meta(book).get('toc_positions', {})
        entries = [(t, pos.get(t, toc[t] + offset if isinstance(toc[t], int) else None))
                   for t in toc_titles(book, meta)[0] if t in toc]
    else:
        entries = contents_entries(book, parts, offset) or [(s['name'], s['pdf'][0]) for s in meta.get('sections', [])]
    marks = [{'title': t, 'page': where[src]} for t, src in entries if src in where]
    spec = final / 'finish.json'
    spec.write_text(json.dumps({'title': title, 'author': meta.get('author', ''), 'lang': meta.get('lang', 'tr'),
                                'bookmarks': marks}, ensure_ascii=False, indent=1), encoding='utf-8')
    book_pdf = final / 'book.pdf'
    r = subprocess.run(['node', str(PIPELINE / 'pdf_finish.js'), str(merged), str(book_pdf), str(spec)],
                       capture_output=True, text=True)
    if r.returncode:
        rep.error(f'adding bookmarks and document info failed: {r.stderr.strip()}')
        return finish(rep, final, 'No book PDF written.')

    # 4. Check the whole book
    n = pdf_pages(book_pdf)
    if n != len(positions):
        rep.error(f'book PDF has {n} pages, expected {len(positions)}')
    elif flow:
        rep.ok(f'book PDF: {n} pages (the source has {total}; flow layout)')
    elif not args.draft and n != total:
        rep.error(f'book PDF has {n} pages, the source has {total}')
    else:
        rep.ok(f'book PDF: {n} pages{"" if args.draft else f", same as the source"}')
    if check_fonts(book_pdf, fonts, 'book PDF', rep):
        rep.ok(f'book PDF: all fonts embedded ({", ".join(sorted({f for f, _ in pdf_fonts(book_pdf)}))})')
    toc_bad = 0
    for t, src in entries:
        if src in where and fold(t) not in fold(page_text(book_pdf, where[src])):
            rep.error(f'contents: "{t}" points to {"page" if flow else "PDF page"} {src} (printed {page_label(meta, src) if flow else src - offset}), '
                      'but that title is not on that page')
            toc_bad += 1
    if entries and not toc_bad:
        rep.ok(f'contents: {len(marks)} entr{"y" if len(marks) == 1 else "ies"} land on their titles; added as bookmarks')
    if rep.errors:
        return finish(rep, final, 'The book PDF has problems; not delivered.')

    # 5. Deliver
    if args.draft:
        out = final / f'{title} - DRAFT.pdf'
    else:
        out = book / 'output' / f'{title}.pdf'
        out.parent.mkdir(exist_ok=True)
    shutil.copy(book_pdf, out)
    contact_sheet(out, labels, final / 'contact-sheet.png', rep)
    for f in (merged, book_pdf, spec):
        f.unlink()
    return finish(rep, final, f'Wrote {out.relative_to(book)} ({out.stat().st_size // 1024} KB). '
                              f'Look over {(final / "contact-sheet.png").relative_to(book)} before sharing it.')


def finish(rep, final, last):
    rep.say(f'\n{last}\n{rep.errors} error(s), {rep.warnings} warning(s). Report: {final / "report.txt"}')
    (final / 'report.txt').write_text('\n'.join(rep.lines) + '\n', encoding='utf-8')
    return 1 if rep.errors else 0


if __name__ == '__main__':
    sys.exit(main())
