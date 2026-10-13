#!/usr/bin/env python3
"""Build one part: DOCX → PDF → page-count check → page images for the visual check.

Usage:  python3 pipeline/build.py <book> <part> [--pages A-B]

--pages is needed the first time a part is built; it is then stored in book.json.
Output:  <book>/docx/part-NN_pdf-pA-B.docx
         <book>/work/render/part-NN.pdf and part-NN/*.png (page images)
Flow books (book.json "layout": "flow"): the part takes as many pages as its text needs; the page count and
the printed page of each contents title are recorded in book.json (layout_pages, toc_pages), and the images
are named tr-NN.png (Turkish page NN of the part).
Older books: images are named p-NNN.png by source page, and exit code 1 when the DOCX does not have
exactly one page per source page.
"""
import argparse
import glob
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (PIPELINE, content_file, die, first_position, is_flow, load_meta, page_text,  # noqa: E402
                    parse_pages, part_id, part_order, part_pages, pdf_pages, plain, resolve_book, save_meta,
                    toc_titles)


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

    for old in (book / 'docx').glob(f'part-{part}_pdf-p*.docx'):
        if old.name != f'part-{part}_pdf-p{first}-{last}.docx':
            print(f'note: an older output with another page range exists: {old.name}')
    docx = book / 'docx' / f'part-{part}_pdf-p{first}-{last}.docx'
    docx.parent.mkdir(exist_ok=True)
    subprocess.run(['node', 'make.js', str(src), str(docx)], cwd=book / 'build', check=True)

    soffice = find_soffice()
    if not soffice:
        print('LibreOffice not found: page count and page images skipped')
        return
    render = book / 'work' / 'render'
    render.mkdir(parents=True, exist_ok=True)
    profile = (PIPELINE / '.lo-profile').as_uri()  # own profile, so a LibreOffice window you have open doesn't block it
    subprocess.run([soffice, f'-env:UserInstallation={profile}', '--headless', '--convert-to', 'pdf',
                    '--outdir', str(render), str(docx)], check=True, capture_output=True)
    pdf = render / f'{docx.stem}.pdf'
    final = render / f'part-{part}.pdf'
    pdf.replace(final)

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
        print(f'{docx.relative_to(book)}: {got} page(s) (source range {first}–{last} has {want}; flow layout)')
        print(f'page images: {imgs}')
        record_layout(book, part, final, got)
        return
    print(f'{docx.relative_to(book)}: {got} page(s), source range {first}–{last} has {want}')
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
    first, offset = first_position(meta, part), meta.get('page_offset') or 0
    titles, own = toc_titles(book, meta)
    texts = [page_text(pdf, i) for i in range(1, n + 1)]
    contents = {i for i, t in enumerate(texts) if sum(plain(x) in t for x in titles) >= 2}  # contents pages
    toc = meta.setdefault('toc_pages', {})
    for t in titles:
        # A title on a contents page is only the contents entry, except the contents page's own title
        hit = next((i for i, x in enumerate(texts) if plain(t) in x and (i not in contents or t in own)), None)
        if hit is not None:
            toc[t] = first + hit - offset
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
