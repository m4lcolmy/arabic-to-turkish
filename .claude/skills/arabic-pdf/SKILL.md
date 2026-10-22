---
name: arabic-pdf
description: Make a text-selectable Arabic PDF of a book (Arabic you can select, copy and search correctly, vowel marks and all) from its page transcriptions with the Nuskha PDF builder, and put it in the person's library (~/Library) in place of the old PDF. Use whenever the person wants a copyable or searchable Arabic edition of a book, says an Arabic PDF copies wrong (e.g. «لمن» comes out «ملن», «الأولى» as «األوىل»), asks to do "the same" for another book, or to rebuild one, even if they don't say PDF or name this skill. Also for a book in ~/Library that has no folder here yet: it is transcribed first.
argument-hint: "<book> [library]"
---

# Arabic text edition of a book

Many Arabic PDFs (made with Word or InDesign) look right but copy wrong: their text layer gives «ملن» for «لمن», «األوىل» for «الأولى». This skill rebuilds the book from its page transcriptions as a new PDF: Typst sets the text in Amiri (A5), and a hidden text layer makes viewers copy and search the Arabic as written. The cover is kept as an image, the title page and everything after it become real text, and «الفهرس» at the end gets the real page numbers and links.

All commands run from the `translations/` folder. The builder is `pipeline/arabic_pdf.mjs`; it uses Nuskha's code in `~/code/Nuskha` (set `NUSKHA=` if it is elsewhere; it needs `npm install` there).

## 1. Find the book
`python3 pipeline/status.py <the request's words>` finds a book folder by any of its names.

A book that has no folder here (a PDF in `~/Library` or elsewhere): `python3 pipeline/new_book.py <file.pdf> --name "<Arabic title>"`, then fill `title_ar`, `aliases` and `author` in its `book.json` so it can be found by name. (new_book also copies the translation templates; leave them.)

## 2. Transcriptions
Every page that goes in must be transcribed in `<book>/source/text/p-NNN.ar.md`. Books translated here have them already. The build stops and lists the missing pages.

To transcribe, read and follow steps 2 and 3 of `.claude/skills/arabic-to-turkish/SKILL.md`: the same format, *exactly as printed*. Work in batches of about ten pages (`python3 pipeline/pages.py "<book>" A-B`, then read each image) and reuse files that exist. The source's text layer (`p-NNN.txt`) is a cross-check only: it is the broken text this edition replaces.

## 3. Settings in book.json
Look at the cover, the title page, the contents and the last pages (images and transcriptions). Then add an `"arabic_pdf"` section to `book.json`. Keep the JSON style of the file (`indent=2`, Arabic unescaped): the Python scripts rewrite this file.

| Key | What it is |
|---|---|
| `author` | **Required.** The author in Arabic, for the title page default, the card and the PDF details. |
| `text` | **Required.** `[first, last]`: PDF pages of the running text, from the end of the front matter to the end of the text. |
| `title` | Default `title_ar`. |
| `cover` | PDF page used as the cover image (cover artwork). Leave it out if there is none. |
| `title_page` | `{"top": [...], "above": [...], "title": "...", "below": [...], "bottom": [...]}`: the title page's lines as printed, markup allowed (`^^سلسلة^^` for a coloured line). Top: basmala and the like; above and below the big title; bottom: publisher. Without it: the title and author. Add no words that the book doesn't print. |
| `card` | Rows `[["الكتاب", "..."], ["المؤلف", "..."], ...]` for «بطاقة الكتاب». Only facts the book prints (cover, title page, colophon): publisher, date, edition. Without it: title and author. |
| `contents` | PDF pages of the source's contents list. They are left out, since the new PDF makes its own «الفهرس». The script reads them to tell chapters from other `#` lines: a `#` line that is in the contents opens a chapter (new page, in «الفهرس»); any other `#` line is a centred red display line. Without `contents`, every `#` line is a chapter. |
| `headings` | `{"3": "المقدمة"}`: a chapter heading the text doesn't print but the contents lists (an introduction without a title). It goes before page 3's text, worded as in the contents. |
| `skip` | Pages inside `text` to leave out (a full-page image, an advert). Blank pages are left out by themselves. |
| `back` | Pages after the text set each on a page of its own, centred: a closing word, a link page, a back-cover text. |
| `running_heads` | One short head per chapter, for odd pages (even pages show the title). Prefer the source's own page headers: the transcription comments record them as `header: …`. Without it, the chapter title is shrunk to fit the line. |
| `colours` | Markup colours as in the source, e.g. `{"^^": "#e8743b"}`. Defaults: `^^` dark blue, `%%` green, `~~` red, `&&` dark gold. In a translated book, `build/make.js` has the colours already matched to the source. |
| `join`, `no_join` | Pages whose first paragraph does or doesn't carry on the paragraph from the page before. Needed only where the translation (`build/content`) hasn't decided it: there the script guesses (the page ends without a full stop, or inside markup). |
| `description`, `keywords`, `file` | PDF details, and the file name (default `<title>.pdf`). |

