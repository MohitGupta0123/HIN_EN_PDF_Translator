# PDF Translate — Automated PDF Translation & Redaction (Python)

[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Supported-blue)](https://www.docker.com/)
[![Build with ocrmypdf](https://img.shields.io/badge/OCR-ocrmypdf-orange)](https://ocrmypdf.readthedocs.io/)
[![Powered by PyMuPDF](https://img.shields.io/badge/PDF-PyMuPDF-red)](https://pymupdf.readthedocs.io/)
[![Translation](https://img.shields.io/badge/Translation-Google%20Translate-yellow)](https://pypi.org/project/googletrans/)
[![Hugging Face Space](https://img.shields.io/badge/🤗%20HuggingFace-Space-purple)](https://huggingface.co/spaces/MohitGupta0123/HIN_EN_PDF_Translator)

## [DEPLOYED LINK](https://mohitg012-pdf-translation.hf.space/)

Automate high-quality translation and selective redaction of PDFs while **preserving layout, font sizing, and colors**. The project blends:

* **OCR** (via `ocrmypdf`/Tesseract) for scanned or low-quality PDFs
* **Text-layer analysis** (PyMuPDF/`fitz`) for precise boxes, spans, lines, and blocks
* **AI translation** (Google Translate via `googletrans`)
* **Overlay & drawing** logic to put translated text back exactly where it belongs
* **Redaction/masking** that adapts to background/foreground contrast

It supports English ↔︎ Hindi out of the box and can be extended to other scripts.

---

## Table of contents

* [Key features](#key-features)
* [How it works](#how-it-works)
* [Project structure](#project-structure)
* [Installation](#installation)
* [Quick start](#quick-start)
* [Command-line usage](#command-line-usage)
* [Fonts](#fonts)
* [Overlay JSON](#overlay-json)
* [Python API (modular usage)](#python-api-modular-usage)
* [Docker](#docker)
* [Samples & outputs](#samples--outputs)
* [Limitations & notes](#limitations--notes)
* [Contributing](#contributing)

---

## Key features

1. **Language translation**
   English ↔︎ Hindi supported; auto direction detection available. Extendable by swapping fonts & translation parameters.

2. **Text layer analysis**
   Extracts *spans, lines, blocks*, and a **hybrid (column/table-aware) mode** to keep text where it belongs even in multi-column pages and tables.

3. **OCR for scanned PDFs**
   Uses `ocrmypdf` to produce a clean, searchable PDF prior to analysis.

4. **Style preservation**
   Transfers **font size & color** from the original objects to the translated overlay so the result looks native.

5. **Smart redaction / masking**

   * `redact` (true PDF redactions) or `mask` (draw filled rectangles).
   * Fill color is chosen **dynamically** from surrounding luminance (dark text → white fill, light text → black fill) to maintain visual consistency.

6. **Overlay options**

   * Generate overlays **automatically** from the current document, or
   * **Drive from JSON** (`page` + `bbox` + `translated_text`) to paint exactly what you want.
   * Render as **real text** or **high-DPI images** (for bulletproof glyph coverage).

7. **CLI & Python API**
   A single **unified script** provides modes for `span`, `line`, `block`, `hybrid`, `overlay`, and `all` (batch all modes + zip).

8. **Error correction helpers**
   Normalizes whitespace and punctuation spacing; de-noises OCR artifacts where possible.

9. **Multiple input formats**
   Any format PyMuPDF can open (primarily PDF; images should be PDF-wrapped before processing—`ocrmypdf` handles this).

10. **Security & compliance**
    Use local OCR and redaction; redact *before* writing translated text to prevent data leaks in sensitive areas.

---

## How it works

1. **OCR pass (optional but recommended)**
   `ocrmypdf` runs with language packs (e.g., `hin+eng`) and deskew/rotate to create a clean text layer.

2. **Text extraction & structure building**
   PyMuPDF extracts raw dicts of blocks/lines/spans; the code constructs:

   * basic **spans**, **lines**, **blocks**
   * **hybrid blocks** that split each raw line into **segments** by significant X-gaps (detects table cells / columns)

3. **Style sampling**
   A lightweight index of original color & font size is built and transferred to translated objects using IoU/nearest heuristics.

4. **Translation**
   Uses `googletrans` (Google Translate) with direction:

   * `hi->en`, `en->hi`, or `auto` (detect from dominant script).

5. **Erasure / Redaction**
   Depending on mode:

   * **mask**: draw filled rectangles (per-box adaptive fill)
   * **redact**: actual redaction annotations applied page-wide

6. **Overlay**
   The translated text is written back using either:

   * **Text boxes** (`insert_textbox` with font fallback), or
   * **High-DPI image tiles** rendered via PIL for maximum glyph fidelity.

7. **All-mode**
   Runs `span`, `line`, `block`, `hybrid`, and optionally `overlay`, writing separate PDFs and a combined ZIP.

---

## Project structure

```
PDF-TRANSLATOR
├── app.py                      # (Optional) app entry (e.g., Streamlit)
├── PDF_Translate/              # Modular library
│   ├── __init__.py
│   ├── cli.py
│   ├── constants.py
│   ├── hybrid.py
│   ├── ocr.py
│   ├── overlay.py
│   ├── pipeline.py
│   ├── textlayer.py
│   └── utils.py
├── pdf_translate_unified.py    # Unified CLI/API (span/line/block/hybrid/overlay/all)
├── assets/
│   └── fonts/                  # Pre-bundled font files (English & Devanagari)
│       ├── NotoSans-Regular.ttf
│       ├── NotoSans-Bold.ttf
│       ├── NotoSansDevanagari-Regular.ttf
│       ├── NotoSansDevanagari-Bold.ttf
│       ├── TiroDevanagariHindi-Regular.ttf
│       ├── Hind-Regular.ttf
│       ├── Karma-Regular.ttf
│       └── Mukta-Regular.ttf
├── samples/
│   ├── Test1.pdf
│   ├── Test1_translated.pdf
│   ├── Test2.pdf
│   ├── Test2_translated.pdf
│   ├── Test3.pdf
│   └── Test3_translated.pdf
├── output_pdfs/                # Generated outputs land here
├── temp/                       # OCR/rasterization scratch (e.g., ocr_fixed.pdf)
├── requirements.txt
├── Dockerfile
└── Readme.md                   # (this document)
```

---

## Installation

### 1) System prerequisites

* **Python**: 3.12 recommended
* **Tesseract & ocrmypdf**: required for OCR
* **Ghostscript + qpdf**: required by `ocrmypdf`

**Ubuntu/Debian**

```bash
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-hin ocrmypdf ghostscript qpdf
```

**macOS (Homebrew)**

```bash
brew install tesseract ocrmypdf ghostscript qpdf
```

**Windows**

* Install **Tesseract** (UB Mannheim build recommended) and make sure `tesseract.exe` is on PATH.
* Install **Ghostscript** and **qpdf**; add to PATH.
* Install **ocrmypdf** via pip (will use the system binaries above).

### 2) Python packages

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Quick start

Translate a PDF (English → Hindi) using **all** modes:

```bash
python pdf_translate_unified.py \
  --input samples/Test3.pdf \
  --output output_pdfs/result.pdf \
  --mode all \
  --translate en->hi
```

What you get:

* `result.span.pdf`
* `result.line.pdf`
* `result.block.pdf`
* `result.hybrid.pdf`
* `result.overlay.pdf`
* `result_all_methods.zip` bundling the above

---

## Command-line usage

```
python pdf_translate_unified.py --help
```

### Required

* `--input / -i`: path to your source PDF
* `--output / -o`: output path (for `--mode all`, this is the **base name**)

### Modes

* `--mode {span,line,block,hybrid,overlay,all}` (default: `all`)

**When to use which**

* `span` – ultra-fine placement, best for mixed inline styles; can look busy
* `line` – per line; balances fidelity & readability
* `block` – per paragraph/block; often the cleanest look
* `hybrid` – **column/table-aware**; great for multi-column layouts and tabular data
* `overlay` – paint from a JSON (see below) or from `--auto-overlay`
* `all` – run several modes and zip them for comparison

### OCR options

* `--lang` (default: `hin+eng`) – languages passed to `ocrmypdf`
* `--dpi` (default: `1000`) – `--image-dpi/--oversample` for `ocrmypdf`
* `--optimize` (default: `3`) – `ocrmypdf --optimize` level
* `--skip-ocr` – use the input PDF as-is (not recommended for scanned PDFs)

### Translation direction

* `--translate {hi->en,en->hi,auto}` (default: `hi->en`)

### Redaction / masking

* `--erase {redact,mask,none}` (default: `redact`)
* `--redact-color r,g,b` – **only** used when a fixed color is required; otherwise the tool automatically picks black or white from context.

### Fonts

* `--font-en-name` (logical name; default `NotoSans`)
* `--font-en-path` (path to TTF; default bundled Noto Sans)
* `--font-hi-name` (default `NotoSansDevanagari`)
* `--font-hi-path` (path to Devanagari TTF; defaults to Base14 `helv` if missing)

### Overlay-specific knobs

* `--overlay-json /path/to/text_data.json`
* `--auto-overlay` – build overlay items from the doc and chosen `--translate`
* `--overlay-render {image,textbox}` (default `image`)
* `--overlay-align {0,1,2,3}` – left/center/right/justify (justify only for textbox)
* `--overlay-line-spacing` (default `1.10`)
* `--overlay-margin-px` (default `0.1`)
* `--overlay-target-dpi` (default `600`)
* `--overlay-scale-x|y`, `--overlay-off-x|y` – fix geometry if the JSON was created on a near-duplicate PDF

### Example commands

**1) English → Hindi (hybrid mode)**

```bash
python pdf_translate_unified.py -i samples/Test1.pdf -o output_pdfs/t1.hybrid.pdf \
  --mode hybrid --translate en->hi
```

**2) Hindi → English (block mode, masking)**

```bash
python pdf_translate_unified.py -i samples/Test2.pdf -o output_pdfs/t2.block.pdf \
  --mode block --translate hi->en --erase mask
```

**3) Overlay from JSON with real text (keep searchable layer)**

```bash
python pdf_translate_unified.py -i samples/Test3.pdf -o output_pdfs/t3.overlay.pdf \
  --mode overlay --overlay-json text_data.json --overlay-render textbox \
  --overlay-align 0 --overlay-line-spacing 1.15
```

**4) Auto-overlay (no JSON; build from doc)**

```bash
python pdf_translate_unified.py -i samples/Test3.pdf -o output_pdfs/t3.overlay.pdf \
  --mode overlay --auto-overlay --translate en->hi
```

---

## Fonts

For **Devanagari**, the bundled fonts work well:

* `NotoSansDevanagari-Regular.ttf`
* `TiroDevanagariHindi-Regular.ttf`
* Others: `Hind`, `Mukta`, `Karma`

Specify alternatives via `--font-hi-path`. For English, `NotoSans` is the default.

---

## Overlay JSON

You can drive the overlay precisely with a JSON file:

```json
[
  {
    "page": 0,
    "bbox": [72.0, 144.0, 270.0, 180.0],
    "translated_text": "Hello world",
    "fontsize": 11.5
  }
]
```

* **Required:** `page`, `bbox` (`[x0,y0,x1,y1]` in PDF points), `translated_text`
* **Optional:** `fontsize` (used as a base; the renderer will fit it)

Run:

```bash
python pdf_translate_unified.py -i in.pdf -o out.pdf \
  --mode overlay --overlay-json text_data.json
```

**Geometry mismatch?** If your JSON came from a slightly different source PDF:

* `--overlay-scale-x|y` to scale all boxes
* `--overlay-off-x|y` to shift them

---

## Python API (modular usage)

You can call the building blocks directly from Python for custom pipelines.

```python
from pdf_translate_unified import (
    extract_original_page_objects, ocr_fix_pdf, build_base,
    resolve_font, run_mode, build_overlay_items_from_doc
)

input_pdf = "samples/Test3.pdf"
output_pdf = "output_pdfs/demo_all.pdf"
translate_direction = "en->hi"

# 1) Style index from original (pre-OCR) for accurate color/size
orig_index = extract_original_page_objects(input_pdf)

# 2) OCR pass
src_fixed = ocr_fix_pdf(input_pdf, lang="hin+eng", dpi="1000", optimize="3")

# 3) Create source/output documents with background preserved
src, out = build_base(src_fixed)

# 4) Configure fonts
en_name, en_file = resolve_font("NotoSans", "assets/fonts/NotoSans-Regular.ttf")
hi_name, hi_file = resolve_font("NotoSansDevanagari", "assets/fonts/TiroDevanagariHindi-Regular.ttf")

# 5) Optional: auto-build overlay items
overlay_items = build_overlay_items_from_doc(src, translate_direction)

# 6) Run any mode (or "all")
run_mode(
    mode="all",
    src=src, out=out,
    orig_index=orig_index,
    translate_dir=translate_direction,
    erase_mode="redact",
    redact_color=(1,1,1),
    font_en_name=en_name, font_en_file=en_file,
    font_hi_name=hi_name, font_hi_file=hi_file,
    output_pdf=output_pdf,
    overlay_items=overlay_items,
    overlay_render="image",
    overlay_target_dpi=600
)
```

---

## Docker

Build:

```bash
docker build -t pdf-translate .
```

Run (mount your PDFs):

```bash
docker run --rm -v "$PWD:/work" pdf-translate \
  python pdf_translate_unified.py -i /work/samples/Test3.pdf \
  -o /work/output_pdfs/result.pdf --mode all --translate en->hi
```

---

## Samples & outputs

See `samples/` for input PDFs and `_translated.pdf` examples.
Recent runs create files under `output_pdfs/`, including individual mode outputs and a zipped bundle like:

```
result_YYYYMMDD-HHMMSS.all.block.pdf
result_YYYYMMDD-HHMMSS.all.hybrid.pdf
result_YYYYMMDD-HHMMSS.all.line.pdf
result_YYYYMMDD-HHMMSS.all.overlay.pdf
result_YYYYMMDD-HHMMSS.all.span.pdf
result_YYYYMMDD-HHMMSS_all_methods.zip
```

---

## Limitations & notes

* `googletrans` relies on unofficial endpoints; for production, consider swapping in an official translation API (e.g., Google Cloud Translate, Azure, DeepL).
* OCR quality determines downstream accuracy; garbage in → garbage out.
* Complex vector art or text on curves isn’t reflowed; overlay is rectangular.
* True layout editing (re-wrapping across pages) is out of scope by design.

---

## Contributing

Issues and PRs are welcome!:

* New language/font packs & font auto-selection rules
* Pluggable translator backends
* Better table detection & alignment heuristics
* Streamlit UX in `app.py` for drag-and-drop PDFs

Please run `ruff`/`black` (if configured) and include before/after sample PDFs for visual changes.

---

## Acknowledgements

* **PyMuPDF (fitz)** for robust PDF parsing/rendering
* **ocrmypdf** + **Tesseract** for OCR
* **Pillow (PIL)** for high-DPI text rendering in image overlays
* **Google Translate** (via `googletrans`) for quick translation prototyping

---
