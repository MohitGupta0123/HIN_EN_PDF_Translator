from typing import Tuple, List, Dict, Any
import statistics, asyncio, nest_asyncio, fitz, re

nest_asyncio.apply()

from .utils import normalize_color, Span, Line, Block, rect_iou, rect_center, point_in_rect, center_dist
from .constants import _TR

def translate_text(text: str, src: str, dest: str) -> str:
    try:
        res = _TR.translate(text, src=src, dest=dest)
        if asyncio.iscoroutine(res):
            loop = asyncio.get_event_loop(); res = loop.run_until_complete(res)
        out = getattr(res, "text", text)
        # normalize whitespace and avoid spaces before punctuation/danda
        out = "\n".join(" ".join(line.split()) for line in out.splitlines())
        out = re.sub(r"\s+([,.;:!?\u0964])", r"\1", out)
        return out
    except Exception as e:
        print(f"[translate] {type(e).__name__}: {e}"); return text

# ------------------ original style extraction ------------------
def extract_original_page_objects(input_pdf: str) -> Dict[int, List[Dict[str, Any]]]:
    doc = fitz.open(input_pdf); per_page: Dict[int, List[Dict[str, Any]]] = {}
    for page_num, page in enumerate(doc):
        arr = per_page.setdefault(page_num, [])
        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block: continue
            for line in block["lines"]:
                for span in line["spans"]:
                    bbox = span.get("bbox")
                    if not bbox: continue
                    arr.append({
                        "bbox": tuple(map(float, bbox)),
                        "color": normalize_color(span.get("color", (0,0,0)) ),
                        "size": float(span.get("size", 10.0)),
                    })
    doc.close(); return per_page

def transfer_color_size_from_original(spans: List[Span],
                                      orig_index: Dict[int, List[Dict[str, Any]]],
                                      iou_hi: float = 0.80,
                                      iou_lo: float = 0.10) -> None:
    for sp in spans:
        candidates = orig_index.get(sp.page, [])
        if not candidates: continue
        best_iou = -1.0; best = None
        for cand in candidates:
            iou = rect_iou(sp.rect, cand["bbox"])
            if iou > best_iou: best_iou = iou; best = cand
        if best and best_iou >= iou_hi:
            sp.color = best["color"]; sp.fontsize = best["size"]; continue
        cx, cy = rect_center(sp.rect)
        inside = [c for c in candidates if point_in_rect((cx,cy), c["bbox"])]
        if inside:
            spec = min(inside, key=lambda c: (c["bbox"][2]-c["bbox"][0])*(c["bbox"][3]-c["bbox"][1]))
            sp.color = spec["color"]; sp.fontsize = spec["size"]; continue
        if best and best_iou >= iou_lo:
            sp.color = best["color"]; sp.fontsize = best["size"]; continue
        nearest = min(candidates, key=lambda c: center_dist(sp.rect, c["bbox"]))
        sp.color = nearest["color"]; sp.fontsize = nearest["size"]

# ------------------ textlayer extractors ------------------
def _rawdict(page: fitz.Page):
    try:
        PRES = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES
        return page.get_textpage(flags=PRES).extractRAWDICT()
    except Exception:
        return page.get_text("rawdict")

