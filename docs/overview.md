# Design brief

## 1. Goal

Turn scanned books into pages a person can read, search and quote: level, cropped pages; their text; their pictures; a searchable PDF. The first two books are Internet Archive scans of Punch and Judy (Collier and Cruikshank, 1828, 206 scans at 360 dpi; a "how to manage the little wooden actors" manual, 1874, 44 scans at 500 dpi), but nothing is specific to them. Automation makes the first draft; the person fixes what it got wrong, page by page, and their fixes are never undone by a re-run.

Prior art is [diary-study](https://github.com/jburnhams/diary-study), which did the same for a handwritten diary (rotate, crop, read with a vision model). What is common to every app lives in the shared projects: models in [strata-models](https://github.com/jburnhams/strata-models) (this app asks its `ocr` role and never loads a model), screens in [strata-react](https://github.com/jburnhams/strata-react), server plumbing in [strata-python](https://github.com/jburnhams/strata-python), records in the shared database.

## 2. Architecture

- **Stages** (`pipeline.py`), run by a `Runner` thread in the server (or in-process by the CLI), each resumable and each recording progress on the book (`stage`, `done`, `total`, `error`):
  - **import** (`sources.py`): a PDF's pages drawn with pypdfium2 at the resolution of the scan inside (largest image's pixels over the page width, capped by `max_dpi`), or a folder's pictures copied in natural order. One `Scan` row and one PNG per scan.
  - **detect** (`geometry.py`): the paper is found in a downscaled copy (Otsu, closed, the largest region and any of comparable size), levelled by its outline (`minAreaRect`) and then by its lines of type (a projection-profile search over ±3°), trimmed to where it is mostly paper, and split at the darkest middle column when it is wider than tall. A region too small (a dark cover, a label) or covering the whole scan keeps the scan whole. Scans with a page a person fixed are left alone.
  - **read**: each page is drawn (`angle`, `crop` from its scan), sent to the `ocr` role with its true dpi (the role returns lines, words, boxes, confidences and a one-page searchable PDF), then pictures are found (`figures.py`: ink by adaptive threshold, minus confidently read words, minus long rules, closed and filtered by size and density). Text is kept line by line where the OCR was sure enough (`keep_line`; a stricter bar on covers and pictures); the kind (text, picture, blank, cover) and the label (the running head) are guessed on the first read only. A text page's text is then corrected against its picture by a vision-language model (setting `correct`, strata-models' `vision-language` role with preset `ocr-correct-v1`); Tesseract's lines and boxes stay, and a failed or implausible correction keeps its text.
  - **export** (`export.py`): Markdown (paragraphs rejoined across line ends and hyphens, running heads dropped, pictures where they stand), plain text, one searchable PDF of every page (the OCR PDFs with their page images re-encoded as JPEG, or the bare picture for a page not read yet), and a zip.
- **Records** (`db/models.py`, schema `stratascan`): `Book`, `Scan` (a picture as imported), `Page` (a cut of a scan: `side`, `angle`, `crop`, `hand`, `kind`, `label`, the OCR result, `text`, `text_edited`), `Figure` (a box on a page, `hand`). Pictures are files (`files.py`): `books/<id>/{scans,pages,ocr,figures,previews,export,uploads}`.
- **HTTP API** (`server/app.py`, listed in its docstring): books (create from a path or an upload, run stages, files), pages (image at three sizes, the OCR lines, edit kind/label/text/angle/crop), a scan's pages (set one or two cuts: split or join a spread), a page's pictures (replace the set). Any change of shape marks the page `hand` and queues a re-read of that page.
- **CLI** (`cli.py`): `doctor`, `add`, `books`, `run`, `export`, `set`, `serve`.
- **Web** (`web/`): Books (add a PDF, each book's state), Book (pages as thumbnails, pictures, files, the running stage), Page (crop and angle on the scan, the text beside the page with the OCR's boxes, pictures drawn on the page).

## 3. Principles

- **A guess is a draft; a person's fix is final.** Every automatic choice is stored where a person can change it, and every stage checks `hand`/`text_edited` before writing.
- **Measure on the real books.** Thresholds in `geometry.py`, `figures.py` and `pipeline.keep_line` were set against pages of both books, with the numbers in `docs/progress.md`.
- **No models here.** OCR, and any later reader (a vision-language model for hard pages), is a role on strata-models, so the GPU and CPU queues are shared with every other app.
- **Hermetic tests on real programs**: synthetic books drawn with Pillow, the real `tesseract`, a real database (SQLite by default), a real HTTP stand-in for strata-models.
