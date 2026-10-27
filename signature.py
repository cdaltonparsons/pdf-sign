"""Make signature pictures with a see-through background.

There are two ways to get one. You can upload a photo of your real signature,
or you can type your name and pick a handwriting style font.

For photos the idea is simple. Paper is light and ink is dark. So we look at
how bright each pixel is. Bright pixels (the paper) become fully transparent.
Dark pixels (the ink) stay solid. Pixels in between fade smoothly, which keeps
the edges of the pen strokes from looking jagged.
"""

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

# iPhones often save photos as HEIC. This optional add-on teaches Pillow to
# read them. If it is not installed, JPG and PNG still work fine.
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

# Photos from a phone can be huge. Shrinking them keeps the app fast and the
# final PDF small. 1200 pixels wide is still very sharp for a signature.
MAX_WIDTH = 1200

# How wide the "fade" zone is, in brightness steps (0 is black, 255 is white).
SOFT_EDGE = 40

DEFAULT_THRESHOLD = 200


def load_photo(file_bytes):
    """Open an uploaded photo and get it ready for processing."""
    image = Image.open(io.BytesIO(file_bytes))
    # Phones store "which way is up" as a hidden tag. This applies it, so a
    # photo taken sideways does not end up sideways in the PDF.
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    if image.width > MAX_WIDTH:
        new_height = round(image.height * MAX_WIDTH / image.width)
        image = image.resize((MAX_WIDTH, new_height), Image.LANCZOS)
    return image


def remove_background(image, threshold=DEFAULT_THRESHOLD):
    """Return a copy of the image where the light paper is transparent.

    threshold is a number from 0 to 255. Any pixel at least this bright
    counts as paper and disappears. Raise it if bits of the signature vanish.
    Lower it if grey shadows from the paper are still showing.
    """
    threshold = max(1, min(255, int(threshold)))
    start_fading = max(0, threshold - SOFT_EDGE)

    def brightness_to_opacity(brightness):
        if brightness >= threshold:
            return 0  # paper: fully see-through
        if brightness <= start_fading:
            return 255  # ink: fully solid
        # In between: fade from solid to see-through.
        return round(255 * (threshold - brightness) / (threshold - start_fading))

    grey = image.convert("L")  # "L" means one brightness value per pixel
    opacity = grey.point(brightness_to_opacity)

    result = image.convert("RGBA")
    result.putalpha(opacity)

    # Trim away the empty border so the signature box fits the ink snugly.
    box = opacity.getbbox()
    if box:
        result = result.crop(box)
    return result


def to_png_bytes(image):
    """Save an image as PNG into memory and return the raw bytes."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# ---------- Typed signatures ----------

# The handwriting fonts live in static/fonts. They are free fonts from Google
# Fonts, under the SIL Open Font License, so we are allowed to ship them with
# the app. Keeping them in the repo means typed signatures work offline.
FONTS_FOLDER = Path(__file__).resolve().parent / "static" / "fonts"

# Each font has a short key (used by the web page), a friendly name and a
# file. To add a font, drop the .ttf file in static/fonts and add a line here.
FONTS = {
    "great-vibes": {"name": "Great Vibes", "file": "GreatVibes-Regular.ttf"},
    "allura": {"name": "Allura", "file": "Allura-Regular.ttf"},
    "sacramento": {"name": "Sacramento", "file": "Sacramento-Regular.ttf"},
    "alex-brush": {"name": "Alex Brush", "file": "AlexBrush-Regular.ttf"},
    "mrs-saint-delafield": {"name": "Mrs Saint Delafield", "file": "MrsSaintDelafield-Regular.ttf"},
    "dancing-script": {"name": "Dancing Script", "file": "DancingScript.ttf"},
}

# How big to draw the letters, in pixels. Big letters stay sharp when the
# signature is printed, even after you stretch it on the page.
TYPED_FONT_SIZE = 200

# Nearly black with a hint of blue, like a real pen.
INK_COLOUR = (20, 25, 60, 255)


def render_typed(text, font_key):
    """Draw the typed name in the chosen font and return a see-through image."""
    text = text.strip()
    if not text:
        raise ValueError("Type your name first.")
    if font_key not in FONTS:
        raise ValueError(f"Unknown font: {font_key}")
    font = ImageFont.truetype(str(FONTS_FOLDER / FONTS[font_key]["file"]), TYPED_FONT_SIZE)

    # Script fonts have curly tails (swashes) that reach past the edges of
    # the letters. So we draw on a canvas with lots of room to spare, and then
    # trim the empty space away, just like we do for photos.
    left, top, right, bottom = font.getbbox(text)
    margin = TYPED_FONT_SIZE
    canvas = Image.new("RGBA", (right - left + 2 * margin, bottom - top + 2 * margin), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((margin - left, margin - top), text, font=font, fill=INK_COLOUR)

    box = canvas.getchannel("A").getbbox()
    return canvas.crop(box) if box else canvas
