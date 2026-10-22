# Translation pipeline

Tools for the workflow in `../RULES.md`. You normally don't run them yourself: in Claude Code, from the `translations/` folder, type

```
/arabic-to-turkish next premise ten premises
/arabic-to-turkish "المقدمات العشر" 15-17
/arabic-to-turkish fifth premise
/arabic-to-turkish new ~/Downloads/kitap.pdf
```

Claude finds the book and pages, transcribes, translates, checks, builds the part PDF, writes the CHECK file and stops for your review.

English books work the same way with `/english-to-turkish` (rules: `../RULES-EN.md`):

```
/english-to-turkish new ~/Downloads/book.pdf
/english-to-turkish next chapter purpose of life
```

The scripts are shared. `"source_lang": "en"` in `book.json` (set by `new_book.py --lang en`) switches them to English: transcriptions are `p-NNN.en.md`, check.py and review.py use the English checks and rules, and run_book.py runs the English skill.

## The scripts

| Command | What it does |
|---|---|
| `python3 pipeline/status.py [book]` | Planned parts, their state, and the next part |
| `python3 pipeline/plan.py <book> [--max-pages 12]` | Groups the sections into parts (whole sections, at most N source pages) for "next" |
| `python3 pipeline/run_book.py <book> [--max-parts N]` | Translates the rest of the book unattended, then makes the PDF (below) |
| `python3 pipeline/finish_part.py <book> 05` | After a part finished by hand (interactive session): checks its PDF, CHECK file and REVIEW-QUEUE.md entry, clears the runner's resume mark for it, logs it in `runs/log.tsv` and commits the book folder, so `run_book.py` moves on to the next part |
| `python3 pipeline/pages.py <book> 15-17` | Renders source pages (+ footnote zoom, text layer) to `<book>/work/pages/` |
| `python3 pipeline/check.py <book> 05` | Automatic checks of a part (below) |
| `python3 pipeline/review.py <book> 05` | Independent review of a part by a ChatGPT model through the Codex CLI; findings in `<book>/reviews/part-05.json` (below) |
| `python3 pipeline/build.py <book> 05 [--pages 15-17]` | The part PDF to review, `<book>/part-NN_pdf-pA-B.pdf` (print quality, fonts embedded; made through a temporary DOCX in `work/build/`), and page images in `<book>/work/render/`; records the part's page count and contents pages in `book.json` |
| `python3 pipeline/new_book.py <file.pdf> [--name …] [--lang en]` | Sets up a new book folder (`--lang en` for an English source) |
| `python3 pipeline/make_pdf.py <book> [--draft]` | The final book PDF in `<book>/output/`, merged from the reviewed part PDFs (below) |
| `node pipeline/arabic_pdf.mjs <book> [--library [--dry-run]]` | The Arabic book as a PDF whose text copies and searches correctly, from the transcriptions; `--library` puts it in `~/Library` (below) |
| `pipeline/quran/fetch.sh` | One-time download of the Qur'an text used by the verse check |

`<book>` can be any of the book's names (folder, Turkish, English or an alias from `book.json`).

## Optional book.json settings

