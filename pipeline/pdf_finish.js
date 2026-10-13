// Final touches on the merged book PDF (called by make_pdf.py): document info, language and bookmarks.
// Usage: node pdf_finish.js <in.pdf> <out.pdf> <spec.json>
// spec: { title, author, lang, bookmarks: [{ title, page }] }, page counted from 1 in the merged PDF
const fs = require('fs');
const { PDFDocument, PDFName, PDFHexString } = require('pdf-lib');

async function main() {
  const [input, output, specFile] = process.argv.slice(2);
  const spec = JSON.parse(fs.readFileSync(specFile, 'utf8'));
  const doc = await PDFDocument.load(fs.readFileSync(input), { updateMetadata: false });

  doc.setTitle(spec.title, { showInWindowTitleBar: true });
  if (spec.author) doc.setAuthor(spec.author);
  if (spec.lang) doc.setLanguage(spec.lang);
  doc.setCreator('translations pipeline (make_pdf.py)');
  doc.setModificationDate(new Date());

  // Outline: a flat list of bookmarks, each opening its page at the current zoom
  const pages = doc.getPages(), ctx = doc.context;
  const marks = spec.bookmarks.filter((b) => b.page >= 1 && b.page <= pages.length);
  if (marks.length) {
    const root = ctx.nextRef();
    const refs = marks.map(() => ctx.nextRef());
    marks.forEach((b, i) => {
      const item = { Title: PDFHexString.fromText(b.title), Parent: root, Dest: [pages[b.page - 1].ref, 'XYZ', null, null, null] };
      if (i > 0) item.Prev = refs[i - 1];
      if (i < refs.length - 1) item.Next = refs[i + 1];
      ctx.assign(refs[i], ctx.obj(item));
    });
    ctx.assign(root, ctx.obj({ Type: 'Outlines', First: refs[0], Last: refs[refs.length - 1], Count: refs.length }));
    doc.catalog.set(PDFName.of('Outlines'), root);
    doc.catalog.set(PDFName.of('PageMode'), PDFName.of('UseOutlines'));
  }

  fs.writeFileSync(output, await doc.save({ useObjectStreams: false }));
  console.log(`wrote ${output} (${pages.length} pages, ${marks.length} bookmarks)`);
}

main().catch((e) => { console.error(e.stack || e.message); process.exit(1); });
