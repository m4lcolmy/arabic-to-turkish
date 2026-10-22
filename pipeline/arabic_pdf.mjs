// The Arabic book as a PDF whose text can be selected, copied and searched, made from its page
// transcriptions (<book>/source/text/p-NNN.ar.md) by Nuskha's PDF builder (~/code/Nuskha,
// src/lib/pdf): Typst sets the pages in Amiri, then a hidden text layer is written over the words, so
// that viewers copy the Arabic as written, vowel marks and all. (Arabic PDFs made with Word or
// InDesign often copy «الأولى» as «األوىل» and «لمن» as «ملن».)
//
//   node pipeline/arabic_pdf.mjs <book>            → <book>/output/<Arabic title>.pdf, then the readback check
//   node pipeline/arabic_pdf.mjs <book> --library  … and put it in ~/Library in place of the old copies
//   --dry-run   with --library: only say what would be moved and copied
//   --pages     readback misses page by page        --no-check  skip the readback check
//   NUSKHA=<Nuskha folder> (default ~/code/Nuskha)   LIBRARY=<folder> (default ~/Library)
//
// <book> is any of the book's names, as for the other pipeline scripts. What goes in is set in the
// "arabic_pdf" section of book.json; .claude/skills/arabic-pdf/SKILL.md describes it.
// Markup as in the transcriptions: **bold**, __underline__, ^^ %% ~~ && colours, [[fn:N]] notes,
// «**first hemistich / second hemistich**» a line of verse; «[الروم: 41]» is set small and grey.