def extract_spans_from_textlayer(doc: fitz.Document) -> List[Span]:
    spans: List[Span] = []
    for pno in range(len(doc)):
        raw = _rawdict(doc[pno])
        for b in raw.get("blocks", []):
            if "lines" not in b: continue
            block_bbox = tuple(b.get("bbox", (0,0,0,0)))
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    # text
                    if isinstance(sp.get("text"), str) and sp["text"].strip():
                        t = " ".join(sp["text"].split())
                    else:
                        chars = sp.get("chars") or []
                        t = "".join(ch.get("c","") for ch in chars).strip()
                    if not t: continue
                    # bbox
                    if sp.get("bbox"): bb = tuple(map(float, sp["bbox"]))
                    else:
                        chars = sp.get("chars") or []
                        if chars:
                            xs0=[c["bbox"][0] for c in chars if "bbox" in c]
                            ys0=[c["bbox"][1] for c in chars if "bbox" in c]
                            xs1=[c["bbox"][2] for c in chars if "bbox" in c]
                            ys1=[c["bbox"][3] for c in chars if "bbox" in c]
                            bb = (min(xs0),min(ys0),max(xs1),max(ys1)) if xs0 else tuple(map(float, block_bbox))
                        else:
                            bb = tuple(map(float, block_bbox))
                    size = float(sp.get("size", 11.5))
                    color = normalize_color(sp.get("color", (0,0,0)))
                    spans.append(Span(pno, (bb[0],bb[1],bb[2],bb[3]), t, size, color))
    return spans

def extract_lines_from_textlayer(doc: fitz.Document) -> List[Line]:
    lines: List[Line] = []
    for pno in range(len(doc)):
        raw = _rawdict(doc[pno])
        for b in raw.get("blocks", []):
            if "lines" not in b: continue
            block_bbox = tuple(b.get("bbox", (0,0,0,0)))
            for ln in b.get("lines", []):
                spans = ln.get("spans", [])
                if not spans: continue
                txts, rects, sizes = [], [], []
                for sp in spans:
                    if isinstance(sp.get("text"), str) and sp["text"].strip():
                        t = " ".join(sp["text"].split()); bb = tuple(map(float, sp.get("bbox", block_bbox)))
                    else:
                        chars = sp.get("chars") or []
                        t = "".join(ch.get("c","") for ch in chars).strip()
                        if chars:
                            xs0=[c["bbox"][0] for c in chars if "bbox" in c]
                            ys0=[c["bbox"][1] for c in chars if "bbox" in c]
                            xs1=[c["bbox"][2] for c in chars if "bbox" in c]
                            ys1=[c["bbox"][3] for c in chars if "bbox" in c]
                            bb = (min(xs0),min(ys0),max(xs1),max(ys1)) if xs0 else tuple(map(float, sp.get("bbox", block_bbox)))
                        else:
                            bb = tuple(map(float, sp.get("bbox", block_bbox)))
                    if t: txts.append(t)
                    rects.append(bb); sizes.append(float(sp.get("size", 11.5)))
                line_text = " ".join(" ".join(txts).split())
                if not line_text: continue
                x0=min(r[0] for r in rects); y0=min(r[1] for r in rects)
                x1=max(r[2] for r in rects); y1=max(r[3] for r in rects)
                avg_size = sum(sizes)/max(1, len(sizes))
                lines.append(Line(pno, (x0,y0,x1,y1), line_text, avg_size, (0.0,)))
    return lines

def extract_blocks_from_textlayer(doc: fitz.Document) -> List[Block]:
    blocks: List[Block] = []
    for pno in range(len(doc)):
        raw = _rawdict(doc[pno])
        for b in raw.get("blocks", []):
            if "lines" not in b: continue
            block_rects: List[Tuple[float,float,float,float]] = []
            block_text_lines: List[str] = []; sizes: List[float] = []
            for ln in b.get("lines", []):
                line_txts, line_rects, line_sizes = [], [], []
                for sp in ln.get("spans", []):
                    if isinstance(sp.get("text"), str) and sp["text"].strip():
                        t = " ".join(sp["text"].split())
                        bb = tuple(map(float, sp.get("bbox", b.get("bbox",(0,0,0,0)))))
                    else:
                        chars = sp.get("chars") or []
                        t = "".join(ch.get("c","") for ch in chars).strip()
                        if chars:
                            xs0=[c["bbox"][0] for c in chars if "bbox" in c]
                            ys0=[c["bbox"][1] for c in chars if "bbox" in c]
                            xs1=[c["bbox"][2] for c in chars if "bbox" in c]
                            ys1=[c["bbox"][3] for c in chars if "bbox" in c]
                            bb = (min(xs0),min(ys0),max(xs1),max(ys1)) if xs0 else tuple(map(float, b.get("bbox",(0,0,0,0))))
                        else:
                            bb = tuple(map(float, b.get("bbox",(0,0,0,0))))
                    if t: line_txts.append(t)
                    line_rects.append(bb); line_sizes.append(float(sp.get("size",11.5)))
                if line_txts: block_text_lines.append(" ".join(line_txts))
                block_rects.extend(line_rects); sizes.extend(line_sizes)
            if not block_text_lines or not block_rects: continue
            x0=min(r[0] for r in block_rects); y0=min(r[1] for r in block_rects)
            x1=max(r[2] for r in block_rects); y1=max(r[3] for r in block_rects)
            try: avg_size = statistics.median(sizes)
            except statistics.StatisticsError: avg_size = sizes[0] if sizes else 11.5
            text = "\n".join(block_text_lines).strip()
            blocks.append(Block(pno, (x0,y0,x1,y1), text, avg_size, (0.0,)))
    return blocks

