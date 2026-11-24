"""Small PDFs of real text made in the test, drawn by pdfium, so the gate reads a real text layer and real ink."""

import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

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
