"""Shared helpers for the translation pipeline (book lookup, book.json, content files)."""
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # translations/
PIPELINE = ROOT / 'pipeline'
NOT_BOOKS = {'pipeline', 'node_modules'}


def die(msg):
    print(f'error: {msg}', file=sys.stderr)
    sys.exit(2)


# ── Text normalisation ──────────────────────────────────────────────────────
AR_MARKS = re.compile('[ؐ-ًؚ-ٰٟۖ-ۭـ]')  # harakat, Qur'anic signs, tatweel
DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')


def norm_ar(s):
    """Arabic without diacritics, with alif/hamza/ta marbuta variants unified."""
    s = unicodedata.normalize('NFKC', s)  # presentation forms → base letters
    s = AR_MARKS.sub('', s)
    s = re.sub('[أإآٱ]', 'ا', s)
    return s.replace('ى', 'ي').replace('ة', 'ه').replace('ؤ', 'و').replace('ئ', 'ي')


def norm_name(s):
    """Loose form for matching names typed by a person (Turkish, English or Arabic)."""
    s = norm_ar(s).replace('İ', 'i').replace('I', 'ı').lower().replace('ı', 'i')
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    s = re.sub(r"[‘’'`ʻʿʾ\"]", '', s)
    return ' '.join(re.sub(r'[^\w]+', ' ', s).split())


# ── Books ───────────────────────────────────────────────────────────────────
def books():
    out = []
    for d in sorted(ROOT.iterdir()):
        if d.is_dir() and not d.name.startswith('.') and d.name not in NOT_BOOKS:
            if (d / 'book.json').exists() or any((d / 'source').glob('*.pdf')):
                out.append(d)
    return out


def load_meta(book):
    p = book / 'book.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def save_meta(book, meta):
    (book / 'book.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def book_names(book):
    m = load_meta(book)
    return [book.name] + [m[k] for k in ('title_ar', 'title_tr', 'title_en') if m.get(k)] + m.get('aliases', [])


def last_touched(book):
    files = list((book / 'build' / 'content').glob('part-*.js')) or [book]
    return max(f.stat().st_mtime for f in files)


def resolve_book(query, latest_if_unnamed=False):
    """Find a book by folder name, title or alias; the query may contain extra words ("next premise ten premises").
    With latest_if_unnamed, a query that names no book ("next") falls back to the most recently worked-on book."""
    all_books = books()
    if not all_books:
        die(f'no books in {ROOT}')
    if not query or not query.strip():
        return max(all_books, key=last_touched)
    p = Path(query).expanduser()
    if p.is_dir() and (p / 'source').is_dir():
        return p.resolve()
    q = norm_name(query)
    hits = [b for b in all_books
            if any((n := norm_name(name)) and (n == q or f' {n} ' in f' {q} ' or (len(q) >= 3 and q in n))
                   for name in book_names(b))]
    if len(hits) == 1:
        return hits[0]
    if not hits and latest_if_unnamed:
        return max(all_books, key=last_touched)
    if not hits:
        die(f'no book matches "{query}". Books: ' + ', '.join(b.name for b in all_books))
    die(f'"{query}" matches several books: ' + ', '.join(b.name for b in hits))


def source_pdf(book):
    m = load_meta(book)
    if m.get('pdf'):
        return book / m['pdf']
    pdfs = sorted((book / 'source').glob('*.pdf'))
    if len(pdfs) != 1:
        die(f'expected exactly one PDF in {book / "source"}, found {len(pdfs)}')
    return pdfs[0]


def pdf_pages(pdf):
    out = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True).stdout
    return int(re.search(r'^Pages:\s+(\d+)', out, re.M).group(1))


# ── Parts ───────────────────────────────────────────────────────────────────
def part_id(s):
    digits = re.sub(r'\D', '', str(s))
    if not digits:
        die(f'part must be a number like 05, got "{s}"')
    return f'{int(digits):02d}'


def parse_pages(s):
    m = re.fullmatch(r'\s*(\d+)\s*(?:[-–]\s*(\d+))?\s*', s)
    if not m:
        die(f'page range must look like 15-17, got "{s}"')
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    if b < a:
        die(f'page range {s} is backwards')
    return a, b


def part_pages(book, part):
    r = load_meta(book).get('parts', {}).get(part)
    if r:
        return tuple(r)
    for f in (book / 'docx').glob(f'part-{part}_pdf-p*-*.docx'):
        a, b = re.search(r'_pdf-p(\d+)-(\d+)', f.name).groups()
        return int(a), int(b)
    die(f'part {part} has no page range yet; run build.py with --pages A-B first')


def content_file(book, part):
    return book / 'build' / 'content' / f'part-{part}.js'


def load_content(book, part):
    f = content_file(book, part)
    if not f.exists():
        die(f'{f} does not exist')
    r = subprocess.run(['node', '-e', 'process.stdout.write(JSON.stringify(require(process.argv[1])))', str(f)],
                       capture_output=True, text=True)
    if r.returncode:
        die(f'cannot load {f}:\n{r.stderr}')
    return json.loads(r.stdout)


# ── Flow layout (book.json "layout": "flow", RULES.md §2) ─────────────────────
def is_flow(meta):
    """Flow books: a part takes as many pages as its Turkish text needs; numbers come from the Turkish layout."""
    return meta.get('layout') == 'flow'


def part_order(meta):
    return [p for p, _ in sorted(meta.get('parts', {}).items(), key=lambda x: x[1][0])]


def first_position(meta, part):
    """Flow books: position in the Turkish book of the part's first page (cover = 1), or None while a part
    before it has no recorded page count. The same rule as firstPosition() in make.js."""
    pos = 1
    for p in part_order(meta):
        if p == part:
            return pos
        n = meta.get('layout_pages', {}).get(p)
        if n is None:
            return None
        pos += n
    return None


def toc_titles(book, meta):
    """(all contents titles, titles of the contents pages themselves) from the 'toc' blocks of the content files."""
    titles, own = [], set()
    for p in part_order(meta):
        if content_file(book, p).exists():
            for pg in load_content(book, p):
                blocks = pg.get('blocks', [])
                for b in blocks:
                    if b.get('type') == 'toc':
                        titles += [t for t, _ in b['entries']]
                        own |= {x.get('text') for x in blocks if x.get('type') == 'title'} | {pg.get('header')}
    return titles, own


def plain(s):
    return ' '.join(unicodedata.normalize('NFKC', s).replace('\xad', '').split())


def page_text(pdf, page):
    return plain(subprocess.run(['pdftotext', '-f', str(page), '-l', str(page), str(pdf), '-'],
                                capture_output=True, text=True).stdout)
