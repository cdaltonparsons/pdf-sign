# PDF Sign

A small, free app for signing PDFs on your own computer. You open a PDF, add a photo of your signature, click where it should go, type any extra text (like the date), and download the signed copy.

It runs on your Mac as a tiny web page in your browser. Nothing is uploaded to the internet. The "server" lives on your laptop and only your laptop can reach it.

## What it can do today

You can open any PDF and see every page. You can upload a photo of your signature on white paper, and the app removes the paper so only the ink is left. A slider lets you tune how much gets removed. If you do not have a photo handy, click "Type it" instead, type your name, and pick one of six handwriting style fonts. The fonts come with the app, so this works without internet. You can click to place the signature or a line of text anywhere, drag things around, resize them, and then download the finished PDF. Some PDFs, like tax and rental forms, come with their own boxes to type in. When you open one of those, the app shades each box light blue on the page. Click a box and type, tick the tick boxes, and pick from the drop-down lists. Your answers are saved into the PDF's real form fields, so they show up in any PDF reader.

## Setting it up on a Mac

You only need to do this once.

**1. Install Python.** Go to [python.org/downloads](https://www.python.org/downloads/) and click the big yellow download button. Open the file it downloads and click through the installer. Python is the language this app is written in.

**2. Open Terminal.** Press Command and Space together, type `Terminal`, and press Return. Terminal is a window where you type commands instead of clicking. Every grey box below is a command. Paste it in and press Return.

**3. Check Python works.** This should print something like `Python 3.13.1`.

```bash
python3 --version
```

**4. Download the app's code.** This copies the project from GitHub into a folder called `pdf-sign` inside your home folder. The first time you use `git`, your Mac may offer to install "command line developer tools". Say yes, wait for it to finish, then run the command again.

```bash
cd ~
git clone https://github.com/cdaltonparsons/pdf-sign.git
cd pdf-sign
```

**5. Make a private space for the app's libraries.** This is called a virtual environment. It keeps the libraries this app needs separate from the rest of your Mac, so nothing else gets mixed up.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

You will now see `(.venv)` at the start of the Terminal line. That means the private space is switched on.

**6. Install the libraries.** This reads `requirements.txt` and downloads Flask (the web server), PyMuPDF (PDF editing) and Pillow (image editing).

```bash
pip install -r requirements.txt
```

## Running the app

Each time you want to use it, open Terminal and run:

```bash
cd ~/pdf-sign
source .venv/bin/activate
python app.py
```

Your browser opens at http://127.0.0.1:5050 by itself. If it does not, paste that address into your browser. When you are done, go back to Terminal and press Control and C together to stop the app.

## Tips for a good signature photo

Sign with a dark pen on plain white paper. Take the photo in good light, straight on, and crop it close to the signature. JPG, PNG and iPhone HEIC photos all work. If parts of the ink disappear, slide the background slider to the right. If grey paper still shows around the ink, slide it to the left.

## About the signature fonts

The handwriting fonts are free fonts from Google Fonts: Great Vibes, Allura, Sacramento, Alex Brush, Mrs Saint Delafield and Dancing Script. They use the SIL Open Font License, which lets anyone use and share them. The font files live in `static/fonts` and their licences are in `static/fonts/licenses`. To add another font, put its `.ttf` file in `static/fonts` and add one line to the `FONTS` list in `signature.py`.

## Getting updates

When new changes are merged on GitHub, pull them down with:

```bash
cd ~/pdf-sign
git pull
source .venv/bin/activate
pip install -r requirements.txt
```

## How the code is organised

`app.py` is the web server. It answers the browser's requests. `signature.py` removes the paper background from a signature photo, and draws typed signatures in the handwriting fonts. `pdf_tools.py` draws pages as pictures and finds and fills the PDF's own form fields, and stamps the signature and text onto the PDF. `templates/index.html`, `static/app.js` and `static/style.css` are the web page you see. The `tests` folder holds automatic checks. Run them with `pip install pytest` and then `python -m pytest`.
