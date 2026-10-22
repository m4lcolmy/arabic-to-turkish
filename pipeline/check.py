#!/usr/bin/env python3
"""Automatic checks for one translated part: source transcription vs. Turkish content file, page by page.
The source language is book.json "source_lang" (ar, the default, or en); a few checks differ by language.

Usage:  python3 pipeline/check.py <book> <part> [--quran FILE]

  ERROR  must be fixed, or explained in CHECK-part-NN.md (deliberate deviation / source error corrected)
  WARN   a hint only; natural Turkish may differ for good reasons. Judge it, don't force it.
  NOTE   something to report to the person (e.g. a corrected Qur'an reference)

Exit code 1 when there is at least one ERROR. The report is also saved to <book>/work/check-part-NN.txt.
"""
import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (DIGITS, PIPELINE, load_content, load_meta, norm_ar, norm_name, part_id,  # noqa: E402
                    part_pages, resolve_book, source_lang, source_pdf, transcription)

FN = re.compile(r'\[\[fn:(\d+)\]\]')
EN = re.compile(r'\[\[en:(\d+)\]\]')  # endnote marker: a superscript number, the note itself is in the notes section
MARK = re.compile(r'\[\[(?:fn|en):\d+\]\]')
HONORIFIC = re.compile(r'\((?:s\.a\.v|r\.a|a\.s|r\.anh[aü]?|k\.s)\.\)')
QURAN_FILE = PIPELINE / 'quran' / 'quran-simple-clean.txt'


# ── Reading both sides ──────────────────────────────────────────────────────
def read_transcription(path):
    """Body and footnotes of source/text/p-NNN.<lang>.md (footnotes come after the last '---' line)."""
    text = path.read_text(encoding='utf-8').replace('\ufd3f', '{').replace('\ufd3e', '}')  # ornate Qur'an brackets
    lines = re.sub(r'<!--.*?-->', '', text, flags=re.S).split('\n')
    cut = max((i for i, line in enumerate(lines) if line.strip() == '---'), default=len(lines))
    fns = []
    for line in lines[cut + 1:]:
        m = re.match(r'\s*[\[(](\d+)[\])]\s*(.*)', line)
        if m:
            fns.append(m.group(2))
        elif line.strip() and fns:
            fns[-1] += ' ' + line.strip()
    return '\n'.join(lines[:cut]), fns


def translation_texts(pg):
    body = []
    for b in pg.get('blocks', []):
        if b.get('type') == 'item' and b.get('n'):  # list number ("1."), set before the item's text
            body.append(str(b['n']))
        if b.get('text'):
            body.append(b['text'])
        if b.get('type') == 'toc':  # 'nums': optional chapter numbers printed before the titles
            body += [f'{c} {t} {n}' for c, (t, n) in zip(b.get('nums') or [''] * len(b['entries']), b['entries'])]
    return '\n'.join(body), list(pg.get('footnotes', {}).items())


def snippet(text, i, width=30):
    return '…' + text[max(0, i - width):i + width].replace('\n', ' ') + '…'


# ── Pronouns: hints for the readability pass (RULES.md §4 "Pronouns") ───────
# Inflected third-person forms only: bare "o" is too often a demonstrative ("o gün", "o kişi").
# A form followed by ’ is skipped: "O’nun", "O’dur" refer to Allah and are unambiguous.
PRON = (r'onu|ona|onun|ondan|onda|onunla|onlar|onları|onlara|onların|onlardan|onlarda|onlarla'
        r'|kendisi|kendisini|kendisine|kendisinin|kendisinden|kendileri|kendilerini|kendilerine|kendilerinin|kendilerinden')
