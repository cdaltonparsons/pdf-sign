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


# The kinds of form field we know how to fill, keyed by PyMuPDF's number for
# each kind. Buttons and signature boxes are left alone.
FIELD_KINDS = {
    pymupdf.PDF_WIDGET_TYPE_TEXT: "text",
    pymupdf.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
    pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: "radio",
    pymupdf.PDF_WIDGET_TYPE_COMBOBOX: "choice",
    pymupdf.PDF_WIDGET_TYPE_LISTBOX: "choice",
}
# Field "flags" are on/off switches packed into one number. These two say
# "you may not change this field" and "this text box takes several lines".
READ_ONLY_FLAG = 1
MULTILINE_FLAG = 4096


def form_fields(pdf_bytes):
    """List the fill-in boxes built into the PDF, if it has any.

    Many official forms come with their own boxes to type in. PDF calls them
    "widgets". Each one we find is described for the browser like this:
      {"id": 12, "page": 0, "kind": "text", "name": "First name",
       "x": .1, "y": .2, "width": .3, "height": .03, "value": "", ...}
    Like everything else, positions are fractions of the visible page.
    A plain PDF simply gives back an empty list.
    """
    fields = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            visible = page.rect
            for widget in page.widgets():
                kind = FIELD_KINDS.get(widget.field_type)
                if kind is None:
                    continue
                # The widget's box is stored on the unrotated page. Turn it
                # the way the page is shown, like _to_page_rect but backwards.
                box = widget.rect * page.rotation_matrix
                box.normalize()
                field = {
                    # The xref is the widget's own number inside the PDF file.
                    # It stays the same, so it makes a handy id.
                    "id": widget.xref,
                    "page": page.number,
                    "kind": kind,
                    "name": widget.field_name or "",
                    "label": widget.field_label or "",
                    "x": box.x0 / visible.width,
                    "y": box.y0 / visible.height,
                    "width": box.width / visible.width,
                    "height": box.height / visible.height,
                    "fontSize": widget.text_fontsize or 0,  # 0 means "fit to the box"
                    "readOnly": bool(widget.field_flags & READ_ONLY_FLAG),
                }
                if kind == "text":
                    field["value"] = widget.field_value or ""
                    field["multiline"] = bool(widget.field_flags & MULTILINE_FLAG)
                    field["maxLength"] = widget.text_maxlen or 0
                elif kind in ("checkbox", "radio"):
                    # A tick box is "on" when its value matches its "on" name,
                    # which is often "Yes" but can be any word.
                    field["value"] = widget.field_value == widget.on_state()
                else:
                    field["value"] = widget.field_value or ""
                    field["options"] = _choice_options(widget.choice_values)
                fields.append(field)
    return fields


def _choice_options(values):
    """A drop-down's options can be plain words or (saved value, shown text)
    pairs. Keep only the saved value, which is also what we write back."""
    return [value[0] if isinstance(value, (list, tuple)) else value for value in values or []]


def _fill_fields(doc, fields):
    """Write the browser's answers into the PDF's own form fields.

    fields is a list like [{"id": 12, "page": 0, "value": "Jane"}]. The value
    is text for text boxes and drop-downs, and True or False for tick boxes
    and round "radio" buttons.
    """
    wanted = {}
    for field in fields:
        wanted.setdefault(int(field["page"]), {})[int(field["id"])] = field["value"]

    for page_number, answers in wanted.items():
        page = doc[page_number]
        for widget in page.widgets():
            if widget.xref not in answers:
                continue
            value = answers.pop(widget.xref)
            kind = FIELD_KINDS.get(widget.field_type)
            if kind in ("text", "choice"):
                widget.field_value = str(value)
            elif kind == "checkbox":
                widget.field_value = bool(value)
            elif kind == "radio":
                # Switching one radio button on switches the others in its
                # group off by itself, so we only need the one that is on.
                if not value:
                    continue
                widget.field_value = True
            else:
                continue
            # update() saves the change and redraws how the box looks, so
            # every PDF reader shows the new value.
            widget.update()
        if answers:
            raise ValueError("Some form fields were not found in this PDF. Try opening it again.")


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


def stamp(pdf_bytes, items, signature_png=None, fields=()):
    """Add signatures and text to the PDF and return the new PDF bytes.

    items is a list of dictionaries sent by the web page. Each one looks like:
      {"type": "signature", "page": 0, "x": .1, "y": .8, "width": .3, "height": .05}
      {"type": "text", "page": 0, "x": .1, "y": .2, "text": "Jane", "size": 12}
    fields holds answers for the PDF's own form boxes (see _fill_fields).
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    _fill_fields(doc, fields)
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
