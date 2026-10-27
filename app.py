"""The web server. Run it with:  python app.py

Flask is a small library that turns Python functions into web pages. Each
function below with @app.route above it answers one web address. The browser
page (templates/index.html and static/app.js) calls these addresses.

Everything stays on your own computer. The server only listens to your Mac
(the address 127.0.0.1), and uploaded files are kept in memory until you
stop the app. Nothing is sent to the internet.
"""

import io
import threading
import uuid
import webbrowser

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException

import pdf_tools
import signature

# Port 5000 is taken by AirPlay on newer Macs, so we use 5050 instead.
PORT = 5050

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # refuse uploads over 50 MB

# Simple in-memory storage. Each upload gets a random id, like a coat check
# ticket, and the browser uses that id to ask for it again later.
pdfs = {}  # id -> {"name": "lease.pdf", "bytes": b"..."}
# id -> {"photo": the photo, already loaded and shrunk}
#    or {"png": a finished typed signature}
signatures = {}


@app.errorhandler(HTTPException)
def show_error(error):
    """Send errors back as JSON so the page can show a readable message."""
    return jsonify({"error": error.description}), error.code


@app.route("/")
def home():
    # Hand the list of signature fonts to the page, so it can show them.
    return render_template("index.html", fonts=signature.FONTS)


@app.post("/api/pdf")
def upload_pdf():
    file = request.files.get("file")
    if not file:
        abort(400, "No file was sent.")
    data = file.read()
    try:
        sizes = pdf_tools.page_sizes(data)
    except Exception:
        abort(400, "That file does not look like a PDF.")
    pdf_id = uuid.uuid4().hex
    pdfs[pdf_id] = {"name": file.filename or "document.pdf", "bytes": data}
    return jsonify({"id": pdf_id, "pages": sizes})


@app.get("/api/pdf/<pdf_id>/page/<int:page_number>.png")
def page_image(pdf_id, page_number):
    pdf = pdfs.get(pdf_id) or abort(404)
    png = pdf_tools.render_page(pdf["bytes"], page_number)
    return send_file(io.BytesIO(png), mimetype="image/png")


@app.post("/api/signature")
def upload_signature():
    file = request.files.get("file")
    if not file:
        abort(400, "No file was sent.")
    try:
        photo = signature.load_photo(file.read())
    except Exception:
        abort(400, "Could not open that image. Try a JPG or PNG.")
    sig_id = uuid.uuid4().hex
    signatures[sig_id] = {"photo": photo}
    return jsonify({"id": sig_id})


@app.post("/api/signature/typed")
def type_signature():
    """Turn a typed name and a chosen font into a signature picture."""
    body = request.get_json() or {}
    try:
        image = signature.render_typed(body.get("text", ""), body.get("font", ""))
    except ValueError as error:
        abort(400, str(error))
    sig_id = uuid.uuid4().hex
    signatures[sig_id] = {"png": signature.to_png_bytes(image)}
    return jsonify({"id": sig_id})


@app.get("/api/signature/<sig_id>.png")
def signature_image(sig_id):
    """Send back the signature with its background removed.

    For photos the browser adds ?threshold=200 (or another number) to the
    address, so moving the slider simply asks for a new picture. Typed
    signatures ignore the threshold because they have no paper to remove.
    """
    png = _clean_signature(sig_id, request.args.get("threshold"))
    return send_file(io.BytesIO(png), mimetype="image/png")


@app.post("/api/pdf/<pdf_id>/sign")
def sign_pdf(pdf_id):
    """Build the finished PDF and send it back as a download."""
    pdf = pdfs.get(pdf_id) or abort(404)
    body = request.get_json()
    signature_png = None
    if body.get("signatureId"):
        signature_png = _clean_signature(body["signatureId"], body.get("threshold"))
    try:
        signed = pdf_tools.stamp(pdf["bytes"], body.get("items", []), signature_png)
    except ValueError as error:
        abort(400, str(error))
    name = pdf["name"].rsplit(".", 1)[0] + "-signed.pdf"
    return send_file(io.BytesIO(signed), mimetype="application/pdf", as_attachment=True, download_name=name)


def _clean_signature(sig_id, threshold):
    saved = signatures.get(sig_id) or abort(404)
    if "png" in saved:
        return saved["png"]  # a typed signature is already clean
    photo = saved["photo"]
    threshold = int(threshold or signature.DEFAULT_THRESHOLD)
    return signature.to_png_bytes(signature.remove_background(photo, threshold))


if __name__ == "__main__":
    address = f"http://127.0.0.1:{PORT}"
    print(f"\nPDF Sign is running. Open {address} in your browser.")
    print("Press Control+C in this window to stop it.\n")
    # Open the browser for you, one second after the server starts.
    threading.Timer(1, lambda: webbrowser.open(address)).start()
    app.run(host="127.0.0.1", port=PORT)