import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { homedir, tmpdir } from 'node:os';
import { basename, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = resolve(import.meta.dirname, '..');
const NUSKHA = process.env.NUSKHA ?? join(homedir(), 'code/Nuskha');
const LIBRARY = process.env.LIBRARY ?? join(homedir(), 'Library');
const FALLBACK_FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'; // symbols Amiri lacks (☚ ♦)
const MARKER = 'text-edition'; // in the PDF's keywords: a file this script made

function die(msg) {
  console.error(`error: ${msg}`);
  process.exit(2);
}

const args = process.argv.slice(2);
const flag = (f) => {
  const i = args.indexOf(f);
  return i >= 0 && args.splice(i, 1).length > 0;
};
const TO_LIBRARY = flag('--library');
const NO_CHECK = flag('--no-check');
const PER_PAGE = flag('--pages');
const DRY_RUN = flag('--dry-run');
if (args.length !== 1) die('usage: node pipeline/arabic_pdf.mjs <book> [--library [--dry-run]] [--pages] [--no-check]');

/** The book's folder, found by pipeline/common.py as for the other scripts. */
function resolveBook(query) {
  try {
    const code = 'import sys; sys.path.insert(0, sys.argv[1]); from common import resolve_book; print(resolve_book(sys.argv[2]))';
    return execFileSync('python3', ['-c', code, join(ROOT, 'pipeline'), query], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
  } catch {
    process.exit(2);
  }
}

const BOOK = resolveBook(args[0]);
const meta = JSON.parse(readFileSync(join(BOOK, 'book.json'), 'utf8'));
const cfg = meta.arabic_pdf ?? die(`no "arabic_pdf" section in ${join(BOOK, 'book.json')} (see .claude/skills/arabic-pdf/SKILL.md)`);
const TITLE = cfg.title ?? meta.title_ar ?? die('no title: set arabic_pdf.title');
const AUTHOR = cfg.author ?? die('no author: set arabic_pdf.author (in Arabic)');
const [FIRST, LAST] = cfg.text ?? die('no text pages: set arabic_pdf.text to [first, last]');
const CONTENTS = cfg.contents ?? [];
const SKIP = new Set([...(cfg.skip ?? []), ...CONTENTS]);
const BACK = cfg.back ?? [];
// Books made before the output/ folder keep their pdf/ folder
const OUTDIR = existsSync(join(BOOK, 'pdf')) && !existsSync(join(BOOK, 'output')) ? 'pdf' : 'output';
const OUT = join(BOOK, OUTDIR, cfg.file ?? `${TITLE}.pdf`);

if (!existsSync(join(NUSKHA, 'src/lib/pdf/make.ts'))) die(`Nuskha not found at ${NUSKHA} (set NUSKHA=<folder>)`);
if (!existsSync(join(NUSKHA, 'node_modules/@myriaddreamin/typst-ts-web-compiler'))) die(`run "npm install" in ${NUSKHA} first`);
const nuskha = (p) => import(pathToFileURL(join(NUSKHA, p)).href);
const { template, SIZE, str } = await nuskha('src/lib/pdf/template.ts');
const { renderPdf } = await nuskha('src/lib/pdf/make.ts');
const { advances } = await nuskha('src/lib/pdf/metrics.ts');
const { COVER_PATH } = await nuskha('src/lib/pdf/protocol.ts');
const { num } = await nuskha('src/lib/format.ts');
const typst = await nuskha('node_modules/@myriaddreamin/typst-ts-web-compiler/pkg/wasm-pack-shim.mjs');

// --- the pages ------------------------------------------------------------------------------------

const pagePath = (n) => join(BOOK, 'source/text', `p-${String(n).padStart(3, '0')}.ar.md`);

// Every page that goes in must be transcribed; the cover (an image) and skipped pages need not be.
const needed = [...range(FIRST, LAST).filter((n) => !SKIP.has(n)), ...BACK, ...CONTENTS];
const missing = needed.filter((n) => !existsSync(pagePath(n)));
if (missing.length) die(`pages not transcribed yet: ${spans(missing)}`);

function range(a, b) {
  return Array.from({ length: b - a + 1 }, (_, i) => a + i);
}

/** 3, 4, 5, 9 → «3–5, 9» */
function spans(list) {
  const out = [];
  for (const n of [...new Set(list)].sort((a, b) => a - b)) {
    const last = out.at(-1);
    if (last && n === last[1] + 1) last[1] = n;
    else out.push([n, n]);
  }
  return out.map(([a, b]) => (a === b ? `${a}` : `${a}–${b}`)).join(', ');
}

/**
 * One page: its blocks (a line break inside a paragraph read as a space, or as nothing before
 * punctuation the source wrapped onto a line of its own), and its notes, a paragraph per line (a
 * line without «[N]» carries on the note above it; at the top, `carried` carries on the last note of
 * the page before). Note markers become [[fn:PAGE-N]], since each page numbers its notes from 1.
 */
function readPage(n) {
  const text = readFileSync(pagePath(n), 'utf8').replace(/<!--[\s\S]*?-->/g, '');
  const [body, foot = ''] = text.split(/\n---\n/);
  const notes = new Map();
  const carried = [];
  let last;
  for (const line of foot.split('\n').filter((l) => l.trim())) {
    const m = line.match(/^\[(\d+)\]\s*(.*)$/);
    if (m) notes.set((last = `${n}-${m[1]}`), m[2].trim());
    else if (last) notes.set(last, `${notes.get(last)}\n${line.trim()}`);
    else carried.push(line.trim());
  }
  const blocks = body
    .split(/\n\s*\n/)
    .map((b) => b.trim())
    .filter((b) => b && b !== '---')
    .map((b) => b.replace(/\s*\n\s*(?=[.،؛:!؟)])/g, '').replace(/\s*\n\s*/g, ' '))
    .map((b) => b.replace(/\[\[fn:(\d+)\]\]/g, (_, k) => `[[fn:${n}-${k}]]`));
  return { blocks, notes, carried };
}

/** Arabic for matching titles: no vowel marks, one form of alif, ya and ta marbuta, letters only. */
const key = (s) =>
  s
    .normalize('NFKC')
    .replace(/\*\*|__|\^\^|%%|~~|&&|\[\[(?:fn|note):[^\]]*\]\]/g, '')
    .replace(/[ؐ-ًؚ-ٰٟۖ-ۭـ]/g, '')
    .replace(/[أإآٱ]/g, 'ا')
    .replace(/ى/g, 'ي')
    .replace(/ة/g, 'ه')
    .replace(/[^\p{L}\p{N}]/gu, '');