Two worked examples: `نصرة للشريعة/book.json` (series transcript: cover, a title page as printed, contents at the end, episode running heads) and `المقدمات العشر/book.json` (contents at the front, an introduction without a heading, closing pages, orange verses).

## 4. Build and read the report
`node pipeline/arabic_pdf.mjs "<book>"` writes `<book>/output/<title>.pdf` in seconds and prints a report. Go through it:

- **notes on the wrong page**: should be 0.
- **guessed joins**: look at those page pairs in the source images. Set `join`/`no_join` where a guess is wrong.
- **display lines**: `#` lines that are not in the contents. Check that each one really isn't a chapter.
- **contents entry with no heading**: add it under `headings` if it opens a chapter. Ignore it if it doesn't, e.g. an entry for the contents itself.
- **note without a marker**: the source printed a note with no marker. It stays at the foot of its page without a number; mention it in the report.
- **readback**: how many words pdf.js (Firefox, Readest) and PDFium (Chrome, Edge) read back. Both should be 99.5% or more. A word missing because the transcription writes two words as one token («والأمر}[سورة», with no space) is the checker splitting words, not an error. `--pages` lists the misses page by page. A known one: a vowel mark just before an en dash («وجلَّ–») copies after the dash in pdf.js.

A wrong transcription stops the build with its page: unbalanced markup, a footnote line it can't read, a note with a marker but no text. Fix the transcription against the source image, never by guessing.

## 5. Look at it
Render the PDF (`pdftoppm -r 60 -png "<pdf>" <scratchpad>/p`) and look at these pages:
- the cover, title page and card;
- the first chapter page;
- a page with footnotes, and one with colours or a verse line;
- an odd and an even page: the running heads must sit on one line, or set `running_heads`;
- the back pages and «الفهرس».

Compare one or two pages with the source image for colours. Fix the settings and build again.

## 6. Put it in the library
Do this when the person asked for the library, or asked to replace the book there. If they only asked for the PDF, ask first.

1. Run `node pipeline/arabic_pdf.mjs "<book>" --library --dry-run`. It shows the plan:
   - copies identical to the book's source PDF, anywhere under `~/Library`, go to the trash (the person can restore them);
   - the new PDF goes in as `~/Library/<title>.pdf`.
2. It also lists other files with the title in their name. They differ from the source, so it leaves them alone: name them to the person and ask before touching them.
3. Then run it without `--dry-run`.

The script refuses to overwrite an existing file it didn't make. It finds its own files by the `text-edition` keyword it writes into the PDF.

## 7. Report
Tell the person:
- the PDF's path and page count, and the readback figures;
- what this edition leaves out: images in the text, blank pages, and the source's contents pages (replaced by «الفهرس» at the end);
- source slips you noticed, such as a note without a marker;
- what changed in the library: files moved to the trash, the new file.

**Readest** reads from `~/Library` but keeps its own entry for each book, with the old title, cover and page count. Tell the person to remove the old book in Readest and import the new file. Warn them: if Readest offers to delete the book's file, that entry may now point at the new PDF.

## Limits
- Text only: photos, charts and decorations are left out, as in the transcription. Say so when a book's images carry meaning.
- The pages are laid out anew (A5, Amiri), so page numbers differ from the source.
- Needs poppler (`pdftoppm`, `pdfinfo`), `gio` for the trash, and DejaVu Sans for symbols Amiri lacks (☚ ♦).
