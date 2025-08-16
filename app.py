import os, io, time, tempfile, zipfile, streamlit as st
from pathlib import Path

from PDF_Translate.constants import (DEFAULT_LANG, DEFAULT_DPI, DEFAULT_OPTIMIZE, DEFAULT_TRANSLATE_DIR,
                                     DEFAULT_ERASE, FONT_EN_LOGICAL, FONT_EN_PATH, FONT_HI_LOGICAL, FONT_HI_PATH)
from PDF_Translate.textlayer import extract_original_page_objects
from PDF_Translate.ocr import ocr_fix_pdf
from PDF_Translate.utils import build_base, resolve_font
from PDF_Translate.overlay import overlay_load_items, build_overlay_items_from_doc
from PDF_Translate.pipeline import run_mode

st.set_page_config(page_title="PDF Translate (EN↔HI)", page_icon="🗎", layout="wide")

st.title("🗎 PDF Translate (EN ↔ HI)")
st.caption("Style-preserving PDF translation with PyMuPDF + (optional) OCRmyPDF + overlay rendering")

with st.sidebar:
    st.header("Settings")
    mode = st.selectbox("Mode", ["all","overlay","hybrid","block","line","span"], index=0)
    translate_dir = st.selectbox("Translate Direction", ["en->hi","hi->en","auto"], index=0)
    erase_mode = st.selectbox("Erase original text", ["redact","mask","none"], index=0)
    lang = st.text_input("OCR language(s)", DEFAULT_LANG)
    dpi = st.text_input("OCR image DPI", DEFAULT_DPI)
    optimize = st.text_input("OCR optimize", DEFAULT_OPTIMIZE)
    skip_ocr = st.checkbox("Skip OCR", value=False)
    auto_overlay = st.checkbox("Auto-build overlay (when overlay/all)", value=True)
    overlay_render = st.selectbox("Overlay render", ["image","textbox"], index=0)
    overlay_align = st.selectbox("Overlay align (0=left, 1=center, 2=right, 3=justify)", options=[0, 1, 2, 3], index=0)
    overlay_line_spacing = st.number_input("Overlay line spacing", value=1.10, step=0.05)
    overlay_margin_px = st.number_input("Overlay inner margin (pt)", value=0.1, step=0.1)
    overlay_target_dpi = st.number_input("Overlay target DPI", value=600, step=50)
    overlay_scale_x = st.number_input("Overlay scale X", value=1.0, step=0.01)
    overlay_scale_y = st.number_input("Overlay scale Y", value=1.0, step=0.01)
    overlay_off_x = st.number_input("Overlay offset X", value=0.0, step=0.5)
    overlay_off_y = st.number_input("Overlay offset Y", value=0.0, step=0.5)

    st.markdown("---")
    st.subheader("Fonts")
    en_font_path = st.text_input("English font path", FONT_EN_PATH)
    hi_font_path = st.text_input("Hindi font path", FONT_HI_PATH)

st.write("Upload a PDF and (optionally) a JSON overlay (only if not using auto-overlay).")

pdf_file = st.file_uploader("PDF", type=["pdf"])

if st.button("Run translation", disabled=pdf_file is None, type="primary"):
    with st.spinner("Processing..."):
        # ---- temp workspace for this run ----
        with tempfile.TemporaryDirectory() as workdir:
            workdir = Path(workdir)

            # save uploaded pdf to temp
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", dir=workdir) as tf:
                tf.write(pdf_file.read())
                input_pdf_path = tf.name

            # collect original styles BEFORE OCR
            orig_index = extract_original_page_objects(input_pdf_path)

            # OCR (optional). If your ocr_fix_pdf writes to relative 'temp/ocr_fixed.pdf',
            # that’s fine; it’s inside the process CWD. Otherwise ensure it writes inside workdir.
            src_fixed = input_pdf_path if skip_ocr else ocr_fix_pdf(
                input_pdf_path, lang=lang, dpi=dpi, optimize=optimize
            )

            # base docs
            src, out = build_base(src_fixed)

            # fonts
            en_name, en_file = resolve_font(FONT_EN_LOGICAL, en_font_path)
            if hi_font_path:
                hi_name, hi_file = resolve_font(FONT_HI_LOGICAL, hi_font_path)
            else:
                hi_name, hi_file = ("helv", None)

            # overlay items (if needed)
            overlay_items = None
            if mode in ("overlay","all"):
                if auto_overlay:
                    overlay_items = build_overlay_items_from_doc(src, translate_dir)
                elif mode == "overlay":
                    st.error("Overlay mode requires JSON or enable Auto overlay."); st.stop()

            # output filename base (but inside temp dir)
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            out_name = f"result_{timestamp}.pdf" if mode!="all" else f"result_{timestamp}.all.pdf"
            output_pdf_path = str(workdir / out_name)

            # go
            run_mode(
                mode=mode,
                src=src, out=out,
                orig_index=orig_index,
                translate_dir=translate_dir,
                erase_mode=erase_mode,
                redact_color=(1,1,1),
                font_en_name=en_name, font_en_file=en_file,
                font_hi_name=hi_name, font_hi_file=hi_file,
                output_pdf=output_pdf_path,
                overlay_items=overlay_items,
                overlay_render=overlay_render,
                overlay_align={0:0,1:1,2:2,3:3}[overlay_align],
                overlay_line_spacing=overlay_line_spacing,
                overlay_margin_px=overlay_margin_px,
                overlay_target_dpi=int(overlay_target_dpi),
                overlay_scale_x=float(overlay_scale_x),
                overlay_scale_y=float(overlay_scale_y),
                overlay_off_x=float(overlay_off_x),
                overlay_off_y=float(overlay_off_y),
            )

            # ===== Build an in-memory ZIP with PDFs from this run =====
            # In 'all' mode your pipeline writes: result_...all.span.pdf, .line.pdf, .block.pdf, .hybrid.pdf, .overlay.pdf
            # In single modes it writes just one file at 'output_pdf_path'
            if mode == "all":
                pdfs = sorted(workdir.glob(f"result_{timestamp}.all.*.pdf"))
                zip_display_name = f"result_{timestamp}.all_all_methods.zip"
            else:
                # Prefer the exact output name; fallback to any single-mode file if pipeline tweaks names
                pdfs = [Path(output_pdf_path)] if Path(output_pdf_path).exists() else sorted(workdir.glob(f"result_{timestamp}*.pdf"))
                zip_display_name = f"result_{timestamp}.{mode}.zip"

            # Create in-memory ZIP
            if not pdfs:
                st.error("No PDFs produced by the pipeline.")
                # Helpful debug: list files in temp
                all_files = [str(p.relative_to(workdir)) for p in workdir.glob("**/*")]
                st.write("Files in temp workspace:", all_files)
                st.stop()

            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                for p in pdfs:
                    # write as just the filename, without temp path
                    zf.write(p, arcname=Path(p).name)
            zip_buf.seek(0)

    st.success("Done!")
    st.download_button(
        "⬇️ Download results (ZIP)",
        data=zip_buf.getvalue(),
        file_name=zip_display_name,
        mime="application/zip"
    )