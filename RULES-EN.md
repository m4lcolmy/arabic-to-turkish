# Translation Rules: English Sources

`RULES.md` applies to English books too: folder layout, page counting, translation quality, design and workflow. This file changes only what is specific to Arabic there. Where the two differ for an English book, this file wins.

## 1. Files

- `book.json` has `"source_lang": "en"` (`new_book.py --lang en` sets it). The pipeline reads it: transcriptions are `source/text/p-NNN.en.md`, `check.py` checks English verse references and salutations, `review.py` sends this file to the reviewer, and `run_book.py` runs `/english-to-turkish`.
- `GLOSSARY.md` has the columns English | Turkish | Note.

## 2. Reading the source (replaces RULES.md §3)

- Read every page **visually**, as for Arabic books.
- An English PDF's text layer (`p-NNN.txt`) is usually reliable enough to start a transcription from, but **every line is checked against the page image**. Typical faults:
  - broken ligatures (fi, fl, ff, ffi);
  - line-end hyphens (join "know-ledge" back into "knowledge", but keep real hyphens such as "well-known");
  - transliteration marks (ā ī ū ḥ ṣ ḍ ṭ ẓ ʿ ʾ) dropped or turned into other characters;
  - superscript footnote numbers run into the text;
  - running heads, page numbers, drop capitals and small capitals mixed into the text.
- A scanned book without a text layer is transcribed from the image alone.

## 3. Translation (adapts RULES.md §4)

Everything in RULES.md §4 applies: faithful and natural, the middle ground between literal and free, add nothing and leave nothing out, keep the author's voice and emphasis devices, glossary, verified source corrections logged and reported. In addition:

- **Turkish sentence structure, not English.** Rebuild English syntax as natural Turkish, with the verb at the end. Long relative clauses, chains of "that…", "it is … that…", "there is/are", and passives become active Turkish sentences where Turkish prefers them (no "tarafından" chains). Split a long English sentence where Turkish needs it. Keep its parts and their logic.
- **No calques or false friends.** Some examples: "take place" → "gerçekleşmek" (not "yer almak"); "play a role" → "rol oynamak" only where Turkish says it; "actually" is not "aktüel", "eventually" is not "eventüel", "realize" is not "realize etmek", "sympathetic" is not "sempatik". An English idiom is rendered by its meaning. A pun that cannot carry over is translated for its meaning and logged under *Deliberate deviations*.
- **Generic "you" / "one" / "we"**: keep the author's direct address to the reader. Otherwise use the Turkish generic form ("insan", the impersonal passive) where a literal "sen" would read as personal.
- **Spoken restatements** (RULES.md §4) are merged only when the English book is itself a transcript of talks. Otherwise the author's repetition stays.
- **Islamic terms.** Use the established Turkish Islamic term, never a paraphrase built from the English. This applies to:
  - transliterated words in the English: tawḥīd → tevhid, sharīʿah → şeriat, fitnah → fitne, bidʿah → bid‘at, ʿaqīdah → akide, taqwā → takvâ;
  - English words that stand for an Islamic concept, once you have checked which concept the context means: prayer → namaz (ṣalāh) or dua (duʿāʾ); charity → zekât or sadaka; the Hereafter → ahiret; the Companions → sahâbe; scholars → âlimler; innovation → bid‘at; polytheism / associating partners → şirk; disbeliever → kâfir; hypocrite → münafık; the Sunnah → Sünnet; jurisprudence → fıkıh.

  "The Messenger of Allah" → "Resûlullah"; "the Prophet" → "Peygamber" or "Nebî", as the glossary settles.
