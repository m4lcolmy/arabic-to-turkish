#!/usr/bin/env python3
"""Translate a whole book unattended: one fresh Claude session per planned part, then the final PDF.

Usage:  python3 pipeline/run_book.py <book> [--max-parts N] [--engine auto|claude|codex] [--dry-run]

Each round asks status.py for the next planned part (plan.py makes the plan), runs
`claude -p "/arabic-to-turkish <book> next unattended"` (/english-to-turkish for a book with
"source_lang": "en") in a new session, checks that the part is done
(part PDF and CHECK file), and commits the book folder to its own local git repository, so one part can be
rolled back without touching the others. When every part is done it runs make_pdf.py and stops.

It stops early, with a desktop notification, when:
  - <book>/BLOCKED.md exists (a session could not go on without the person; read it, fix, delete it)
  - the same part fails twice
  - --max-parts parts are done (e.g. --max-parts 2 to check the first parts before the rest)
  - make_pdf.py reports a failed check
A usage limit is not a failure. A part whose session was cut off (usage limit, error) is resumed by its page
range even when its part PDF and CHECK file already exist, since the last steps (review decisions, REVIEW-QUEUE.md)
may be missing; the runner moves on only after a session that ended normally. With --engine auto (the default) a Claude usage limit hands the same part to
a ChatGPT model through the Codex CLI (`codex exec`, signed in with ChatGPT), which follows the same SKILL.md and
RULES.md and resumes from whatever files the stopped session left. Every new part tries Claude first again, so
Claude takes over by itself once its limit resets. When Codex is limited too (or with --engine claude), the
runner waits and tries the same part again.

Every session is logged to <book>/runs/ (JSON result, and a line in log.tsv with the peak context and
any compaction), so the part size in book.json "part_max_pages" can be tuned with plan.py.
Corrections and items to review from every part collect in <book>/REVIEW-QUEUE.md.

--model, --effort      default claude-opus-5-5, high
--engine               auto (Claude, Codex on a Claude usage limit), claude (wait out limits), codex (Codex only)
--fallback-model, --fallback-effort   the Codex translator, default gpt-6-astra, high
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
from common import LANGS, PIPELINE, ROOT, load_meta, resolve_book, source_lang  # noqa: E402
from review import CODEX_HOME, find_codex  # noqa: E402

TRAILER = 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
LIMIT = re.compile(r'usage limit|rate limit|limit reached|hit your (usage )?limit|overloaded|\b429\b|\b529\b'
                   r'|resets? at|resets \d', re.I)


def skill_name(book):
    """The translation skill for the book's source language: arabic-to-turkish, english-to-turkish."""
    return f'{LANGS[source_lang(load_meta(book))].lower()}-to-turkish'


def skill_file(book):
    return ROOT / '.claude' / 'skills' / skill_name(book) / 'SKILL.md'


CODEX_PROMPT = """You are the fallback translator of this unattended run: Claude is out of usage, so you do its job.
Below is the skill Claude follows (SKILL.md). Follow it exactly, all steps 0–10 in unattended mode; RULES.md is the
authority on quality and design. The request is:

    {request}

Notes for this environment (they change no rule):
- The SKILL.md below is the current one. Ignore any other copy of the skill (e.g. under .agents/skills/): it may
  be out of date.
- Read every page image (p-NNN.png, p-NNN-zoom.png, the renders in work/render/) by opening it with your image
  viewing tool. The text layer is a cross-check only, as the skill says.
- Some commands are slow: give `python3 pipeline/review.py` a timeout of at least 600 seconds and `build.py` at
  least 300 seconds.
- A part may be half done by a session that stopped (Claude ran out of usage, or the run was interrupted). Reuse
  what exists, as the skill says for a part in progress: check existing transcriptions against the images and keep
  them when right; continue the content file and CHECK file instead of starting over.
- Change only this part's files and the shared files the skill names (GLOSSARY.md, REVIEW-QUEUE.md, BLOCKED.md,
  book.json through the scripts). Never edit a finished part's transcriptions, content file, CHECK file or part PDF.
- Write "Translated by {model} (Codex fallback)" as the first line under *Result* in the CHECK file, and add
  " · translated by {model}" to the end of this part's REVIEW-QUEUE.md heading.
- Do not commit; the runner commits the part.

===== SKILL.md =====
{skill}
"""
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


