# Changelog

Newest first, grouped by day. One entry per change, in the same commit or PR as the change.

## 2026-11-28

**Pictures as JPEGs, grey unless coloured; a page at most A4 (branch `smaller-pdfs`)**
Jonathan, on the third book's 287 MB PDF: "we should not be storing as lossless. treat a book's pages as at most A4 size. use greyscale where little evidence of colour". Its 45 picture pages were 270 MB of it: each plate went in losslessly at full scan size, about 20 MB; and the Internet Archive PDF gave its pages as their pixels at 72 dpi, so each page was 32 by 45 inches and no compression would shrink its pictures.
- `layout.py`: `save_picture` writes every picture a rebuilt page carries as a JPEG (quality `JPEG`, 85), in grey unless `has_colour` finds coloured ink once the paper is white (`whitened`; `COLOUR`, `COLOURED`): an engraving on browned paper is grey, a hand-coloured plate or a red stamp is not. `cut_picture` and `cut_as_is` write through it. **New** `with_figure_pictures`: a text page's pictures are cut here and given to page-build, which draws them as given; its own crops were lossless and always grey, so a coloured plate on a text page lost its colour.
- `marks.py` `save`: the lifted marks through `save_picture`.
- `pipeline.py` `scan_dpi`: raised so that the page (its crop, not its scan: a spread is two pages) is at most A4 (`A4`).
- And from Jonathan's review of the third book's PDF (by PDF page): page 2, the jacket flap's text on orange paper, was taken for a pattern and kept as a picture: a page the OCR read surely (over `READABLE`, 60 %) is now always set in type, whatever its paper; only an unsure one (the marbled endpaper's letters, 40 %) can be a pattern or the book photographed. Page 11 had words set bold mid-page and "théâtre populaire" overprinted: the book's shortlist was every face the sample's answers named (thirteen), and font-match set a line's words in three of them. `book_faces` now votes: the `SHORTLIST` (5) faces most named. A text page's engraving (a layout names it `engraving`, not `figure`) is cut too, and a picture's paper is whitened by the page's, not its own: a densely hatched engraving whitened by itself kept a grey box round it.
- Page 15: its engraving lost its top, and the text under it came out bold and blurred: the layout model's box for the picture started below the engraving's top and ran on over the caption and the text, so the scan's text was drawn under the type. **New** `picture_box`: a picture's box found again from the ink near the one it was given, joined into shapes, clear of the lines of the layout's text blocks; `with_figure_pictures` cuts that and gives page-build the box found.
- Page 16 was set without its engraving: the layout model gave its box in the wrong units (y from 1000 to 1630 thousandths), and page-build drew nothing. **New** `merged_figures`: a layout picture whose box is not a box of the page is dropped, and each picture the read found (`figures.py`, or a person drew) that no layout picture covers is added (`pipeline.rebuild_one`).
- A quality check for each of those faults, so the next book's are found before anyone reads it (Jonathan: "not just fixing the issue, but come up with a quality control pass that can detect them as well"). **New** `qc.py`, run by the gate on every set page (`gate.check_page`'s `look`, given the pictures the read found: `pipeline.read_pictures`): a line's words in uneven weights; a word (of two letters or more) at a size far from its line's; any word over another; a picture whose ink runs on past its cut; a picture the read found that is not drawn; a line of text with a picture drawn over it; a page larger than A4 or heavier than 4 MB. A page made as a picture page fails when it was read surely (its text kept as a picture) or is too large (`rebuild_picture`). Run over the three books' current PDFs it flags every page Jonathan named (2, 11, 14, 15, 16, 17, 18 of the third), and 20 of the 1874 book's 44, 23 of the 1828 book's 206 for stray words alone, and 116 of the third's 168, before these fixes.
- `tests/unit/test_qc.py` (**new**), `tests/utils/pdfs.py` (`text_pdf` can stroke a word), `tests/unit/test_layout.py` (the picture's box from its ink; the read's pictures fill in), `test_pipeline.py` (a sure page on any paper is set; the voted shortlist), `test_cli.py` (a test page cut a little larger than A4 is read a little finer).

## 2026-11-27

**A dense page of type is not a pattern (branch `dense-text`)**
The third book's first finished PDF: 120 of its 154 text pages came out as their scans. Each was photographed on greyish paper, and `marks.lift` found 16-29 % of the page to be marks, over `PATTERN` (0.2), so `rebuild_one` took them for patterned paper and kept them whole.
- `marks.py`: `PATTERN` is 0.6. Marbled paper measures 0.89-0.94 (the 1874 book's endpaper, the 1828 book's edge shot), a dense page of type 0.16-0.29, a leaf with handwriting under 0.05.
- `tests/unit/test_marks.py`: a dense page of type on grey paper is no pattern.

