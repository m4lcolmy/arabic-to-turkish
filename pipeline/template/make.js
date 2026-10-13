// Layout engine for a Turkish edition (template from المقدمات العشر; adapt the design tokens per book).
// Usage: node make.js <content-file.js> <output.docx>
// The content file exports an array of pages, one per source page (fields: header, pageStart (non-flow books), tight,
// newPage, blocks, footnotes; a block may have cont: true). Pages of one section flow together, see below.
const fs = require('fs');
const path = require('path');
const JSZip = require('jszip');
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Header, Footer, AlignmentType, TabStopType,
  PageNumber, FootnoteReferenceRun, BorderStyle, HorizontalPositionRelativeFrom,
  VerticalPositionRelativeFrom, TextWrappingType, Table, TableRow, TableCell, WidthType,
  VerticalAlign,
} = require('docx');

const BOOK = path.resolve(__dirname, '..');
const img = (f) => fs.readFileSync(path.join(BOOK, 'assets', f));
const [contentFile, OUT] = process.argv.slice(2);
const pages = require(path.resolve(contentFile));
const META = (() => { try { return JSON.parse(fs.readFileSync(path.join(BOOK, 'book.json'), 'utf8')); } catch { return {}; } })();

// Flow layout (book.json "layout": "flow", RULES.md §2): a part takes as many pages as its Turkish text needs.
// Page numbers and contents numbers come from the Turkish layout: build.py records each part's page count
// (layout_pages) and the printed page each contents title landed on (toc_pages). A part starts right after
// the real last page of the part before it. Without "flow", pages are numbered from `pageStart` in the content file.
const FLOW = META.layout === 'flow';
const PART = (path.basename(contentFile).match(/part-(\d+)/) || [])[1];
function firstPosition() {  // position in the Turkish book of this part's first page (cover = 1)
  const order = Object.entries(META.parts || {}).sort((a, b) => a[1][0] - b[1][0]).map(([p]) => p);
  let pos = 1;
  for (const p of order) {
    if (p === PART) return pos;
    const n = (META.layout_pages || {})[p];
    if (n == null) throw new Error(`part ${p} comes before part ${PART} but has not been built yet; build the parts in order`);
    pos += n;
  }
  throw new Error(`part ${PART} is not listed in book.json "parts"; build it with build.py --pages A-B`);
}

// Design tokens, taken from the Arabic edition
const RED = 'C8302B', ORANGE = 'EE8A3A', VERSE = 'F07A3C', NAVY = '263852', INK = '1E1E1E';
const FONT = 'Open Sans';
const PAGE_W = 11906, PAGE_H = 16838, MX = 1000, TEXT_W = PAGE_W - 2 * MX; // A4, DXA
const BODY_SIZE = 19, FN_SIZE = 14; // half-points

// Inline markup: **bold**, ^^Qur’an verse in orange^^, [[fn:N]] footnote reference
function runs(text, base = {}) {
  const out = [];
  for (const part of text.split(/(\*\*[^*]+\*\*|\^\^[^^]+\^\^|\[\[fn:\d+\]\])/)) {
    if (!part) continue;
    const fn = part.match(/^\[\[fn:(\d+)\]\]$/);
    if (fn) out.push(new FootnoteReferenceRun(Number(fn[1])));
    else if (part.startsWith('**')) out.push(new TextRun({ ...base, text: part.slice(2, -2), bold: true }));
    else if (part.startsWith('^^')) out.push(new TextRun({ ...base, text: part.slice(2, -2), color: VERSE }));
    else out.push(new TextRun({ ...base, text: part }));
  }
  return out;
}

const NONE = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
const noBorders = { top: NONE, bottom: NONE, left: NONE, right: NONE };
const ruleParagraph = () => new Paragraph({
  spacing: { before: 0, after: 0, line: 120, lineRule: 'exact' },
  border: { bottom: { style: BorderStyle.THICK_THIN_SMALL_GAP, size: 12, color: ORANGE, space: 1 } },
  children: [new TextRun({ text: '', size: 2 })],
});

