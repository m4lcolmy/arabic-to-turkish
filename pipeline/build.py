#!/usr/bin/env python3
"""Build one part: the part PDF (via a temporary DOCX) → page-count check → page images for the visual check.

Usage:  python3 pipeline/build.py <book> <part> [--pages A-B]

--pages is needed the first time a part is built; it is then stored in book.json.
Output:  <book>/part-NN_pdf-pA-B.pdf   the part as it will print, fonts embedded: the file to review, and what
                                       make_pdf.py merges into the book (book.json "built" records what it was made from)
         <book>/work/render/part-NN.pdf and part-NN/*.png (page images); work/build/part-NN.docx (temporary)
Flow books (book.json "layout": "flow"): the part takes as many pages as its text needs; the page count and
the printed page of each contents title are recorded in book.json (layout_pages, toc_pages), and the images
are named tr-NN.png (Turkish page NN of the part).
Older books: images are named p-NNN.png by source page, and exit code 1 when the part does not have
exactly one page per source page.
"""
import argparse
import glob
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (PIPELINE, build_inputs, build_numbers, content_file, die, first_position, fold, is_flow,
                    load_content, load_meta, part_pdf, page_label,  # noqa: E402
                    page_text, parse_pages, part_id, part_order, part_pages, pdf_pages, plain, resolve_book, save_meta,
                    toc_titles)


# Print quality: keep images at full resolution, JPEG quality 100 (LibreOffice's defaults resample to
# 300 dpi and recompress at 90). Bookmarks come from the contents page instead of Word headings.
# The same settings as the final book PDF (make_pdf.py), so the part PDF is the book as it will print.
PDF_EXPORT = 'pdf:writer_pdf_Export:' + json.dumps({
    'ReduceImageResolution': {'type': 'boolean', 'value': 'false'},
    'Quality': {'type': 'long', 'value': '100'},
    'EmbedStandardFonts': {'type': 'boolean', 'value': 'true'},
    'ExportBookmarks': {'type': 'boolean', 'value': 'false'},
})


def docx_fonts(docx):
    """Font families the DOCX asks for (theme defaults aside: runs and styles name their font)."""
    fonts = set()
    with zipfile.ZipFile(docx) as z:
        for n in z.namelist():
            if n.startswith('word/') and n.endswith('.xml') and '/theme/' not in n:
                fonts |= set(re.findall(r'w:(?:ascii|hAnsi|cs|eastAsia)="([^"]+)"', z.read(n).decode('utf-8')))
    return fonts


