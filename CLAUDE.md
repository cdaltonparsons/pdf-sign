# CLAUDE.md

Notes for Claude (and any other AI helper) working on this repo.

## About the project

PDF Sign is a small, local-only app for signing PDFs. It runs on the owner's Mac as a Flask server on http://127.0.0.1:5050 with a plain HTML and JavaScript page. There is no build step, no database and no JavaScript framework. Keep it that way unless asked. The goal is a free, no-bloat tool.

The owner, Charlie, is new to Python and to coding with AI. This is a learning project. When you change code, explain what you did and why in plain, simple words. Keep changes small so each one is easy to follow. Code comments should also be in plain language.

## Writing style

In replies, docs and comments, do not use em dashes. Avoid semicolons. Prefer prose to bullet points and keep sentences short.

## How it fits together

`app.py` holds the Flask routes and keeps uploads in memory, keyed by a random id. `signature.py` uses Pillow to remove the light paper background from a signature photo. Pixels brighter than the threshold become transparent, with a soft fade near the threshold, and the result is cropped to the ink. `pdf_tools.py` uses PyMuPDF to render pages and to stamp items. `static/app.js` handles placing, dragging and resizing.

The browser sends positions as fractions of the visible page (0 to 1), not as pixels or points. `pdf_tools.py` converts them to PDF points and uses `page.derotation_matrix` so pages with a rotation setting still work. If you touch placement code, keep the rotation tests passing.

Text uses Helvetica in both the browser and the PDF. `TEXT_TOP_TO_BASELINE` in `pdf_tools.py` lines the two up, so change it together with the `.item.text` CSS if you change fonts.

## Commands

Set up with `python3 -m venv .venv`, then `source .venv/bin/activate`, then `pip install -r requirements.txt`. Run the app with `python app.py`. Run the tests with `python -m pytest` (install pytest first).

## Roadmap

Version 1 places a signature and free text anywhere on a page. The next step is filling the PDF's own form fields (PyMuPDF `page.widgets()`).
