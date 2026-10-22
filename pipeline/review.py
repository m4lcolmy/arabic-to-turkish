#!/usr/bin/env python3
"""Independent review of a translated part by a ChatGPT model (skill step 9).

Usage:  python3 pipeline/review.py <book> NN [--model M] [--effort E] [--timeout MIN]

Sends the part's source page images, the transcriptions, the Turkish content file, RULES.md (and RULES-EN.md
for an English book), the glossary
the part's CHECK file (so known deliberate deviations are not raised again) and the part's entry in
REVIEW-QUEUE.md, if any, to a ChatGPT model through the Codex CLI (`codex exec`, signed in with ChatGPT: no
API key needed). The model only reads; it changes nothing. It reports findings (R1, R2 …) and gives an opinion
on every open decision (Q1, Q2 …: the *Please review* items and the deliberate deviations worth a look).
Both are written to <book>/reviews/part-NN.json and printed, for the translating session to verify against
the source and apply or reject (the skill, step 9).

--model     default gpt-6.1-sol
--effort    reasoning effort, default medium
--timeout   minutes, default 9 (fits one shell call of the translating session)

Exit code 0: findings written (possibly none). 2: the review could not run (codex missing, not signed in,
timeout, unreadable answer); the session logs that the review was skipped and goes on.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (LANGS, PIPELINE, ROOT, content_file, load_meta, part_id, part_pages,  # noqa: E402
                    resolve_book, source_lang, transcription)

CODEX_CANDIDATES = ['/usr/lib/chatgpt/resources/codex']
CODEX_HOME = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))

CATEGORIES = ['omission', 'addition', 'mistranslation', 'number-or-reference', 'terminology',
              'naturalness', 'pronoun', 'punctuation', 'other']

SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['summary', 'findings', 'open_items'],
    'properties': {
        'summary': {'type': 'string'},
        'open_items': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['item', 'verdict', 'recommended', 'reason'],
                'properties': {
                    'item': {'type': 'string'},
                    'verdict': {'type': 'string', 'enum': ['keep', 'change']},
                    'recommended': {'type': 'string'},
                    'reason': {'type': 'string'},
                },
            },
        },
        'findings': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['page', 'severity', 'category', 'source', 'turkish', 'proposed', 'reason'],
                'properties': {
                    'page': {'type': 'integer'},
                    'severity': {'type': 'string', 'enum': ['error', 'suggestion']},
                    'category': {'type': 'string', 'enum': CATEGORIES},
                    'source': {'type': 'string'},
                    'turkish': {'type': 'string'},
                    'proposed': {'type': 'string'},
                    'reason': {'type': 'string'},
                },
            },
        },
    },
}

PROMPT = """You are an independent reviewer of an {lang} → Turkish book translation. Another translator made it;
your job is to find what they got wrong. You change nothing yourself: you only report.

Attached are the images of the source PDF pages {a}–{b} (in order, one image per page). Below are the rules the
translation must follow, the book's glossary, the transcription of each page, the Turkish content file, the
translator's own completeness check and the translator's open decisions for this part.

Compare the Turkish with the source page images (the transcriptions are a help; the images are the authority),
sentence by sentence, and report:
- error: something missing or added; a meaning changed or mistranslated; a wrong number, verse/hadith reference,
  name or date; a sentence whose pronoun can point to two things in a way that changes the meaning.
- suggestion: a clearly better Turkish word, an unnatural or stiff sentence a Turkish reader would stumble on, a
  term used inconsistently with the glossary or earlier usage without a reason.

Do not report:
- anything the completeness check lists as a deliberate deviation or a corrected source error, unless the reason
  given there is wrong;
- greetings, farewells and "we continue the series" lines left out (a book-specific rule);
- layout, markup (^^ %% ~~ && ** __ ++ [[fn:]]), page breaks or the `cont` mechanism;
- harmless matters of taste. Natural, literate Turkish that keeps the meaning and the author's voice is correct.

For each finding give the PDF page number, the {lang} words concerned (copied from the source), the Turkish
text exactly as it appears in the content file (so it can be searched for), your proposed Turkish replacement
for that same text (empty when the fix is only to add a missing passage elsewhere: then give the missing
Turkish in "proposed" and say where in "reason"), and a short reason in English. Be precise and sparing: every
finding will be checked against the source by hand. If the translation is sound, return an empty list.
"summary": two or three sentences in English on the overall quality.

