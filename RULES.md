# Translation Rules

These rules apply to every translation made in this folder. Follow them for each new book and each new part of a book.

## 1. Folder layout

```
translations/
├── RULES.md                      ← this file
├── pipeline/                     ← shared tools for the workflow (see pipeline/README.md)
├── .claude/skills/arabic-to-turkish ← the /arabic-to-turkish command
└── <book name>/                  ← named after the original title (e.g. المقدمات العشر)
    ├── book.json                 ← names, page offset, sections and parts (used by the pipeline)
    ├── source/                   ← the original PDF, never modified
    │   └── text/                 ← page transcriptions p-NNN.ar.md, exactly as printed
    ├── assets/                   ← images extracted from the source (+ rebuilt cover, decorations)
    ├── build/                    ← build scripts; content/part-NN.js holds the translated text
    ├── docx/                     ← one DOCX per part: part-NN_pdf-pX-Y.docx
    ├── pdf/                      ← final combined PDF (made only at the end)
    ├── work/                     ← renders and check reports (temporary, rebuilt on demand)
    ├── GLOSSARY.md               ← fixed term choices for this book
    └── CHECK-part-NN.md          ← completeness check for each part
```

## 2. Scope and page counting

- Page ranges of parts always refer to **physical pages of the source PDF** (the cover is page 1), not to the printed page numbers.
- **The Turkish layout follows the Turkish text, not the Arabic page count.** A part takes as many pages as its text needs at the normal font size and spacing; it may be shorter or longer than its source range. Don't squeeze or stretch text to hit a page count, and never cut content.
- **Text flows inside a section.** A sentence or paragraph that doesn't fit continues on the next page, and no page ends early in the middle of a section. Only a section's last page may end part-way down.
- **These always start on a new page and stand alone:** the cover, blank pages, the contents page, the first page of each section (introduction, each chapter), full-page images and back matter.
- **Page numbers and the contents come from the Turkish layout.** Numbering runs on from part to part without a gap, and each contents entry shows the printed page where that title actually lands in the Turkish edition. The pipeline does this (`"layout": "flow"` in `book.json`); never copy page numbers from the Arabic contents.
- Books built before this rule (المقدمات العشر) keep their one-page-per-source-page layout and are not rebuilt.

## 3. Reading the source

- Read every page **visually** (render it to an image and zoom into small text such as footnotes).
- The PDF's text layer may only be used as a cross-check: Arabic fonts in InDesign PDFs often extract with broken letters (e.g. "املقدمة األوىل" instead of "المقدمة الأولى").

## 4. Translation quality

- Make a **professional, context-preserving translation**: faithful to the meaning, tone and rhetoric of the author, written in natural, literate Turkish. It must not be word-for-word, and it must not be a free paraphrase either.
- **Add nothing and leave nothing out.** Keep every sentence, list item, bracket, parenthesis, exclamation, repetition (e.g. «كل إنسان»), footnote marker and footnote.
- **Balance clarity and literary style (find the middle ground).** Every sentence and title must be understandable and must not sound strange or "translated". But do **not** flatten the author's literary, rhetorical voice into plain everyday Turkish.
  - Fix only what is really unclear or odd, with the **smallest** change: add one word (e.g. «الآلام ليست مقياساً» → "**Çekilen** Acılar Bir Ölçü Değildir") or adjust word order. Rewriting a sentence that already works is not a fix.
  - Keep literary words that Turkish readers know and use: çokluk, ehli, makam, tesir, idrak, hayret, emel, gaye, önden göndermek, ebedîlik… Replace only rare or obscure ones (e.g. "süs" → "görünüm"). If a technical term stays, gloss it after it: "Tecdit (Yenilenme)".
  - Keep the author's rhetoric: exclamations («ما أكثر» → "ne çok…!"), parallelism and ellipsis ("Dünya Bir Noktadır, Ahiret ise Sonsuz Bir Çizgi"), terse phrases («خلودٌ فلا موت» → "ebedîlik var, ölüm yok!"), Qur’anic and hadith echoes («فلا تعد عيناك عنها» → "gözlerin onlardan ayrılmasın").
  - **Spoken restatements are merged.** The text comes from the author's spoken videos, so a fact is sometimes said twice in a row, a little differently (e.g. «شخص زبيدي جاء لمكة، رجل من زبيد أتى من اليمن»). Say it once, keeping every piece of information: "İşte Zübeydli bir adam Yemen’den Mekke’ye gelmiş", not "Mekke’ye gelmiş Zübeydli biri, Yemen’den gelmiş Zübeydli bir adam". This also covers a word repeated in one sentence («في زماننا… في زماننا») and a closing clause that repeats the sentence's opening. Rhetorical repetition stays (emphasis such as «كل إنسان، كل إنسان», a refrain, a hadith word repeated for stress, a verse quoted again). List every merge in the CHECK file.
  - Emphatic fragments stay emphatic and short (e.g. «…كل إنسان!» → "istisnasız her insan!").
  - Don't add explanatory content words that aren't in the source (e.g. «بم يرجع» → "ne ile dönüyor", not "ne kadar suyla").
  - Test each title and sentence twice: "Would a Turkish reader understand it immediately?" and "Does it still sound like the author?"
