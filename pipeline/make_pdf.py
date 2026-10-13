#!/usr/bin/env python3
"""Combine a book's reviewed part DOCX files into the final PDF (RULES.md §6, step 9).

Usage:  python3 pipeline/make_pdf.py <book> [--draft]

Nothing is retranslated or rebuilt: each DOCX in <book>/docx/ is converted as it was reviewed.
Before converting, the script stops if the parts in book.json leave a source page out or overlap,
a DOCX or CHECK file is missing, a needed font is not installed, or a DOCX no longer matches what
build/make.js makes from its content file today (rebuild it with build.py and review it again).
Each part's PDF is then checked: page count, every font embedded and no fallback font (a missing
glyph), and the printed page number on every page. The parts are merged, the entries of the contents
page become PDF bookmarks, and each entry is checked to land on the page that carries its title.

Flow books (book.json "layout": "flow", RULES.md §2): a part may have more or fewer pages than its source
range. Page numbers must run on without a gap from part to part, and the contents numbers are the printed
pages where build.py found each title. A part whose DOCX differs from today's build only in those contents
numbers is rebuilt here, so the contents shows the final numbers.

--draft  uses the parts that exist so far: gaps, out-of-date DOCX files and missing CHECK files
         become warnings. The result goes to work/final/, never to pdf/.

Output:  <book>/pdf/<Turkish title>.pdf            (with --draft: work/final/<title> - DRAFT.pdf)
         <book>/work/final/report.txt, contact-sheet.png (every page at a glance), part PDFs
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
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import find_soffice  # noqa: E402
from common import (PIPELINE, content_file, die, first_position, is_flow, load_content, load_meta,  # noqa: E402
                    page_text, pdf_pages, plain, resolve_book, source_pdf, toc_titles)

# Print quality: keep images at full resolution, JPEG quality 100 (LibreOffice's defaults resample to
# 300 dpi and recompress at 90). Bookmarks come from the contents page instead of Word headings.
PDF_EXPORT = 'pdf:writer_pdf_Export:' + json.dumps({
    'ReduceImageResolution': {'type': 'boolean', 'value': 'false'},
    'Quality': {'type': 'long', 'value': '100'},
    'EmbedStandardFonts': {'type': 'boolean', 'value': 'true'},
    'ExportBookmarks': {'type': 'boolean', 'value': 'false'},
})
CONVERT_TIMEOUT = 300  # seconds per DOCX


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
def check_coverage(parts, total, rep):
    """Parts must cover PDF pages 1..total once each, in order."""
    nxt = 1
    for p, (a, b) in parts:
        if a < nxt:
            rep.error(f'Part {p} (PDF {a}–{b}) overlaps the part before it')
        elif a > nxt:
            rep.error(f'PDF pages {nxt}–{a - 1} belong to no part', soft=True)
        nxt = max(nxt, b + 1)
    if nxt <= total:
        rep.error(f'PDF pages {nxt}–{total} belong to no part (not translated yet)', soft=True)
    elif nxt - 1 > total:
        rep.error(f'parts in book.json go up to PDF page {nxt - 1}, but the source has {total} pages')


def docx_entries(path):
    with zipfile.ZipFile(path) as z:  # docProps/core.xml only holds the build time
        return {n: z.read(n) for n in z.namelist() if n != 'docProps/core.xml'}


TOC_NUMBER = re.compile(rb'(<w:t[^>]*>\t)[^<]*(</w:t>)')  # the page number after the dot leader of a contents entry


def stale_reason(book, part, docx, tmp):
    """None when make.js turns today's content file into exactly this DOCX, 'contents numbers' when only the
    page numbers of contents entries differ, else what differs."""
    fresh = tmp / f'fresh-part-{part}.docx'
    r = subprocess.run(['node', 'make.js', str(content_file(book, part)), str(fresh)],
                       cwd=book / 'build', capture_output=True, text=True)
    if r.returncode:
        return 'make.js fails on the content file: ' + (r.stderr.strip().splitlines() or ['?'])[-1]
    old, new = docx_entries(docx), docx_entries(fresh)
    differ = sorted(n for n in old.keys() | new.keys() if old.get(n) != new.get(n))
    if differ and all(TOC_NUMBER.sub(rb'\1\2', old.get(n, b'')) == TOC_NUMBER.sub(rb'\1\2', new.get(n, b''))
                      for n in differ):
        return 'contents numbers'
    return f'differs in {", ".join(differ[:3])}{" …" if len(differ) > 3 else ""}' if differ else None


def docx_fonts(docx):
    """Font families the DOCX asks for (theme defaults aside: runs and styles name their font)."""
    fonts = set()
    with zipfile.ZipFile(docx) as z:
        for n in z.namelist():
            if n.startswith('word/') and n.endswith('.xml') and '/theme/' not in n:
                fonts |= set(re.findall(r'w:(?:ascii|hAnsi|cs|eastAsia)="([^"]+)"', z.read(n).decode('utf-8')))
    return fonts


def installed_families():
    out = subprocess.run(['fc-list', ':', 'family'], capture_output=True, text=True).stdout
    return {f.strip() for line in out.splitlines() for f in line.split(',')}


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


def footer_text(pdf, page):
    """The lowest line of text on the page: the page number in the footer."""
    words = page_words(pdf, page)
    if not words:
        return ''
    bottom = max(y for y, _, _ in words)
    return ' '.join(w for y, x, w in sorted(words, key=lambda t: t[1]) if bottom - y < 2)


# ── Steps ───────────────────────────────────────────────────────────────────
def convert(soffice, docx, outdir, rep, label):
    """DOCX → PDF with LibreOffice's own pipeline profile; one retry."""
    out = outdir / f'{docx.stem}.pdf'
    profile = (PIPELINE / '.lo-profile').as_uri()  # own profile, so an open LibreOffice window doesn't block it
    problem = ''
    for _ in range(2):
        out.unlink(missing_ok=True)
        try:
            r = subprocess.run([soffice, f'-env:UserInstallation={profile}', '--headless', '--convert-to', PDF_EXPORT,
                                '--outdir', str(outdir), str(docx)], capture_output=True, text=True, timeout=CONVERT_TIMEOUT)
            problem = (r.stderr or r.stdout).strip()
        except subprocess.TimeoutExpired:
            problem = f'LibreOffice took longer than {CONVERT_TIMEOUT} s'
        if out.exists() and out.stat().st_size:
            return out
    rep.error(f'{label}: LibreOffice made no PDF. {problem}')
    return None


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
    total, offset = pdf_pages(source_pdf(book)), meta.get('page_offset') or 0
    flow = is_flow(meta)
    title = meta.get('title_tr') or book.name
    parts = sorted(((p, tuple(r)) for p, r in meta['parts'].items()), key=lambda x: x[1])
    final = book / 'work' / 'final'
    shutil.rmtree(final, ignore_errors=True)
    final.mkdir(parents=True)
    rep = Report(args.draft)
    rep.say(f'{book.name}: {title}, {total} source pages, {len(parts)} part(s)'
            f'{", flow layout" if flow else ""}{" (DRAFT)" if args.draft else ""}\n')

    # 1. Before converting
    check_coverage(parts, total, rep)
    if flow:
        titles, _ = toc_titles(book, meta)
        unplaced = [t for t in titles if t not in meta.get('toc_pages', {})]
        if unplaced:
            rep.error(f'contents: no page found yet for {len(unplaced)} title(s), e.g. "{unplaced[0]}"; build the '
                      'parts that hold them (the title in the text must match the contents entry)', soft=True)
    soffice = find_soffice()
    if not soffice:
        rep.error('LibreOffice not found (PATH or /opt/libreoffice*)')
    todo, fonts, stale = [], set(), 0
    with tempfile.TemporaryDirectory() as tmp:
        for p, (a, b) in parts:
            docx = book / 'docx' / f'part-{p}_pdf-p{a}-{b}.docx'
            others = [f.name for f in (book / 'docx').glob(f'part-{p}_pdf-p*.docx') if f != docx]
            if others:
                rep.warn(f'Part {p}: ignoring {", ".join(others)} (page range differs from book.json)')
            if not docx.exists():
                rep.error(f'Part {p}: {docx.name} is missing; build it with build.py', soft=True)
                continue
            if not (book / f'CHECK-part-{p}.md').exists():
                rep.error(f'Part {p}: CHECK-part-{p}.md is missing (completeness check not done)', soft=True)
            if not content_file(book, p).exists():
                rep.error(f'Part {p}: {content_file(book, p).relative_to(book)} is missing', soft=True)
            elif (reason := stale_reason(book, p, docx, Path(tmp))) == 'contents numbers' and flow:
                r = subprocess.run([sys.executable, str(PIPELINE / 'build.py'), str(book), p], capture_output=True, text=True)
                if r.returncode:
                    rep.error(f'Part {p}: rebuilding it with the final contents numbers failed: {r.stdout}{r.stderr}')
                else:
                    rep.ok(f'Part {p}: rebuilt with the final contents numbers (nothing else changed)')
            elif reason:
                stale += 1
                rep.error(f'Part {p}: {docx.name} is not what the content file and make.js make today ({reason}). '
                          f'It is out of date or was edited by hand: rebuild with build.py "{book.name}" {p}, '
                          'review it, and run this again', soft=True)
            fonts |= docx_fonts(docx)
            todo.append((p, a, b, docx))
    missing = sorted(f for f in fonts if f not in installed_families())
    if missing:
        rep.error(f'font(s) not installed: {", ".join(missing)}; LibreOffice would substitute another font')
    if not todo:
        rep.error('no part DOCX to convert')
    if rep.errors:
        return finish(rep, final, 'Stopped before converting.')
    fresh = 'up to date' if not stale else f'{len(todo) - stale} up to date, {stale} out of date (draft)'
    rep.ok(f'{len(todo)} DOCX file(s) to convert, {fresh}; fonts installed: {", ".join(sorted(fonts))}')

    # 2. Convert and check each part
    part_pdfs, positions, labels = [], [], []
    for p, a, b, docx in todo:
        label = f'Part {p}'
        pdf = convert(soffice, docx, final, rep, label)
        if not pdf:
            continue
        pdf = pdf.replace(final / f'part-{p}.pdf')
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
            got, expect = footer_text(pdf, i), str(at - offset)
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
        labels += [f'p. {x - offset}' if flow else f'PDF p. {x}' for x in pos]
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
        entries = [(t, toc[t] + offset) for t in toc_titles(book, meta)[0] if t in toc]
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
        if src in where and plain(t) not in page_text(book_pdf, where[src]):
            rep.error(f'contents: "{t}" points to {"page" if flow else "PDF page"} {src} (printed {src - offset}), '
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
        out = book / 'pdf' / f'{title}.pdf'
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