// Header: red section title | orange double rule | logo  (mirror of the RTL original)
function header(title) {
  const titleW = Math.min(5200, 300 + title.length * 118);
  const logoW = 1000, gapW = 240;
  const lineW = TEXT_W - titleW - logoW - gapW;
  const cell = (w, children, align = VerticalAlign.CENTER) => new TableCell({
    width: { size: w, type: WidthType.DXA }, borders: noBorders, verticalAlign: align,
    margins: { top: 0, bottom: 0, left: 0, right: 0 }, children,
  });
  return new Header({ children: [new Table({
    width: { size: TEXT_W, type: WidthType.DXA },
    columnWidths: [titleW, lineW, gapW, logoW],
    borders: { ...noBorders, insideHorizontal: NONE, insideVertical: NONE },
    rows: [new TableRow({ children: [
      cell(titleW, [new Paragraph({ children: [new TextRun({ text: title, font: FONT, bold: true, size: 22, color: RED })] })]),
      cell(lineW, [ruleParagraph()]),
      cell(gapW, [new Paragraph({ children: [] })]),
      cell(logoW, [new Paragraph({ alignment: AlignmentType.RIGHT, children: [
        new ImageRun({ type: 'png', data: img('logo.png'), transformation: { width: 60, height: 56 } })] })]),
    ] })],
  })] });
}

// Footer: orange double rule running into a rounded page-number box (image), number on top
const footer = () => new Footer({ children: [new Paragraph({
  alignment: AlignmentType.RIGHT, indent: { right: 170 }, spacing: { before: 0, after: 0 },
  children: [
    new ImageRun({
      type: 'png', data: img('footer_badge.png'), transformation: { width: 660, height: 26 },
      floating: {
        horizontalPosition: { relative: HorizontalPositionRelativeFrom.MARGIN, offset: 0 },
        verticalPosition: { relative: VerticalPositionRelativeFrom.PARAGRAPH, offset: -4 * 9525 },
        wrap: { type: TextWrappingType.NONE }, behindDocument: true, allowOverlap: true,
      },
    }),
    new TextRun({ children: [PageNumber.CURRENT], font: FONT, bold: true, size: 18, color: NAVY }),
  ],
})] });

const pageProps = (start) => ({ page: {
  size: { width: PAGE_W, height: PAGE_H },
  margin: { top: 1420, bottom: 1150, left: MX, right: MX, header: 520, footer: 560 },
  ...(start ? { pageNumbers: { start } } : {}),
} });

// Block renderers (a page with `tight: true` gets reduced line and paragraph spacing, for dense source pages)
const R = {
  p: (b, pg) => new Paragraph({
    alignment: AlignmentType.JUSTIFIED, spacing: { after: pg.tight ? 0 : b.after ?? 90, line: pg.tight ? 256 : 276 },
    children: runs(b.text),
  }),
  title: (b) => new Paragraph({
    keepNext: true, keepLines: true, spacing: { before: 40, after: 200 }, alignment: b.center ? AlignmentType.CENTER : AlignmentType.LEFT,
    children: [new TextRun({ text: b.text, font: FONT, bold: true, size: b.size || 32, color: b.color === 'navy' ? NAVY : RED })],
  }),
  image: (b) => new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: b.before ?? 0, after: b.after ?? 180 },
    children: [new ImageRun({ type: b.file.endsWith('.png') ? 'png' : 'jpg', data: img(b.file), transformation: { width: b.width, height: b.height } })],
  }),
  signature: (b) => new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: b.before ?? 0, after: b.after ?? 30 },
    children: [new TextRun({ text: b.text, font: FONT, bold: true, size: b.size || 21, color: RED })],
  }),
  toc: (b) => b.entries.map(([t, n]) => new Paragraph({
    tabStops: [{ type: TabStopType.RIGHT, position: TEXT_W, leader: 'dot' }],
    indent: { right: 500 }, spacing: { after: 140 },
    children: [
      new TextRun({ text: t, font: FONT, bold: true, size: 20, color: NAVY }),
      new TextRun({ text: `\t${FLOW ? (META.toc_pages || {})[t] ?? '' : n}`, font: FONT, bold: true, size: 20, color: NAVY }),
    ],
  })),
};

