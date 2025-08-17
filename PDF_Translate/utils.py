from dataclasses import dataclass
from typing import Any, Tuple, List, Optional
import fitz, os
from pathlib import Path

from .constants import _LAT, _DEV

# ------------------ dataclasses ------------------
@dataclass
class Span:
    page: int
    rect: Tuple[float, float, float, float]
    text: str
    fontsize: float
    color: Tuple[float, ...]

@dataclass
class Line:
    page: int
    rect: Tuple[float, float, float, float]
    text: str
    fontsize: float
    color: Tuple[float, ...]

@dataclass
class Block:
    page: int
    rect: Tuple[float, float, float, float]
    text: str
    fontsize: float
    color: Tuple[float, ...]

def normalize_color(c: Any) -> Tuple[float, ...]:
    if c is None: return (0.0,)
    if isinstance(c, int):
        r = (c >> 16) & 255; g = (c >> 8) & 255; b = c & 255
        return (r/255.0, g/255.0, b/255.0)
    if isinstance(c, str):
        s = c.strip().lstrip("#")
        if len(s) == 6:
            r = int(s[0:2], 16); g = int(s[2:4], 16); b = int(s[4:6], 16)
            return (r/255.0, g/255.0, b/255.0)
        return (0.0,)
    if isinstance(c, (list, tuple)):
        vals = tuple(float(v) for v in c)
        if any(v > 1.0 for v in vals): vals = tuple(v/255.0 for v in vals)
        if len(vals) in (1,3,4): return tuple(max(0.0, min(1.0, v)) for v in vals)
        return (0.0,)
    return (0.0,)

def rect_iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a; bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    w, h = max(0.0, ix1-ix0), max(0.0, iy1-iy0)
    inter = w*h
    if inter <= 0: return 0.0
    area_a = (ax1-ax0)*(ay1-ay0); area_b = (bx1-bx0)*(by1-by0)
    union = max(1e-9, area_a + area_b - inter)
    return inter/union

def rect_center(r): x0,y0,x1,y1 = r; return ((x0+x1)/2.0, (y0+y1)/2.0)

def point_in_rect(pt, r): x,y=pt; x0,y0,x1,y1=r; return (x0<=x<=x1) and (y0<=y<=y1)

def center_dist(a,b):
    cx,cy=rect_center(a); dx,dy=rect_center(b)
    return ((cx-dx)**2 + (cy-dy)**2)**0.5

def _to_rgb(color: Tuple[float, ...]) -> Tuple[float, float, float]:
    """Normalize 1/3/4-tuple colors into RGB (0..1)."""
    if not color:
        return (0.0, 0.0, 0.0)
    if len(color) == 1:
        v = float(color[0])
        return (v, v, v)
    r = float(color[0]); g = float(color[1]); b = float(color[2])
    return (max(0.0, min(1.0, r)),
            max(0.0, min(1.0, g)),
            max(0.0, min(1.0, b)))

def _rel_luminance(rgb: Tuple[float, float, float]) -> float:
    """Relative luminance (sRGB-ish weights)."""
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def pick_redact_fill_for_color(color: Tuple[float, ...]) -> Tuple[float, float, float]:
    """
    If text is very light (close to white), redact with black; else white.
    Threshold 0.85 works well for PDFs.
    """
    L = _rel_luminance(_to_rgb(color))
    return (0.0, 0.0, 0.0) if L >= 0.85 else (1.0, 1.0, 1.0)

def _dominant_script(text: str) -> str:
    dev = len(_DEV.findall(text or "")); lat = len(_LAT.findall(text or ""))
    if dev > lat: return "hi"
    if lat > dev: return "en"
    return "auto"

def build_base(src_pdf: str) -> Tuple[fitz.Document, fitz.Document]:
    src = fitz.open(src_pdf); out = fitz.open()
    for p in range(len(src)):
        po = out.new_page(width=src[p].rect.width, height=src[p].rect.height)
        po.show_pdf_page(po.rect, src, p)
    return src, out

def choose_langs(text: str, translate_dir: str) -> Tuple[str,str]:
    if translate_dir == "hi->en": return "hi","en"
    if translate_dir == "en->hi": return "en","hi"
    sl = _dominant_script(text)
    if sl == "hi": return "hi","en"
    if sl == "en": return "en","hi"
    return "hi","en"

def insert_text_fit(page: fitz.Page, rect, text: str, fontname: str,
                    base_size: float, color: Tuple[float, ...],
                    fontfile: Optional[str] = None,
                    pad_px: Optional[float] = None,
                    debug_outline: bool = False) -> bool:
    r = fitz.Rect(*rect)
    if pad_px is None: pad_px = max(1.2, 0.20 * base_size)
    r = fitz.Rect(r.x0 - pad_px, r.y0 - pad_px, r.x1 + pad_px, r.y1 + pad_px)
    if debug_outline:
        sh = page.new_shape(); sh.draw_rect(r)
        sh.finish(width=0, color=None, fill=(1,0,0)); sh.commit(overlay=True)
    for pct in (100,98,96,92,88,85,80,76,72,68,64,60,56,52,48,44,40,36,32,28,24,20,18,16,14,12,10,8,4,2):
        fs = max(6.0, base_size*(pct/100.0))
        rv = page.insert_textbox(
            r, text, fontname=fontname, fontfile=fontfile, fontsize=fs,
            lineheight=fs*1.12, color=color, align=fitz.TEXT_ALIGN_LEFT, encoding=0
        )
        if rv is not None and rv >= 0: return True
    page.insert_text(r.bl, text, fontname=fontname, fontfile=fontfile, fontsize=base_size, color=color, encoding=0)
    return False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets" / "fonts"

def resolve_font(logical_name, font_path=None):
    BASE14_SHORT = {"helv","times","cour","symbol","zapfdingbats"}
    if logical_name in BASE14_SHORT:
        return logical_name, None
    if not font_path:
        font_path = ASSETS_DIR / f"{logical_name}-Regular.ttf"
    if not os.path.exists(font_path):
        raise ValueError(f"Font '{logical_name}' needs a valid font file. Got: {font_path}")
    return logical_name, str(font_path)

def redact_page_regions(page: fitz.Page, rects: List[fitz.Rect], fill=(1,1,1)):
    for rr in rects: page.add_redact_annot(rr, fill=fill)
    page.apply_redactions()