- **Pronouns.** Arabic pronouns carry gender and number (and the dual), so an Arabic reader resolves «هو / هي / هم / ـه / ـها» at once; Turkish "o / onu / ona / onun / kendisi" carries neither. For every pronoun ask: *could a Turkish reader attach it to anything else in the last sentence or two?* If so, name the referent (a noun, "bu kişi", "böylesi", "o topluluk") or rephrase until only one candidate is left (e.g. «وهو لا شيء», masculine → the deed, not the feminine «النقطة»). In particular:
  - never leave two different "o" referents in one clause (e.g. "onu zayi ederse hayvanlar ona üstün gelir" → "**aklını** zayi ederse…");
  - the noun comes before its pronoun: Turkish non-finite clauses often pull an Arabic trailing clause to the front («يسهل عليك أن تعرف المنافق… بأن تجرد أقواله» → "**münafığın** sözlerini soyutlayarak… **onu** tanıman kolaylaşır");
  - keep one number: when the Arabic slides from "they" to a generic "he" («ينفقون… يحشر نفسه… فيتبعه»), introduce the singular with a noun ("Münafık…") or stay plural;
  - every footnote must make sense on its own: never open a footnote with a pronoun or an unstated subject;
  - a pronoun whose antecedent lies outside a quotation is dropped or replaced by a generic noun («ولو قبضت يده» → "Konuşan kişinin eli…");
  - «في نفسه / بنفسه» about an idea → "X’in kendisi", not "kendi özünde / kendi başına";
  - «غيره» meaning "what is not X" → "X olmayan", not "başkası" (which means another *person*);
  - a bare «ﷺ» as subject → "Resûlullah (s.a.v.)"; Allah keeps the capital "O / O’nun".

  Naming a referent this way is not an "added word" under the add-nothing rule. Log non-obvious cases in the CHECK file.