def derive_line_styles_from_spans(lines: List[Line], spans: List[Span]) -> None:
    spans_by_page: Dict[int, List[Span]] = {}
    for sp in spans: spans_by_page.setdefault(sp.page, []).append(sp)
    for ln in lines:
        sps = [sp for sp in spans_by_page.get(ln.page, [])
               if rect_iou(ln.rect, sp.rect) > 0.5 or point_in_rect(rect_center(sp.rect), ln.rect)]
        if not sps: continue
        sizes = [sp.fontsize for sp in sps]
        try: ln.fontsize = statistics.median(sizes)
        except statistics.StatisticsError: ln.fontsize = sizes[0]
        color_counts: Dict[Tuple[float, ...], int] = {}
        for sp in sps: color_counts[sp.color] = color_counts.get(sp.color, 0) + 1
        ln.color = max(color_counts.items(), key=lambda kv: kv[1])[0]

def derive_block_styles_from_spans(blocks: List[Block], spans: List[Span]) -> None:
    spans_by_page: Dict[int, List[Span]] = {}
    for sp in spans: spans_by_page.setdefault(sp.page, []).append(sp)
    for bl in blocks:
        sps = [sp for sp in spans_by_page.get(bl.page, [])
               if rect_iou(bl.rect, sp.rect) > 0.4 or point_in_rect(rect_center(sp.rect), bl.rect)]
        if not sps: continue
        sizes = [sp.fontsize for sp in sps]
        try: bl.fontsize = statistics.median(sizes)
        except statistics.StatisticsError: bl.fontsize = sizes[0]
        color_counts: Dict[Tuple[float, ...], int] = {}
        for sp in sps: color_counts[sp.color] = color_counts.get(sp.color, 0) + 1
        bl.color = max(color_counts.items(), key=lambda kv: kv[1])[0]

def map_block_styles_from_spans(blocks: List[Block], spans: List[Span]) -> None:
    spans_by_page: Dict[int, List[Span]] = {}
    for sp in spans:
        spans_by_page.setdefault(sp.page, []).append(sp)

    for bl in blocks:
        sps = [sp for sp in spans_by_page.get(bl.page, [])
               if (max(0.0, min(bl.rect[2], sp.rect[2]) - max(bl.rect[0], sp.rect[0])) *
                   max(0.0, min(bl.rect[3], sp.rect[3]) - max(bl.rect[1], sp.rect[1]))) > 0]
        if not sps: 
            continue
        sizes = [sp.fontsize for sp in sps]
        try:
            bl.fontsize = statistics.median(sizes)
        except statistics.StatisticsError:
            bl.fontsize = sizes[0]
        color_counts: Dict[Tuple[float, ...], int] = {}
        for sp in sps:
            color_counts[sp.color] = color_counts.get(sp.color, 0) + 1
        bl.color = max(color_counts.items(), key=lambda kv: kv[1])[0]