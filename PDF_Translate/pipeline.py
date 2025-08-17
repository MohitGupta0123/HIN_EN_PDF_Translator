from typing import List, Tuple, Dict, Optional, Any
import fitz, os, zipfile, statistics
from .utils import Span, pick_redact_fill_for_color, insert_text_fit, _dominant_script
from .constants import _DEV
from .textlayer import extract_blocks_from_textlayer, extract_lines_from_textlayer, extract_spans_from_textlayer, derive_line_styles_from_spans, derive_block_styles_from_spans, transfer_color_size_from_original, translate_text
from .overlay import overlay_choose_fontfile_for_text, overlay_draw_text_as_image, overlay_transform_rect, dominant_text_fill_for_rect
from .hybrid import extract_blocks_with_segments, is_table_like, build_columns

def erase_original_text(out_doc: fitz.Document, spans: List[Span], mode: str, erase_mode: str, _unused_fill):
    """
    Dynamic per-span fill:
      - if span text color is light -> redact black
      - else -> redact white
    """
    if erase_mode not in ("mask", "redact"):
        return

    spans_by_page: Dict[int, List[Span]] = {}
    for sp in spans:
        spans_by_page.setdefault(sp.page, []).append(sp)

    for pno, sps in spans_by_page.items():
        page = out_doc[pno]
        if erase_mode == "mask":
            for sp in sps:
                pad = max(1.0, 0.18 * sp.fontsize)
                r = fitz.Rect(*sp.rect)
                r = fitz.Rect(r.x0 - pad, r.y0 - pad, r.x1 + pad, r.y1 + pad) & page.rect
                if r.is_empty:
                    continue
                fill = pick_redact_fill_for_color(sp.color)
                page.draw_rect(r, color=None, fill=fill, overlay=True, width=0)
        else:
            added_any = False
            for sp in sps:
                pad = max(1.0, 0.18 * sp.fontsize)
                r = fitz.Rect(*sp.rect)
                r = fitz.Rect(r.x0 - pad, r.y0 - pad, r.x1 + pad, r.y1 + pad) & page.rect
                if r.is_empty:
                    continue
                fill = pick_redact_fill_for_color(sp.color)
                page.add_redact_annot(r, fill=fill)
                added_any = True
            if added_any:
                try:
                    page.apply_redactions()
                except Exception as e:
                    print(f"[page {pno}] apply_redactions error: {e}")