- **Punctuation follows the source.** Don't add any punctuation mark that isn't in the main text: no extra "!", "…", ":", dashes or quotation marks. If a sentence ends with "." in the source, it ends with "." in Turkish; a title or closing line without punctuation stays without it (e.g. «وليُقسْ ما لم يُقلْ» → "Söylenmeyeni de söylenene kıyas et", no "!"). Dialogue inside hadiths isn't wrapped in extra “ ” unless the source has them. Qur’an verse separators such as "*" are kept. Only marks that Turkish grammar strictly requires are allowed: commas for vocatives ("Ey Âdemoğlu,"), "?" on a direct question, and sentence breaks inside a long Arabic sentence.
- Keep the author's emphasis devices (brackets, dashes, "= nokta", parenthetical glosses) in the same positions.
- Religious terminology follows standard Turkish Islamic usage: Allah, Resûlullah (s.a.v.), ahiret, berzah, salât ve selâm, tefsir, şerh, şer‘î, hamd. Use "(s.a.v.)" for ﷺ (the body font has no ﷺ glyph).
- Hadith sources use the Turkish form: *Müslim (2858)*, *Tirmizî (2465)*, *İbn Mâce (4110)*, *el-Beyân ve’t-Tebyîn (1/83)*.
- Personal names are transliterated with circumflexes and ‘ayn marks: İmrân b. Fadl Şâkir el-A‘vân, el-Karâfî, Câhiz.
- **External references (e.g. the author's YouTube videos and their subtitles) are secondary only.** Use them to check terminology or understand intent, never as the base text. The PDF is always the main reference.
- Record every recurring term choice in the book's `GLOSSARY.md` and reuse it in later parts.
- **Correct verifiable source errors in the translation.** If the source has a factual slip that can be checked, such as a wrong Qur’an verse or sura reference, a wrong hadith number or a wrong book/volume/page reference, write the correct value in the Turkish text. Correct only errors that you have verified against the actual verse or hadith. Never "correct" the author's wording, opinions or style. If you aren't sure, keep the source as printed and flag it.
  - List every correction in the part's `CHECK-part-NN.md` under **Source errors corrected**, with the page, the printed value and the corrected value.
  - **Always report every correction to the user** in the delivery message for that part, even if it seems trivial, so it can be reviewed.

## 5. Design

- The Turkish edition must look as professional as the Arabic one: **mirror the original layout for left-to-right reading**.
- Font: **Open Sans** for everything (body, headings, footnotes, contents).
- Reuse the same colours, header and footer as the original:
  - Header: red section title, then an orange double rule, then the book's logo on the right.
  - Footer: an orange double rule that runs into a rounded navy box holding the page number.
  - Titles: red bold. Contents page: navy bold, with dot leaders.
  - Footnotes: small text under a short rule, numbering restarts on every page. A footnote always sits on the page of its marker (it moves with the flowing text).
  - A section title never stays alone at the bottom of a page.
- Use **the same images as the source PDF** (extracted with `pdfimages`, not screenshots). The cover uses the original artwork with the Arabic title replaced by the Turkish one.
- Body text is justified, with no first-line indent (as in the original).

## 6. Workflow

`/arabic-to-turkish` (see `pipeline/README.md`) runs these steps in order; the rules are the same when working by hand.

1. Render the part's pages (`pipeline/pages.py`) and read every page visually.
2. Transcribe each page into `source/text/p-NNN.ar.md`, exactly as printed.
3. Translate into `build/content/part-NN.js`.
4. **Automatic checks** (`pipeline/check.py`): fix every ERROR or explain it in the CHECK file; judge each WARN on its merits, since natural Turkish wins over matching counts.
5. Build the DOCX (`pipeline/build.py`); build parts in book order, since each part's page numbers start after the previous part's real last page. Check every rendered page visually: no page ending early inside a section, every section starting on a new page, footnotes on the page of their marker, missing glyphs. If a part's page count changes after later parts were built, rebuild the later parts (build.py lists them).
6. **Completeness check** (required, to prevent AI hallucination): compare source and translation sentence by sentence. Confirm that nothing is missing or added and that every number, page reference, hadith number and source is correct. Write the result to `CHECK-part-NN.md`, listing any deliberate deviations.
7. **Readability pass:** re-read the whole Turkish text (titles, body, footnotes, cover) as a Turkish reader would, without looking at the source. Fix anything unclear, stiff or strange with minimal changes that keep the literary tone (see the balance rule in §4), then re-run the completeness check on the changed sentences.
   - **Pronoun check** (§4 *Pronouns*): read every footnote on its own, then every sentence with two or more "o / onu / ona / onun / kendisi" forms, and make sure each pronoun can point to only one thing. `check.py` lists likely candidates as WARN.
8. Deliver the DOCX for review. Work part by part in DOCX only.
9. **PDF comes last:** once all parts are approved, combine all DOCX files into one PDF (with fonts embedded) in `pdf/` with `pipeline/make_pdf.py`, and look over its contact sheet. It fills the contents page with the final Turkish page numbers first.