def codex_stats(thread_id):
    """Peak context (tokens) and compactions of a finished Codex session, from its rollout file."""
    peak, compactions = 0, 0
    for f in (CODEX_HOME / 'sessions').glob(f'*/*/*/rollout-*-{thread_id}.jsonl') if thread_id else []:
        for line in f.open(encoding='utf-8'):
            if '"context_compacted"' in line or '"type":"compacted"' in line:
                compactions += 1
            if '"token_count"' not in line:
                continue
            try:
                u = ((json.loads(line).get('payload') or {}).get('info') or {}).get('last_token_usage') or {}
            except json.JSONDecodeError:
                continue
            peak = max(peak, u.get('input_tokens') or 0)
    return peak, compactions


def progress(tool):
    """One short line for a tool call, so the terminal shows what the session is doing."""
    i = tool.get('input') or {}
    what = i.get('file_path') or i.get('command') or i.get('skill') or i.get('pattern') or ''
    what = ' '.join(str(what).split()).replace(str(ROOT) + '/', '')
    return f'{tool.get("name")}: {what[:110]}'


def request(book, a, b, resume):
    """The skill request: the next planned part, or this part by its range when an earlier session stopped early."""
    if not resume:
        return f'{book.name} next unattended'
    return (f'{book.name} {a}-{b} unattended. Resume: an earlier session on this part stopped before the end; its '
            f'part PDF and CHECK file may exist but are not final. Go through every step, reuse what is right and finish '
            f'what is missing (independent review decisions, the REVIEW-QUEUE.md entry).')


def claude_session(book, part, args, raw, start, req):
    sid = str(uuid.uuid4())
    prompt = f'/{skill_name(book)} {req}'
    cmd = ['claude', '-p', prompt, '--model', args.model, '--effort', args.effort,
           '--permission-mode', 'auto', '--output-format', 'stream-json', '--verbose', '--session-id', sid,
           '-n', f'{book.name} · Part {part}']
    res = None
    with subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
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
    res = res or {'is_error': True, 'result': stderr[-2000:]}
    return res, str(res.get('result', '')), proc.returncode, stderr, sid, *session_stats(sid)


def codex_session(book, part, args, raw, start, req):
    """The same part through the Codex CLI: SKILL.md as the instructions, sandboxed to translations/."""
    skill = skill_file(book).read_text(encoding='utf-8').split('---', 2)[-1].strip()
    prompt = CODEX_PROMPT.format(request=req, model=args.fallback_model, skill=skill)
    last = book / 'runs' / f'part-{part}-codex-last.txt'
    last.unlink(missing_ok=True)
    cmd = [find_codex(), 'exec', '--json', '--ignore-user-config', '--skip-git-repo-check', '-C', str(ROOT),
           '-m', args.fallback_model, '-c', f'model_reasoning_effort="{args.fallback_effort}"',
           '--sandbox', 'workspace-write', '-c', 'sandbox_workspace_write.network_access=true',
           '--add-dir', str(CODEX_HOME), '-o', str(last), '-']
    thread, errors, failed = '', [], False
    with subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True) as proc:
        proc.stdin.write(prompt)
        proc.stdin.close()
        for line in proc.stdout:
            raw.write(line)
            raw.flush()
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = ev.get('item') or {}
            if ev.get('type') == 'thread.started':
                thread = ev.get('thread_id', '')
            elif ev.get('type') in ('error', 'turn.failed'):   # 'error' alone can be a retry that recovers
                failed |= ev.get('type') == 'turn.failed'
                errors.append(str(ev.get('message') or ev.get('error') or ev))
            elif ev.get('type') == 'item.started' and item.get('type') == 'command_execution':
                cmdline = re.sub(r'^/bin/(ba)?sh -lc ([\'"]?)(.*)\2$', r'\3', item.get('command', ''), flags=re.S)
                print(f'    {time.time() - start:5.0f}s  {progress({"name": "Shell", "input": {"command": cmdline}})}',
                      flush=True)
            elif ev.get('type') == 'item.completed' and item.get('type') == 'file_change':
                for c in item.get('changes') or []:
                    print(f'    {time.time() - start:5.0f}s  {c.get("kind", "edit")}: '
                          f'{str(c.get("path", "")).replace(str(ROOT) + "/", "")}', flush=True)
        stderr = proc.stderr.read()
    text = last.read_text(encoding='utf-8') if last.exists() else '\n'.join(errors) or stderr[-2000:]
    error = bool(proc.returncode or failed or not last.exists())
    res = {'is_error': error, 'result': text}
    if error:
        stderr = '\n'.join(errors) + '\n' + stderr
    return res, text, proc.returncode, stderr, thread, *codex_stats(thread)


