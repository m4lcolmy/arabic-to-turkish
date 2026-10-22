#!/usr/bin/env python3
"""Render source pages for reading and transcription.

Usage:  python3 pipeline/pages.py <book> <first>[-<last>]

Writes to <book>/work/pages/:
  p-NNN.png       whole page, 150 dpi (for reading)
  p-NNN-zoom.png  lower 45 % of the page at 260 dpi (footnotes and small text)
  p-NNN.txt       PDF text layer: a cross-check only (Arabic letters are often broken; English is a
                  good starting draft for the transcription, checked against the image)
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import die, parse_pages, pdf_pages, resolve_book, source_pdf  # noqa: E402


def render(pdf, n, dpi, out_stem, crop=None):
    cmd = ['pdftoppm', '-f', str(n), '-l', str(n), '-r', str(dpi), '-png', '-singlefile']
    if crop:
        cmd += ['-x', str(crop[0]), '-y', str(crop[1]), '-W', str(crop[2]), '-H', str(crop[3])]
    subprocess.run(cmd + [str(pdf), str(out_stem)], check=True)


def page_size(pdf, n):
    info = subprocess.run(['pdfinfo', '-f', str(n), '-l', str(n), str(pdf)], capture_output=True, text=True).stdout
    w, h = re.search(rf'Page\s+{n} size:\s+([\d.]+) x ([\d.]+)', info).groups()
    return float(w), float(h)


def main():
    if len(sys.argv) != 3:
        die(__doc__)
    book = resolve_book(sys.argv[1])
    first, last = parse_pages(sys.argv[2])
    pdf = source_pdf(book)
    if last > pdf_pages(pdf):
        die(f'{pdf.name} has only {pdf_pages(pdf)} pages')
    out = book / 'work' / 'pages'
    out.mkdir(parents=True, exist_ok=True)
    for n in range(first, last + 1):
        w, h = (round(x / 72 * 260) for x in page_size(pdf, n))
        stem = out / f'p-{n:03d}'
        render(pdf, n, 150, stem)
        render(pdf, n, 260, f'{stem}-zoom', crop=(0, int(h * 0.55), w, h - int(h * 0.55)))
        subprocess.run(['pdftotext', '-f', str(n), '-l', str(n), '-layout', str(pdf), f'{stem}.txt'], check=True)
        print(f'{stem}.png  {stem}-zoom.png  {stem}.txt')


if __name__ == '__main__':
    main()
