#!/usr/bin/env python3
"""Translate a whole book unattended: one fresh Claude session per planned part, then the final PDF.

Usage:  python3 pipeline/run_book.py <book> [--max-parts N] [--dry-run]

Each round asks status.py for the next planned part (plan.py makes the plan), runs
`claude -p "/arabic-to-turkish <book> next unattended"` in a new session, checks that the part is done
(DOCX and CHECK file), and commits the book folder to its own local git repository, so one part can be
rolled back without touching the others. When every part is done it runs make_pdf.py and stops.

It stops early, with a desktop notification, when:
  - <book>/BLOCKED.md exists (a session could not go on without the person; read it, fix, delete it)
  - the same part fails twice
  - --max-parts parts are done (e.g. --max-parts 2 to check the first parts before the rest)
  - make_pdf.py reports a failed check
A usage limit is not a failure: the runner waits and tries the same part again.

Every session is logged to <book>/runs/ (JSON result, and a line in log.tsv with the peak context and
any compaction), so the part size in book.json "part_max_pages" can be tuned with plan.py.
Corrections and items to review from every part collect in <book>/REVIEW-QUEUE.md.

--model, --effort      default claude-opus-5-5, high
--wait-minutes         wait after a usage limit (default 30)
--dry-run              show the next part and the command, run nothing
"""
import argparse
import datetime as dt
import fcntl
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PIPELINE, ROOT, load_meta, resolve_book  # noqa: E402

TRAILER = 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
LIMIT = re.compile(r'usage limit|rate limit|limit reached|overloaded|\b429\b|\b529\b|resets? at', re.I)
BOOK_GITIGNORE = 'work/\n__pycache__/\n.~lock.*#\n'


def say(msg, notify=False):
    print(f'[{dt.datetime.now():%H:%M}] {msg}', flush=True)
    if notify and shutil.which('notify-send'):
        subprocess.run(['notify-send', 'Translation runner', msg], check=False)