def run_mode(mode: str, src: fitz.Document, out: fitz.Document,
             orig_index: Dict[int, List[Dict[str, Any]]],
             translate_dir: str,
             erase_mode: str, redact_color: Tuple[float,...],
             font_en_name: str, font_en_file: Optional[str],
             font_hi_name: str, font_hi_file: Optional[str],
             output_pdf: str,
             # ----- overlay parameters -----
             overlay_items: Optional[List[Dict[str, Any]]] = None,
             overlay_render: str = "image",     # "image" | "textbox"
             overlay_align: int = 0,
             overlay_line_spacing: float = 1.10,
             overlay_margin_px: float = 0.1,
             overlay_target_dpi: int = 600,
             overlay_scale_x: float = 1.0, overlay_scale_y: float = 1.0,
             overlay_off_x: float = 0.0, overlay_off_y: float = 0.0) -> None:
    """
    - span/line/block/hybrid: style-preserving translation and draw.
    - overlay: paint from prebuilt JSON items.
    - all: run span, line, block, hybrid, and (if provided) overlay; zip results.
    """

    # ======================= "ALL" MODE =======================
    if mode == "all":
        src_path = getattr(src, "name", None)
        if not src_path or not os.path.exists(src_path):
            raise ValueError("all mode requires 'src' to come from a real file (src.name must exist).")

        try:
            out.close()
        except Exception:
            pass
        try:
            src.close()
        except Exception:
            pass

        base, ext = os.path.splitext(output_pdf)
        out_files: List[Tuple[str, str]] = []

        def _make_output(label: str) -> str:
            return f"{base}.{label}{ext}"

        def _fresh_src_out() -> Tuple[fitz.Document, fitz.Document]:
            s = fitz.open(src_path)
            o = fitz.open()
            for p in range(len(s)):
                po = o.new_page(width=s[p].rect.width, height=s[p].rect.height)
                po.show_pdf_page(po.rect, s, p)
            return s, o

        for sub_mode in ("span", "line", "block", "hybrid"):
            try:
                s, o = _fresh_src_out()
                run_mode(
                    mode=sub_mode, src=s, out=o,
                    orig_index=orig_index, translate_dir=translate_dir,
                    erase_mode=erase_mode, redact_color=redact_color,
                    font_en_name=font_en_name, font_en_file=font_en_file,
                    font_hi_name=font_hi_name, font_hi_file=font_hi_file,
                    output_pdf=_make_output(sub_mode),
                )
                out_files.append((sub_mode, _make_output(sub_mode)))
            except Exception as e:
                print(f"[WARN] {sub_mode} failed: {e}")

        if overlay_items:
            try:
                s, o = _fresh_src_out()
                run_mode(
                    mode="overlay", src=s, out=o,
                    orig_index=orig_index, translate_dir=translate_dir,
                    erase_mode=erase_mode, redact_color=redact_color,
                    font_en_name=font_en_name, font_en_file=font_en_file,
                    font_hi_name=font_hi_name, font_hi_file=font_hi_file,
                    output_pdf=_make_output("overlay"),
                    overlay_items=overlay_items, overlay_render=overlay_render,
                    overlay_align=overlay_align, overlay_line_spacing=overlay_line_spacing,
                    overlay_margin_px=overlay_margin_px, overlay_target_dpi=overlay_target_dpi,
                    overlay_scale_x=overlay_scale_x, overlay_scale_y=overlay_scale_y,
                    overlay_off_x=overlay_off_x, overlay_off_y=overlay_off_y,
                )
                out_files.append(("overlay", _make_output("overlay")))
            except Exception as e:
                print(f"[WARN] overlay failed: {e}")
        else:
            print("[info] overlay skipped in 'all' mode (no overlay_items provided).")

        zip_path = f"{base}_all_methods.zip"
        os.makedirs(os.path.dirname(zip_path) or ".", exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for label, path in out_files:
                if os.path.exists(path):
                    arc = os.path.basename(path)
                    zf.write(path, arcname=arc)
                else:
                    print(f"[WARN] missing output for {label}: {path}")

        print(f"[OK] Wrote {len(out_files)} PDFs and zipped -> {zip_path}")
        return

    # --------- Shared: spans (for style/erase in non-overlay modes) ----------
    spans = extract_spans_from_textlayer(src)
    transfer_color_size_from_original(spans, orig_index)

    # ======================= OVERLAY MODE =======================
    if mode == "overlay":
        if not overlay_items:
            raise ValueError("overlay mode requires overlay_items (use overlay_load_items on your JSON).")

        if erase_mode in ("mask", "redact"):
            spans_by_page: Dict[int, List[Span]] = {}
            for sp in spans:
                spans_by_page.setdefault(sp.page, []).append(sp)

            redacted_pages = set()
            for it in overlay_items:
                pno = int(it["page"])
                if pno < 0 or pno >= len(out):
                    continue
                page = out[pno]
                r = overlay_transform_rect(
                    it["bbox"], scale_x=overlay_scale_x, scale_y=overlay_scale_y,
                    off_x=overlay_off_x, off_y=overlay_off_y
                ) & page.rect
                if r.is_empty:
                    continue

                fill = dominant_text_fill_for_rect(pno, r, spans_by_page)

                if erase_mode == "mask":
                    page.draw_rect(r, color=None, fill=fill, overlay=True, width=0)
                else:
                    page.add_redact_annot(r, fill=fill)
                    redacted_pages.add(pno)

            if erase_mode == "redact":
                for pno in redacted_pages:
                    try:
                        out[pno].apply_redactions()
                    except Exception as e:
                        print(f"[page {pno}] apply_redactions error: {e}")

        # Draw each overlay item (image or textbox)
        for it in overlay_items:
            pno = int(it["page"])
            if pno < 0 or pno >= len(out):
                continue
            page = out[pno]
            rect = overlay_transform_rect(
                it["bbox"], scale_x=overlay_scale_x, scale_y=overlay_scale_y,
                off_x=overlay_off_x, off_y=overlay_off_y
            )
            if rect.is_empty:
                continue
            text = it.get("text", "") or it.get("translated_text", "") or ""
            base_fs = float(it.get("fontsize", 11.5))

            fontfile = overlay_choose_fontfile_for_text(text, font_en_file, font_hi_file)

            if overlay_render == "image":
                overlay_draw_text_as_image(
                    page, rect, text, base_fs, fontfile,
                    target_dpi=overlay_target_dpi,
                    line_spacing=overlay_line_spacing,
                    align=overlay_align,
                    margin_px=overlay_margin_px,
                )
            else:
                # Real text (keeps text layer). Choose fontname logically by script, but feed fontfile.
                if _DEV.search(text or ""):
                    fname, ffile = font_hi_name, font_hi_file
                else:
                    fname, ffile = font_en_name, font_en_file
                insert_text_fit(
                    page, (rect.x0, rect.y0, rect.x1, rect.y1),
                    text, fname, base_fs, (0.0,), fontfile=ffile
                )

        # Save & close
        os.makedirs(os.path.dirname(output_pdf) or ".", exist_ok=True)
        out.save(output_pdf); out.close(); src.close()
        print(f"[OK] Wrote translated PDF to: {output_pdf}")
        return

    if mode == "hybrid":
        hblocks = extract_blocks_with_segments(src)
        derive_block_styles_from_spans(hblocks, spans)

        # ---- ERASE: dynamic fill, supports both overlay_items and block fallback ----
        if erase_mode in ("mask", "redact"):
            spans_by_page: Dict[int, List[Span]] = {}
            for sp in spans:
                spans_by_page.setdefault(sp.page, []).append(sp)

            redacted_pages = set()

            def _erase_rect(pno: int, r: fitz.Rect, pad_pt: float):
                page = out[pno]
                rr = fitz.Rect(r.x0 - pad_pt, r.y0 - pad_pt, r.x1 + pad_pt, r.y1 + pad_pt) & page.rect
                if rr.is_empty:
                    return
                fill = dominant_text_fill_for_rect(pno, rr, spans_by_page)
                if erase_mode == "mask":
                    page.draw_rect(rr, color=None, fill=fill, overlay=True, width=0)
                else:
                    page.add_redact_annot(rr, fill=fill)
                    redacted_pages.add(pno)

            if overlay_items:
                for it in overlay_items:
                    pno = int(it["page"])
                    if not (0 <= pno < len(out)):
                        continue
                    rect = overlay_transform_rect(
                        it["bbox"],
                        scale_x=overlay_scale_x, scale_y=overlay_scale_y,
                        off_x=overlay_off_x, off_y=overlay_off_y
                    )
                    base_fs = float(it.get("fontsize", 11.5))
                    pad = max(1.0, 0.18 * base_fs)
                    _erase_rect(pno, rect, pad)
            else:
                for bl in hblocks:
                    pno = bl.page
                    rect = fitz.Rect(*bl.rect)
                    pad = max(1.0, 0.18 * (bl.fontsize or 11.5))
                    _erase_rect(pno, rect, pad)

            if erase_mode == "redact":
                for pno in redacted_pages:
                    try:
                        out[pno].apply_redactions()
                    except Exception as e:
                        print(f"[page {pno}] apply_redactions error: {e}")

        for bl in hblocks:
            if translate_dir == "hi->en":
                sl, dl = "hi", "en"
            elif translate_dir == "en->hi":
                sl, dl = "en", "hi"
            else:
                sl = _dominant_script(bl.text); dl = "en" if sl == "hi" else "hi"
                if sl not in ("hi", "en"): sl, dl = "hi", "en"

            page = out[bl.page]
            if is_table_like(bl):
                cols = build_columns(bl)
                for ln in bl.lines:
                    y0, y1 = ln.rect[1], ln.rect[3]
                    for seg in ln.segments:
                        text_out = translate_text(seg.text, sl, dl) or ""
                        if text_out and _DEV.search(text_out):
                            fname, ffile = font_hi_name, font_hi_file
                        else:
                            fname, ffile = font_en_name, font_en_file
                        try:
                            base_size = statistics.median(seg.sizes)
                        except statistics.StatisticsError:
                            base_size = bl.fontsize
                        color = bl.color
                        best_col = max(
                            cols,
                            key=lambda c: max(0.0, min(seg.rect[2], c[1]) - max(seg.rect[0], c[0]))
                        )
                        cell_rect = (best_col[0], y0, best_col[1], y1)
                        insert_text_fit(page, cell_rect, text_out, fname, base_size, color, fontfile=ffile)
            else:
                text_out = translate_text(bl.text, sl, dl) or ""
                if text_out and _DEV.search(text_out):
                    fname, ffile = font_hi_name, font_hi_file
                else:
                    fname, ffile = font_en_name, font_en_file
                insert_text_fit(page, bl.rect, text_out, fname, bl.fontsize, bl.color, fontfile=ffile)

        os.makedirs(os.path.dirname(output_pdf) or ".", exist_ok=True)
        out.save(output_pdf); out.close(); src.close()
        print(f"[OK] Wrote translated PDF to: {output_pdf}")
        return

    erase_original_text(out, spans, mode, erase_mode, redact_color)

    if mode == "span":
        for sp in spans:
            if translate_dir == "hi->en": sl, dl = "hi","en"
            elif translate_dir == "en->hi": sl, dl = "en","hi"
            else:
                sl = _dominant_script(sp.text); dl = "en" if sl=="hi" else "hi"
                if sl not in ("hi","en"): sl, dl = "hi","en"
            text_out = translate_text(sp.text, sl, dl) or ""
            page = out[sp.page]
            if text_out and _DEV.search(text_out): fname, ffile = font_hi_name, font_hi_file
            else:                                   fname, ffile = font_en_name, font_en_file
            insert_text_fit(page, sp.rect, text_out, fname, sp.fontsize, sp.color, fontfile=ffile)

    elif mode == "line":
        lines = extract_lines_from_textlayer(src)
        derive_line_styles_from_spans(lines, spans)
        for ln in lines:
            if translate_dir == "hi->en": sl, dl = "hi","en"
            elif translate_dir == "en->hi": sl, dl = "en","hi"
            else:
                sl = _dominant_script(ln.text); dl = "en" if sl=="hi" else "hi"
                if sl not in ("hi","en"): sl, dl = "hi","en"
            text_out = translate_text(ln.text, sl, dl) or ""
            page = out[ln.page]
            if text_out and _DEV.search(text_out): fname, ffile = font_hi_name, font_hi_file
            else:                                   fname, ffile = font_en_name, font_en_file
            base_size = ln.fontsize if ln.fontsize else 11.5
            color     = ln.color if ln.color else (0.0,)
            insert_text_fit(page, ln.rect, text_out, fname, base_size, color, fontfile=ffile)

    elif mode == "block":
        blocks = extract_blocks_from_textlayer(src)
        derive_block_styles_from_spans(blocks, spans)
        for bl in blocks:
            if translate_dir == "hi->en": sl, dl = "hi","en"
            elif translate_dir == "en->hi": sl, dl = "en","hi"
            else:
                sl = _dominant_script(bl.text); dl = "en" if sl=="hi" else "hi"
                if sl not in ("hi","en"): sl, dl = "hi","en"
            text_out = translate_text(bl.text, sl, dl) or ""
            page = out[bl.page]
            if text_out and _DEV.search(text_out): fname, ffile = font_hi_name, font_hi_file
            else:                                   fname, ffile = font_en_name, font_en_file
            base_size = bl.fontsize if bl.fontsize else 11.5
            color     = bl.color if bl.color else (0.0,)
            insert_text_fit(page, bl.rect, text_out, fname, base_size, color, fontfile=ffile)

    else:
        raise ValueError(f"Unknown mode: {mode}")

    os.makedirs(os.path.dirname(output_pdf) or ".", exist_ok=True)
    out.save(output_pdf); out.close(); src.close()
    print(f"[OK] Wrote translated PDF to: {output_pdf}")