PRON_WORD = re.compile(rf'(?<![\w’\'])(?:{PRON})(?![\w’\'])', re.I)
FN_OPENING = re.compile(rf'^\W*(?:o(?![\w’\'])|(?:\w+\s+){{0,2}}?(?:{PRON})(?![\w’\']))', re.I)  # "O …" or a form in the first 3 words
PRON_SAV = re.compile(r'(?<![\w’])(?:o|onu|ona|onun|ondan|onunla)\s+\(s\.a\.v\.\)', re.I)
PRON_LIMIT = 3  # pronoun forms in one sentence (split at . ! ? ;) before a WARN


def pronoun_hints(label, text, is_footnote, say):
    plain = re.sub(r'\[\[(?:fn|en):\d+\]\]|\^\^|\*\*', '', text)
    if is_footnote and (m := FN_OPENING.match(plain)):
        say('WARN', f'pronoun: {label} opens with a pronoun; a footnote must make sense on its own: {snippet(plain, m.end())}')
    for m in PRON_SAV.finditer(plain):
        say('WARN', f'pronoun: {label}: bare pronoun for the Prophet, name him ("Resûlullah (s.a.v.)"): {snippet(plain, m.start())}')
    masked = re.sub(r'\b(b|s|bk)\. ', r'\1  ', HONORIFIC.sub(' ', plain))  # keep "b. ", "s. 266" inside a sentence
    masked = re.sub(r'\{[^{}]*\}', '{…}', masked)  # Qur'an and hadith wording follows the standard rendering
    for sentence in re.split(r'(?<=[.!?;…])\s+|\n', masked):
        hits = PRON_WORD.findall(sentence)
        if len(hits) >= PRON_LIMIT and len({h.lower() for h in hits}) > 1:  # one form repeated = a refrain
            say('WARN', f'pronoun: {label}: {len(hits)} pronoun forms in one sentence ({", ".join(hits)}); '
                        f'check each has one clear referent: «{sentence.strip()[:90]}…»')


# ── Qur'an ──────────────────────────────────────────────────────────────────
def skel(s):
    """Consonant skeleton: survives spelling differences (Uthmani vs. standard script, hamza seats, spacing)."""
    return re.sub(r'[^ء-ي]|[اويء]', '', norm_ar(s))


class Quran:
    def __init__(self, path):
        self.sk = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            p = line.split('|')
            if len(p) == 3 and p[0].isdigit():
                self.sk[(int(p[0]), int(p[1]))] = skel(p[2])
        self.keys = sorted(self.sk)

    def span(self, s, a, b):
        return ''.join(self.sk.get((s, v), '') for v in range(a, b + 1))

    def tight(self, s, a, b, segs):
        """Smallest verse range inside s:a-b that holds every segment, or None."""
        used = set()
        for seg in segs:
            one = [v for v in range(a, b + 1) if seg in self.sk.get((s, v), '')]
            two = [v for v in range(a, b) if seg in self.span(s, v, v + 1)]
            if one:
                used.add(one[0])
            elif two:
                used |= {two[0], two[0] + 1}
            else:
                return None
        return (s, min(used), max(used))

    def locate(self, segs):
        """All places (s, a, b) holding every segment, searching around the longest segment's hits."""
        key = max(segs, key=len)
        found = set()
        for i, (s, a) in enumerate(self.keys):
            nxt = self.keys[i + 1] if i + 1 < len(self.keys) else None
            if key in self.sk[(s, a)] or (nxt and nxt[0] == s and key in self.sk[(s, a)] + self.sk[nxt]):
                t = self.tight(s, max(1, a - 3), a + 4, segs)
                if t:
                    found.add(t)
        return sorted(found)


def load_suras():
    ar, tr = {}, {}
    for line in (PIPELINE / 'quran' / 'suras.tsv').read_text(encoding='utf-8').splitlines():
        if line.startswith('#') or not line.strip():
            continue
        n, ars, trs = line.split('\t')
        for x in ars.split(','):
            ar[ar_key(x)] = int(n)
        for x in trs.split(','):
            tr[tr_key(x)] = int(n)
    return ar, tr


def ar_key(name):
    k = norm_name(name).replace('سوره', '').replace(' ', '')
    return k[2:] if k.startswith('ال') and len(k) > 4 else k


