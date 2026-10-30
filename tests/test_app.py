"""Automatic checks. Run them with:  python -m pytest

Each function starting with test_ is one check. pytest runs them all and
tells you if anything broke. They make their own small PDF and a fake
signature photo, so no real files are needed.
"""

import io
import sys
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw

# Let the tests import app.py and friends from the folder above.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as web_app  # noqa: E402
import pdf_tools  # noqa: E402
import signature  # noqa: E402


def make_pdf(rotation=0):
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)  # US Letter
    page.set_rotation(rotation)
    return doc.tobytes()


def make_signature_photo():
    """A white "paper" with a black scribble and a light grey smudge."""
    image = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.line([(50, 150), (150, 50), (250, 150), (350, 50)], fill="black", width=8)
    draw.rectangle([(10, 10), (30, 30)], fill=(235, 235, 235))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_background_removal_makes_paper_clear_and_keeps_ink():
    photo = signature.load_photo(make_signature_photo())
    clean = signature.remove_background(photo, threshold=200)
    alpha = clean.getchannel("A")
    # The light smudge is gone, so the picture is cropped to the scribble.
    assert clean.width < 320 and clean.height < 120
    # Corners are see-through, the middle of a stroke is solid.
    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getextrema()[1] == 255


def test_big_photos_are_shrunk():
    big = Image.new("RGB", (4000, 1000), "white")
    buffer = io.BytesIO()
    big.save(buffer, format="PNG")
    assert signature.load_photo(buffer.getvalue()).width == signature.MAX_WIDTH


def test_text_lands_where_it_was_placed():
    item = {"type": "text", "page": 0, "x": 0.25, "y": 0.5, "text": "Hello", "size": 12}
    signed = pdf_tools.stamp(make_pdf(), [item])
    page = pymupdf.open(stream=signed)[0]
    words = page.get_text("words")
    assert words[0][4] == "Hello"
    left, top = words[0][0], words[0][1]
    assert left == pytest.approx(0.25 * 612, abs=2)
    assert top == pytest.approx(0.5 * 792, abs=4)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_signature_lands_where_it_was_placed(rotation):
    png = signature.to_png_bytes(signature.remove_background(signature.load_photo(make_signature_photo())))
    item = {"type": "signature", "page": 0, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}
    signed = pdf_tools.stamp(make_pdf(rotation), [item], png)
    page = pymupdf.open(stream=signed)[0]
    visible = page.rect
    # Where does the image show up on the page as you would see it?
    shown = page.get_image_rects(page.get_images()[0][0])[0] * page.rotation_matrix
    shown.normalize()
    assert shown.x0 == pytest.approx(0.1 * visible.width, abs=1)
    assert shown.y0 == pytest.approx(0.2 * visible.height, abs=1)


def test_whole_flow_through_the_web_server():
    client = web_app.app.test_client()

    pdf = client.post("/api/pdf", data={"file": (io.BytesIO(make_pdf()), "lease.pdf")}).get_json()
    assert pdf["pages"] == [{"width": 612, "height": 792}]
    assert client.get(f"/api/pdf/{pdf['id']}/page/0.png").mimetype == "image/png"

    sig = client.post("/api/signature", data={"file": (io.BytesIO(make_signature_photo()), "sig.jpg")}).get_json()
    assert client.get(f"/api/signature/{sig['id']}.png?threshold=180").mimetype == "image/png"

    items = [
        {"type": "signature", "page": 0, "x": 0.1, "y": 0.8, "width": 0.3, "height": 0.05},
        {"type": "text", "page": 0, "x": 0.5, "y": 0.8, "text": "Charlie", "size": 14},
    ]
    response = client.post(f"/api/pdf/{pdf['id']}/sign", json={"items": items, "signatureId": sig["id"]})
    assert response.status_code == 200
    assert "lease-signed.pdf" in response.headers["Content-Disposition"]
    assert "Charlie" in pymupdf.open(stream=response.data)[0].get_text()


def test_bad_upload_gives_a_clear_error():
    client = web_app.app.test_client()
    response = client.post("/api/pdf", data={"file": (io.BytesIO(b"not a pdf"), "x.pdf")})
    assert response.status_code == 400
    assert "PDF" in response.get_json()["error"]


@pytest.mark.parametrize("font_key", list(signature.FONTS))
def test_every_typed_font_draws_a_signature(font_key):
    image = signature.render_typed("Charlie Parsons", font_key)
    alpha = image.getchannel("A")
    # Some ink, some see-through gaps between letters, and wider than tall.
    assert alpha.getextrema() == (0, 255)
    assert image.width > image.height
    # Trimmed snugly: every edge of the picture touches some ink.
    assert alpha.getbbox() == (0, 0, image.width, image.height)


def test_typed_signature_needs_a_name_and_a_real_font():
    with pytest.raises(ValueError):
        signature.render_typed("   ", "allura")
    with pytest.raises(ValueError):
        signature.render_typed("Charlie", "comic-sans")


def test_typed_signature_through_the_web_server():
    client = web_app.app.test_client()
    assert b"sig-great-vibes" in client.get("/").data  # the page lists the fonts

    pdf = client.post("/api/pdf", data={"file": (io.BytesIO(make_pdf()), "lease.pdf")}).get_json()
    sig = client.post("/api/signature/typed", json={"text": "Charlie", "font": "great-vibes"}).get_json()
    assert client.get(f"/api/signature/{sig['id']}.png").mimetype == "image/png"

    items = [{"type": "signature", "page": 0, "x": 0.1, "y": 0.8, "width": 0.3, "height": 0.05}]
    response = client.post(f"/api/pdf/{pdf['id']}/sign", json={"items": items, "signatureId": sig["id"]})
    assert response.status_code == 200
    assert len(pymupdf.open(stream=response.data)[0].get_images()) == 1

    bad = client.post("/api/signature/typed", json={"text": "", "font": "great-vibes"})
    assert bad.status_code == 400


