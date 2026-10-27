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
