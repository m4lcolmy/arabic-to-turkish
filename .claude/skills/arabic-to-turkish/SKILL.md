---
name: arabic-to-turkish
description: Translate the next part of a book in this translations folder (Arabic PDF → Turkish DOCX) by the rules in RULES.md, with transcription, automatic checks, DOCX build and the CHECK file; or set up a new book from a PDF. Use when the person runs /arabic-to-turkish or asks to translate the next premise, section or pages of a book here.
argument-hint: "<book> <pages | next | fifth premise>  ·  new <file.pdf>"
---

# Translate a part

The text after `/arabic-to-turkish` says which book and which pages, in any form:
`"المقدمات العشر" 15-17` · `next premise ten premises` · `next` · `fifth premise` · `on öncül 15-17` · `new ~/kitap.pdf`.

All commands run from the `translations/` folder. `RULES.md` is the authority on quality and design; this skill only adds the order of work and the tools.

## 0. Prepare
Read `RULES.md`, the book's `GLOSSARY.md`, and the previous part's content file and CHECK file, so terms and voice continue.

## 1. Work out book, pages and part number
- Request starts with `new` → go to **Setting up a new book** below.
- Run `python3 pipeline/status.py <the request's words>`. It finds the book from any of its names inside the phrase (no book named → the most recent one) and prints the parts, the open sections and a `Next:` line.
- Pages: an explicit range is used as given. "next" / "next premise|section|chapter" → the `Next:` line. A named section ("fifth premise", "beşinci öncül", "المقدمة الخامسة") → that section's range.
- Part number: the next free one, unless an existing part is being redone.
- Ask only when it is really ambiguous: several books match, or the range splits a section or overlaps a finished part. Otherwise state one line, e.g. `Part 05 = Beşinci Öncül, PDF pp. 15–17`, and go on.

## 2. Read the source
`python3 pipeline/pages.py "<book>" A-B` → `<book>/work/pages/`. Read every `p-NNN.png`, and `p-NNN-zoom.png` for footnotes and small text. `p-NNN.txt` (text layer) is a cross-check only.

## 3. Transcribe
Write each page to `<book>/source/text/p-NNN.ar.md` (3-digit PDF page number), **exactly as printed**: wording, punctuation (`!.` `..` `؟!`), dashes, brackets, «», ﷺ, and printed references even when they look wrong. If a transcription already exists, check it against the image and reuse it.

```
<!-- PDF page 15 · header: المقدمات العشر - المقدمة الخامسة -->
# Title as printed

Paragraph text, footnote markers as [[fn:1]] (numbered as printed on this page),
^^orange text^^ where the source colours it, **bold**, verses {…} [سورة …: n], hadith {…}.

**First hemistich / second hemistich**

---
[1] Footnote 1 text
[2] Footnote 2 text
```
One blank line between paragraphs; footnotes after the last `---` line. Images and decorations are not transcribed.
- Ornate Qur'an brackets ﴿ ﴾ are written { }. Harakat may be left out in prose; keep the words and letters exact.
- Volume/page numbers in logical order, volume first: (1/83). The text layer often shows them reversed.
- The cover page is transcribed for the record but skipped by the checker.