# ---------- Form fields ----------


def make_form_pdf(rotation=0):
    """A one page form with a text box, a tick box, two radio buttons and a
    drop-down, like the official forms people get sent."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)

    def add(kind, name, rect, **settings):
        widget = pymupdf.Widget()
        widget.field_type = kind
        widget.field_name = name
        widget.rect = pymupdf.Rect(rect)
        for key, value in settings.items():
            setattr(widget, key, value)
        page.add_widget(widget)

    add(pymupdf.PDF_WIDGET_TYPE_TEXT, "Full name", (72, 72, 312, 92))
    add(pymupdf.PDF_WIDGET_TYPE_CHECKBOX, "Agree", (72, 120, 86, 134))
    add(pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON, "Colour", (72, 150, 86, 164))
    add(pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON, "Colour", (100, 150, 114, 164))
    add(pymupdf.PDF_WIDGET_TYPE_COMBOBOX, "State", (72, 180, 200, 200), choice_values=["CA", "NY"])

    # PyMuPDF does not give new radio buttons proper "on" names, but real
    # forms always have them. Give ours the names "Red" and "Blue".
    radios = [w for w in page.widgets() if w.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON]
    for widget, on_name in zip(radios, ["Red", "Blue"]):
        looks = doc.xref_get_key(widget.xref, "AP/N")[1]
        drawings = [part for part in looks.replace("<<", " ").replace(">>", " ").split("/") if " R" in part]
        off, on = (part.split(None, 1)[1].strip() for part in drawings)
        doc.xref_set_key(widget.xref, "AP/N", f"<</Off {off} /{on_name} {on}>>")
        doc.xref_set_key(widget.xref, "AS", "/Off")

    page.set_rotation(rotation)
    return doc.tobytes()


def read_fields(pdf_bytes):
    """Read the form back as {name: value}. Radio buttons report the one that is on."""
    values = {}
    for widget in pymupdf.open(stream=pdf_bytes)[0].widgets():
        if widget.field_type_string == "RadioButton":
            if widget.field_value not in ("Off", None):
                values[widget.field_name] = widget.field_value
        else:
            values[widget.field_name] = widget.field_value
    return values


def test_plain_pdf_has_no_form_fields():
    assert pdf_tools.form_fields(make_pdf()) == []


def test_form_fields_are_found():
    fields = pdf_tools.form_fields(make_form_pdf())
    assert [f["kind"] for f in fields] == ["text", "checkbox", "radio", "radio", "choice"]
    assert fields[0]["name"] == "Full name" and fields[0]["value"] == ""
    assert fields[1]["value"] is False
    assert fields[4]["options"] == ["CA", "NY"]


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_form_field_boxes_match_what_you_see(rotation):
    pdf = make_form_pdf(rotation)
    text_box = pdf_tools.form_fields(pdf)[0]
    page = pymupdf.open(stream=pdf)[0]
    # Where the widget really shows up on the page as you would see it.
    shown = next(page.widgets()).rect * page.rotation_matrix
    shown.normalize()
    assert text_box["x"] * page.rect.width == pytest.approx(shown.x0, abs=0.5)
    assert text_box["y"] * page.rect.height == pytest.approx(shown.y0, abs=0.5)
    assert text_box["width"] * page.rect.width == pytest.approx(shown.width, abs=0.5)


def test_form_fields_get_filled_in():
    pdf = make_form_pdf()
    ids = [f["id"] for f in pdf_tools.form_fields(pdf)]
    answers = [
        {"id": ids[0], "page": 0, "value": "Charlie Parsons"},
        {"id": ids[1], "page": 0, "value": True},
        {"id": ids[3], "page": 0, "value": True},  # the "Blue" radio button
        {"id": ids[4], "page": 0, "value": "NY"},
    ]
    filled = pdf_tools.stamp(pdf, [], fields=answers)
    assert read_fields(filled) == {"Full name": "Charlie Parsons", "Agree": "Yes", "Colour": "Blue", "State": "NY"}
    # The typed name is drawn on the page too, not just stored.
    assert "Charlie Parsons" in pymupdf.open(stream=filled)[0].get_text()

    # Opening the filled PDF again shows the new answers.
    again = pdf_tools.form_fields(filled)
    assert [f["value"] for f in again] == ["Charlie Parsons", True, False, True, "NY"]


def test_form_fields_through_the_web_server():
    client = web_app.app.test_client()
    pdf = client.post("/api/pdf", data={"file": (io.BytesIO(make_form_pdf()), "form.pdf")}).get_json()
    assert len(pdf["fields"]) == 5
    name_box = pdf["fields"][0]

    # Fill a field and place free text in the same go.
    fields = [{"id": name_box["id"], "page": 0, "value": "Charlie"}]
    items = [{"type": "text", "page": 0, "x": 0.5, "y": 0.8, "text": "Extra note", "size": 12}]
    response = client.post(f"/api/pdf/{pdf['id']}/sign", json={"items": items, "fields": fields})
    assert response.status_code == 200
    assert read_fields(response.data)["Full name"] == "Charlie"
    assert "Extra note" in pymupdf.open(stream=response.data)[0].get_text()

    # A field id that is not in the PDF gives a clear error.
    bad = client.post(f"/api/pdf/{pdf['id']}/sign", json={"fields": [{"id": 99999, "page": 0, "value": "x"}]})
    assert bad.status_code == 400
