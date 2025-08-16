<!-- # Hindi ↔ English PDF Translator (Layout-Preserving)

Translate PDFs between Hindi and English **while preserving** the original layout, tables, images, and fonts.  
Built for free usage: **CTranslate2** (offline translation) + **Tesseract OCR** + **PyMuPDF**.

## Features
- Two-way translation: **Hindi → English**, **English → Hindi**
- Layout-preserving: copies original drawings/images, overlays translated text in the **same rectangles**
- Acronym/ALL-CAPS/URLs/emails/numbers/units **kept** via placeholders
- OCR fallback for scanned pages (`eng+hin`)
- Streamlit UI + one-click deploy to Streamlit Cloud

## Tech Stack
- UI: Streamlit
- PDF parse/render: PyMuPDF
- OCR: Tesseract via `pytesseract`
- Translation: **IndicTrans2** (converted to **CTranslate2**)  
  > Fully offline & free. Place models under `models/indictrans2-ct2/hi-en/` and `.../en-hi/`

## Project Structure
```

pdf-translator/
├── app.py
├── core/
│   ├── layout.py
│   ├── ocr.py
│   ├── rules.py
│   ├── translate.py
│   ├── typeset.py
│   └── utils.py
├── models/
│   └── indictrans2-ct2/
│       ├── hi-en/  (CT2 model + spm\_src.model + spm\_tgt.model)
│       └── en-hi/  (CT2 model + spm\_src.model + spm\_tgt.model)
├── fonts/
│   ├── NotoSans-Regular.ttf
│   ├── NotoSans-Bold.ttf
│   ├── NotoSansDevanagari-Regular.ttf
│   └── NotoSansDevanagari-Bold.ttf
├── requirements.txt
└── README.md

````

## Setup

1) Install OS deps
- Install **Tesseract** (Linux: `apt install tesseract-ocr`, Windows: installer from UB Mannheim build).
- Ensure `tesseract` is in PATH (on Windows you may set `pytesseract.pytesseract.tesseract_cmd`).

2) Python env
```bash
python -m venv .venv
source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
````

3. Fonts
   Place Noto fonts into `./fonts/` (names as above).
   (Any Unicode fonts are fine; Noto Sans + Noto Sans Devanagari recommended.)

4. Models
   Place **CTranslate2**-converted IndicTrans2 models:

```
models/indictrans2-ct2/
  ├─ hi-en/
  │   ├─ model.bin / model.json
  │   ├─ spm_src.model
  │   └─ spm_tgt.model
  └─ en-hi/
      ├─ model.bin / model.json
      ├─ spm_src.model
      └─ spm_tgt.model
```

> If models are missing, the app will **pass-through** text (no translation) to let you test the pipeline.

5. Run

```bash
streamlit run app.py
```

## How It Works

* For each page: copy drawings/images with `show_pdf_page`, then overlay translated text blocks back into the **same bboxes** via `insert_textbox`.
* Acronyms/ALL-CAPS/URLs/emails/numbers/units are replaced by placeholders before translation, restored after → **guaranteed not translated**.
* If a page has no extractable text and “OCR scanned pages” is on, we rasterize & OCR to get approximate blocks.

## Notes / Tradeoffs

* Long translations may overflow a bbox; we **shrink font** (configurable) and wrap. As last resort we write at smaller fixed size.
* OCR grouping is line-based; it’s robust enough for most scanned pages.
* If you need per-span styling (bold/italic), you can extend `layout.py` to carry span-level styles and write multiple textboxes.

---

## What next?
- If you want, share one of your sample PDFs and I’ll quickly sanity-check the pipeline on it (e.g., tweak OCR grouping or font sizes).
- When you deploy to Streamlit Cloud, remember to **add the fonts** and **models** to the repo (or download them at startup if allowed).
 -->


[![MohitGupta0123/HIN_EN_PDF_Translator context](https://badge.forgithub.com/MohitGupta0123/HIN_EN_PDF_Translator)](https://uithub.com/MohitGupta0123/HIN_EN_PDF_Translator)