def tr_key(name):
    return re.sub(r'\bsuresi\b', '', norm_name(name)).replace(' ', '')


SRC_REF = re.compile(r'\{([^{}]*)\}(?:\s|\^\^|\[\[fn:\d+\]\]|[،,])*\[([^\[\]:]+):\s*([\d٠-٩]+)(?:\s*[-–]\s*([\d٠-٩]+))?\s*\]')
TR_REF = re.compile(r'\[(?!\[)([^\[\]:]{2,40}?):\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*\]')


def src_refs(text, suras):
    out = []
    for m in SRC_REF.finditer(text):
        a = int(m.group(3).translate(DIGITS))
        b = int((m.group(4) or m.group(3)).translate(DIGITS))
        out.append((m.group(1), suras.get(ar_key(m.group(2))), a, b, f'[{m.group(2).strip()}: {m.group(3)}{"-" + m.group(4) if m.group(4) else ""}]'))
    return out


def tr_refs(text, suras):
    out = []
    for m in TR_REF.finditer(text):
        if m.group(1).strip() == 'fn':
            continue
        a, b = int(m.group(2)), int(m.group(3) or m.group(2))
        out.append((suras.get(tr_key(m.group(1))), a, b, m.group(0)))
    return out


def fmt(s, a, b):
    return f'{s}:{a}' + (f'-{b}' if b != a else '')


def check_verses(src, tr, quran, suras_ar, suras_tr, say):
    sr, trr = src_refs(src, suras_ar), tr_refs(tr, suras_tr)
    if len(sr) != len(trr):
        say('ERROR', f"Qur'an references: source has {len(sr)}, translation {len(trr)}. "
                     f"Source: {', '.join(r[4] for r in sr) or '-'} · Translation: {', '.join(r[3] for r in trr) or '-'}")
        return
    verified = 0
    for (quote, s, a, b, raw), (ts, ta, tb, traw) in zip(sr, trr):
        if s is None:
            say('WARN', f'unknown sura name in source reference {raw}; add it to pipeline/quran/suras.tsv')
            continue
        if ts is None:
            say('ERROR', f'unknown sura name in translation reference {traw}')
            continue
        printed, given = (s, a, b), (ts, ta, tb)
        if not quran:
            if given != printed:
                say('ERROR', f'{traw} differs from the source {raw} (if this is a correction, verify it and log it)')
            continue
        segs = [k for k in (skel(x) for x in re.split(r'\*|…|\.{2,}|۞', quote)) if len(k) >= 8]
        if not segs:
            say('WARN', f'{raw}: quote too short to verify automatically')
            continue
        t = quran.tight(s, a, b, segs)
        if t:
            verified += 1
            if given == printed:
                if t != printed:
                    say('WARN', f'{raw}: the quoted words are only in {fmt(*t)}; the reference is wider than the quote')
            elif given == t:
                say('NOTE', f'{raw} narrowed to {traw}: the quote is only in {fmt(*t)}. Log it under "Source errors corrected"')
            else:
                say('ERROR', f'{traw} is wrong: the source {raw} is correct')
            continue
        hits = quran.locate(segs)
        if len(hits) == 1:
            actual = hits[0]
            if given == actual or (given[0] == actual[0] and given[1] <= actual[1] and actual[2] <= given[2]):
                say('NOTE', f'source error corrected: printed {raw}, the quote is at {fmt(*actual)}; translation has {traw}. '
                            'Log it under "Source errors corrected" and report it')
            else:
                say('ERROR', f'printed {raw} is wrong: the quote is at {fmt(*actual)}; translation has {traw}')
        elif hits:
            say('WARN', f'{raw}: quote not in the printed verses; it matches {", ".join(fmt(*h) for h in hits)}. Check by hand')
        else:
            say('WARN', f'{raw}: quote not found in the Qur\'an text (spelling or transcription?). Check by hand')
    if verified:
        say('OK', f"{verified} Qur'an reference(s) verified against the text")


