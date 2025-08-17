from typing import Tuple, List, Dict, Optional, Any
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from .utils import rect_iou, rect_center, _rel_luminance, point_in_rect, _to_rgb, Span, _dominant_script
from .constants import _DEV, _LAT
from .textlayer import extract_spans_from_textlayer, map_block_styles_from_spans, translate_text#,  derive_block_styles_from_spans
from .hybrid import extract_blocks_with_segments
import json, fitz, os, statistics


# ========= JSON overlay helpers (ADD) =========
def overlay_load_items(json_path: str) -> List[Dict[str, Any]]:
    """Load items: requires keys page, bbox, translated_text; fontsize optional."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = []
    for it in data:
        if not {"page", "bbox", "translated_text"} <= set(it.keys()):
            continue
        items.append({
            "page": int(it["page"]),
            "bbox": tuple(float(v) for v in it["bbox"]),
            "text": str(it["translated_text"] or "").strip(),
            "fontsize": float(it.get("fontsize", 11.5)),
        })
    return items

def overlay_transform_rect(b: Tuple[float, float, float, float],
                           scale_x: float = 1.0, scale_y: float = 1.0,
                           off_x: float = 0.0, off_y: float = 0.0) -> fitz.Rect:
    """Optional affine tweak if JSON was produced on a slightly different source."""
    x0, y0, x1, y1 = b
    return fitz.Rect(
        x0 * scale_x + off_x, y0 * scale_y + off_y,
        x1 * scale_x + off_x, y1 * scale_y + off_y
    )

def overlay_choose_fontfile_for_text(txt: str,
                                     font_en_path: Optional[str],
                                     font_hi_path: Optional[str]) -> Optional[str]:
    """Pick a font file by detected script; returns a single TTF path or None."""
    dev = len(_DEV.findall(txt or "")); lat = len(_LAT.findall(txt or ""))
    if dev >= lat:
        return font_hi_path if (font_hi_path and os.path.exists(font_hi_path)) else font_en_path
    else:
        return font_en_path if (font_en_path and os.path.exists(font_en_path)) else font_hi_path

def overlay_draw_text_as_image(page: fitz.Page,
                               rect: fitz.Rect,
                               text: str,
                               base_fontsize_pt: float,
                               fontfile: Optional[str],
                               target_dpi: int = 600,
                               line_spacing: float = 1.10,
                               align: int = 0,          # 0=left,1=center,2=right,3=justify
                               margin_px: float = 0.1) -> None:
    """
    Render text into a high-DPI PNG and place it in rect. Crisp & glyph-safe.
    """
    if not text or rect.is_empty:
        return

    # Compute pixel size from PDF points at target DPI
    W = max(1, int(round(rect.width  / 72.0 * target_dpi)))
    H = max(1, int(round(rect.height / 72.0 * target_dpi)))

    # Canvas
    img_mode = "L"                 # 8-bit gray
    bg_val = 255
    fg_val = 0
    img = Image.new(img_mode, (W, H), bg_val)
    draw = ImageDraw.Draw(img)

    # Font factory
    def make_font(px: int):
        try:
            if fontfile and Path(fontfile).exists():
                return ImageFont.truetype(fontfile, px)
        except Exception:
            pass
        try:
            return ImageFont.truetype("arial.ttf", px)  # best-effort fallback
        except Exception:
            return ImageFont.load_default()

    # Greedy wrap + fit
    def render_with_size(size_px: int) -> Tuple[bool, Optional[Image.Image]]:
        f = make_font(size_px)
        inner_w = max(1, W - int(2 * (margin_px * target_dpi / 72.0)))
        inner_h = max(1, H - int(2 * (margin_px * target_dpi / 72.0)))

        words = text.split()
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if draw.textlength(trial, font=f) <= inner_w:
                cur = trial
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)

        ascent, descent = f.getmetrics()
        lh = max(1, int((ascent + descent) * line_spacing))
        total_h = lh * len(lines)
        if total_h > inner_h:
            return False, None

        canvas = Image.new(img_mode, (W, H), bg_val)
        d = ImageDraw.Draw(canvas)
        y = int(margin_px * target_dpi / 72.0)
        x_left = int(margin_px * target_dpi / 72.0)

        for ln in lines:
            if align == 1:   # center
                ln_w = d.textlength(ln, font=f)
                x = max(0, (W - ln_w) // 2)
            elif align == 2: # right
                ln_w = d.textlength(ln, font=f)
                x = max(0, W - ln_w - x_left)
            else:
                x = x_left
            d.text((x, y), ln, fill=fg_val, font=f)
            y += lh

        return True, canvas

    start_px = max(4, int(round(base_fontsize_pt / 72.0 * target_dpi)))
    lo, hi = 4, max(4, start_px + 3)
    ok, best_img = False, None

    success, tmp = render_with_size(hi)
    if success:
        ok, best_img = True, tmp
    else:
        while hi - lo > 1:
            mid = (lo + hi) // 2
            success, tmp = render_with_size(mid)
            if success:
                ok, best_img = True, tmp
                lo = mid
            else:
                hi = mid
        if not ok:
            success, tmp = render_with_size(lo)
            ok, best_img = success, tmp

    if not ok or best_img is None:
        return

    buf = BytesIO()
    best_img.save(buf, format="PNG", optimize=True)
    stream = buf.getvalue()
    page.insert_image(rect, stream=stream, keep_proportion=False, overlay=True)

def dominant_text_fill_for_rect(pno: int, rect: fitz.Rect, spans_by_page: Dict[int, List[Span]]) -> Tuple[float, float, float]:
    """
    Look at spans under/overlapping rect on this page; choose fill based on their average luminance.
    Fallback to white if nothing found.
    """
    cand = []
    for sp in spans_by_page.get(pno, []):
        if rect_iou(sp.rect, (rect.x0, rect.y0, rect.x1, rect.y1)) > 0.10 or \
           point_in_rect(rect_center(sp.rect), (rect.x0, rect.y0, rect.x1, rect.y1)):
            cand.append(sp.color)
    if not cand:
        return (1.0, 1.0, 1.0)  # safe default

    lum = [_rel_luminance(_to_rgb(c)) for c in cand]
    avgL = sum(lum) / len(lum)
    return (0.0, 0.0, 0.0) if avgL >= 0.85 else (1.0, 1.0, 1.0)

def build_overlay_items_from_doc_v2(doc: fitz.Document,
                                 translate_dir: str) -> List[Dict[str, Any]]:
    """
    Build overlay items (text_data-like dicts) directly from the doc using the
    hybrid block/segment extraction, sampling styles, and translating text.
    Returns a list of dicts with:
      - page
      - bbox (x0,y0,x1,y1)
      - fontsize
      - original_text
      - translated_text
    """
    spans_for_style = extract_spans_from_textlayer(doc)
    hblocks = extract_blocks_with_segments(doc)
    derive_block_styles_from_spans(hblocks, spans_for_style)

    items: List[Dict[str, Any]] = []

    for bl in hblocks:
        if translate_dir in ("hi->en", "en->hi"):
            sl, dl = translate_dir.split("->", 1)
        else:
            # auto
            sl = _dominant_script(bl.text)
            dl = "en" if sl == "hi" else "hi"
            if sl not in ("hi", "en"):
                sl, dl = "hi", "en"

        for ln in bl.lines:
            for seg in ln.segments:
                original = (seg.text or "").strip()
                if not original:
                    continue
                try:
                    base_size = statistics.median(seg.sizes)
                except statistics.StatisticsError:
                    base_size = bl.fontsize or 11.5

                translated = translate_text(original, sl, dl) or ""

                items.append({
                    "page": int(bl.page),
                    "bbox": [float(seg.rect[0]), float(seg.rect[1]),
                             float(seg.rect[2]), float(seg.rect[3])],
                    "fontsize": float(base_size),
                    "original_text": original,
                    "translated_text": translated,
                })
    return items


def build_overlay_items_from_doc(doc: fitz.Document,
                                 translate_direction: str) -> List[Dict[str, Any]]:

    # 1) Extract structure and sample styles
    spans_for_style = extract_spans_from_textlayer(doc)
    blocks = extract_blocks_with_segments(doc)
    map_block_styles_from_spans(blocks, spans_for_style)

    items: List[Dict[str, Any]] = []

    # 2) Iterate blocks/segments and translate per 'translate_direction'
    for bl in blocks:
        # decide language direction (block-level is stable)
        if translate_direction in ("hi->en", "en->hi"):
            sl, dl = translate_direction.split("->", 1)
        else:
            # auto: infer from this block's text
            sl_guess = _dominant_script(bl.text or "")
            if   sl_guess == "hi": sl, dl = "hi", "en"
            elif sl_guess == "en": sl, dl = "en", "hi"
            else:                  sl, dl = "hi", "en"

        for ln in bl.lines:
            for seg in ln.segments:
                original = (seg.text or "").strip()
                if not original:
                    continue

                # fontsize for this area
                try:
                    base_size = statistics.median(seg.sizes)
                except statistics.StatisticsError:
                    base_size = bl.fontsize or 11.5

                translated = translate_text(original, sl, dl) or ""

                items.append({
                    "page": int(bl.page),
                    "bbox": (
                        float(seg.rect[0]), float(seg.rect[1]),
                        float(seg.rect[2]), float(seg.rect[3])
                    ),
                    "fontsize": float(base_size),
                    "original_text": original,
                    "translated_text": translated,
                    "text": translated,  # convenient alias for overlay drawers
                })
    return items