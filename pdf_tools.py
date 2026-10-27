"""Everything that touches the PDF itself, using the PyMuPDF library.

A note on positions. The web page tells us where things go as fractions of
the page. For example x=0.5 means "halfway across". That way the browser does
not need to know the real size of the page. We turn those fractions into PDF
units here. PDF units are called points, and 72 points make one inch.
"""

import pymupdf

# Where the top of a line of text sits compared with its baseline (the line
# letters "sit" on), as a share of the font size. It matches how the browser
# draws Helvetica, so text lands where you clicked.
TEXT_TOP_TO_BASELINE = 0.85


def page_sizes(pdf_bytes):
    """Return the width and height (in points) of every page."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return [{"width": page.rect.width, "height": page.rect.height} for page in doc]


def render_page(pdf_bytes, page_number, zoom=2.0):
    """Draw one page as a PNG picture so the browser can show it.

    zoom=2 draws the page at twice its normal size, which looks sharp on a
    Mac Retina screen.
    """
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        page = doc[page_number]
        picture = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        return picture.tobytes("png")


def _to_page_rect(page, x, y, width, height):
    """Turn fractions of the visible page into a real rectangle on the page.

    Some PDFs are stored sideways and told to "display rotated". The visible
    page and the stored page then disagree, so we undo the rotation here.
    """
    visible = page.rect
    rect = pymupdf.Rect(
        x * visible.width,
        y * visible.height,
        (x + width) * visible.width,
        (y + height) * visible.height,
    )
    return rect * page.derotation_matrix


def stamp(pdf_bytes, items, signature_png=None):
    """Add signatures and text to the PDF and return the new PDF bytes.

    items is a list of dictionaries sent by the web page. Each one looks like:
      {"type": "signature", "page": 0, "x": .1, "y": .8, "width": .3, "height": .05}
      {"type": "text", "page": 0, "x": .1, "y": .2, "text": "Jane", "size": 12}
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    for item in items:
        page = doc[int(item["page"])]

        if item["type"] == "signature":
            if signature_png is None:
                raise ValueError("A signature was placed but no signature was added. Upload a photo or type your name first.")
            rect = _to_page_rect(page, item["x"], item["y"], item["width"], item["height"])
            # rotate makes the picture stand upright on sideways pages.
            # keep_proportion=False fills the box exactly as shown on screen.
            page.insert_image(rect, stream=signature_png, rotate=page.rotation, keep_proportion=False)

        elif item["type"] == "text":
            size = float(item.get("size", 12))
            visible = page.rect
            baseline = pymupdf.Point(
                item["x"] * visible.width,
                item["y"] * visible.height + size * TEXT_TOP_TO_BASELINE,
            )
            page.insert_text(
                baseline * page.derotation_matrix,
                item["text"],
                fontsize=size,
                fontname="helv",  # Helvetica, built into every PDF reader
                rotate=page.rotation,
            )

        else:
            raise ValueError(f"Unknown item type: {item['type']}")

    # garbage and deflate tidy up and compress the file before saving.
    result = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return result