# ── Qur'an references in English sources ───────────────────────────────────
# English books cite verses by number: (2:255), [al-Baqarah 2:255-256], (Qur'an 3:7). The quoted wording is an
# English rendering, so only the references are checked: they must exist and match the Turkish [Bakara: 255].
EN_REF = re.compile(r'(?<![\d:.,/])(\d{1,3})\s*:\s*(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?(?![\d:])')
NOT_QURAN = re.compile(r"(?:bukh[aā]r[iī]|muslim|tirmidh|d[aā]w[uū]d|nas[aā]|m[aā]jah|ahmad|musnad|muwa[tṭ][tṭ]a|"
                       r"vol|volume|hadith|ḥad[iī]th|no\.|book|pp?\.)[^()\[\]\n]{0,12}$", re.I)
EN_NAME_REF = re.compile(r"[\[(](?:s[uū]rah?|s[uū]rat)?\s*(?:[aA][a-z]{0,2}-)?[A-Z][\w'‘’ʿʾ-]+,?\s*:?\s*(?:ayah|verse|v\.)?\s*\d{1,3}"
                         r"(?:\s*[-–]\s*\d{1,3})?\s*[\])]")
NOT_SURA = re.compile(NOT_QURAN.pattern.removesuffix(r'[^()\[\]\n]{0,12}$') + r'|chapter|page|part|section|ibid|figure|table'
                      r'|sunan|sa[hḥ][iī][hḥ]|j[aā]mi', re.I)


def en_name_refs(text):
    """Verse references by sura name only, e.g. (al-Baqarah: 255)."""
    return [m for m in EN_NAME_REF.finditer(text) if not EN_REF.search(m.group(0)) and not NOT_SURA.search(m.group(0))]


def sura_skel(name):
    """Consonants of a transliterated sura name, so al-Baqarah ~ Bakara, al-Ma'idah ~ Mâide, Yusuf ~ Yûsuf."""
    k = norm_name(re.sub(r'(?i)\b(?:s[uū]rah?|s[uū]rat|suresi)\b', '', name)).replace('ş', 's').replace('ç', 'c')
    k = re.sub(r'^(?:a[lnrtdsz]|ash|adh|ath)\s', '', k).translate(str.maketrans('qwj', 'kvc'))
    return re.sub(r'(.)\1+', r'\1', re.sub(r'[^a-z]|[aeiouhy]', '', k))


def en_refs(text):
    """Numeric verse references in English text: [(s, a, b, raw, span)]; hadith and volume numbers are skipped."""
    out = []
    for m in EN_REF.finditer(text):
        s, a = int(m.group(1)), int(m.group(2))
        b = int(m.group(3) or a)
        if not 1 <= s <= 114 or b < a or NOT_QURAN.search(text[max(0, m.start() - 30):m.start()]):
            continue
        out.append((s, a, b, m.group(0), m.span()))
    return out


