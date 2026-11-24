"""Small PDFs of real text made in the test, drawn by pdfium, so the gate reads a real text layer and real ink."""

import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)

W, H = 400, 500  # points
DPI = 200


def text_pdf(path, lines, size=14):
    """One page: (x, y from the top, text[, size]) each set in Helvetica (WinAnsi, so curly quotes and daggers can be written)."""
    w = PdfWriter()
    page = w.add_blank_page(W, H)
    ops = []
    for ln in lines:
        x, y, text, *rest = ln
        escaped = text.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        ops.append(b"BT /F1 %d Tf %d %d Td (%s) Tj ET" % (rest[0] if rest else size, x, H - y, escaped))
    stream = DecodedStreamObject()
    stream.set_data(b"\n".join(ops))
    page[NameObject("/Contents")] = w._add_object(stream)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): w._add_object(font)})}
    )
    with open(path, "wb") as f:
        w.write(f)
    return str(path)


def scan_png(path, pdf, paper=225, dpi=DPI):
    """The page as a scan of it would be: drawn at `dpi`, black type on paper that is not white."""
    doc = pdfium.PdfDocument(pdf)
    gray = np.asarray(doc[0].render(scale=dpi / 72, grayscale=True).to_numpy())
    doc.close()
    gray = gray.reshape(gray.shape[:2])
    Image.fromarray(np.where(gray < 128, 30, paper).astype(np.uint8)).save(path)
    return str(path)


def blocks_of(lines, dpi=DPI, width=360, height=18):
    """The layout's blocks for the lines of `text_pdf`: one box a line, in the scan's pixels."""
    k = dpi / 72
    return [{"role": "body", "lines": [[x * k, (y - height) * k, width * k, height * 1.5 * k] for x, y, *_ in lines]}]


def box_pdf(path, char="\u2020", hollow=True):
    """One page whose text layer says `char` but whose font draws a missing-glyph box (or nothing): what a font that lacks the glyph does."""
    w = PdfWriter()
    page = w.add_blank_page(W, H)
    proc = DecodedStreamObject()
    frame = b"0 0 600 600 re 80 80 440 440 re f* " if hollow else b""
    proc.set_data(b"700 0 0 0 600 600 d1 " + frame)
    ucs = DecodedStreamObject()
    ucs.set_data(
        b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapName /X def /CMapType 2 def\n"
        b"1 begincodespacerange <00> <FF> endcodespacerange\n"
        + f"1 beginbfchar <61> <{ord(char):04X}> endbfchar\n".encode()
        + b"endcmap end end"
    )

    def num(*v):
        return ArrayObject([FloatObject(x) for x in v])

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type3"),
            NameObject("/FontBBox"): num(0, 0, 700, 700),
            NameObject("/FontMatrix"): num(0.001, 0, 0, 0.001, 0, 0),
            NameObject("/CharProcs"): DictionaryObject({NameObject("/a"): w._add_object(proc)}),
            NameObject("/Encoding"): DictionaryObject(
                {NameObject("/Differences"): ArrayObject([NumberObject(97), NameObject("/a")])}
            ),
            NameObject("/FirstChar"): NumberObject(97),
            NameObject("/LastChar"): NumberObject(97),
            NameObject("/Widths"): num(700),
            NameObject("/ToUnicode"): w._add_object(ucs),
        }
    )
    body = DecodedStreamObject()
    body.set_data(b"BT /F1 24 Tf 50 300 Td (a) Tj ET")
    page[NameObject("/Contents")] = w._add_object(body)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): w._add_object(font)})}
    )
    with open(path, "wb") as f:
        w.write(f)
    return str(path)
