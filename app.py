# app.py
import os, io, time, tempfile, zipfile, json, re
from pathlib import Path

import streamlit as st
import fitz

from PDF_Translate.constants import (
    DEFAULT_LANG, DEFAULT_DPI, DEFAULT_OPTIMIZE, DEFAULT_TRANSLATE_DIR,
    DEFAULT_ERASE, FONT_EN_LOGICAL, FONT_EN_PATH, FONT_HI_LOGICAL,
    FONT_HI_PATH, FONT_HI_PATH_2, FONT_HI_LOGICAL_2
)
from PDF_Translate.textlayer import extract_original_page_objects
from PDF_Translate.ocr import ocr_fix_pdf
from PDF_Translate.utils import build_base, resolve_font
from PDF_Translate.overlay import build_overlay_items_from_doc
from PDF_Translate.pipeline import run_mode

from PDF_Translate.highlight_boxes import _hex_to_rgb01, add_boxes_to_pdf, build_annotation_items_from_pdf

# ----------------------------
# Streamlit layout
# ----------------------------
st.set_page_config(page_title="PDF Translate (EN↔HI)", page_icon="🗎", layout="wide")
st.title("🗎 PDF Translate (EN ↔ HI)")
st.caption("Style-preserving PDF translation with PyMuPDF + (optional) OCRmyPDF + overlay rendering")

# ----------------------------
# Sidebar settings
# ----------------------------
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
    hi_font_path = st.text_input("Hindi font path", FONT_HI_PATH_2)

    st.markdown("---")
    st.subheader("Annotation (auto-generate)")
    do_annotate = st.checkbox("Create and add annotations automatically", value=True)
    annot_method = st.selectbox(
        "What to highlight?",
        ["All text blocks", "Devanagari words", "English words", "Custom regex"],
        index=0
    )
    custom_regex = st.text_input("Custom regex (used if 'Custom regex' selected)", r"[\u0900-\u097F]+")
    merge_lines = st.checkbox("Merge words into line boxes", value=False)
    min_w = st.number_input("Min box width (pt)", value=1.0, step=0.5)
    min_h = st.number_input("Min box height (pt)", value=1.0, step=0.5)
    expand_margin = st.number_input("Expand margin around boxes (pt)", value=0.0, step=0.5)

    annot_use_annot = st.selectbox("Annotation method", ["draw-on-page", "annotation-layer"], index=0)
    annot_stroke_width = st.number_input("Stroke width", value=1.5, step=0.5)
    annot_fill_opacity = st.slider("Fill opacity", 0.0, 1.0, 0.15, step=0.05)
    annot_color_hex = st.color_picker("Color", "#FF0000")
    annot_fill = st.checkbox("Fill rectangle", value=True)

# ----------------------------
# Main UI
# ----------------------------
st.write("Upload a PDF for Translation.")
pdf_file = st.file_uploader("PDF", type=["pdf"])