def check_verses_en(src, tr, quran, suras_tr, say):
    sr = en_refs(src)
    for m in en_name_refs(src):  # sura None: by name only
        v = [int(x) for x in re.findall(r'\d+', m.group(0))]
        sr.append((None, v[0], v[-1], m.group(0), m.span()))
    sr.sort(key=lambda r: r[4])
    trr = tr_refs(tr, suras_tr)
    if len(sr) != len(trr):
        say('ERROR', f"Qur'an references: source has {len(sr)}, translation {len(trr)}. "
                     f"Source: {', '.join(r[3] for r in sr) or '-'} · Translation: {', '.join(r[3] for r in trr) or '-'}")
        return
    exists = (lambda s, a, b: all((s, v) in quran.sk for v in range(a, b + 1))) if quran else (lambda *_: True)
    for (s, a, b, raw, _), (ts, ta, tb, traw) in zip(sr, trr):
        if ts is None:
            say('ERROR', f'unknown sura name in translation reference {traw}')
        elif s is None:  # by sura name only
            name = re.sub(r'[\[\](),:\d–-]+$|^[\[(]', '', raw.strip()).strip()
            if (ta, tb) != (a, b):
                say('ERROR', f'{traw} differs from the source {raw} (if this is a correction, verify it and log it)')
            elif sura_skel(name) != sura_skel(traw.split(':')[0].strip('[ ')):
                say('WARN', f'{raw}: check by hand that the sura is the one in {traw}')
        elif (ts, ta, tb) == (s, a, b):
            if not exists(s, a, b):
                say('WARN', f'{raw} does not exist in the Qur\'an; find the quoted verse and correct the reference')
        elif not exists(s, a, b) and exists(ts, ta, tb):
            say('NOTE', f'printed {raw} does not exist; translation has {traw}. Verify the quote is there, log it '
                        'under "Source errors corrected" and report it')
        else:
            say('ERROR', f'{traw} differs from the source {raw} (if this is a correction, verify it and log it)')


# English salutations: ﷺ-type forms are only for the Prophet; "peace be upon him" may be any prophet's (a.s.)
EN_SAV = re.compile(r"ﷺ|\bp\.?b\.?u\.?h\b\.?|\(s\.?a\.?w\.?s?\.?\)|\(s\.?a\.?a\.?w?\.?s\.?\)"
                    r"|[sṣ]all[aā]?\s*(?:a?ll[aā]hu|ll[aā]hu)\s*['ʿ‘’]?\s*alayhi\s*wa\s*-?\s*sallam", re.I)
EN_PEACE = re.compile(r"peace (?:and blessings )?(?:of (?:allah|god) )?be upon (?:him|them|her)|\(a\.?s\.?\)"
                      r"|['ʿ‘’]?alayhi(?:s|\s*a?l?-?)\s*-?\s*sal[aā]m", re.I)


def check_salutations_en(src, tr, say):
    sav, peace = len(EN_SAV.findall(src)), len(EN_PEACE.findall(src))
    t_sav, t_as = tr.count('(s.a.v.)'), tr.count('(a.s.)')
    if sav + peace != t_sav + t_as:
        say('ERROR', f'salutations: source has {sav} for the Prophet (ﷺ, pbuh, ṣallā Allāhu…) and {peace} '
                     f'"peace be upon him"-type; translation has {t_sav} "(s.a.v.)" and {t_as} "(a.s.)"')
    elif sav > t_sav:
        say('WARN', f'salutations: {sav} ﷺ-type forms in the source but only {t_sav} "(s.a.v.)"')


# ── Simple counts ───────────────────────────────────────────────────────────
def numbers(s):
    return re.findall(r'\d+', MARK.sub(' ', s.translate(DIGITS)))


ANY_REF = re.compile(r'\[(?!\[)[^\[\]:]{1,40}:\s*[\d٠-٩]+(?:\s*[-–]\s*[\d٠-٩]+)?\s*\]')


def without_refs(s, lang='ar', turkish=False):
    """Verse references are compared by the Qur'an check, not the number check."""
    if lang == 'en' and not turkish:
        for i, j in sorted([r[4] for r in en_refs(s)] + [m.span() for m in en_name_refs(s)], reverse=True):
            s = s[:i] + '\0' + s[j:]
        s = re.sub(r'[\[(][^\[\]()\n]{0,40}?\0[^\[\]()\n]{0,5}[\])]', ' ', s).replace('\0', ' ')  # with its brackets
    return ANY_REF.sub(' ', s)


def punct(s):
    s = MARK.sub('', s).replace('؟', '?')
    return {'!': s.count('!'), '?': s.count('?'), '!.': s.count('!.'),
            '..': len(re.findall(r'(?<![.…])\.\.(?![.])', s)), '…': s.count('…') + s.count('...') + s.count('. . .')}


