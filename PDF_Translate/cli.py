import argparse, os
from .constants import DEFAULT_TRANSLATE_DIR, DEFAULT_DPI, DEFAULT_ERASE, DEFAULT_LANG, DEFAULT_OPTIMIZE, FONT_EN_LOGICAL, FONT_EN_PATH, FONT_HI_LOGICAL, FONT_HI_PATH
from .pipeline import run_mode
from .ocr import ocr_fix_pdf
from .overlay import build_overlay_items_from_doc, overlay_load_items
from .utils import build_base, resolve_font
from .textlayer import extract_original_page_objects

# ------------------ CLI ------------------
def main():
    ap = argparse.ArgumentParser(
        description="Unified PDF translator (span/line/block/hybrid/overlay/all) with OCR + style preservation."
    )
    ap.add_argument("--input", "-i", required=True, help="Input PDF path")
    ap.add_argument("--output", "-o", required=True,
                    help="Output PDF path (for 'all' this is the base name)")
    ap.add_argument("--mode", "-m",
                    choices=["span", "line", "block", "hybrid", "overlay", "all"],
                    default="all",
                    help="Translation/paint mode")
    ap.add_argument("--lang", default=DEFAULT_LANG,
                    help="ocrmypdf language (e.g., 'hin+eng')")
    ap.add_argument("--translate", default=DEFAULT_TRANSLATE_DIR,
                    choices=["hi->en", "en->hi", "auto"],
                    help="Translation direction for in-script translation modes")
    ap.add_argument("--dpi", default=DEFAULT_DPI,
                    help="ocrmypdf --image-dpi / --oversample")
    ap.add_argument("--optimize", default=DEFAULT_OPTIMIZE,
                    help="ocrmypdf --optimize level (0-3)")
    ap.add_argument("--erase", choices=["redact", "mask", "none"],
                    default=DEFAULT_ERASE,
                    help="Erase original text before writing/overlay")
    ap.add_argument("--redact-color", default="1,1,1",
                    help="Redaction fill RGB floats, e.g., '1,1,1' for white")

    # Fonts
    ap.add_argument("--font-en-name", default=FONT_EN_LOGICAL)
    ap.add_argument("--font-en-path", default=FONT_EN_PATH)
    ap.add_argument("--font-hi-name", default=FONT_HI_LOGICAL)
    ap.add_argument("--font-hi-path", default=FONT_HI_PATH)

    # OCR control
    ap.add_argument("--skip-ocr", action="store_true",
                    help="Use original PDF without ocrmypdf pass")

    # ---------- OVERLAY-SPECIFIC KNOBS ----------
    ap.add_argument("--overlay-json",
                    help="Path to text_data.json (required for mode=overlay unless --auto-overlay)")
    ap.add_argument("--auto-overlay", action="store_true",
                    help="Auto-build overlay items from the (OCR-fixed) document using --translate")
    ap.add_argument("--overlay-render", choices=["image", "textbox"],
                    default="image", help="How to paint overlay items")
    ap.add_argument("--overlay-align", type=int, default=0, choices=[0, 1, 2, 3],
                    help="Overlay alignment: 0=left, 1=center, 2=right, 3=justify (image mode uses 0/1/2)")
    ap.add_argument("--overlay-line-spacing", type=float, default=1.10,
                    help="Overlay line spacing")
    ap.add_argument("--overlay-margin-px", type=float, default=0.1,
                    help="Inner margin (PDF points) for overlay")
    ap.add_argument("--overlay-target-dpi", type=int, default=600,
                    help="Image overlay DPI (crispness)")

    # Geometry fixes for overlay JSON produced on a slightly different source
    ap.add_argument("--overlay-scale-x", type=float, default=1.0)
    ap.add_argument("--overlay-scale-y", type=float, default=1.0)
    ap.add_argument("--overlay-off-x", type=float, default=0.0)
    ap.add_argument("--overlay-off-y", type=float, default=0.0)

    args = ap.parse_args()

    # ---- parse colors ----
    try:
        redact_rgb = tuple(float(x) for x in args.redact_color.split(","))
    except Exception:
        raise SystemExit("Invalid --redact-color. Expected 'r,g,b' floats in [0,1].")

    # ---- collect original style BEFORE OCR ----
    orig_index = extract_original_page_objects(args.input)

    # ---- OCR-fix (optional) ----
    src_fixed = args.input if args.skip_ocr else ocr_fix_pdf(
        args.input, lang=args.lang, dpi=args.dpi, optimize=args.optimize
    )

    # ---- build base docs (copies background) ----
    src, out = build_base(src_fixed)

    # ---- resolve fonts ----
    en_name, en_file = resolve_font(args.font_en_name, args.font_en_path)
    # If Hindi font path is omitted or missing, fallback to Base14 helv
    if args.font_hi_path:
        hi_name, hi_file = resolve_font(args.font_hi_name, args.font_hi_path)
    else:
        hi_name, hi_file = ("helv", None)

    # ---- overlay items (if needed) ----
    overlay_items = None
    if args.mode in ("overlay", "all"):
        if args.overlay_json and os.path.exists(args.overlay_json):
            overlay_items = overlay_load_items(args.overlay_json)
        elif args.auto_overlay:
            # Build directly from the (possibly OCR-fixed) doc in memory
            overlay_items = build_overlay_items_from_doc(src, args.translate)
        elif args.mode == "overlay":
            raise SystemExit(
                "overlay mode requires --overlay-json or --auto-overlay to supply overlay items."
            )

    # ---- run selected mode ----
    run_mode(
        mode=args.mode,
        src=src, out=out,
        orig_index=orig_index,
        translate_dir=args.translate,
        erase_mode=args.erase,
        redact_color=redact_rgb,
        font_en_name=en_name, font_en_file=en_file,
        font_hi_name=hi_name, font_hi_file=hi_file,
        output_pdf=args.output,
        # overlay knobs
        overlay_items=overlay_items,
        overlay_render=args.overlay_render,
        overlay_align=args.overlay_align,
        overlay_line_spacing=args.overlay_line_spacing,
        overlay_margin_px=args.overlay_margin_px,
        overlay_target_dpi=args.overlay_target_dpi,
        overlay_scale_x=args.overlay_scale_x, overlay_scale_y=args.overlay_scale_y,
        overlay_off_x=args.overlay_off_x, overlay_off_y=args.overlay_off_y,
    )