def run_part(book, part, a, b, args, attempt, engine, resume):
    runs = book / 'runs'
    runs.mkdir(exist_ok=True)
    tag = '' if engine == 'claude' else '-codex'
    start = time.time()
    with (runs / f'part-{part}{tag}-try{attempt}.jsonl').open('w') as raw:
        session = claude_session if engine == 'claude' else codex_session
        res, text, code, stderr, sid, peak, compactions = session(book, part, args, raw, start,
                                                                  request(book, a, b, resume))
    minutes = (time.time() - start) / 60
    if stderr.strip():
        (runs / f'part-{part}{tag}-try{attempt}.stderr').write_text(stderr)
    meta = load_meta(book)
    tr_pages = meta.get('layout_pages', {}).get(part, '')
    model = args.model if engine == 'claude' else args.fallback_model
    log = runs / 'log.tsv'
    header = 'date\tpart\tpdf\tsource_pages\tturkish_pages\tattempt\tminutes\tpeak_context\tcompactions\tcost_usd\tsession'
    if not log.exists():
        log.write_text(header + '\tengine\n')
    elif not log.read_text().startswith(header + '\tengine'):
        log.write_text(log.read_text().replace(header, header + '\tengine', 1))
    with log.open('a') as f:
        f.write(f'{dt.datetime.now():%Y-%m-%d %H:%M}\t{part}\t{a}-{b}\t{b - a + 1}\t{tr_pages}\t{attempt}\t'
                f'{minutes:.0f}\t{peak}\t{compactions}\t{res.get("total_cost_usd", "")}\t{sid}\t{engine}:{model}\n')
    limited = (code or res.get('is_error')) and LIMIT.search(text + stderr)
    return res, text, bool(limited), peak, compactions, minutes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book')
    ap.add_argument('--max-parts', type=int)
    ap.add_argument('--model', default='claude-opus-5-5')
    ap.add_argument('--effort', default='high')
    ap.add_argument('--engine', choices=['auto', 'claude', 'codex'], default='auto')
    ap.add_argument('--fallback-model', default='gpt-6-astra')
    ap.add_argument('--fallback-effort', default='high')
    ap.add_argument('--wait-minutes', type=int, default=30)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    book = resolve_book(args.book)
    if args.engine != 'codex' and not shutil.which('claude'):
        sys.exit('the claude command is not in PATH')
    if args.engine != 'claude' and not find_codex():
        if args.engine == 'codex':
            sys.exit('the Codex CLI (codex) was not found')
        say('Codex CLI not found: a Claude usage limit will be waited out instead.')
        args.engine = 'claude'
    (book / 'work').mkdir(exist_ok=True)
    lock = (book / 'work' / 'run.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(f'another runner is already working on {book.name}')

    # A part whose session is under way or was cut off (limit, error, Ctrl+C): resumed first, also by a new run.
    resume_file = book / 'work' / 'resume.json'
    resume = tuple(json.loads(resume_file.read_text())) if resume_file.exists() else None
    done, failures = 0, {}
    if not args.dry_run:
        snapshot(book, 'Before the runner')
    while True:
        blocked = book / 'BLOCKED.md'
        if blocked.exists():
            say(f'Stopped: {blocked} exists. Read it, fix the problem, delete the file and start again.', True)
            return 1
        if resume:
            part, a, b = resume
        else:
            nxt = status_next(book)
            if nxt == 'NOPLAN':
                say(f'Stopped: sections are left that no part covers. Run: python3 pipeline/plan.py "{book.name}"', True)
                return 1
            if nxt == 'DONE':
                if args.dry_run:
                    print('Every part is done; a run would make the final PDF (make_pdf.py).')
                    return 0
                break
            part, a, b = nxt.split()
            a, b = int(a), int(b)
        if args.dry_run:
            print(f'Next: Part {part}, PDF {a}–{b}{" (resuming a session that was cut off)" if resume else ""}')
            if args.engine != 'codex':
                print(f'Would run: claude -p "/{skill_name(book)} {request(book, a, b, resume)}" '
                      f'--model {args.model} --effort {args.effort} --permission-mode auto')
            if args.engine != 'claude':
                print(f'{"On a Claude usage limit" if args.engine == "auto" else "Would run"}: codex exec '
                      f'-m {args.fallback_model} (effort {args.fallback_effort}, workspace-write sandbox) '
                      f'with SKILL.md and "{request(book, a, b, True if args.engine == "auto" else resume)}"')
            return 0
        if args.max_parts is not None and done >= args.max_parts:
            say(f'Paused after {done} part(s) (--max-parts). Next is Part {part}; check REVIEW-QUEUE.md, then run again.', True)
            return 0

        attempt = failures.get(part, 0) + 1
        engine = 'codex' if args.engine == 'codex' else 'claude'
        say(f'Part {part}: PDF {a}–{b} ({b - a + 1} pages), attempt {attempt}{", resuming" if resume else ""} …')
        resume_file.write_text(json.dumps([part, a, b]))
        res, text, limited, peak, compactions, minutes = run_part(book, part, a, b, args, attempt, engine, resume)
        if limited and args.engine == 'auto':
            engine, resume = 'codex', (part, a, b)   # Codex continues whatever Claude left
            say(f'Part {part}: Claude usage limit reached; handing the part to {args.fallback_model} (Codex).', True)
            res, text, limited, peak, compactions, minutes = run_part(book, part, a, b, args, attempt, engine, resume)
        if limited:
            resume = (part, a, b)
            say(f'Part {part}: usage limit reached ({engine}); waiting {args.wait_minutes} min and trying again.')
            time.sleep(args.wait_minutes * 60)
            continue
        if res.get('is_error') or status_next(book).split()[:1] == [part]:
            failures[part], resume = attempt, (part, a, b)
            say(f'Part {part}: not finished ({"session ended with an error" if res.get("is_error") else "no part PDF or CHECK file"}). '
                f'Last words: {text[-300:]!r}')
            if attempt >= 2:
                say(f'Stopped: Part {part} failed twice. Logs in {book / "runs"}.', True)
                return 1
            continue
        resume = None
        resume_file.unlink(missing_ok=True)
        if engine == 'codex':
            snapshot(book, f'Part {part} (PDF {a}–{b}), translated by {args.fallback_model} (Codex fallback)')
        else:
            snapshot(book, f'Part {part} (PDF {a}–{b})')
        done += 1
        warn = ''
        if compactions:
            warn = f'; context was compacted {compactions}× — lower part_max_pages with plan.py'
        by = f' by {args.fallback_model}' if engine == 'codex' else ''
        say(f'Part {part} done{by} in {minutes:.0f} min, peak context {peak:,} tokens{warn}.')

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