// Pages flow (RULES.md §2): the content file has one entry per source page, but consecutive body pages of
// one section are laid out as one continuous text, so no page ends early in the middle of a section.
// A new page starts at the cover, a blank page, a page whose header differs from the previous one
// (a new section), and a page marked `newPage: true` (contents, full-page image, back matter).
// A first block with `cont: true` continues the previous page's last paragraph (a sentence split by the source).
const footnotes = {};
const flows = [];
for (const pg of pages) {
  for (const [id, text] of Object.entries(pg.footnotes || {})) {
    // A '\n' in a footnote starts a new paragraph inside the same note (unnumbered continuation, as in the source)
    footnotes[id] = { children: text.split('\n').map((t) => new Paragraph({
      alignment: AlignmentType.JUSTIFIED, spacing: { after: pg.tight ? 0 : 20, line: pg.tight ? 212 : 230 },
      children: runs(t, { size: FN_SIZE, font: FONT, color: '333333' }),
    })) };
  }
  const prev = flows[flows.length - 1];
  const own = pg.type === 'cover' || pg.type === 'blank';
  if (!prev || own || prev.page.type || pg.newPage || pg.header !== prev.page.header) {
    flows.push({ page: pg, items: [] });
  }
  const flow = flows[flows.length - 1];
  for (const [i, b] of (pg.blocks || []).entries()) {
    const last = flow.items[flow.items.length - 1];
    if (i === 0 && b.cont) {
      if (!last || flow.page === pg || last.b.type !== 'p' || b.type !== 'p') {
        throw new Error(`cont: true on a page that does not continue a paragraph (header "${pg.header}")`);
      }
      last.b = { ...last.b, text: `${last.b.text} ${b.text}`, after: b.after };
      continue;
    }
    flow.items.push({ b, pg });
  }
}

// Flow layout: the first numbered page of the part gets its real number (cover and blank pages are one page each)
let startAt = FLOW ? firstPosition() - (META.page_offset || 0) : null;
const sections = flows.map(({ page: pg, items }) => {
  if (startAt != null && (pg.type === 'cover' || pg.type === 'blank')) startAt += 1;
  if (pg.type === 'cover') {
    return {
      properties: { page: { size: { width: PAGE_W, height: PAGE_H }, margin: { top: 0, bottom: 0, left: 0, right: 0, header: 0, footer: 0 } } },
      children: [new Paragraph({ children: [new ImageRun({
        type: 'jpg', data: img(pg.image), transformation: { width: 794, height: 1123 },
        floating: {
          horizontalPosition: { relative: HorizontalPositionRelativeFrom.PAGE, offset: 0 },
          verticalPosition: { relative: VerticalPositionRelativeFrom.PAGE, offset: 0 },
          wrap: { type: TextWrappingType.NONE }, behindDocument: true,
        },
      })] })],
    };
  }
  if (pg.type === 'blank') {
    // An empty page: no header, footer or page number
    const empty = () => ({ children: [new Paragraph({ children: [] })] });
    return {
      properties: pageProps(),
      headers: { default: new Header(empty()) }, footers: { default: new Footer(empty()) },
      children: [new Paragraph({ children: [] })],
    };
  }
  const start = FLOW ? startAt : pg.pageStart;
  startAt = null;  // later sections of the part continue the numbering
  return {
    properties: pageProps(start),
    headers: { default: header(pg.header || '') },
    footers: { default: footer() },
    // Trailing plain paragraph: LibreOffice styles the footer PAGE field like the section's last paragraph
    children: [...items.flatMap(({ b, pg: from }) => R[b.type](b, from)), new Paragraph({ spacing: { after: 0, line: 120, lineRule: 'exact' }, children: [] })],
  };
});

const doc = new Document({
  creator: META.author || '', title: META.title_tr || '',
  styles: { default: { document: { run: { font: FONT, size: BODY_SIZE, color: INK } } } },
  footnotes, sections,
});

// Restart footnote numbering on every page, as in the Arabic edition
async function restartFootnotesEachPage(buf) {
  const zip = await JSZip.loadAsync(buf);
  let xml = await zip.file('word/document.xml').async('string');
  xml = xml.replace(/<w:sectPr\b([^>]*)>([\s\S]*?)<\/w:sectPr>/g, (m, attrs, inner) => {
    const fp = '<w:footnotePr><w:numRestart w:val="eachPage"/></w:footnotePr>';
    const at = inner.search(/<w:(endnotePr|type|pgSz)\b/);
    return `<w:sectPr${attrs}>${inner.slice(0, at)}${fp}${inner.slice(at)}</w:sectPr>`;
  });
  zip.file('word/document.xml', xml);
  // Give the PAGE field a cached result, otherwise LibreOffice styles it like the page's last paragraph
  for (const name of Object.keys(zip.files).filter((n) => /^word\/footer\d+\.xml$/.test(n))) {
    const f = await zip.file(name).async('string');
    zip.file(name, f.replace('<w:fldChar w:fldCharType="separate"/><w:fldChar w:fldCharType="end"/>',
      '<w:fldChar w:fldCharType="separate"/><w:t>1</w:t><w:fldChar w:fldCharType="end"/>'));
  }
  return zip.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' });
}

Packer.toBuffer(doc).then(restartFootnotesEachPage).then((b) => { fs.writeFileSync(OUT, b); console.log('wrote', OUT); });
