# Translation pipeline

Tools for the workflow in `../RULES.md`. You normally don't run them yourself: in Claude Code, from the `translations/` folder, type

```
/arabic-to-turkish next premise ten premises
/arabic-to-turkish "المقدمات العشر" 15-17
/arabic-to-turkish fifth premise
/arabic-to-turkish new ~/Downloads/kitap.pdf
```

Claude finds the book and pages, transcribes, translates, checks, builds the DOCX, writes the CHECK file and stops for your review.

## The scripts

| Command | What it does |
|---|---|
| `python3 pipeline/status.py [book]` | Parts done, sections left, and the next part |
| `python3 pipeline/pages.py <book> 15-17` | Renders source pages (+ footnote zoom, text layer) to `<book>/work/pages/` |
| `python3 pipeline/check.py <book> 05` | Automatic checks of a part (below) |
| `python3 pipeline/build.py <book> 05 [--pages 15-17]` | DOCX → PDF → page images in `<book>/work/render/`; records the part's page count and contents pages in `book.json` |
| `python3 pipeline/new_book.py <file.pdf> [--name …]` | Sets up a new book folder |
| `python3 pipeline/make_pdf.py <book> [--draft]` | The final book PDF from the reviewed DOCX files (below) |
| `pipeline/quran/fetch.sh` | One-time download of the Qur'an text used by the verse check |

`<book>` can be any of the book's names (folder, Turkish, English or an alias from `book.json`).

## What check.py checks

It compares the Arabic transcription (`<book>/source/text/p-NNN.ar.md`) with the Turkish content file, page by page.

- **ERROR** (fix, or explain in the CHECK file): footnote markers and footnotes; every number (hadith numbers, volumes/pages, years); ﷺ vs "(s.a.v.)"; Qur'an references: each quoted verse is looked up in the Qur'an text, a wrong printed reference is reported with the right one, and the Turkish reference must point to the verse actually quoted.
- **WARN** (a hint only; natural Turkish wins): differing counts of `! ? !. .. …`, of brackets, «» and dashes; Arabic letters left in the Turkish; numbers in the PDF text layer that the transcription lacks.
- **WARN `pronoun:`** (hints for the readability pass, RULES.md §4 *Pronouns*): a footnote that opens with a pronoun; "onun (s.a.v.)" instead of the Prophet's name; a sentence with 3+ third-person pronoun forms ("onu, ona, kendisi…", text in `{…}` and a single repeated form are ignored). Read each one and confirm every pronoun has one clear referent.
- **NOTE**: a corrected reference, to log under *Source errors corrected* and report.

There is no glossary enforcement: the glossary guides word choice, it doesn't override natural Turkish.

## What make_pdf.py does

The last step (RULES.md §6.9). It converts each part's DOCX **as reviewed** (nothing is rebuilt), merges them into `<book>/pdf/<Turkish title>.pdf` and checks the result.

- **Before converting** it stops if: the parts in `book.json` leave a source page out or overlap; a DOCX or CHECK file is missing; a font the DOCX uses isn't installed; or a DOCX isn't exactly what `make.js` makes from today's content file (edited after the build, or edited by hand). Then rebuild that part with `build.py`, review it, and run again.
- **Each part's PDF:** every font embedded and no fallback font (a fallback means a missing glyph, e.g. ﷺ), and the right printed page number on every page: numbering runs on from the previous part. (Older books without `"layout": "flow"`: one page per source page, numbered as in the source.)
- **Contents:** a part whose DOCX differs from today's build only in its contents numbers is rebuilt first, so the contents shows the final Turkish page numbers.
- **The book PDF:** the contents entries become bookmarks, and each must land on the page that carries its title. (Older books: total page count must equal the source's.) Title, author and language (`tr`) are set.
- Images keep full resolution (JPEG quality 100), so the file is fit for print.
- `--draft` builds from the parts done so far; gaps, out-of-date DOCX files and missing CHECK files become warnings. The draft goes to `work/final/`, never to `pdf/`.
- `work/final/` also holds `report.txt` and `contact-sheet.png`, every page at a glance, for a last look before sharing. Exit code 1 means a check failed and no PDF was delivered.

## Files per book

- `book.json`: names, PDF, `page_offset` (pages before printed page 1, e.g. the cover), `sections` (from the contents page) and `parts` (source PDF range of each part); `status.py` and "next" rely on it. `"layout": "flow"` (set for new books) frees the page count; build.py then keeps `layout_pages` (pages per part) and `toc_pages` (printed page of each contents title) up to date.
- `source/text/`: page transcriptions; `work/`: renders and check reports (safe to delete, rebuilt on demand).

## Setup notes

- After cloning: `npm install` (Node packages) and `pipeline/quran/fetch.sh` (Qur'an text, not kept in git). Also needed: Python 3, LibreOffice, poppler-utils (`pdftoppm`, `pdfimages`), ImageMagick and the Open Sans font.
- Book folders are not kept in git (see `.gitignore`); only the pipeline, the rules and the skill are.
- `pipeline/template/make.js` is the layout engine copied into each new book. Pages of one section flow together and page numbers come from the Turkish layout; see RULES.md §2 and the comments in the file.

- `docx` and `pdf-lib` (Node) are installed once in `translations/node_modules`, shared by all books.
- `build.py` finds LibreOffice in `PATH` or `/opt/libreoffice*` and uses its own profile, so an open LibreOffice window doesn't interfere.
- Qur'an text: Tanzil "Simple Clean" (tanzil.net, CC BY 3.0). Without it, references are still compared with the source but not verified.
