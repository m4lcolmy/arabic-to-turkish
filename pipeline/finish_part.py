#!/usr/bin/env python3
"""Close the runner's bookkeeping for a part finished in an interactive session (not by run_book.py).

    python3 pipeline/finish_part.py <book> NN

run_book.py marks a part it starts in <book>/work/resume.json and clears the mark only when its own session ends
normally. A part finished by hand after such a session was cut off keeps the mark, and the next run_book.py resumes
it again. This script does what the runner does after a finished part:
  - checks the part is complete: part PDF, CHECK file and a "## Part NN" entry in REVIEW-QUEUE.md;
  - removes the resume mark when it names this part;
  - adds a line to runs/log.tsv (engine "interactive");
  - commits the book folder to its own git repository ("Part NN (PDF A–B), finished interactively").
It refuses while run_book.py is working on the book (the runner then finishes the part itself).
"""
import datetime as dt
import fcntl
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import die, load_meta, part_id, part_pdf, resolve_book  # noqa: E402
from run_book import snapshot  # noqa: E402

LOG_HEADER = ('date\tpart\tpdf\tsource_pages\tturkish_pages\tattempt\tminutes\tpeak_context\tcompactions\tcost_usd'
              '\tsession\tengine')


def main():
    if len(sys.argv) != 3:
        die(__doc__.strip().splitlines()[2].strip())
    book = resolve_book(sys.argv[1])
    part = part_id(sys.argv[2])
    meta = load_meta(book)
    if part not in meta.get('parts', {}):
        die(f'Part {part} is not in the plan of {book.name}')
    a, b = meta['parts'][part]

    (book / 'work').mkdir(exist_ok=True)
    lock = (book / 'work' / 'run.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        die(f'run_book.py is working on {book.name} now; it finishes the part itself. Run this again after it stops.')

    missing = []
    if not part_pdf(book, part, meta).exists():
        missing.append(part_pdf(book, part, meta).name)
    if not (book / f'CHECK-part-{part}.md').exists():
        missing.append(f'CHECK-part-{part}.md')
    queue = book / 'REVIEW-QUEUE.md'
    if not (queue.exists() and re.search(rf'^## Part {part}\b', queue.read_text(), re.M)):
        missing.append(f'the "## Part {part} — …" entry in REVIEW-QUEUE.md')
    if missing:
        die(f'Part {part} is not finished: missing ' + '; '.join(missing))

    resume_file = book / 'work' / 'resume.json'
    if resume_file.exists():
        mark = json.loads(resume_file.read_text())
        if mark and mark[0] == part:
            resume_file.unlink()
            print(f'cleared the resume mark for Part {part}')
        else:
            print(f'resume mark left in place: it names Part {mark[0]}, not {part}')

    runs = book / 'runs'
    runs.mkdir(exist_ok=True)
    log = runs / 'log.tsv'
    if not log.exists():
        log.write_text(LOG_HEADER + '\n')
    tr_pages = meta.get('layout_pages', {}).get(part, '')
    with log.open('a') as f:
        f.write(f'{dt.datetime.now():%Y-%m-%d %H:%M}\t{part}\t{a}-{b}\t{b - a + 1}\t{tr_pages}\t\t\t\t\t\t\tinteractive\n')

    snapshot(book, f'Part {part} (PDF {a}–{b}), finished interactively')
    print(f'Part {part} closed: logged and committed to the book repository ({book.name}/.git).')


if __name__ == '__main__':
    main()