- **"God": decide by who is speaking.** Compare who says it, not only the word:
  - in the words of a Muslim (a quotation of bin Laden or of a scholar, a translated Arabic text, a Muslim author's own voice) → "Allah";
  - in the voice of a non-Muslim author or speaker (e.g. a Western author's own "God", a dedication, a Christian speaking of God) → "Tanrı" ("Tanrı’nın", "O’nun");
  - "Allah" printed as such stays "Allah", whoever writes it.
- **Salutations.**
  - ﷺ, (pbuh), (saw), (saws), "peace and blessings be upon him" and ṣallā Allāhu ʿalayhi wa sallam → "(s.a.v.)".
  - "peace be upon him" after another prophet, (as) and ʿalayhi al-salām → "(a.s.)".
  - "may Allah be pleased with him/her/them" and (ra) → "(r.a.)" / "(r.anha)" / "(r.anhüm)".
  - Other formulas (e.g. "may Allah have mercy on him") take the form settled in `GLOSSARY.md`, chosen on Part 01.
- **Pronouns** (RULES.md §4 *Pronouns*). English "he / she / it / they" keep gender and number apart; Turkish "o / onu / ona / onun / kendisi" do not. A sentence with "he" and "it", or with "he" for two different people, needs the same care as the Arabic. The capitalised "He / His / Him" for Allah → "O / O’nun / O’na". A bare "he" for the Prophet that could be misread → "Resûlullah (s.a.v.)". Every other point of that section applies as written.
- **Names.**
  - People from Islamic history: Turkish transliteration with circumflexes and ‘ayn marks, in the form established in Turkish. Abū Hurayrah → Ebû Hüreyre; ʿUmar ibn al-Khaṭṭāb → Ömer b. Hattâb; ʿĀʾishah → Âişe; Ibn Taymiyyah → İbn Teymiyye; Ibn al-Qayyim → İbnü’l-Kayyim; al-Ghazālī → Gazzâlî.
  - Western names stay as printed, except names with an established Turkish form (Aristotle → Aristoteles).
  - Record each name in the glossary the first time it appears.
- **Cited works.** An Arabic work goes by its Turkish transliterated title (*el-Beyân ve’t-Tebyîn*). An English work keeps its English title.
- **Punctuation.** RULES.md §4 holds for the author's own marks (!, ?, …, dashes, brackets, the quotation marks around speech or quoted text): don't add any, don't drop any. English *typographic conventions* do not carry over. Use Turkish rules for:
  - the serial comma, and the comma before "and/but" between clauses;
  - commas and full stops inside closing quotes ("word," → "word",);
  - the capital after a colon.

  Quotation marks are “ ” (‘ ’ inside them). Headings keep the capitalisation used for titles in the Turkish edition.
- **Numbers and dates.**
  - 1,000 → 1.000 and 2.5 → 2,5; "3rd" → "3.".
  - "15 March 1999" / "March 15, 1999" → "15 Mart 1999".
  - AH / CE → h. / m.
  - "vol. 3, p. 45" → "c. 3, s. 45".
- **Qur’an verses.** English books quote an English rendering (Sahih International, Yusuf Ali, the author's own…).
  - Translate the verse in the register of a standard Turkish meal, from the meaning of the Arabic verse. Stay as close to the book's rendering as Turkish allows.
  - Keep the book's bracketed insertions ("[i.e., …]") as brackets.
  - If the author argues from a word of the English rendering, keep that sense, and log it if the meal wording would differ.
  - Check every verse against the Arabic text (`pipeline/quran/quran-simple-clean.txt`), so that the Turkish never says what the verse does not.
- **Verse references** in the Turkish form used in this folder: (2:255), [al-Baqarah 2:255] or (Qur'an 2:255) → "[Bakara: 255]"; a range → "[Bakara: 255-256]"; Turkish sura names as in `pipeline/quran/suras.tsv` ("[Bakara Sûresi: 255]" is the same reference; the glossary fixes which form the book uses). `check.py` compares them with the source and checks that the verses exist.
- **Hadith references** in the Turkish form (RULES.md §4):
  - Ṣaḥīḥ al-Bukhārī 6018 → *Buhârî (6018)*;
  - Ṣaḥīḥ Muslim → *Müslim*, Jāmiʿ al-Tirmidhī → *Tirmizî*, Sunan Abī Dāwūd → *Ebû Dâvûd*, Sunan al-Nasāʾī → *Nesâî*, Sunan Ibn Mājah → *İbn Mâce*, Musnad Aḥmad → *Ahmed b. Hanbel, el-Müsned*, al-Muwaṭṭaʾ → *Muvatta*.

  Numbers stay as printed; a book/chapter numbering ("Book 2, Hadith 13") is kept with its numbers.
- **Arabic script inside the English book** (a verse, a dua, a term) is source content: keep it as printed, next to the Turkish. The body font has no Arabic glyphs, so such a book needs an Arabic font in `build/make.js`, agreed on Part 01.

## 4. Markup

- Italics: `++italic++` in transcriptions and content files (the template `make.js` sets it in italics). Keep italics on titles of works, on emphasis and on foreign words that stay foreign in Turkish. Drop them on transliterated terms that are ordinary Turkish words (namaz, tevhid, Sünnet).
- Endnotes (notes collected at the back, `"notes": "endnotes"` in `book.json`): the marker is `[[en:N]]` in transcriptions and content files, numbered as printed; it is set as a superscript number and `check.py` compares the markers page by page. The notes themselves are translated as their own pages in the notes section.
- Everything else as for Arabic books: `**bold**`, `[[fn:N]]`, `^^colour^^` for text the source sets in colour, footnotes after the last `---`.