def status_next(book):
    r = subprocess.run([sys.executable, str(PIPELINE / 'status.py'), str(book), '--next'],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


def git(book, *args, check=True):
    return subprocess.run(['git', '-C', str(book), *args], capture_output=True, text=True, check=check)


def snapshot(book, message):
    """Commit the book folder to its own local repository (book folders stay out of the main repo)."""
    if not (book / '.git').exists():
        git(book, 'init', '-q')
        (book / '.gitignore').write_text(BOOK_GITIGNORE)
    git(book, 'add', '-A')
    if git(book, 'diff', '--cached', '--quiet', check=False).returncode:
        git(book, 'commit', '-q', '-m', f'{message}\n\n{TRAILER}')


def session_stats(session_id):
    """Peak context (tokens) and compactions of a finished session, from its transcript."""
    peak, compactions = 0, 0
    for f in Path.home().glob(f'.claude/projects/*/{session_id}.jsonl'):
        for line in f.open(encoding='utf-8'):
            if '"compact_boundary"' in line or '"isCompactSummary":true' in line:
                compactions += 1
            if '"usage"' not in line:
                continue
            try:
                u = json.loads(line).get('message', {}).get('usage') or {}
            except json.JSONDecodeError:
                continue
            peak = max(peak, sum(u.get(k) or 0 for k in
                                 ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')))
    return peak, compactions


def progress(tool):
    """One short line for a tool call, so the terminal shows what the session is doing."""
    i = tool.get('input') or {}
    what = i.get('file_path') or i.get('command') or i.get('skill') or i.get('pattern') or ''
    what = ' '.join(str(what).split()).replace(str(ROOT) + '/', '')
    return f'{tool.get("name")}: {what[:110]}'


def run_part(book, part, a, b, args, attempt):
    sid = str(uuid.uuid4())
    prompt = f'/arabic-to-turkish {book.name} next unattended'
    cmd = ['claude', '-p', prompt, '--model', args.model, '--effort', args.effort,
           '--permission-mode', 'auto', '--output-format', 'stream-json', '--verbose', '--session-id', sid,
           '-n', f'{book.name} · Part {part}']
    runs = book / 'runs'
    runs.mkdir(exist_ok=True)
    start, res = time.time(), None
    with (runs / f'part-{part}-try{attempt}.jsonl').open('w') as raw, \
            subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
        for line in proc.stdout:
            raw.write(line)
            raw.flush()
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get('type') == 'result':
                res = ev
            elif ev.get('type') == 'assistant':
                for c in ev.get('message', {}).get('content') or []:
                    if c.get('type') == 'tool_use':
                        print(f'    {time.time() - start:5.0f}s  {progress(c)}', flush=True)
        stderr = proc.stderr.read()
    minutes = (time.time() - start) / 60
    if stderr:
        (runs / f'part-{part}-try{attempt}.stderr').write_text(stderr)
    res = res or {'is_error': True, 'result': stderr[-2000:]}
    peak, compactions = session_stats(sid)
    meta = load_meta(book)
    tr_pages = meta.get('layout_pages', {}).get(part, '')
    log = runs / 'log.tsv'
    if not log.exists():
        log.write_text('date\tpart\tpdf\tsource_pages\tturkish_pages\tattempt\tminutes\tpeak_context\tcompactions\tcost_usd\tsession\n')
    with log.open('a') as f:
        f.write(f'{dt.datetime.now():%Y-%m-%d %H:%M}\t{part}\t{a}-{b}\t{b - a + 1}\t{tr_pages}\t{attempt}\t'
                f'{minutes:.0f}\t{peak}\t{compactions}\t{res.get("total_cost_usd", "")}\t{sid}\n')
    text = str(res.get('result', ''))
    limited = (proc.returncode or res.get('is_error')) and LIMIT.search(text + stderr)
    return res, text, bool(limited), peak, compactions, minutes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book')
    ap.add_argument('--max-parts', type=int)
    ap.add_argument('--model', default='claude-opus-5-5')
    ap.add_argument('--effort', default='high')
    ap.add_argument('--wait-minutes', type=int, default=30)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    book = resolve_book(args.book)
    if not shutil.which('claude'):
        sys.exit('the claude command is not in PATH')
    (book / 'work').mkdir(exist_ok=True)
    lock = (book / 'work' / 'run.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(f'another runner is already working on {book.name}')

    done, failures = 0, {}
    if not args.dry_run:
        snapshot(book, 'Before the runner')
    while True:
        blocked = book / 'BLOCKED.md'
        if blocked.exists():
            say(f'Stopped: {blocked} exists. Read it, fix the problem, delete the file and start again.', True)
            return 1
        nxt = status_next(book)
        if nxt == 'NOPLAN':
            say(f'Stopped: sections are left that no part covers. Run: python3 pipeline/plan.py "{book.name}"', True)
            return 1
        if nxt == 'DONE':
            break
        part, a, b = nxt.split()
        a, b = int(a), int(b)
        if args.dry_run:
            print(f'Next: Part {part}, PDF {a}–{b}\nWould run: claude -p "/arabic-to-turkish {book.name} next unattended" '
                  f'--model {args.model} --effort {args.effort} --permission-mode auto')
            return 0
        if args.max_parts is not None and done >= args.max_parts:
            say(f'Paused after {done} part(s) (--max-parts). Next is Part {part}; check REVIEW-QUEUE.md, then run again.', True)
            return 0

        attempt = failures.get(part, 0) + 1
        say(f'Part {part}: PDF {a}–{b} ({b - a + 1} pages), attempt {attempt} …')
        res, text, limited, peak, compactions, minutes = run_part(book, part, a, b, args, attempt)
        if limited:
            say(f'Part {part}: usage limit reached; waiting {args.wait_minutes} min and trying again.')
            time.sleep(args.wait_minutes * 60)
            continue
        if status_next(book).split()[:1] == [part]:
            failures[part] = attempt
            say(f'Part {part}: not finished (no DOCX or CHECK file). Last words: {text[-300:]!r}')
            if attempt >= 2:
                say(f'Stopped: Part {part} failed twice. Logs in {book / "runs"}.', True)
                return 1
            continue
        snapshot(book, f'Part {part} (PDF {a}–{b})')
        done += 1
        warn = ''
        if compactions:
            warn = f'; context was compacted {compactions}× — lower part_max_pages with plan.py'
        say(f'Part {part} done in {minutes:.0f} min, peak context {peak:,} tokens{warn}.')

    say('Every part is done; making the final PDF …')
    r = subprocess.run([sys.executable, str(PIPELINE / 'make_pdf.py'), str(book)], cwd=ROOT)
    snapshot(book, 'Final PDF' if r.returncode == 0 else 'make_pdf.py failed')
    if r.returncode:
        say(f'Stopped: make_pdf.py found a problem; see {book / "work/final/report.txt"}.', True)
        return 1
    say(f'Finished: the book PDF is in {book / "pdf"}. Read REVIEW-QUEUE.md and the contact sheet in work/final/.', True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