"open_items": the translator left some decisions open for the reader (the items under *Please review* and
*Deliberate deviations worth a look* in the open decisions below; when that section is empty, the items marked
*Please review* in the completeness check). Give your opinion on every one of them, in order: "item" names it
in a few words, "verdict" is keep (the translator's choice is best) or change, "recommended" is the exact Turkish
you recommend (the current choice when keeping; one of the listed alternatives or your own when changing; for a
yes/no item such as keeping or cutting a passage, say which), "reason" one or two sentences in English. Judge
by the source, the rules and natural Turkish; listed alternatives get no preference over the current choice.

===== RULES.md =====
{rules}

===== GLOSSARY.md =====
{glossary}

===== Source transcriptions (PDF pages {a}–{b}) =====
{transcriptions}

===== Turkish content file: build/content/part-{part}.js =====
{content}

===== Translator's completeness check: CHECK-part-{part}.md =====
{check}

===== Open decisions: this part's entry in REVIEW-QUEUE.md =====
{queue}
"""


def find_codex():
    for c in [shutil.which('codex'), *CODEX_CANDIDATES,
              *map(str, Path.home().glob('.vscode/extensions/openai.chatgpt-*/bin/*/codex'))]:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return None


def read(p):
    return p.read_text(encoding='utf-8') if p.exists() else '(missing)'


def queue_entry(book, part):
    """This part's section of REVIEW-QUEUE.md (open decisions of an unattended run), or '' when it has none."""
    q = book / 'REVIEW-QUEUE.md'
    if not q.exists():
        return ''
    m = re.search(rf'^## Part {part}\b.*?(?=^## Part |\Z)', q.read_text(encoding='utf-8'), re.M | re.S)
    return m.group(0).strip() if m else ''


def fail(msg):
    print(f'review skipped: {msg}', file=sys.stderr)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book')
    ap.add_argument('part')
    ap.add_argument('--model', default='gpt-6.1-sol')
    ap.add_argument('--effort', default='medium')
    ap.add_argument('--timeout', type=float, default=9)
    args = ap.parse_args()

    book = resolve_book(args.book)
    part = part_id(args.part)
    a, b = part_pages(book, part)
    codex = find_codex()
    if not codex:
        fail('the Codex CLI (codex) was not found; install the ChatGPT desktop app or `npm i -g @openai/codex`')
    if not (CODEX_HOME / 'auth.json').exists():
        fail('Codex is not signed in; run `codex login` once')
    if not content_file(book, part).exists():
        fail(f'{content_file(book, part)} does not exist')

    pages = book / 'work' / 'pages'
    if not all((pages / f'p-{n:03d}.png').exists() for n in range(a, b + 1)):
        subprocess.run([sys.executable, str(PIPELINE / 'pages.py'), str(book), f'{a}-{b}'],
                       check=True, capture_output=True)
    images = [str(pages / f'p-{n:03d}.png') for n in range(a, b + 1)]
    meta = load_meta(book)
    lang = source_lang(meta)
    transcriptions = '\n\n'.join(f'----- PDF page {n} -----\n' + read(transcription(book, n, meta))
                                 for n in range(a, b + 1))
    rules = read(ROOT / 'RULES.md')
    if lang == 'en':
        rules += '\n\n===== RULES-EN.md (English sources: it overrides RULES.md where they differ) =====\n' + read(ROOT / 'RULES-EN.md')
    prompt = PROMPT.format(a=a, b=b, part=part, lang=LANGS[lang], rules=rules, glossary=read(book / 'GLOSSARY.md'),
                           transcriptions=transcriptions, content=read(content_file(book, part)),
                           check=read(book / f'CHECK-part-{part}.md'),
                           queue=queue_entry(book, part) or '(none yet: use the completeness check)')

    with tempfile.TemporaryDirectory(prefix='review-') as tmp:
        tmp = Path(tmp)
        (tmp / 'schema.json').write_text(json.dumps(SCHEMA))
        out = tmp / 'answer.json'
        cmd = [codex, 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
               '--sandbox', 'read-only', '-C', str(tmp), '--color', 'never',
               '-c', f'model_reasoning_effort="{args.effort}"',
               '--output-schema', str(tmp / 'schema.json'), '-o', str(out)]
        if args.model:
            cmd += ['-m', args.model]
        for img in images:
            cmd += [f'--image={img}']
        start = time.time()
        try:
            r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=args.timeout * 60)
        except subprocess.TimeoutExpired:
            fail(f'no answer within {args.timeout:g} minutes')
        if r.returncode or not out.exists():
            fail(f'codex exited with {r.returncode}: {(r.stderr or r.stdout)[-1500:]}')
        try:
            answer = json.loads(out.read_text())
        except json.JSONDecodeError:
            fail(f'unreadable answer: {out.read_text()[:500]}')

    answer = {'part': part, 'pdf_pages': [a, b], 'model': args.model, 'effort': args.effort,
              'minutes': round((time.time() - start) / 60, 1), **answer}
    (book / 'reviews').mkdir(exist_ok=True)
    dest = book / 'reviews' / f'part-{part}.json'
    dest.write_text(json.dumps(answer, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    f, o = answer['findings'], answer['open_items']
    print(f'Independent review of Part {part} by {answer["model"]} ({answer["minutes"]} min): '
          f'{sum(x["severity"] == "error" for x in f)} error(s), '
          f'{sum(x["severity"] == "suggestion" for x in f)} suggestion(s); '
          f'{len(o)} open decision(s), {sum(x["verdict"] == "change" for x in o)} to change. '
          f'Saved to {dest.relative_to(ROOT)}\n')
    print(answer['summary'] + '\n')
    for i, x in enumerate(f, 1):
        print(f'R{i} · p. {x["page"]} · {x["severity"]} · {x["category"]}\n'
              f'   SRC: {x["source"]}\n   TR:  {x["turkish"]}\n   NEW: {x["proposed"]}\n   WHY: {x["reason"]}\n')
    if o:
        print('Open decisions:\n')
    for i, x in enumerate(o, 1):
        print(f'Q{i} · {x["verdict"]} · {x["item"]}\n   USE: {x["recommended"]}\n   WHY: {x["reason"]}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
