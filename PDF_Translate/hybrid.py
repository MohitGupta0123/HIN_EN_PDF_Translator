from dataclasses import dataclass
from typing import List, Tuple
import fitz

@dataclass
class HybridSegment:
    rect: Tuple[float, float, float, float]
    text: str
    sizes: List[float]

@dataclass
class HybridLine:
    rect: Tuple[float, float, float, float]
    text: str
    segments: List[HybridSegment]

@dataclass
class HybridBlock:
    page: int
    rect: Tuple[float, float, float, float]
    lines: List[HybridLine]
    text: str
    fontsize: float = 11.5
    color: Tuple[float, ...] = (0.0,)

def extract_blocks_with_segments(doc: fitz.Document) -> List[HybridBlock]:
    """
    One HybridBlock per raw PDF block. Each raw line is split into column/cell-like
    segments by large x-gaps so we can place translated text per cell.
    """
    blocks: List[HybridBlock] = []
    try:
        PRES = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES
        getter = lambda p: p.get_textpage(flags=PRES).extractRAWDICT()
    except Exception:
        getter = lambda p: p.get_text("rawdict")

    for pno in range(len(doc)):
        raw = getter(doc[pno])
        for b in raw.get("blocks", []):
            if "lines" not in b: 
                continue
            brect = tuple(map(float, b.get("bbox", (0, 0, 0, 0))))
            lines: List[HybridLine] = []
            block_text_lines: List[str] = []

            bw = max(1.0, brect[2] - brect[0])
            SEG_GAP = max(10.0, 0.12 * bw)  # 12% of block width or 10 px

            for ln in b.get("lines", []):
                spans = ln.get("spans", [])
                if not spans:
                    continue
                pieces = []  # (bbox, text, size)
                rects  = []
                sizes  = []
                for sp in spans:
                    if isinstance(sp.get("text"), str) and sp["text"].strip():
                        t = " ".join(sp["text"].split())
                        bb = tuple(map(float, sp.get("bbox", brect)))
                    else:
                        chars = sp.get("chars") or []
                        t = "".join(ch.get("c", "") for ch in chars).strip()
                        if chars:
                            xs0 = [c["bbox"][0] for c in chars if "bbox" in c]
                            ys0 = [c["bbox"][1] for c in chars if "bbox" in c]
                            xs1 = [c["bbox"][2] for c in chars if "bbox" in c]
                            ys1 = [c["bbox"][3] for c in chars if "bbox" in c]
                            bb = (min(xs0), min(ys0), max(xs1), max(ys1)) if xs0 else tuple(map(float, brect))
                        else:
                            bb = tuple(map(float, brect))
                    if t:
                        pieces.append((bb, t, float(sp.get("size", 11.5))))
                    rects.append(bb)
                    sizes.append(float(sp.get("size", 11.5)))
                if not pieces:
                    continue

                x0 = min(r[0] for r in rects); y0 = min(r[1] for r in rects)
                x1 = max(r[2] for r in rects); y1 = max(r[3] for r in rects)

                pieces.sort(key=lambda it: it[0][0])  # left x
                segments: List[HybridSegment] = []
                cur_texts, cur_rects, cur_sizes = [], [], []
                last_x1 = None
                for bb, t, sz in pieces:
                    if last_x1 is not None and (bb[0] - last_x1) > SEG_GAP:
                        if cur_texts:
                            srect = (min(r[0] for r in cur_rects), min(r[1] for r in cur_rects),
                                     max(r[2] for r in cur_rects), max(r[3] for r in cur_rects))
                            segments.append(HybridSegment(srect, " ".join(cur_texts), cur_sizes[:]))
                        cur_texts, cur_rects, cur_sizes = [], [], []
                    cur_texts.append(t); cur_rects.append(bb); cur_sizes.append(sz)
                    last_x1 = bb[2]
                if cur_texts:
                    srect = (min(r[0] for r in cur_rects), min(r[1] for r in cur_rects),
                             max(r[2] for r in cur_rects), max(r[3] for r in cur_rects))
                    segments.append(HybridSegment(srect, " ".join(cur_texts), cur_sizes[:]))

                line_text = " ".join(it[1] for it in pieces)
                lines.append(HybridLine((x0, y0, x1, y1), line_text, segments))
                block_text_lines.append(line_text)

            if not lines:
                continue
            block_text = "\n".join(block_text_lines).strip()
            blocks.append(HybridBlock(pno, brect, lines, block_text))
    return blocks


def is_table_like(hb: HybridBlock) -> bool:
    """
    Heuristic: if >=30% of lines have 2+ segments OR there are >=2 persistent x-bands,
    treat as table/columns.
    """
    if not hb.lines:
        return False
    multi = sum(1 for ln in hb.lines if len(ln.segments) >= 2)
    if multi >= max(2, int(0.3 * len(hb.lines))):
        return True

    # persistent x-bands
    bands = []
    for ln in hb.lines:
        for seg in ln.segments:
            bands.append((seg.rect[0], seg.rect[2]))
    if not bands:
        return False
    bands.sort()
    merged = []
    tol = 8.0
    for x0, x1 in bands:
        if not merged or x0 > (merged[-1][1] - tol):
            merged.append([x0, x1])
        else:
            merged[-1][1] = max(merged[-1][1], x1)
    return len(merged) >= 2


def build_columns(hb: HybridBlock) -> List[Tuple[float, float]]:
    bands = []
    for ln in hb.lines:
        for seg in ln.segments:
            bands.append((seg.rect[0], seg.rect[2]))
    if not bands:
        return [(hb.rect[0], hb.rect[2])]
    bands.sort()
    cols = []
    tol = 8.0
    for x0, x1 in bands:
        if not cols or x0 > (cols[-1][1] - tol):
            cols.append([x0, x1])
        else:
            cols[-1][1] = max(cols[-1][1], x1)
    return [(c[0], c[1]) for c in cols]