## 4. Translate
Write `<book>/build/content/part-NN.js` with the same structure as the previous part: one entry per source page, `header`, `blocks`, and `footnotes` with ids unique across the part. (Books without `"layout": "flow"` in `book.json`, such as المقدمات العشر, also need `pageStart`, the printed page number, on the first page.)
- Contents page: a `toc` block with the entries as printed, numbers included (the checks compare them with the source). In flow books the build replaces the numbers with the real Turkish pages, so each entry's title must be **exactly** the title as it appears in the text.
- Entries stay one per source page (the checks compare page by page), but the build **flows** the pages of one section together (RULES.md §2). A new page starts automatically at the cover, a blank page and a header change (new section). Add `newPage: true` to a page that must stand alone otherwise: contents, full-page image, back matter.
- A paragraph the source splits across two pages: write its first half at the end of one page and its second half as the next page's first block with `cont: true`. The build joins them into one paragraph. Apply RULES.md §4 in full: faithful, natural literate Turkish, punctuation from the source, source errors corrected only when verified.
- The glossary is guidance, not a rule: use its terms for consistency, but natural Turkish in context wins. Add new recurring choices to `GLOSSARY.md`.
- Images: find the page's original with `pdfimages -list -f A -l B "<pdf>"` (new books already have them as `assets/src-PAGE-NUM.*`) and give it a clear name in `assets/`. An image with text baked in is rebuilt as a new image with Turkish text.
- The page count may differ from the source (RULES.md §2): don't squeeze or stretch text to match it. `tight: true` is only for a page that looks crowded in the source too. Never cut content.

## 5. Automatic checks
`python3 pipeline/check.py "<book>" NN`
- **ERROR**: fix it, or, when it is a deliberate deviation or a verified source correction, explain it in the CHECK file.
- **WARN**: look at each one and decide. Change the Turkish only if the source really has that mark and Turkish allows it. Never bend natural Turkish to silence a warning.
- **NOTE** (corrected reference): verify the verse yourself, log it under *Source errors corrected*, and report it.
- If the verse check says a quote is somewhere else, first re-check your transcription against the image.
Re-run until no ERROR is left unexplained.

## 6. Build and look
`python3 pipeline/build.py "<book>" NN --pages A-B` (`--pages` only the first time). Build parts in book order: a part's page numbers start after the previous part's real last page. build.py records the part's page count and where the contents titles landed, and names any later parts to rebuild when the count changed. Look at every image in `<book>/work/render/part-NN/` (`tr-NN.png`, Turkish page NN of the part): no page ending early inside a section, each section starting on a new page, titles not stranded at a page bottom, footnotes on the page of their marker, missing glyphs, images. Fix and rebuild.

## 7. Completeness pass
Source image against the Turkish, sentence by sentence (RULES.md §6). Write `<book>/CHECK-part-NN.md` in the format of the previous CHECK files: ✓ list per page, *Deliberate deviations*, *Source errors corrected*, *Readability pass*, *Result*. Add one line on the automatic checks (errors fixed; warnings accepted and why).

## 8. Readability pass
Read the Turkish alone, as a Turkish reader. Make minimal fixes that keep the author's voice (RULES.md §4 balance rule), re-check changed sentences against the source, and re-run steps 5–6 if anything changed.
Include the pronoun check (RULES.md §4 *Pronouns*, §6 step 7): every footnote read on its own, every pronoun-heavy sentence resolved to one referent. The `pronoun` WARNs from check.py are the starting list; log non-obvious fixes in the CHECK file.

## 9. Independent review
Reserved for later; not enabled yet.

## 10. Deliver and stop
Report: the DOCX path and page count (and the source range's count when they differ), **every source correction** (page, printed → corrected), anything marked *Please review*, and new glossary entries. Then stop; the next part starts only after the person approves.

---

## Setting up a new book
1. `python3 pipeline/new_book.py <file.pdf> [--name "<original title>"]` creates the folder, copies the PDF, extracts images and copies the layout template.
2. Render and read the cover, the contents page and the last pages (`pages.py`). Fill `book.json`: `title_ar`, `title_tr`, `title_en`, `aliases` (include forms without diacritics), `author`, `page_offset` (PDF page − printed page; confirm on two pages; the Turkish edition starts its numbering after the same front pages), and `sections` from the contents, plus front and back matter, covering every PDF page.
3. Match the original design (RULES.md §5): adapt the design tokens, header and footer in `build/make.js` (copied from `pipeline/template/`; keep its page-flow logic), prepare logo, footer and cover assets (`build/cover.py` is the previous book's cover script, a starting point). Agree the look with the person on Part 01 before continuing.
4. Then translate Part 01 with steps 0–10.