def marks(s, turkish, lang='ar'):
    s = MARK.sub('', s)
    if turkish:
        s = HONORIFIC.sub('', s)
    if turkish or lang == 'en':  # hyphens inside words (al-Bukhārī, well-known) are not dashes
        dashes = len(re.findall(r'—|(?<!\d)–(?!\d)| - ', s))
    else:
        dashes = len(re.findall(r'(?<!\d)\s*[-–—]\s*(?!\d)', s))
    return {'[ ]': s.count('['), '{ }': s.count('{'), '( )': s.count('('), '« »': s.count('«'), 'dashes': dashes}


def diff(a, b):
    return ', '.join(f'"{k}" {a[k]} → {b[k]}' for k in a if a[k] != b[k])


# ── Per page ────────────────────────────────────────────────────────────────
def check_page(n, pg, book, meta, quran, suras, say):
    lang = source_lang(meta)
    tr_body, tr_fns = translation_texts(pg)
    tr_all = tr_body + '\n' + '\n'.join(t for _, t in tr_fns)

    # Turkish side on its own
    for label, text in [('body', tr_body)] + [(f'footnote {i}', t) for i, t in tr_fns]:
        if text.count('^^') % 2 or text.count('**') % 2 or text.count('++') % 2:
            say('ERROR', f"{label}: unbalanced ^^, ** or ++ markup")
        if text.count('{') != text.count('}'):
            say('ERROR', f'{label}: unbalanced {{ }}')
        if m := re.search(r'[؀-ۿ]', text):
            say('WARN', f'{label}: Arabic script left in the Turkish: {snippet(text, m.start())}')
        pronoun_hints(label, text, label != 'body', say)
    ids = [int(x) for x in FN.findall(tr_body)]
    fn_ids = [int(i) for i, _ in tr_fns]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        say('ERROR', f'footnote markers out of order or repeated: {ids}')
    if set(ids) != set(fn_ids):
        say('ERROR', f'footnote markers {sorted(ids)} do not match footnote texts {sorted(fn_ids)}')

    src_path = transcription(book, n, meta)
    if not src_path.exists():
        say('WARN', f'no transcription ({src_path.relative_to(book)}); source comparison skipped')
        return
    src_body, src_fns = read_transcription(src_path)
    src_all = src_body + '\n' + '\n'.join(src_fns)

    # Footnotes
    src_ids = FN.findall(src_body)
    if len(src_ids) != len(src_fns):
        say('WARN', f'transcription: {len(src_ids)} footnote markers but {len(src_fns)} footnotes')
    if (len(src_ids), len(src_fns)) != (len(ids), len(tr_fns)):
        say('ERROR', f'footnotes: source {len(src_ids)} markers / {len(src_fns)} notes, '
                     f'translation {len(ids)} markers / {len(tr_fns)} notes')

    # Endnote markers
    src_en, tr_en = EN.findall(src_body), EN.findall(tr_body)
    if src_en != tr_en:
        say('ERROR', f'endnote markers: source {", ".join(src_en) or "none"}, translation {", ".join(tr_en) or "none"}')

    # ﷺ
    if lang == 'en':
        check_salutations_en(src_all, tr_all, say)
    else:
        sav_src = src_all.count('ﷺ') + norm_ar(src_all.replace('ﷺ', '')).count('صلي الله عليه وسلم')
        sav_tr = tr_all.count('(s.a.v.)')
        if sav_src != sav_tr:
            say('ERROR', f'ﷺ appears {sav_src}×, "(s.a.v.)" {sav_tr}×')

    # Numbers
    ns = Counter(numbers(without_refs(src_all, lang)))
    nt = Counter(numbers(without_refs(tr_all, lang, turkish=True)))
    for num, k in (ns - nt).items():
        i = src_all.translate(DIGITS).find(num)
        say('ERROR', f'number {num} missing from the translation{f" ({k}×)" if k > 1 else ""}: {snippet(src_all, i)}')
    for num in (nt - ns):
        i = tr_all.find(num)
        say('WARN', f'number {num} is in the translation but not the source: {snippet(tr_all, i)}')

    # Text layer cross-check: numbers the transcription may have missed
    layer = subprocess.run(['pdftotext', '-f', str(n), '-l', str(n), '-raw', str(source_pdf(book)), '-'],
                           capture_output=True, text=True).stdout
    printed_no = n - meta['page_offset'] if meta.get('page_offset') is not None else None
    known = set(numbers(src_all)) | set(EN.findall(src_body))  # endnote markers are numbers in the text layer
    missed = sorted({x for x in numbers(layer) if int(x) >= 10 and int(x) != printed_no} - known, key=int)
    if missed:
        say('WARN', f'PDF text layer has numbers the transcription lacks: {", ".join(missed)}')

    if lang == 'en':  # note markers out of the way: "[[en:1]]" would read as a reference "[en: 1]"
        check_verses_en(MARK.sub('', src_all), MARK.sub('', tr_all), quran, suras[1], say)
    else:
        check_verses(src_all, tr_all, quran, *suras, say)

    # Punctuation and emphasis marks: hints only
    if d := diff(punct(src_all), punct(tr_all)):
        say('WARN', f'punctuation counts differ: {d}')
    if lang == 'en':  # (2:255) becomes [Bakara: 255]: references are not brackets of the text
        src_marks, tr_marks = marks(without_refs(src_all, lang), False, lang), marks(without_refs(tr_all, lang, True), True)
    else:
        src_marks, tr_marks = marks(src_all, False), marks(tr_all, True)
    if d := diff(src_marks, tr_marks):
        say('WARN', f'brackets/dashes differ: {d}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book')
    ap.add_argument('part')
    ap.add_argument('--quran', type=Path, default=QURAN_FILE)
    args = ap.parse_args()

    book, part = resolve_book(args.book), part_id(args.part)
    meta = load_meta(book)
    first, last = part_pages(book, part)
    pages = load_content(book, part)
    quran = Quran(args.quran) if args.quran.exists() else None
    suras = load_suras()

    lines, counts = [], Counter()

    def out(s=''):
        lines.append(s)
        print(s)

    out(f'Part {part} · {book.name} · PDF pages {first}–{last}')
    if not quran:
        out(f"  (Qur'an text not installed: references are only compared with the source. Run pipeline/quran/fetch.sh)")
    if len(pages) != last - first + 1:
        out(f'  ERROR  content file has {len(pages)} pages, the range {first}–{last} has {last - first + 1}')
        counts['ERROR'] += 1
    fn_pages = {}  # footnote id → first page using it: make.js keys footnotes by id across the whole part
    for i, pg in enumerate(pages):
        n = first + i
        out(f'\n── PDF page {n} ' + '─' * 50)
        if pg.get('type') in ('cover', 'blank'):
            out(f"  {pg['type']}: skipped")
            continue
        page_items = []
        check_page(n, pg, book, meta, quran, suras, lambda lvl, msg: page_items.append((lvl, msg)))
        for fid in pg.get('footnotes', {}):
            if fid in fn_pages:
                page_items.append(('ERROR', f'footnote id {fid} is already used on PDF page {fn_pages[fid]}: '
                                            'ids must be unique across the part, or the notes land on the wrong page'))
            fn_pages.setdefault(fid, n)
        for lvl, msg in page_items:
            counts[lvl] += 1
            out(f'  {lvl:<5}  {msg}')
        if not page_items:
            out('  OK     nothing to report')

    out(f'\nSummary: {counts["ERROR"]} error(s), {counts["WARN"]} warning(s), {counts["NOTE"]} note(s)')
    report = book / 'work' / f'check-part-{part}.txt'
    report.parent.mkdir(exist_ok=True)
    report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Saved to {report}')
    sys.exit(1 if counts['ERROR'] else 0)


if __name__ == '__main__':
    main()