def find_soffice():
    found = shutil.which('soffice') or shutil.which('libreoffice')
    return found or next(iter(sorted(glob.glob('/opt/libreoffice*/program/soffice'), reverse=True)), None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book')
    ap.add_argument('part')
    ap.add_argument('--pages', help='source PDF page range, e.g. 15-17')
    args = ap.parse_args()

    book, part = resolve_book(args.book), part_id(args.part)
    if args.pages:
        first, last = parse_pages(args.pages)
        meta = load_meta(book)
        meta.setdefault('parts', {})[part] = [first, last]
        meta['parts'] = dict(sorted(meta['parts'].items()))
        save_meta(book, meta)
    else:
        first, last = part_pages(book, part)
    src = content_file(book, part)
    if not src.exists():
        die(f'{src} does not exist yet')

    meta = load_meta(book)
    numbers = build_numbers(book, meta, part)  # what make.js reads now: recorded with the PDF below
    tmp = book / 'work' / 'build'
    tmp.mkdir(parents=True, exist_ok=True)
    docx = tmp / f'part-{part}_pdf-p{first}-{last}.docx'
    subprocess.run(['node', 'make.js', str(src), str(docx)], cwd=book / 'build', check=True)

    soffice = find_soffice()
    if not soffice:
        die('LibreOffice not found (PATH or /opt/libreoffice*): no part PDF')
    render = book / 'work' / 'render'
    render.mkdir(parents=True, exist_ok=True)
    profile = (PIPELINE / '.lo-profile').as_uri()  # own profile, so a LibreOffice window you have open doesn't block it
    subprocess.run([soffice, f'-env:UserInstallation={profile}', '--headless', '--convert-to', PDF_EXPORT,
                    '--outdir', str(render), str(docx)], check=True, capture_output=True)
    pdf = render / f'{docx.stem}.pdf'
    final = render / f'part-{part}.pdf'
    pdf.replace(final)
    # The part as it will print, fonts embedded: the file the person reviews and make_pdf.py merges
    for old in book.glob(f'part-{part}_pdf-p*.pdf'):
        old.unlink()
    out = part_pdf(book, part, meta)
    shutil.copy(final, out)
    meta = load_meta(book)
    meta.setdefault('built', {})[part] = {'pdf': out.name, 'inputs': build_inputs(book, part), 'numbers': numbers,
                                          'fonts': sorted(docx_fonts(docx))}
    meta['built'] = dict(sorted(meta['built'].items()))
    save_meta(book, meta)
    print(f'part PDF: {out.name}')

    imgs = render / f'part-{part}'
    shutil.rmtree(imgs, ignore_errors=True)
    imgs.mkdir()
    subprocess.run(['pdftoppm', '-r', '80', '-png', str(final), str(imgs / 'x')], check=True)
    pngs = sorted(imgs.glob('x-*.png'), key=lambda p: int(p.stem.split('-')[1]))
    flow = is_flow(load_meta(book))
    for i, p in enumerate(pngs):
        p.rename(imgs / (f'tr-{i + 1:02d}.png' if flow else f'p-{first + i:03d}.png'))

    got, want = pdf_pages(final), last - first + 1
    if flow:
        print(f'{out.name}: {got} page(s) (source range {first}–{last} has {want}; flow layout)')
        print(f'page images: {imgs}')
        record_layout(book, part, final, got)
        return
    print(f'{out.name}: {got} page(s), source range {first}–{last} has {want}')
    print(f'page images: {imgs}')
    if got != want:
        if got > want:
            print('ERROR: more pages than the source. Tighten the layout (e.g. "tight: true" on a dense page); never cut content.')
        else:
            print('ERROR: fewer pages than the source. Remove "tight", then loosen spacing slightly; never pad with an empty page.')
        sys.exit(1)


def record_layout(book, part, pdf, n):
    """Flow books: store the part's page count and the printed page of each contents title found in it."""
    meta = load_meta(book)
    old = meta.setdefault('layout_pages', {}).get(part)
    meta['layout_pages'][part] = n
    first = first_position(meta, part)
    titles, own = toc_titles(book, meta)
    texts = [fold(page_text(pdf, i)) for i in range(1, n + 1)]  # case-folded: titles may be set in capitals
    contents = {i for i, t in enumerate(texts) if sum(fold(x) in t for x in titles) >= 2}  # contents pages
    toc = meta.setdefault('toc_pages', {})
    positions = meta.setdefault('toc_positions', {})  # Turkish book position of each title (for bookmarks)
    # Only titles of sections in this part ('title' blocks and page headers): a short title such as "Notlar"
    # may also occur as an ordinary word in the text of other parts
    content = load_content(book, part)
    here = {b.get('text') for pg in content for b in pg.get('blocks', []) if b.get('type') == 'title'}
    here |= {pg.get('header') for pg in content}
    for t in titles:
        if t not in here and t not in own:
            continue
        # A title on a contents page is only the contents entry, except the contents page's own title
        hit = next((i for i, x in enumerate(texts) if fold(t) in x and (i not in contents or t in own)), None)
        if hit is not None:
            label = page_label(meta, first + hit)
            toc[t] = int(label) if label.isdigit() else label
            positions[t] = first + hit
    save_meta(book, meta)
    later = [p for p in part_order(meta)[part_order(meta).index(part) + 1:] if p in meta['layout_pages']]
    if old is not None and old != n and later:
        print(f'note: part {part} went from {old} to {n} pages; the page numbers of the parts after it shift. '
              f'Rebuild them: {", ".join(later)}')
    found = [t for t in titles if t in toc]
    if titles:
        print(f'contents: {len(found)} of {len(titles)} titles placed so far')


if __name__ == '__main__':
    main()