/** The entries of the source's contents pages (one per line), without their page numbers. */
function contentsEntries() {
  return CONTENTS.flatMap((n) =>
    readFileSync(pagePath(n), 'utf8')
      .replace(/<!--[\s\S]*?-->/g, '')
      .split('\n')
      .filter((l) => l.trim() && !l.startsWith('#'))
      .map((l) => l.replace(/[\s.…]*[0-9٠-٩]+\s*$/, '').trim()),
  ).filter(Boolean);
}

/** Pages whose first paragraph carries on the paragraph before, from the translation (build/content). */
function contFromContent() {
  const require = createRequire(import.meta.url);
  const out = new Map();
  for (const [part, [a, b]] of Object.entries(meta.parts ?? {})) {
    const file = join(BOOK, 'build/content', `part-${part}.js`);
    if (!existsSync(file)) continue;
    const list = require(file);
    if (list.length !== b - a + 1) continue; // not one entry per page: no help here
    list.forEach((pg, i) => out.set(a + i, !!pg.blocks?.[0]?.cont));
  }
  return out;
}

/** Markup left open at the end of a text, outermost first. */
function unclosed(s) {
  const open = [];
  for (const m of s.match(/\*\*|__|\^\^|%%|~~|&&/g) ?? []) open.at(-1) === m ? open.pop() : open.push(m);
  return open;
}

const plainEnd = (s) => s.replace(/\[\[(?:fn|note):[^\]]*\]\]|\*\*|__|\^\^|%%|~~|&&/g, '').trim();

/**
 * The text as blocks { kind: chapter | section | display | p | verse, text }: a paragraph split by
 * a page joined again (as the translation decided, else guessed: the page ends inside markup or
 * without a full stop); «# » headings are chapters when they are in the source's contents (all of
 * them when it has none), else display lines; «## » sections.
 */
