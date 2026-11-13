"""Books, their scans, the pages cut from them and the pictures found on the pages: typed records for omarchy-db (one schema, `stratascan`, in
the shared Postgres; SQLite in tests). Images are files in the data folder (see `files.py`); the rows hold what was decided about them.

A scan is one picture as it came (a PDF page, a photo). A page is what a person reads: a scan turned by `angle` and cut to `crop`, so one scan
can give two pages (a spread). Every decision the finder made can be overridden by hand; `hand` records that, so "detect again" leaves a
person's work alone. OCR output is kept as it came (`ocr`, lines and words with boxes, for drawing it over the page) beside the text a person
may have corrected (`text`), because a re-read must not overwrite a correction."""

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from omarchy_db import make_base  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

Base = make_base()


class Book(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    title: Mapped[str]
    source: Mapped[str]  # where it was imported from: a PDF or a folder of pictures (a path on this machine)
    author: Mapped[str | None] = mapped_column(default=None)
    lang: Mapped[str] = mapped_column(default="eng", server_default="eng")  # Tesseract's language list for the ocr role
    # The work the book is waiting for or doing: idle, import, detect, read, export. One stage at a time per book, run by pipeline.Runner.
    stage: Mapped[str] = mapped_column(default="idle", server_default="idle")
    done: Mapped[int] = mapped_column(default=0, server_default="0")
    total: Mapped[int] = mapped_column(default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(
        default=None
    )  # the last stage's failure, in words; cleared when a stage starts
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp(), init=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.current_timestamp(), onupdate=func.current_timestamp(), init=False
    )


class Scan(Base):
    __tablename__ = "scans"
    __table_args__ = (sa.UniqueConstraint("book_id", "position"),)
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    position: Mapped[int]  # 1-based order in the source
    file: Mapped[str]  # relative to the book's folder
    width: Mapped[int]
    height: Mapped[int]
    dpi: Mapped[int | None] = mapped_column(default=None)


class Page(Base):
    __tablename__ = "pages"
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    position: Mapped[int]  # reading order in the book, 1-based
    side: Mapped[str] = mapped_column(default="single")  # single, left, right (halves of a spread)
    angle: Mapped[float] = mapped_column(default=0.0)  # degrees counter-clockwise, see geometry.py
    crop_x: Mapped[int] = mapped_column(default=0)
    crop_y: Mapped[int] = mapped_column(default=0)
    crop_w: Mapped[int] = mapped_column(default=0)
    crop_h: Mapped[int] = mapped_column(default=0)
    confidence: Mapped[float] = mapped_column(default=0.0)  # the finder's, 0-1; low ones are listed first for checking
    hand: Mapped[bool] = mapped_column(default=False, server_default=sa.false())  # rotation or crop set by a person
    # text, picture, blank, cover, skip: skip leaves the page out of every export; the rest are guesses a person may change
    kind: Mapped[str] = mapped_column(default="text", server_default="text")
    label: Mapped[str | None] = mapped_column(default=None)  # the printed page number or a name ("Frontispiece")
    rendered: Mapped[bool] = mapped_column(
        default=False, server_default=sa.false()
    )  # pages/<id>.png matches the geometry
    ocr: Mapped[dict[str, Any] | None] = mapped_column(sa.JSON, default=None)  # the ocr role's answer, as it came
    ocr_model: Mapped[str | None] = mapped_column(default=None)
    ocr_conf: Mapped[float | None] = mapped_column(default=None)  # mean word confidence, 0-100
    text: Mapped[str | None] = mapped_column(
        sa.Text, default=None
    )  # the page's text: the OCR's until a person edits it
    text_edited: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    error: Mapped[str | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.current_timestamp(), onupdate=func.current_timestamp(), init=False
    )


class Figure(Base):
    """A picture on a page (an engraving, a diagram, a decoration), in the page's pixels."""

    __tablename__ = "figures"
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    x: Mapped[int]
    y: Mapped[int]
    w: Mapped[int]
    h: Mapped[int]
    caption: Mapped[str | None] = mapped_column(default=None)
    hand: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