- `front_pages`: Turkish pages before printed page 1, when the Turkish front matter differs in length from the source's (default `page_offset`). `front_roman_from`: the position (cover = 1) numbered "i"; front matter is then numbered in roman, otherwise not at all.
- `page_number: "header"`: the page number is in the running head ("12 | TITLE"); `make_pdf.py` reads it there (section openers: at the foot).
- `omit`: PDF page ranges left out of the Turkish edition on purpose (e.g. an index that points to the source's page numbers); `make_pdf.py` counts them as covered.
- `notes: "endnotes"`: notes at the back; markers `[[en:N]]` (RULES-EN.md §4).
- Contents titles are matched on the built pages without case (titles may be set in capitals), and only in the part whose section they title.

## What check.py checks

It compares the Arabic transcription (`<book>/source/text/p-NNN.ar.md`) with the Turkish content file, page by page.

- **ERROR** (fix, or explain in the CHECK file): footnote markers and footnotes; every number (hadith numbers, volumes/pages, years); ﷺ vs "(s.a.v.)"; Qur'an references: each quoted verse is looked up in the Qur'an text, a wrong printed reference is reported with the right one, and the Turkish reference must point to the verse actually quoted.
- **WARN** (a hint only; natural Turkish wins): differing counts of `! ? !. .. …`, of brackets, «» and dashes; Arabic letters left in the Turkish; numbers in the PDF text layer that the transcription lacks.
- **WARN `pronoun:`** (hints for the readability pass, RULES.md §4 *Pronouns*): a footnote that opens with a pronoun; "onun (s.a.v.)" instead of the Prophet's name; a sentence with 3+ third-person pronoun forms ("onu, ona, kendisi…", text in `{…}` and a single repeated form are ignored). Read each one and confirm every pronoun has one clear referent.
- **NOTE**: a corrected reference, to log under *Source errors corrected* and report.

English books (`"source_lang": "en"`) differ in three checks:
- **Qur'an**: an English quote can't be matched against the Arabic text, so only the references are checked. Numeric ones such as (2:255), [al-Baqarah 2:255-256] and (Qur'an 3:7) must match the Turkish [Bakara: 255] and exist in the Qur'an (ERROR, or a NOTE for a corrected one that doesn't exist). A reference by sura name only, e.g. (al-Ma'idah: 3), is compared by its verse numbers, and gets a WARN when the sura name doesn't obviously match. Numbers after a hadith collection or "vol." are not taken for verses.
- **Salutations**: ﷺ, (pbuh), (saw), ṣallā Allāhu ʿalayhi wa sallam and "peace be upon him"-type forms are counted against "(s.a.v.)" + "(a.s.)".
- **Marks**: hyphens inside words don't count as dashes, and verse references don't count as brackets.

There is no glossary enforcement: the glossary guides word choice, it doesn't override natural Turkish.

## What review.py does

Step 9 of the skill. It sends the part's source page images, transcriptions, Turkish content file, `RULES.md`, the glossary and the CHECK file to a ChatGPT model with `codex exec` (read-only, no files changed), and asks for errors (omissions, additions, wrong meaning, numbers, references, ambiguous pronouns) and suggestions (stiff Turkish, glossary inconsistencies). Deliberate deviations already explained in the CHECK file are not raised again; instead it gives an opinion (keep / change, with the wording it recommends) on every open decision: the *Please review* items and deliberate deviations of the CHECK file and of the part's `REVIEW-QUEUE.md` entry.

For an English book it also sends `RULES-EN.md`. The findings are saved to `<book>/reviews/part-NN.json` and printed as R1, R2 … (findings) and Q1, Q2 … (open decisions). The translating session checks each one against the source image, applies or rejects it, logs the decision under *Independent review* in the CHECK file and reports it (in unattended runs, in `REVIEW-QUEUE.md`). A failed review (exit code 2) is logged and skipped, never blocks a part.

- Needs the Codex CLI signed in with ChatGPT (`codex login`; the ChatGPT desktop app ships one in `/usr/lib/chatgpt/resources/codex`). No OpenAI API key.
- `--model` defaults to `gpt-6.1-sol`, `--effort` to `medium` (enough for this job at a fraction of the frontier model's usage); `--timeout` to 9 minutes. A part of ~10 pages takes about 3–5 minutes.

## What make_pdf.py does

The last step (RULES.md §6.10). It merges the part PDFs **as reviewed** into `<book>/output/<Turkish title>.pdf` and checks the result.

- **Before merging** it stops if: the parts in `book.json` leave a source page out or overlap; a part PDF or CHECK file is missing; or a part PDF is out of date (its content file, `make.js` or assets changed after it was built: `book.json` "built" records what each was made from). Then rebuild that part with `build.py`, review it, and run again.
- **Each part's PDF:** every font embedded and no fallback font (a fallback means a missing glyph, e.g. ﷺ), and the right printed page number on every page: numbering runs on from the previous part. (Older books without `"layout": "flow"`: one page per source page, numbered as in the source.)
- **Numbers:** a part whose text is unchanged but whose page numbers or contents numbers moved (a part before it changed length, later titles were placed) is rebuilt first, so the contents shows the final Turkish page numbers.
- **The book PDF:** the contents entries become bookmarks, and each must land on the page that carries its title. (Older books: total page count must equal the source's.) Title, author and language (`tr`) are set.
- Images keep full resolution (JPEG quality 100), so the file is fit for print.
- `--draft` builds from the parts done so far; gaps, out-of-date part PDFs and missing CHECK files become warnings. The draft goes to `work/final/`, never to `output/`.
- `work/final/` also holds `report.txt` and `contact-sheet.png`, every page at a glance, for a last look before sharing. Exit code 1 means a check failed and no PDF was delivered.

## What arabic_pdf.mjs does

The Arabic edition, for reading and copying: the `/arabic-pdf` skill runs it. Many Arabic PDFs copy wrong (their text layer gives «ملن» for «لمن»), so it rebuilds the book from `source/text/` with the PDF builder of Nuskha (`~/code/Nuskha`, or `NUSKHA=`): A5 pages in Amiri with a hidden text layer that viewers copy as written, the cover as an image, «الفهرس» at the end with links.

- Its settings are the `"arabic_pdf"` section of `book.json` (text pages, cover, title page, contents pages, running heads, colours…; the skill lists them).
- It reports notes on the wrong page, paragraphs it joined across pages by guess, `#` lines it set as display lines, contents entries it found no heading for, and how much of the text pdf.js and PDFium read back.
- `--library` moves the copies identical to the source PDF (anywhere under `~/Library`, or `LIBRARY=`) to the trash and puts the new PDF there; `--dry-run` only shows what it would do. Other files with the title in their name are left alone.

## Unattended run (run_book.py)

```
python3 pipeline/run_book.py nusra --max-parts 2    # two parts, then pause for a look
python3 pipeline/run_book.py nusra                  # the rest, then the final PDF
```

One fresh `claude -p` session (Opus 5.5, high effort) per planned part, in book order, running `/arabic-to-turkish` or, for an English book, `/english-to-turkish`. After each part the book folder is committed to its own local git repository (`git -C "<book>" log`; roll back one part with `git -C "<book>" revert <commit>`). Review items collect in `<book>/REVIEW-QUEUE.md`; `<book>/runs/log.tsv` records minutes, peak context and compactions per part. It stops on `<book>/BLOCKED.md`, on a part failing twice, or when make_pdf.py finds a problem; it waits out usage limits. Stop it any time with Ctrl+C: the next run resumes the unfinished part.

### When Claude's usage runs out (Codex fallback)

With the default `--engine auto`, a Claude usage limit doesn't stop the run: the same part goes to **`gpt-6-astra`** (effort `high`) through the Codex CLI, signed in with ChatGPT. Codex gets `SKILL.md` as its instructions and the same request (`<book> next unattended`), so it follows the same steps and `RULES.md`. It resumes from the files the stopped session left (transcriptions, content file, CHECK file). Every new part tries Claude first again, so Claude takes over by itself once its limit resets. If Codex is limited too, the runner waits `--wait-minutes` and tries again.

- A part whose session was cut off (usage limit, error, Ctrl+C) is marked in `work/resume.json` and resumed first, by its page range, even when its part PDF and CHECK file already exist (the last steps, review decisions and the REVIEW-QUEUE.md entry, may be missing). The runner moves on only after a session that ended normally.
- The review step (`review.py`, `gpt-6.1-sol`) is unchanged. On a Codex part, translator and reviewer are both OpenAI models (different ones, separate sessions), and both draw on the same ChatGPT quota.
- A Codex part says *Translated by gpt-6-astra (Codex fallback)* in its CHECK file, in its `REVIEW-QUEUE.md` heading and in its book commit; read those parts a little more carefully.
- Codex runs in its `workspace-write` sandbox: it can write only inside `translations/` and `~/.codex` (the nested `review.py` → `codex` call needs that), with network on for the review. Your own `~/.codex/config.toml` isn't loaded.
- Logs: `runs/part-NN-codex-tryN.jsonl`; `runs/log.tsv` has an `engine` column (`claude:…` / `codex:…`).
- `--engine codex` uses Codex only (e.g. when you know Claude is out); `--engine claude` waits out limits as before. `--fallback-model` / `--fallback-effort` change the Codex model (`gpt-6.1-sol` has a larger context window if Codex parts get compacted).

## Files per book

- `book.json`: names, PDF, `page_offset` (pages before printed page 1, e.g. the cover), `sections` (from the contents page), `parts` (source PDF range of each planned part, from `plan.py`) and `part_max_pages`; `status.py` and "next" rely on them. `"layout": "flow"` (set for new books) frees the page count; build.py then keeps `layout_pages` (pages per part) and `toc_pages` (printed page of each contents title) up to date.
- `source/text/`: page transcriptions; `reviews/`: the ChatGPT review of each part; `work/`: renders and check reports (safe to delete, rebuilt on demand).

## Setup notes

- After cloning: `npm install` (Node packages) and `pipeline/quran/fetch.sh` (Qur'an text, not kept in git). Also needed: Python 3, LibreOffice, poppler-utils (`pdftoppm`, `pdfimages`), ImageMagick and the Open Sans font.
- Book folders are not kept in git (see `.gitignore`); only the pipeline, the rules and the skill are.
- `pipeline/template/make.js` is the layout engine copied into each new book. Pages of one section flow together and page numbers come from the Turkish layout; see RULES.md §2 and the comments in the file.

- `docx` and `pdf-lib` (Node) are installed once in `translations/node_modules`, shared by all books.
- `build.py` finds LibreOffice in `PATH` or `/opt/libreoffice*` and uses its own profile, so an open LibreOffice window doesn't interfere.
- Qur'an text: Tanzil "Simple Clean" (tanzil.net, CC BY 3.0). Without it, references are still compared with the source but not verified.