if st.button("Run translation", disabled=pdf_file is None, type="primary"):
    with st.spinner("Processing..."):
        with tempfile.TemporaryDirectory() as workdir:
            workdir = Path(workdir)

            # Save uploaded PDF to temp
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", dir=workdir) as tf:
                tf.write(pdf_file.read())
                input_pdf_path = tf.name

            # Extract original layout index (for overlay / alignment)
            orig_index = extract_original_page_objects(input_pdf_path)

            # Optionally OCR-fix PDF
            src_fixed = input_pdf_path if skip_ocr else ocr_fix_pdf(
                input_pdf_path, lang=lang, dpi=dpi, optimize=optimize
            )

            # Build base in/out paths
            src, out = build_base(src_fixed)

            # Resolve fonts
            en_name, en_file = resolve_font(FONT_EN_LOGICAL, en_font_path)
            if hi_font_path:
                hi_name, hi_file = resolve_font(FONT_HI_LOGICAL_2, hi_font_path)
            else:
                hi_name, hi_file = ("helv", None)

            # Overlay items (optional)
            overlay_items = None
            if mode in ("overlay","all"):
                if auto_overlay:
                    overlay_items = build_overlay_items_from_doc(src, translate_dir)
                elif mode == "overlay":
                    st.error("Overlay mode requires JSON or enable Auto overlay.")
                    st.stop()

            # Output naming
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            out_name = f"result_{timestamp}.pdf" if mode!="all" else f"result_{timestamp}.all.pdf"
            output_pdf_path = str(workdir / out_name)

            # Run the pipeline
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

            # Collect produced PDFs
            if mode == "all":
                pdfs = sorted(workdir.glob(f"result_{timestamp}.all.*.pdf"))
                zip_display_name = f"result_{timestamp}.all_all_methods.zip"
            else:
                pdfs = [Path(output_pdf_path)] if Path(output_pdf_path).exists() else sorted(workdir.glob(f"result_{timestamp}*.pdf"))
                zip_display_name = f"result_{timestamp}.{mode}.zip"

            if not pdfs:
                st.error("No PDFs produced by the pipeline.")
                all_files = [str(p.relative_to(workdir)) for p in workdir.glob("**/*")]
                st.write("Files in temp workspace:", all_files)
                st.stop()

            # ----------------------------
            # Auto-generate annotation JSON (no upload needed)
            # ----------------------------
            annotated_pdfs = []
            generated_json_bytes = None
            if do_annotate:
                try:
                    # Choose generation mode
                    if annot_method == "Devanagari words":
                        gen_mode = "devanagari_words"
                        pattern = r"[\u0900-\u097F]+"
                    elif annot_method == "English words":
                        gen_mode = "english_words"
                        pattern = r"[A-Za-z]+"
                    elif annot_method == "All text blocks":
                        gen_mode = "all_text_blocks"
                        pattern = ""
                    else:
                        gen_mode = "regex"
                        pattern = custom_regex or r".+"

                    # Generate items from the *produced* PDF you want to annotate.
                    # Here we annotate each produced PDF independently.
                    color = _hex_to_rgb01(annot_color_hex)
                    for p in pdfs:
                        p = Path(p)
                        items = build_annotation_items_from_pdf(
                            pdf_path=str(p),
                            mode=gen_mode,
                            regex_pattern=pattern,
                            min_w=float(min_w),
                            min_h=float(min_h),
                            merge_lines=bool(merge_lines),
                            margin=float(expand_margin),
                        )
                        # Save the JSON (optional, for debugging/user download)
                        gen_json_path = p.with_name(p.stem + ".annotation_items.json")
                        with open(gen_json_path, "w", encoding="utf-8") as jf:
                            json.dump(items, jf, ensure_ascii=False, indent=2)

                        out_annot = p.with_name(p.stem + ".annot.pdf")
                        add_boxes_to_pdf(
                            input_pdf=str(p),
                            items=items,
                            output_pdf=str(out_annot),
                            page_is_one_based=False,
                            color=color,
                            stroke_width=float(annot_stroke_width),
                            fill_opacity=float(annot_fill_opacity),
                            use_annot=(annot_use_annot == "annotation-layer"),
                            fill=bool(annot_fill),
                        )
                        annotated_pdfs.append(out_annot)

                    if annotated_pdfs:
                        zip_display_name = zip_display_name.replace(".zip", ".with_annotations.zip")
                except Exception as e:
                    st.error(f"Failed to auto-generate annotations: {e}")

            # ----------------------------
            # Package results (original + annotated, if any)
            # ----------------------------
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                for p in pdfs:
                    zf.write(p, arcname=Path(p).name)
                for ap in annotated_pdfs:
                    zf.write(ap, arcname=Path(ap).name)
                # also include the JSONs we generated (one per PDF)
                if do_annotate:
                    for p in pdfs:
                        gen_json = Path(p).with_name(Path(p).stem + ".annotation_items.json")
                        if gen_json.exists():
                            zf.write(gen_json, arcname=gen_json.name)
            zip_buf.seek(0)

    st.success("Done!")
    st.download_button(
        "⬇️ Download results (ZIP)",
        data=zip_buf.getvalue(),
        file_name=zip_display_name,
        mime="application/zip"
    )