function readText() {
  const entries = contentsEntries();
  const chapterKeys = new Set(entries.map(key));
  const decided = contFromContent();
  const join_ = new Set(cfg.join ?? []);
  const noJoin = new Set(cfg.no_join ?? []);
  const blocks = [];
  const notes = new Map();
  const guessed = [];
  const display = new Map();
  const orphans = [];
  for (let n = FIRST; n <= LAST; n++) {
    if (SKIP.has(n)) continue;
    const page = readPage(n);
    if (page.carried.length) {
      const prev = [...notes.keys()].at(-1) ?? die(`p-${n}: a footnote line without [N], and no note before it to carry on`);
      notes.set(prev, [notes.get(prev), ...page.carried].join('\n'));
    }
    for (const [k, v] of page.notes) notes.set(k, v);
    if (!page.blocks.length) continue; // a blank page
    const added = cfg.headings?.[n];
    if (added) blocks.push({ kind: 'chapter', text: added });
    // A note the page's text has no marker for (the source left it out) stays at the foot of its
    // page, without a number: it goes in at the start of the page's first paragraph.
    let lead = [...page.notes.keys()]
      .filter((id) => !page.blocks.some((b) => b.includes(`[[fn:${id}]]`)))
      .map((id) => (orphans.push(id), `[[note:${id}]]`))
      .join('');
    const withLead = (s) => {
      const out = lead + s;
      lead = '';
      return out;
    };
    page.blocks.forEach((b, i) => {
      if (b.startsWith('## ')) return blocks.push({ kind: 'section', text: b.slice(3).trim() });
      if (b.startsWith('# ')) {
        const text = b.slice(2).trim();
        const chapter = !CONTENTS.length || chapterKeys.has(key(text));
        if (!chapter) display.set(text, (display.get(text) ?? 0) + 1);
        return blocks.push({ kind: chapter ? 'chapter' : 'display', text });
      }
      const prev = blocks.at(-1);
      if (i === 0 && !added && prev?.kind === 'p') {
        const open = unclosed(prev.text);
        const guess = open.length > 0 || !/[.!؟?:)»"”…\]]$/.test(plainEnd(prev.text));
        const cont = join_.has(n) || (!noJoin.has(n) && (decided.has(n) ? decided.get(n) : guess));
        if (cont) {
          if (!decided.has(n) && !join_.has(n)) guessed.push(n);
          // Markup the page before leaves open is either opened again at the top of this page or
          // just closed further on: one run again.
          const left = open.join('');
          prev.text += ` ${withLead(left && b.startsWith(left) ? b.slice(left.length) : b)}`;
          return;
        }
      }
      const verse = b.match(/^\*\*([^*]+?) \/ ([^*]+?)\*\*$/);
      blocks.push(verse ? { kind: 'verse', text: withLead(verse[1]), second: verse[2] } : { kind: 'p', text: withLead(b) });
    });
    if (lead) die(`p-${n}: a note without a marker, and no paragraph on the page to put it in`);
  }

  const found = new Set(blocks.filter((b) => b.kind === 'chapter').map((b) => key(b.text)));
  const own = new Set(CONTENTS.flatMap((n) => readPage(n).blocks.filter((b) => b.startsWith('#')).map((b) => key(b.replace(/^#+\s*/, '')))));
  const unmatched = entries.filter((e) => !found.has(key(e)) && !own.has(key(e)));
  return { blocks, notes, guessed, display, unmatched, orphans, decided: decided.size > 0 };
}

/** A page set by itself after the text («تم بحمد الله», a closing word): its blocks, centred. */
function readBack(n) {
  const page = readPage(n);
  return { blocks: page.blocks, notes: page.notes };
}

// --- Typst ----------------------------------------------------------------------------------------

/** Closes a paragraph: keeps the last word's marker in the line (Nuskha's build.ts, END). */
const END = '#h(0pt)';

const COLOUR_NAMES = { '^^': 'verse', '%%': 'hadith', '~~': 'law', '&&': 'saying' };
const COLOURS = { '^^': '#1f3d6e', '%%': '#1f5c3e', '~~': '#8b1e1e', '&&': '#7a5a14', ...(cfg.colours ?? {}) };
const MARKS = /(\*\*|__|\^\^|%%|~~|&&|\[\[(?:fn|note):[\d-]+\]\])/;
// «[الروم: 41]», «[المائدة: 65، 66]», «[سورة سبأ: 32]»
const REF = /(\[[^[\]:]{2,40}:\s*\d+(?:\s*[-–,،]\s*\d+)*\])/;

/** Book text as Typst strings, each word followed by its marker (see Nuskha's template.ts). */
class Writer {
  words = [];
  space = false;
  ids = [];
  notes = 0;

  text(s, size) {
    let out = '';
    let ws = '';
    for (const part of s.split(/(\s+)/)) {
      if (!part) continue;
      if (/^\s/.test(part)) {
        ws += part;
        this.space = true;
        continue;
      }
      out += `#${str(ws + part)}#metadata(${this.words.length})<w>`;
      this.words.push({ t: part, s: size, sp: this.space });
      this.space = false;
      ws = '';
    }
    return ws ? `${out}#${str(ws)}` : out;
  }

  /** Text with references set small and grey. */
  plain(s, size) {
    return s
      .split(REF)
      .map((piece, i) => (i % 2 ? `#rf[${this.text(piece, size * SIZE.note)}]` : this.text(piece, size)))
      .join('');
  }

  /** The transcription's markup, as Typst. */
  markup(s, size, notes) {
    let out = '';
    const open = [];
    const fill = () => COLOUR_NAMES[open.findLast((m) => COLOUR_NAMES[m])] ?? 'ink';
    for (const part of s.split(MARKS)) {
      if (!part) continue;
      if (part.startsWith('[[')) {
        const plain = part.startsWith('[[note:');
        const id = part.slice(plain ? 7 : 5, -2);
        const body = notes.get(id);
        if (body === undefined) die(`note ${id} has a marker but no text`);
        notes.delete(id);
        const space = this.space;
        this.space = false;
        const paras = body.split('\n').map((l) => `${this.markup(l, SIZE.note, notes)}${END}`).join('#parbreak()');
        if (plain) out += `#note("")[${paras}]`; // Nuskha's note without a marker
        else {
          const label = `fn${++this.notes}`;
          out += `#footnote[${paras}]<${label}>`;
          this.ids.push(label);
        }
        this.space = space;
      } else if (part.length === 2 && MARKS.test(part)) {
        if (open.at(-1) === part) {
          out += ']';
          open.pop();
        } else if (open.includes(part)) die(`crossed markup ${part}: ${s.slice(0, 80)}`);
        else {
          // Bold: there is no bold Amiri here, so the letters get an outline of their own colour.
          out += part === '**' ? `#text(stroke: 0.022em + ${fill()})[` : part === '__' ? '#underline[' : `#text(fill: ${COLOUR_NAMES[part]})[`;
          open.push(part);
        }
      } else out += this.plain(part, size);
    }
    if (open.length) die(`unclosed markup ${open.join(' ')}: ${s.slice(0, 80)}`);
    return out;
  }
}

function buildDoc() {
  const text = readText();
  const { notes } = text;
  const w = new Writer();
  const lines = [];
  const headings = [];
  const starts = [];
  const notesAt = {};

  /** A block of the text, its notes recorded for Nuskha's check of notes left on the wrong page. */
  const push = (typst, first) => {
    lines.push(typst);
    for (const id of w.ids.splice(0)) notesAt[id] = { block: lines.length - 1, word: first };
  };
  const heading = (level, s, size) => {
    const label = `h${headings.length + 1}`;
    const from = w.words.length;
    starts.push({ block: lines.length, rank: level });
    push(`#heading(level: ${level})[${w.markup(s, size, notes)}${END}]<${label}>`, from);
    const title = w.words
      .slice(from)
      .map((x, i) => (i && x.sp ? ' ' : '') + x.t)
      .join('');
    headings.push({ label, level, title });
  };
  const bold = (s, size) => w.markup(`**${s}**`, size, notes);

  for (const b of text.blocks) {
    const first = w.words.length;
    if (b.kind === 'chapter') heading(1, b.text, SIZE.chapter);
    else if (b.kind === 'section') heading(2, b.text, 1.22);
    else if (b.kind === 'display') push(`#display[${w.markup(b.text, 1.3, notes)}${END}]`, first);
    else if (b.kind === 'verse') {
      const a = bold(b.text, 1);
      w.space = true;
      push(`#verse-line[${a}][${bold(b.second, 1)}${END}]`, first);
    } else push(`${w.markup(b.text, 1, notes)}${END}`, first);
  }
  for (const n of BACK) {
    const back = readBack(n);
    const body = back.blocks.map((b) =>
      b.startsWith('#') ? `#text(size: 1.6em, fill: red)[${w.markup(b.replace(/^#+\s*/, ''), 1.6, back.notes)}${END}]` : `${w.markup(b, 1, back.notes)}${END}`,
    );
    push(`#back-page[${body.join('\n\n')}]`, w.words.length);
  }
  for (const id of notes.keys()) console.warn(`warning: note ${id} has no marker in the text; left out`);

  const chapters = headings.filter((h) => h.level === 1).length;
  const heads = cfg.running_heads;
  if (heads && heads.length !== chapters) die(`${chapters} chapters, but ${heads.length} running_heads`);

  // The running head's title shares a line with the page number: a space before it («٩٨ نصرة»).
  w.space = true;
  const colours = Object.entries(COLOUR_NAMES)
    .map(([m, name]) => `#let ${name} = rgb(${str(COLOURS[m])})`)
    .join('\n');
  const preamble =
    template({
      size: 'a5',
      title: w.text(TITLE, SIZE.head),
      docTitle: TITLE,
      author: AUTHOR,
      description: cfg.description ?? `«${TITLE}»، ${AUTHOR}. نسخة نصية صُفّت بـ«نسخة».`,
      keywords: [...(cfg.keywords ?? []), MARKER],
      chapterLevel: 1,
      volumeLevel: 0,
    }) +
    `
// --- this book (pipeline/arabic_pdf.mjs) -------------------------------------------------------
${colours}
#let rf(body) = text(size: ${SIZE.note}em, fill: grey, body)
#let display(body) = align(center, block(above: 1.2em, below: 1em, text(size: 1.3em, fill: red, body)))
#let verse-line(first, second) = align(center, block(above: 0.8em, below: 0.8em, [#first#h(2.5em)#second]))
#let back-page(body) = page(header: none, {
  set align(center + horizon)
  set par(justify: false)
  body
})

// The running head: Nuskha's, with the chapter on odd pages given by running_heads (when set) and
// made smaller to fit one line when it is long. No printed-page range.
#let running-heads = (${(heads ?? []).map(str).join(', ')}${heads?.length === 1 ? ',' : ''})
#let chapter-head() = context {
  counter(footnote).update(0)
  let n = here().page()
  if first-from(query(<blank>), n) != none { return }
  let chapters = query(heading.where(level: chapter-level))
  if first-from(chapters, n) != none { return }
  let even = calc.even(counter(page).get().first())
  let k = chapters.filter(h => h.location().page() <= n).len()
  let num = numbering("١", ..counter(page).get())
  show footnote: none
  show super: none
  set text(size: ${SIZE.head}em, fill: red, top-edge: "ascender", bottom-edge: "descender")
  set par(justify: false)
  let middle = if even or k == 0 { book-title } else if running-heads.len() > 0 { lit(running-heads.at(k - 1), ${SIZE.head}) } else { chapters.at(k - 1).body }
  let fitted = layout(size => {
    let w = measure(middle).width
    box(height: 1.2em, clip: true, if w > size.width { text(size: calc.max(0.6, size.width / w) * 1em, middle) } else { middle })
  })
  let cells = (text(fill: ink, lit(num, ${SIZE.head})), align(center, fitted), [])
  grid(
    columns: (1.4fr, 3.2fr, 1.4fr),
    align: (start + bottom, center + bottom, end + bottom),
    ..(if even { cells } else { cells.rev() }),
  )
  v(-0.35em)
  line(length: 100%, stroke: 0.4pt + gold)
}
#set page(header: chapter-head())

// «الفهرس» as Nuskha's, but the dot leaders on the baseline: with the text's tall bottom edge, the
// box of dots stood on the line's baseline 0.7 em above theirs.
#let fx(i, level, title, n) = {
  let size = if level <= 1 { 1 } else { 0.94 }
  block(above: 0.3em, below: 0.3em, pad(right: (level - 1) * 1.2em, text(size: size * 1em, {
    lit(title, size)
    [#metadata(i)<fx>]
    box(width: 1fr, inset: (x: 0.3em), repeat(text(fill: grey, bottom-edge: "baseline")[.], gap: 0.15em))
    text(fill: grey, lit(n, size))
  })))
}
`;

  // The title page: lines given in arabic_pdf.title_page (with markup), else the title and author.
  const tp = cfg.title_page ?? { title: TITLE, below: [AUTHOR] };
  const lineList = (list, size) => (list ?? []).map((s) => `${w.markup(s, size, new Map())}${END}`).join(' #linebreak() ');
  const titlePage = `#page(header: none, numbering: none, {
  set align(center)
  set par(justify: false)
  v(6%)
  text(size: 1.05em, [${lineList(tp.top, 1.05)}])
  v(${tp.top?.length ? '14%' : '18%'})
  text(size: 1.2em, [${lineList(tp.above, 1.2)}])
  v(0.6em)
  text(size: 2.3em, fill: red, [${lineList([tp.title ?? TITLE], 2.3)}])
  v(1em)
  text(fill: gold, size: 1.2em)[۞]
  v(1em)
  text(size: 1.25em, [${lineList(tp.below, 1.25)}])
  place(bottom + center, dy: -4%, text(fill: grey, [${lineList(tp.bottom, 1)}]))
})`;

  const card = (k, v) => `#k[${w.text(`${k}:`, SIZE.card)}]${w.text(` ${v}`, SIZE.card)}${END}`;
  const today = new Date();
  const date = `${num(today.getFullYear())}/${num(today.getMonth() + 1)}/${num(today.getDate())}`;
  const about = `هذه نسخة نصية من الكتاب: صُفّ نصه من جديد كما هو في ملف الأصل، ليمكن نسخه والبحث فيه.${cfg.cover ? ' الغلاف من ملف الأصل.' : ''}`;
  const cardPage = `#card-page[${[
    ...(cfg.card ?? [['الكتاب', TITLE], ['المؤلف', AUTHOR]]).map(([k, v]) => card(k, v)),
    '#v(1.2em)',
    `${w.text(about, SIZE.card)}${END}`,
    `${w.text(`أُنشئ هذا الملف بـ«نسخة» في ${date}. الخط: أميري (رخصة SIL Open Font License).`, SIZE.card)}${END}`,
  ].join('\n\n')}]`;

  const front = [cfg.cover ? `#cover-page(${str(COVER_PATH)})` : '', titlePage, cardPage].filter(Boolean).join('\n');
  return { doc: { preamble, front, blocks: lines, words: w.words, notes: notesAt, headings, starts, docTitle: TITLE }, text };
}

// --- the PDF --------------------------------------------------------------------------------------

/** The source's cover page, as a JPEG. */
function cover(page) {
  const dir = mkdtempSync(join(tmpdir(), 'arabic-pdf-cover-'));
  try {
    execFileSync('pdftoppm', ['-f', `${page}`, '-l', `${page}`, '-r', '200', '-jpeg', '-jpegopt', 'quality=88', '-singlefile', join(BOOK, meta.pdf), join(dir, 'cover')]);
    return new Uint8Array(readFileSync(join(dir, 'cover.jpg')));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const amiri = new Uint8Array(readFileSync(join(NUSKHA, 'public/fonts/Amiri-Regular.ttf')));
await typst.default({ module_or_path: readFileSync(join(NUSKHA, 'node_modules/@myriaddreamin/typst-ts-web-compiler/pkg/typst_ts_web_compiler_bg.wasm')) });
const builder = new typst.TypstCompilerBuilder();
builder.set_dummy_access_model();
await builder.add_raw_font(amiri);
if (existsSync(FALLBACK_FONT)) await builder.add_raw_font(new Uint8Array(readFileSync(FALLBACK_FONT)));
const compiler = await builder.build();

// Width of the hidden text where nothing on its right bounds it (the start of a line, a whole entry of
// «الفهرس»): Amiri's isolated letter forms run about 1.45 times as wide as the joined word (measured
// with Typst). Unscaled, a long entry of «الفهرس» ran past the page's edge, and pdf.js and Poppler
// dropped its first words.
const isolated = advances(amiri);
const advance = (cp) => isolated(cp) * (cp >= 0x621 && cp <= 0x64a ? 0.7 : 1);

const t = performance.now();
const { doc, text } = buildDoc();
const r = renderPdf(compiler, { doc, size: 'a5', cover: cfg.cover ? cover(cfg.cover) : undefined, advance });
mkdirSync(join(BOOK, OUTDIR), { recursive: true });
writeFileSync(OUT, r.pdf);

const chapters = doc.headings.filter((h) => h.level === 1).length;
const pages = Number(execFileSync('pdfinfo', [OUT], { encoding: 'utf8' }).match(/^Pages:\s+(\d+)/m)[1]);
console.log(`${OUT}`);
console.log(`  ${pages} pages, ${(r.pdf.length / 1024 / 1024).toFixed(1)} MB, ${doc.words.length} words, ${chapters} chapters, made in ${((performance.now() - t) / 1000).toFixed(1)} s`);
console.log(`  notes on the wrong page: ${r.misplaced[1]}`);
console.log(`  paragraphs joined across pages: ${text.decided ? 'as in the translation' : 'guessed'}${text.guessed.length ? `; guessed at pages ${spans(text.guessed)}` : ''}`);
for (const [s, n] of text.display) console.log(`  display line (a «#» line not in the contents): «${s}»${n > 1 ? ` ×${n}` : ''}`);
for (const e of text.unmatched) console.log(`  contents entry with no heading in the text: «${e}» (add it under "headings" if it opens a chapter)`);
for (const id of text.orphans) console.log(`  note ${id.replace('-', ' [')}] has no marker in the text: kept at the foot of its page, without a number`);

// --- check: the text viewers read back ------------------------------------------------------------

let ok = true;
if (!NO_CHECK) {
  // PDFium (Emscripten) hands the script's path to its environment, which must be ASCII.
  process.argv[1] = 'arabic_pdf.mjs';
  const { found, inOrder, pageWords, pdfiumPages, pdfjsPages, words } = await nuskha('scripts/pdf-text.ts');
  const expected = doc.words.flatMap((x) => words(x.t));
  const perPage = pageWords(r.marks, (v) => (Array.isArray(v) ? v[0] : (doc.words[v]?.t ?? '')));
  for (const [viewer, read] of [['pdf.js', pdfjsPages], ['PDFium', pdfiumPages]]) {
    const back = await read(r.pdf);
    const f = found(expected, back.join('\n'));
    const o = inOrder(perPage, back);
    if (f.score < 0.99 || o < 0.99) ok = false;
    const miss = f.missing.slice(0, 8).map(([x, n]) => `${x}×${n}`).join(' ');
    console.log(`  ${viewer.padEnd(6)} reads back ${(f.score * 100).toFixed(2)}% of the words, ${(o * 100).toFixed(2)}% in order${miss ? `  (missing: ${miss})` : ''}`);
    if (PER_PAGE) {
      perPage.forEach((exp, i) => {
        const m = found(exp, back[i] ?? '').missing;
        if (m.length) console.log(`    page ${i + 1}: ${m.map(([x, n]) => `${x}×${n}`).join(' ')}`);
      });
    }
  }
  if (!ok) {
    console.log('  under 99%: look at the misses (--pages) before using the file');
    process.exitCode = 1;
  }
}

// --- the library ------------------------------------------------------------------------------------

if (TO_LIBRARY) {
  if (!ok) die('not put in the library: the readback check is under 99%');
  toLibrary();
}

function md5(file) {
  return createHash('md5').update(readFileSync(file)).digest('hex');
}

/** Files under a folder (not hidden ones). */
function* walk(dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name.startsWith('.')) continue;
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (e.isFile()) yield p;
  }
}

/** Was this file made by this script? */
function ours(file) {
  try {
    return execFileSync('pdfinfo', [file], { encoding: 'utf8' }).includes(MARKER);
  } catch {
    return false;
  }
}

/**
 * The new PDF in the library, under its title. The old copies are the files identical to the
 * book's source PDF: they go to the trash (gio trash: the person can restore them). Other files
 * with the title in their name differ from the source and are left alone, for the person to decide.
 */
function toLibrary() {
  if (!existsSync(LIBRARY)) die(`no library folder at ${LIBRARY}`);
  const source = join(BOOK, meta.pdf);
  const size = statSync(source).size;
  const sum = md5(source);
  const target = join(LIBRARY, basename(OUT));
  const old = [];
  const other = [];
  for (const f of walk(LIBRARY)) {
    if (statSync(f).size === size && md5(f) === sum) old.push(f);
    else if (f !== target && key(basename(f)).includes(key(TITLE)) && /\.(pdf|epub)$/i.test(f)) other.push(f);
  }
  if (existsSync(target) && !old.includes(target) && !ours(target)) {
    die(`${target} is there already and is neither the source PDF nor made by this script: ask the person`);
  }
  if (!DRY_RUN) {
    for (const f of old) execFileSync('gio', ['trash', f]);
    copyFileSync(OUT, target);
  }
  const would = DRY_RUN ? 'would be ' : '';
  console.log(`library${DRY_RUN ? ' (dry run, nothing changed)' : ''}: ${target}${existsSync(target) && !old.includes(target) ? ` (${would}replaced: an earlier build)` : ''}`);
  for (const f of old) console.log(`  ${would}moved to the trash (identical to the source PDF): ${f}`);
  if (!old.length) console.log('  no copy of the source PDF was there');
  for (const f of other) console.log(`  left alone (differs from the source PDF): ${f}`);
}
