#!/usr/bin/env python3
"""Set up a new book folder from a PDF.

Usage:  python3 pipeline/new_book.py <file.pdf> [--name "<original title>"]

Creates translations/<name>/ with the layout from RULES.md §1, copies the PDF into source/,
extracts its images into assets/ (pdfimages, original quality), copies the layout template into build/,
and writes empty book.json and GLOSSARY.md files to fill in from the contents page.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PIPELINE, ROOT, die, pdf_pages, save_meta  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pdf', type=Path)
    ap.add_argument('--name', help='folder name, normally the original title (default: the PDF file name)')
    args = ap.parse_args()

    pdf = args.pdf.expanduser().resolve()
    if not pdf.is_file() or pdf.suffix.lower() != '.pdf':
        die(f'{pdf} is not a PDF file')
    name = (args.name or pdf.stem).strip()
    book = ROOT / name
    if (book / 'book.json').exists():
        die(f'{book} is already set up')

    for d in ('source/text', 'assets', 'build/content', 'docx', 'pdf', 'work'):
        (book / d).mkdir(parents=True, exist_ok=True)
    target = book / 'source' / pdf.name
    if not target.exists():
        shutil.copy2(pdf, target)
    for f in ('make.js', 'cover.py'):
        if not (book / 'build' / f).exists():
            shutil.copy2(PIPELINE / 'template' / f, book / 'build' / f)

    subprocess.run(['pdfimages', '-all', '-p', str(target), str(book / 'assets' / 'src')], check=True)
    images = sorted((book / 'assets').glob('src-*'))

    save_meta(book, {
        'title_ar': name, 'title_tr': '', 'title_en': '', 'aliases': [], 'author': '', 'layout': 'flow',
        'pdf': f'source/{pdf.name}', 'page_offset': None, 'sections': [], 'parts': {},
    })
    glossary = book / 'GLOSSARY.md'
    if not glossary.exists():
        glossary.write_text(f'# Glossary — {name} → (Turkish title)\n\n| Arabic | Turkish | Note |\n|---|---|---|\n',
                            encoding='utf-8')

    print(f'Set up {book}')
    print(f'  {pdf_pages(target)} pages · {len(images)} images extracted to assets/ (named src-PAGE-NUM)')
    print('Next: fill book.json from the contents page (titles, aliases, author, page_offset, sections),')
    print('      adapt the design in build/make.js to the original, then translate Part 01.')


if __name__ == '__main__':
    main()