**Haiku lays pages out first, Opus only those that fail; one font shortlist a book; every Claude call of a rebuild in bulk (branch `cheap-first`)**
Jonathan: lay out with Haiku (or Tesseract) and fall back to Opus only when a page fails; batch the font checks, asking for a sample of the book to get a fuller list for the rest; and no Claude call sent on its own (strata-models batches bulk calls, but some went one at a time).
- `settings.py`: `layout` defaults to `claude-haiku-5-5-api`; **new** `layout_fallback` (default `claude-opus-5-5-api`, or `off`).
- `pipeline.py` `stage_rebuild` works in rounds, each round's Claude calls in one bulk call through strata-models' batch API however few (`queued_ahead(batch=True)`): the book's font shortlist (`sample_faces`: the font-match proposer, Sonnet, asked about `SAMPLE` (6) text pages spread through the book, plain or not; its answers kept in the book's `faces.json` and given to every page's font-match as `candidates`, so no page asks a proposer of its own); every page set from its first layout, with its line fix and second reading; then the pages that failed from a layout the fallback could better (Haiku's, or none) laid out again by the fallback in one bulk call (`relayout`; the layout keeps `first_model`) and set again, only then trying their other routes. `book_faces` reads `faces.json`; `SHORTLIST` goes.
- A page whose layout call got no answer is never set without one (Jonathan: "if layout calls fail then shouldn't allow typeset"; the third book's 148 layout calls all failed when strata-models was restarted during its read, and the rebuild would have set each page as one block): `layout.CallError` tells a call that failed from an answer that was no layout (`layout_page` writes `call`); `unread_layouts` asks those pages again in one bulk call before anything is set, and a page still with none is left unset, the book's error saying why. Only an answer that was no layout still falls back to the page's own lines.
- Review: a page set again after its layout was read again keeps its first PDF aside and gets it back if the second setting cannot be made at all (`rebuild_again`), so a failed fit never leaves it a scan.
- `ahead.py`: `send(batch=)`; a cloud model's answer is kept once waited for, so a page set twice asks it once.
- `layout.py`: `propose_params`, `PROPOSE_MODEL`, `PROPOSE_PRESET`, `PROPOSE_PROMPT` (strata-models' own).
- `tests/unit/test_ahead.py`, `test_pipeline.py` (the shortlist from a sample in bulk; a failed page laid out again by Opus in a batch; a failed layout call asked again, the page not set while it fails).

**A full-page plate in a book scanned with no bed is the whole scan (branch `no-bed`)**
Jonathan added a third book (Punch & Judy: a history, 168 scans, each already the page). Seven of its scans were cut to a strip or a patch: full-page plates, whose dark ink runs to the edges, so the light region the page finder takes for the paper was a strip of margin (five were called blank or had no words), and the inside of the front flap.
- `geometry.py`: `unbedded`: in a book where most scans are the page already (`BEDLESS` of them covering `WHOLE` of their scan), a single page found covering less than `PATCH` of its scan is the whole scan; a book on a bed, and spreads, keep what was found. `whole_page`: the scan as the page, levelled by its type (what `find_page` already did with no bed).
- `pipeline.py` `stage_detect`: every scan's pages are found first, then the book is looked at as a whole before they are written. On the three books: none changes in the 1874 and 1828 books; the third's scans 2, 77, 103, 109, 110, 111 and 113, the seven that were wrong, become whole.
- `tests/unit/test_geometry.py`.

## 2026-11-26

**A patterned leaf stays within its page crop, and photographs and patterns read as text are not set in type (branch `pattern-crop`)**
Review of PR 19: a marbled endpaper on one side of a two-page scan was cut from the whole scan, bringing the other page with it.
- `pipeline.py` `rebuild_picture`: only a cover or the book photographed is cut from its whole scan; a pattern keeps its page crop. `book_in` does nothing for one side of a spread.
- And from the remake of both books: a page that is the book photographed is cut to the book even when the read found a picture on it (the 1828 book's page 3, an edge shot, came out as that "picture" whitened like an engraving); a text page that is the book photographed or a pattern is not set in type (the 1874 book's marbled endpaper, page 42, had OCR letters "AAA", "ARAA" and was set as type). Both pages were put right in the live books by marking them cover and picture. And a page that is not a picture page is its marks lifted onto white even when the reader boxed them as pictures (two of the 1828 book's endpapers, with a bookplate and a signature, came out on cream boxes).
- `tests/unit/test_pipeline.py`.

**Handwriting and bookplates kept on white, covers trimmed to the book, and pages already made not made again (branch `keep-marks`)**
Jonathan: keep what is on the near-empty pages (endpapers with a bookplate, an owner's name, pencilled notes; photographs of the spine and edges), cropped to the edge of the page or book, ideally the handwriting alone on white; err on the side of keeping content; use the paper colour seen on text pages to take it out. And: most pages don't need redoing, so don't redo them.
- **new** `marks.py`: `lift` takes the paper out of a page twice: its tone (each pixel over the lightest paper near it) and its colour (`paper_hue`, from the book's fullest text pages: a mark in the paper's own hue that is more colour than dark is a stain or foxing). What is left, marks with a dark seed and their faint strokes, in clusters that span a word, is kept on white; a lone speck and the leaf's edge are not. `backdrop` and `book_box` find the book in a photograph of it (a scan with a plain edge); `dark` tells a page that is the book photographed (cloth, a spine) from a leaf.
- `pipeline.py` `rebuild_picture`: a cover, or a page that is the book photographed, is cut from its whole scan (turned by its angle) to the book, not from its page crop, which for the 1828 book's edge shots cut into the book or took in the backdrop; any other page with no pictures is its marks on white, whole when they are most of it (marbled paper), or a blank. `paper_hue` is worked out once a book. On the 1828 book this keeps the bookplate and the "Herbert M. Bower 1897" and pencil notes of the endpapers, and pencilled shelf marks on two blank leaves; the 1874 book's covers and marbled endpapers come out whole.
- `layout.py`: `picture_page` takes pictures already made (`images`), can leave out rules, and cuts a whole page as it is (`whole`, `cut_as_is`): a cloth cover had been made "paper white" like an engraving, washing it out. `inked_share` and `INKED` go.
- `pipeline.py` `made` and `stage_rebuild`: a rebuild of the whole book skips a page whose PDF is the one it would make now: a text page that passed the gate as the kind it is now, any other page made this way (`PICTURES`, written beside its PDF, so a page never read counts too). Pages named are made again. `server/app.py`: drawing a page's pictures again removes its PDF.
- `tests/unit/test_marks.py` (**new**), `test_pipeline.py` (a second rebuild sets only the page that failed; a leaf with a name on it and a cover on a backdrop), `test_layout.py`.

**No scans in the finished PDF: blanks as true blanks, covers and patterns kept whole, pictures on clean paper, every text page in type; the last Collier faults (branch `last-pages`)**
Jonathan: fix the remaining failures, falling back to other techniques for the hard ones; the only scans he wants are blanks and covers; then: blanks should be true blanks, and the rest neatly set with borders and blank areas drawn, only pictures and patterns kept from the scan.
- `layout.py`: a footnote mark Tesseract read as "+" takes the corrected text's ("+ Vol. iv." for "\u2020 Vol. iv."), and a bracket it left off a line end is put back ("again." for "again.]"). `picture_page` and `cut_picture`: a page with no text is its pictures cut from the scan onto clean paper (grey for an engraving, in colour for a coloured print), its rules drawn, or a blank of its size; `inked_share` tells a pattern (marbled paper) from a blank leaf. A failed line fix no longer stops a page: the corrected text's words are set.
- `gate.py`: ink between 0.65 and 0.70 is measured again with each line free to move a few pixels (`text_ink`'s `shift`), and passes at 0.73 (`SHIFTED`): a warped page sits a little off the straight lines a rebuild sets. On both books' 166 set pages it changes only the 1828 book's page 123 (0.68, 0.74 so) and keeps its stained page 106 out (0.67, 0.70).
- `pipeline.py`: the rebuild sets every page but a skipped one (`typeset`: text pages in type, any other as its pictures, its pattern, the whole cover, or a blank). A text page that fails both routes is read again by another reader (`READER`, docTR's boxes with Claude Haiku's text) and set from that if it passes; one that fails every route keeps its first setting, listed to look at. A text page whose layout could not be read is laid out from its own lines.
- `export.py`: every page set again stands in the finished PDF. `web/`: "Look at type" for a page that failed the checks; the finished PDF's description.
- Review: a text page laid out from its own lines keeps its pictures (the stored figures); a page never read is set but stays unread, so its first reading still guesses its kind; README, AGENTS.md and docs/overview.md no longer promise scans.
- Needs strata-models' page-build to draw a picture it is given (strata-models PR "page-build: a figure's own picture").
- The 1828 book's last six faults, rebuilt in scratch: five pass; page 106 (a stain: four lines set squashed, a font-fit fault) fails every route and is set and listed.
- `tests/unit/test_layout.py`, `test_gate.py`, `test_pipeline.py`, `web/tests/`.

**Footnote marks kept, and hyphened words counted alike (branch `gate-fixes`)**
Jonathan: look into the 17 pages of the 1828 book the gate kept as scans. 14 were faults of this app's own making, 3 the gate rightly caught.
- `rows.py` `tidy`: a footnote's mark or a bracket just left of its row ("* He uses general terms", "‡ The title") is kept; only a mark with no letters and none of `MARKS` (the frame read as "|") goes. It had dropped them, and on one page took the running head's box with it, which was then drawn twice.
- `layout.py` `with_corrected`: a word the corrected text has with a reference mark the line fix lacks ("Faustus," for "Faustus,†") takes the mark.
- `gate.py` `unbroken`: a hyphen inside a line joins its compound as a line-end one does (pdfium gives some as U+FFFE: "two-hundred", "extem-pore"), and so does one followed by a space ("etymo- logy", as a reading may give it); U+2010 and U+2011 are the hyphen (review).
- The 17 pages rebuilt with these, in a scratch copy: 12 pass. Of the other 5, four lack a symbol (a "†" the line fix read as "+", "]" at two line ends) and one is a stained page whose lines came out squashed; one more (page 123) fails on ink against a pale scan though it looks right.
- `tests/unit/test_rows.py`, `test_layout.py`, `test_gate.py`.

**A plain page asks no layout model, and a book's plain pages share one font shortlist (branch `plain-pages`)**
Jonathan: a page full of text shouldn't need layout, and the font shortlist can be the same for all similar pages of a book. The layout model (Opus) was two thirds of the cost of setting a book in type, and the shortlist (Sonnet) most of the rest.
- `layout.py`: `plain_groups`: a page of 12 lines or more of one size of type, with no pictures, is laid out from its own lines (running head and page number at the top, a page number at the foot, centred short lines standing alone as headings, the rest body in blocks parted at gaps), with a streak read as a tall line left out. Its layout's `model` is `plain`. On the 1874 book it takes 12 of its 13 pages of running text and gives the layout model's answer; adverts, the title, the notice, verse, the Preface and pages with pictures go to the model. Of 12 sampled pages of the 1828 book, 8 are plain. Review: two columns, and a line of capitals with no page number beside it (a running head, or a chapter's title?), go to the model too.
- `pipeline.py`: the read stage queues no layout call for a plain page. The rebuild asks for a font shortlist for the first `SAMPLE` (3) plain pages of a book, then gives the rest the 4 faces those named most (`ocr["type"]`).
- The 13 plain pages of the 1874 book set this way through the live service: all pass the gate, ink as before, $0.073 (about 0.6 cents a page instead of about 5.5).
- `tests/unit/test_layout.py`, `test_pipeline.py` (the stand-in page-build lists real line boxes).

## 2026-11-25

**A book's Claude calls are queued in bulk, at the batch price (branch `claude/calls-in-bulk`)**
Jonathan asked for strata-models' bulk endpoint to be used everywhere, and pointed out that a page's cloud calls are small once its OCR is done, so they can be batched. strata-models only batches a bulk call of 20 or more (Claude Message Batches, half the price, answered within a day); this app made every call alone and waited for it.
- `ahead.py` **new**: calls a stage can name ahead are queued in one bulk call per role and model (`clients.models.submit_many`), then answered from there when a page makes them; any other call is made at once, as before, and so is every planned call when strata-models refuses the bulk call.
- `pipeline.py`: `read` runs in two passes: every page's OCR first (`first_read`), then the corrections and layouts of every text page queued in bulk (`read_calls`) and each page finished as they come (`finish_read`; `read_page` does both for one page). `rebuild` queues each page's line-text fix and second reading before the first page is set (`rebuild_calls`); the type fits stay one page at a time. `correct_params`, `tidied`, `correction_prompt` split out.
- `layout.py`: `layout_params`, `text_params`, `read_params` and `settled` split out, so a stage plans the very calls the page makes.
- strata-python 0.2.22 or later (`submit_many`; normal and low jobs go through strata-models' bulk endpoint, the only one it takes them on now). `tests/utils/models_service.py` answers the bulk endpoint too.
- Tests: `test_ahead.py` **new**; the layout, rebuild and CLI tests check that the calls went in bulk before any page needed them.
- `pipeline.py`: a `Reading` keeps no decoded image (the stage holds every page's until the bulk answers come; a 200-page book of 3000x4000 scans would be about 7 GB), so `finish_read` reads the page again to cut its pictures, and drops each reading once its page is done (a review finding).
- `.github/workflows/unit.yml`, `integration.yml`: on Windows, when Chocolatey leaves no `tesseract.exe` (its feed refused the package on 2026-11-25 and still exited 0), install conda-forge's build through micromamba instead; a new step checks `tesseract --version` on every OS, so a missing command fails at install, not as 15 test errors.

**Pages the gate kept as scans go into type: lines the OCR missed put on their rows of ink, and fairer checks (branch `rows-from-ink`)**
Jonathan: look at the pages that couldn't be processed, some seem fairly normal. Ten of the 1874 book's 25 set pages were scans. Tesseract had skipped whole lines of display type on the adverts ("PAPERHANGINGS", "STRAW GOODS"), though the corrected text had them, or boxed lines with the page's frame or a neighbouring row; page 10 failed on one slip of the second reader; page 7's overlaps were italics leaning on each other.

- `rows.py` **new**: the rows of print found from the ink, paired in order with the corrected text's lines. `repair` puts a line the OCR missed or boxed badly on its row, word by word; `tidy` drops the frame read as a word ("|") and cuts boxes to their row, keeping the lines' numbers. A picture word (a pointing hand) is cut from the scan.
- `pipeline.py`: a page that fails is set again from its repaired lines, with a layout read for them, and that is kept only when it passes (`lines_put_right`, and `from_rows`: why it failed even so). A first version repaired every page and made well-read dialogue pages worse.
- `gate.py`: a word is lost when both readings have it and the page does not, or it stands in a run of two or more either has (`lost_words`); a letter's next neighbour must be covered by 60 % to count as overlapping; a picture character is no symbol to print; a line of one character is an ornament.
- `layout.py`: names the OCR saw in small capitals stay so ("Polly", not "POLLY"), not in a line of display capitals; a line the line fix emptied is kept when the corrected text has its words (a page number); a tidied page whose lines are numbered otherwise is set from the one its layout was read from; lines put on their rows are never left out of the layout.
- `tests/unit/test_rows.py` **new**, `test_gate.py`, `test_layout.py`, `test_pipeline.py`. Needs strata-models' branch `line-faces` for the adverts' faces.

**Pages set in type draw the corrected text, and the gate sees wrong sizes and misreads (branch `rebuild-text-size`)**
The first finished PDF of a whole book (44 pages, 17 of its 25 set pages passed) had pages the gate should not have passed: lines set too big, a headline's word set tiny, and names misread ("Juvpy", "PorrLy", "ccffin") though the page's stored text was right.

- `layout.py`: misread words are put right from the page's corrected text, word for word, each by the like word that stands for it (`with_corrected`): the lines stay the print's. A first version put whole corrected lines in, and page 11's, which joins a paragraph, ran off the page. `read_again`: the page read by Haiku from the picture alone. `align.py`: `letters` is shared.
- `pipeline.py`: the gate checks the words against that second reading when it is plausible, as well as against the page's text (`ocr["gate"]["by"]`), and the worse counts: a reading that stopped short must not relax it (review). Checking a rebuild against the reading it drew from hid misreads, and lines that reading never found.
- `gate.py`: **size**: no line over 1.25 times its block's size, and no words on one baseline over 1.8 times apart. Set on 25 pages of the 1874 book and 10 of the 1828 book: it flags every size fault seen by eye, and no other page.
- `tests/unit/`: the above.

## 2026-11-24

**A quality gate on pages set in type, and a finished PDF that keeps the scan of those that fail (branch `quality-gate`)**
Jonathan asked for a finished PDF for each input, with a gate set on the most difficult pages first; the marks and the fallback to the scan are the ones he agreed on 2026-11-24.

- `gate.py` **new**: a rebuilt page passes when at most 1 % of its corrected text's words are missing from the PDF, at most 1 % of its characters lie over others and none is off the page, its ink agrees with the scan's by at least 0.70 on the text, and every symbol of the text is drawn (a missing dagger shows as a box or a blank, which no other check sees). Character error against a reference is no gate: adverts whose text is perfect still drop and misplace lines.
- `pipeline.py`: the rebuild checks each page (`ocr["gate"]`, no migration) and does the worst read first. `export.py`: `book-rebuilt.pdf` is the finished PDF: pages that pass in type, every other page as its scan.
- `server/app.py`: a page's `gate` (null until it is set). `web/`: the Book screen says which pages are set in type and which kept their scan, with the reason on hover; the file is called Finished PDF.
- `tests/unit/test_gate.py`, `tests/utils/pdfs.py` **new** (real PDFs of real text, drawn by pdfium), `tests/unit/test_pipeline.py`, `web/tests/`. `README.md`, `AGENTS.md`, `docs/overview.md` follow.
- The marks were set knowing which of 14 hard pages looked right (7 pass, 7 fail). On 10 printed pages not looked at first: 8 pass, 2 fail (an advert with a line lost, a page whose daggers are not drawn), and by eye both failures are right. Two of the 8 have one line set visibly too big, and a misread word or two passes (1 % of a 300-word page is three words): no check sees a wrong size, and a running head's words can hide a lost one. The 7 unprinted pages among the worst read could not be set at all, so they keep their scans.
- Review: the pipeline test runs the real gate, and the symbol check looks at the drawing, not only the text layer (`tests/utils/pdfs.py` makes a font that draws a box for a dagger).

**Latest strata-python and strata-react, and the best page models from strata-models' evals (branch `claude/latest-libs-page-layout`)**
Jonathan asked for the latest shared libraries, and for the results of strata-models' page scan, layout and type evals to be used.

- strata-python 0.1 (git) to 0.2.13 (PyPI, `[db]`), strata-react 1.0.39 to 1.3.7. `strata_python.db` replaces the git-pinned `omarchy_db` (`[tool.strata-db]`, `STRATA_DB_LIVE`, `STRATA_DB_DATABASE`; the migrations are unchanged) and `strata_python.clients.models` replaces `strata_models_client`. Tests use the plugin's fixtures (`tests/utils/fakes.py` goes), `tests/unit/test_database.py` runs the standard database tests, and Dependabot replaces the upgrade workflow. A service must set `STRATA_DB_LIVE=1` and `STRATA_DB_DATABASE`.
- **Correction** (eval ocr-hard, ten worst pages, 2026-11-24): the text corrected is now Tesseract's reading of the adaptively cleaned page, by Claude Haiku (preset ocr-correct-v2): 0.27 % of characters wrong, against 3.7 % with qwen3.5-9b-vl, the model it replaces. Ten pages only: plain Tesseract then Haiku, 0.88 %, is not clearly worse. Its lines are matched to the kept OCR lines by likeness (`align.py`).
- **Layout** (page-layout, 20 pages): a text page's blocks and roles are Claude Opus's (page-layout-fix-v2; blocks found 96.5 %, Tesseract's 64 %). `book.md` follows it: headings marked, running heads and page numbers dropped, reading order. Setting `layout`.
- **Rebuild** (page-rebuild, 20 pages, candidate full-opus): stage `rebuild`, the Set in type button: each text page set again in matched type with its figures and rules, into `book-rebuilt.pdf`. Only run when asked. Ink agreement 76 % with the scan, Tesseract in Times 37 %.
- `export.py` (review): a body line the layout missed, or a corrected line with no like among the OCR's, is never dropped with a running head; a block's lines keep the layout's order; a line part text and part page number is text (`tests/unit/test_export.py`).
- `web/tests/visual/baselines/`: 30 rewritten by the CI workflow for strata-react 1.3.7 and the Set in type button. `AGENTS.md` follows.
- `pipeline.py`: the rebuild does one page at a time (a run of 14 hard pages ran strata-models out of memory; its font-match fix is strata-models #116, which the rebuild needs).
- The page-rebuild report's own pick is `full-every-face` (78 %, the fonts tried exhaustively). It is 2 points over the shortlist, under the 3 the eval asks for a change, and twice the time, so the font-match default Jonathan chose on 2026-11-23 stays.

## 2026-11-14

**Correct every text page's OCR with a vision-language model (branch `claude/project-thread-0n1ijc`)**
Jonathan asked for evals of the trickier pages, before and after OCR. On strata-models' ocr-pages eval (10 hard pages of both books, typed out by hand), Tesseract alone got 5.1 % of characters wrong, the best page cleaning 3.1 %, and Tesseract then qwen3.5-9b-vl correcting its text against the page 0.3 % (small capitals: "Puxcr", "Jupy" became PUNCH, JUDY), at about 18 s of GPU time a page. He chose to correct every text page.

- `pipeline.py`: after the OCR, a text page's text (noise lines already dropped) goes with its picture to strata-models' `vision-language` role (`models_correct`: preset `ocr-correct-v1`, temperature 0), and the page's text is the answer; `ocr["corrected"]` keeps `{model, text}` or `{model, error}`. Tesseract's lines and boxes stay, so the searchable PDF and figure finding are as before. A failed correction, or one far shorter or longer than its text (`plausible`), keeps Tesseract's text. Covers, pictures, blanks and typed pages are not sent; the kind is now guessed before the correction so a picture page is never sent. `Runner(correct=...)` stands in for the service in tests.
- `export.py`: `corrected_lines` puts each corrected line where Tesseract found the line it corrects, so the Markdown keeps its paragraphs and pictures in place; a correction that joined or split lines goes in whole as one block (review: corrected lines no longer matched the OCR's and were dropped from `book.md`). `pipeline.py`: the correction records which OCR lines it corrected (`kept_lines`). `tests/unit/test_export.py`: both cases.
- `settings.py`: `correct` (STRATASCAN_CORRECT), the model key (default `qwen3.5-9b-vl`) or `off`.
- `tests/unit/test_pipeline.py`: corrections replace text pages' text and keep both; typed pages, pictures and covers are not sent; a failed or implausible correction keeps the OCR text; `off`. `tests/conftest.py`: the shared runner has no correction. `tests/utils/models_service.py`: the stand-in answers `vision-language` correction jobs; `tests/integration/test_cli.py`: each text page is sent for correction with its picture.
- README, `docs/overview.md`, `docs/progress.md`: the correction pass and its numbers.

## 2026-11-13

**Stop committing the web build (branch `claude/project-thread-0n1ijc`)**
Jonathan asked about the static assets folder: the built web app had been committed, because `.gitignore` still named the template's `src/app/server/static/` after the package rename.

- `.gitignore`: ignores `src/stratascan/server/static/` (what `npm run build` writes and `strata-scan serve` serves); the 18 built files are removed from git. Deploying builds them (`docs/deploying.md`, step 1).

**Review fixes: hand work, one-page tasks and failed reads (branch `claude/project-thread-0n1ijc`)**
Three findings from the automated review on #5, each confirmed by a test that failed before the fix.

- `src/stratascan/pipeline.py`: detect leaves a scan alone when any of its pages has a person's work (a cut, typed text, or a hand-drawn picture), not only a hand cut: re-detecting deleted the pages and their typed text and pictures with them. A task for chosen pages follows their scans through detect, which gives the new pages new ids (a following `read` found none). The book's error is cleared once per task, so a successful export no longer hides a read that failed.
- `tests/unit/test_pipeline.py`: a test for each.

**strata-scan: the web app, and blank pages kept whole (branch `claude/project-thread-0n1ijc`)**
The second half of the same request: the screens to look at a book, correct a page's cut, text and pictures, and make the files. Running the 1874 book through the API showed blank pages with no scanner bed cropped to a patch, so the page finder changed too.

- `web/src/api.ts`: the books/pages/scans/figures endpoints and their types, the geometry helpers the cut editor shares with the server (`turnedSize`, `turnCrop`, `wrapAngle`) and the sentences (`describeBook`, `pageName`).
- `web/src/screens/BooksScreen.tsx`, `BookScreen.tsx`, `PageScreen.tsx`: **new**; the shelf (add by upload or by path), a book (its work as a `useJob`, pages, pictures, files) and a page (cut: turn, crop, split or join a spread; text: unsure lines, kind, label; pictures: draw, remove). `Layout.tsx`, `routes.tsx`, `SystemScreen.tsx` (whether strata-models can read), `SettingsScreen.tsx` (data folder, resolution, pages at once), `NotFoundScreen.tsx`. `GreetingsScreen.tsx`, `LogScreen.tsx` and their tests, stories and baselines: removed.
- `web/src/mocks/fixtures.ts`, `handlers.ts`, `images.ts` (**new**: three page previews from the 1874 book, public domain): the two books as sample data, every endpoint and each failure state.
- `web/tests/integration/{Books,Book,Page}Screen.test.tsx` **new**; `App`, `Settings`, `System` tests and `tests/unit/logic.test.ts` rewritten. 65 tests, 100% on every coverage metric.
- `web/stories/{books,book,page}.stories.tsx` **new**, `system.stories.tsx`: NoReader. `web/strata-visual.config.ts`: books, book, page, system and settings routes; `web/tests/visual/baselines/`: all new (greetings and log removed).
- `web/vite.config.ts`: a function of the mode; `--mode visual` (`build:visual` in `package.json`) adds `<base href="/">`, because the visual runner serves the build without the server's `<base>` and a nested route (`/books/1`) otherwise asks for `/books/assets/...`. `web/vitest.config.ts` calls it for the test mode. Bundle size comment corrected (940 kB).
- `src/stratascan/geometry.py`: `_page_mask` takes the whole scan as the page when Otsu's two classes are closer than `BED_CONTRAST` (30): a scan of paper only. `tests/unit/test_geometry.py`: a blank page with no bed stays whole.

**strata-scan: scanned books to pages, text, pictures and a searchable PDF; backend and CLI (branch `claude/project-thread-0n1ijc`)**
Jonathan asked to turn this repo (until now a copy of python-app-template) into a web app for processing two scanned books: rotate, crop, extract text and pictures, OCR, with model work in strata-models and screens from strata-react. This entry is the backend, CLI, tests and deploy files; the web app follows on the same branch.

- `src/app` -> `src/stratascan`, `app`/`app.cmd` -> `strata-scan`/`strata-scan.cmd`; `pyproject.toml`: name `strata-scan`, script `strata-scan`, port 8368, dependencies opencv-python-headless, numpy, pypdfium2, pypdf, pillow, python-multipart, omarchy-db and strata-models-client (git sources), `[tool.omarchy-db]`, plugin tuning variables. `uv.lock`.
- `src/app/greet.py`, `tests/unit/test_greet.py`: removed with the greetings sample.
- `settings.py`: `data_dir`, `max_dpi` (600), `workers` (4).
- `db/models.py`, `migrations/20261113_85a64741b9b6_initial.py`, `store.py`: **new**; books, scans, pages, figures in schema `stratascan` (defaults written portably by hand: `sa.false()`, `CURRENT_TIMESTAMP`).
- `files.py`, `sources.py`, `geometry.py`, `figures.py`, `pipeline.py`, `export.py`: **new**; the folder layout, import, page finding, picture finding, the four stages and their runner, the exports. Why each threshold is what it is: `docs/progress.md`.
- `server/app.py`: the books/pages/scans/figures API (listed in its docstring); the greetings routes removed. `server/landing.html`: lists the books when the web app is not built. `system.py`: data folder size and whether strata-models has the `ocr` role. `cli.py`: `add`, `books` (`--json` is the API's book shape), `run`, `export`; `run` on a missing book says so.
- `tests/utils/books.py`, `tests/utils/models_service.py`: **new**; synthetic books (real type, an engraving, a scanner bed, a tilt, a cover) and a strata-models stand-in that runs the real `tesseract`. `tests/conftest.py`: a fresh database per test (`db_env`), `runner`, `make_book`, `models_service`.
- `tests/unit/test_{geometry,figures,sources,pipeline,export,server}.py`: **new**; `test_{cli,settings,system,version}.py` rewritten. 45 tests, 96% coverage.
- `tests/integration/`: rewritten for the CLI (a book added, read and exported through the stand-in) and the API on a real server (`live_app`: upload, wait, re-crop, typed text survives a re-read, hand-drawn picture, zip download).
- `.github/workflows/unit.yml`, `integration.yml`: install Tesseract on Linux, macOS and Windows; `dbtool check` once.
- `deploy/app.service` -> `deploy/strata-scan.service` (database and strata-models variables), `deploy/strata-scan.caddy` **new**; `docs/deploying.md`: the database and strata-models steps.
- `README.md`, `AGENTS.md`, `tests/README.md`, `docs/overview.md`, `docs/implementation-plan.md`, `docs/progress.md`: describe strata-scan instead of the template sample.

## 2026-11-09

**Regenerate visual baselines on the CI runner (branch `claude/project-thread-iw7199`)**
Jonathan wants every dependency kept current, including Dependabot's playwright and lucide-react bumps. Those change the Chromium or the icons behind every screenshot, and a laptop cannot reproduce the CI Chromium, so the baselines are now written by a manual workflow.

- `.github/workflows/update-visual-baselines.yml`: **new**; manual run on a chosen branch: `test:visual:update`, then `test:visual` to prove stability, then commits `web/tests/visual/baselines` to that branch.
- `AGENTS.md`: CI section mentions it.

**Move onto the strata-python library (branch `claude/project-thread-iw7199`)**
Jonathan asked for the shared server code to live in a `strata-python` project (like strata-react) so the template stops duplicating it, and for apps to track its latest. This replaces the template's own copies; behaviour is unchanged except where noted.

- `pyproject.toml`, `uv.lock`: depend on `strata-python` as a git source tracking `main` (the lock pins the commit); pytest options `strata_env_prefix`/`strata_tuning_vars` configure the library's plugin.
- `src/app/oslib.py`, `scripts/check.py`, `tests/utils/http_server.py`, `tests/unit/test_oslib.py`, `tests/unit/test_http_server.py`: **removed**, now `strata_python.oslib`, `strata-check` and the plugin's `http_server` fixture (the library tests them, with real processes and sockets).
- `src/app/settings.py`: declares the two settings with `strata_python.settings.Settings`; same files and `APP_*` variables. Corrections: a bad `data_dir` or blank greeting now raises ValueError from `save` (the API answers 400, as it did for a relative path), `~` in `data_dir` is expanded when saved, and a bad stored or environment value falls back to the default instead of crashing.
- `src/app/server/app.py`, `src/app/cli.py`: health, settings and page routes, `serve`, `doctor` and `set` come from the library; the app keeps its own routes and `hello`/`messages`.
- `tests/conftest.py`: hermetic environment, no-network guard and `http_server` fixture removed (plugin). The `fake_*` fixtures stay as last resorts.
- `scripts/check`, `.github/workflows/unit.yml`: run `strata-check`. `.github/workflows/upgrade-strata-python.yml` **new**: weekly lock upgrade that runs the gate and opens a PR.
- `AGENTS.md`, `README.md`: describe the library, the tracking-main rule and the upgrade workflow.

**Testing policy: real code over mocks (branch `claude/project-thread-iw7199`)**
Asked to steer tests away from mocks towards real HTTP, embedded databases and installed tools, and to make skipping deliberate.

- `AGENTS.md`: **new** Testing policy section (real by default; mocks only for true externals in quick many-case unit tests; install ffmpeg and the like instead of mocking; no silent skips, a skip is a marker with a reason and a switch; machine-heavy tests are marked and run where the machine is).
- `tests/utils/http_server.py`, `tests/unit/test_http_server.py`: **new**. A real loopback HTTP server scripted per test (`http_server` fixture in `tests/conftest.py`); a request no route answers fails the test at teardown.
- `tests/utils/fakes.py`: docstring marks the doubles as a last resort. `tests/README.md`: layout notes point to the policy.
- `pyproject.toml`: ruff `TID` rules selected, `pytest.importorskip` banned with the reason.

**AGENTS.md reorganised as the basis for apps made from the template (branch `claude/project-thread-iw7199`)**
Asked to make the agent instructions suitable as the starting point for future apps, and to point database work at the shared database project.

- `AGENTS.md`: regrouped into rules for every change (run `scripts/check`, changelog and docs in the same commit, comment the why, no secrets or machine-specific details, strict types, tests, report what was run), layout, Python tooling, tests, web, CI and a closing checklist. Says which parts to keep unchanged in a derived app. Content of the earlier bullets is kept.
- `AGENTS.md`: **new** Database section. Apps use [jburnhams/database](https://github.com/jburnhams/database) (one shared database, one schema per app, models and migrations in the app repo, `dbtool check` in CI, never one database per app) and link its adoption guide rather than repeating it.

**Generic deployment notes and a systemd unit example (branch `claude/project-thread-iw7199`)**
A Docker image was dropped from the plan because apps are not deployed that way. These files are deliberately free of machine-specific details.

- `deploy/app.service`: **new**. Example systemd user unit running `uv run --locked --no-dev app serve`.
- `docs/deploying.md`: **new**. Build, install, run, reverse-proxy and how to keep a service file in step with the repo.
- `AGENTS.md`: points to them; the stale `setup_env` mention is gone (corrects the earlier line left behind by the uv change).

**Move the Python side to uv, typed strict, one gate (branch `claude/project-thread-iw7199`)**
Asked for an evaluation of this template against current best practice; the tooling gaps it found are closed here. Behaviour of the app is unchanged.

- `pyproject.toml`: now a real project (`[project]`, hatchling build, `app` console script, `[dependency-groups] dev`), with `--strict-markers --strict-config` for pytest, ruff rules `E,F,I,B,UP,SIM,RUF,C4,PT,S` at line length 120, and pyright strict.
- `uv.lock`, `.python-version`: **new**. Builds are reproducible; CI installs with `uv sync --locked`.
- `requirements.txt`, `requirements-test.txt`, `scripts/setup_env.sh`, `scripts/setup_env.ps1`: **removed**; `uv sync` replaces them. `app` and `app.cmd` stay as thin wrappers over `uv run app`.
- `scripts/check`, `scripts/check.py`: **new**. The one gate (lockfile, ruff lint and format, pyright, ty, unit tests with coverage) for git hooks, agents and CI.
- `src/app/`: fully annotated; `__version__` now reads the package metadata. `oslib.py` relaxes pyright for that one file because its Windows branches use APIs the Linux stubs lack. Formatting is `ruff format` (separate commit, no behaviour change).
- `tests/`: new `test_version.py` and a partial-settings test (coverage is 100% again); a few asserts split for ruff's PT018.
- `.github/workflows/unit.yml`, `integration.yml`: uv with cache; lint, format and types run once on Linux 3.13; weekly `uv audit`. `.github/dependabot.yml`: **new** (uv, npm, actions).
- README, AGENTS.md, test READMEs, docs: commands updated to uv and `scripts/check`.
- Not done yet: Dockerfile and systemd unit, copier conversion, release workflow (next phases).
