# Implementation plan

- [x] **M0 from the template**: python-app-template renamed (`stratascan`, `strata-scan`, port 8368), the greetings sample removed, settings `data_dir`, `max_dpi`, `workers`.
- [x] **M1 backend**: shared-database records and migration, import (PDF and pictures), page finding (level, crop, split, covers), OCR through strata-models' new `ocr` role, pictures, kinds and labels, export (Markdown, text, searchable PDF, zip), HTTP API, CLI. Unit and integration suites on synthetic books with the real Tesseract.
- [x] **M2 the two books**: both run end to end; thresholds checked on their pages (`docs/progress.md`).
- [x] **M3 web app**: Books, Book and Page screens on strata-react (RegionEditor for crops and pictures), mocks, jsdom tests, stories, visual baselines. Still to do: a box overlay for the OCR's lines (a strata-react component), a theme generated from the subject.
- [ ] **M4 deploy**: user unit and Caddy snippet on the home server, schema and role in the shared database, Tesseract installed beside strata-models.
- [ ] **Next**: a vision-language reader as a second `ocr` model on strata-models, compared with Tesseract on the hard pages (small caps, title pages, italics); captions under pictures; a reading view of the finished book.
