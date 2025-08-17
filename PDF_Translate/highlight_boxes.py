import re, fitz

# ----------------------------
# Helpers (for annotations)
# ----------------------------
def _hex_to_rgb01(hx: str):
    """#RRGGBB hex -> (r,g,b) in 0..1 floats for PyMuPDF."""
    hx = (hx or "").lstrip("#")
    if len(hx) != 6:
        return (1.0, 0.0, 0.0)  # default red
    return (int(hx[0:2], 16) / 255.0, int(hx[2:4], 16) / 255.0, int(hx[4:6], 16) / 255.0)

def _expand_rect(x0, y0, x1, y1, margin):
    return (x0 - margin, y0 - margin, x1 + margin, y1 + margin)

def add_boxes_to_pdf(
    input_pdf: str,
    items: list,
    output_pdf: str,
    page_is_one_based: bool = False,
    color=(1, 0, 0),
    stroke_width: float = 1.5,
    fill_opacity: float = 0.15,
    use_annot: bool = True,
    fill: bool = True,
):
    """Add rectangle boxes to a PDF using either annotation layer or drawn shapes."""
    doc = fitz.open(input_pdf)
    n_pages = len(doc)

    for i, item in enumerate(items):
        try:
            # page index (int), bbox = [x0,y0,x1,y1] in PDF points
            p = int(item["page"])
            if page_is_one_based:
                p -= 1
            if not (0 <= p < n_pages):
                continue

            x0, y0, x1, y1 = map(float, item["bbox"])
            rect = fitz.Rect(x0, y0, x1, y1)
            page = doc[p]

            if use_annot:
                annot = page.add_rect_annot(rect)
                annot.set_colors(stroke=color, fill=(color if fill else None))
                annot.set_border(width=stroke_width)
                if fill:
                    annot.set_opacity(fill_opacity)
                annot.update()
            else:
                page.draw_rect(
                    rect,
                    color=color,
                    width=stroke_width,
                    fill=(color if fill else None),
                    fill_opacity=(fill_opacity if fill else 0.0),
                )
        except Exception:
            # Skip malformed entries robustly
            continue

    doc.save(output_pdf, garbage=4, deflate=True)
    doc.close()
    return output_pdf

def build_annotation_items_from_pdf(
    pdf_path: str,
    mode: str = "devanagari_words",
    regex_pattern: str = r"[\u0900-\u097F]+",
    min_w: float = 1.0,
    min_h: float = 1.0,
    merge_lines: bool = True,
    margin: float = 0.0,
):
    """
    Create a list of {'page': int, 'bbox': [x0,y0,x1,y1]} items derived from the PDF content.
    - mode:
        'devanagari_words' -> words containing Devanagari chars ([\u0900-\u097F])
        'english_words'    -> words with A-Za-z
        'regex'            -> custom regex on words
        'all_text_blocks'  -> page.get_text('blocks') rectangles (text only)
    - merge_lines: when using word-based modes, merge words by (block_no, line_no).
    - margin: expand each rectangle by this many points on all sides.
    """
    items = []
    doc = fitz.open(pdf_path)

    # Compile regex if needed
    rx = None
    if mode in ("devanagari_words", "english_words", "regex"):
        if mode == "devanagari_words":
            rx = re.compile(r"[\u0900-\u097F]+")
        elif mode == "english_words":
            rx = re.compile(r"[A-Za-z]+")
        else:
            rx = re.compile(regex_pattern)

    for page_ix in range(len(doc)):
        page = doc[page_ix]

        if mode == "all_text_blocks":
            # get_text("blocks") -> [x0,y0,x1,y1,"text", block_no, block_type, ...]
            blocks = page.get_text("blocks")
            for b in blocks:
                if len(b) < 6:
                    continue
                x0, y0, x1, y1, text, bno = b[0], b[1], b[2], b[3], b[4], b[5]
                # block_type is at index 6 for some versions; if present and not text (0), skip
                if len(b) >= 7:
                    block_type = b[6]
                    if block_type not in (0, 1):  # 0=text, 1=image; keep text only
                        continue
                    if block_type == 1:
                        continue
                w = x1 - x0
                h = y1 - y0
                if w >= min_w and h >= min_h:
                    x0e, y0e, x1e, y1e = _expand_rect(x0, y0, x1, y1, margin)
                    items.append({"page": page_ix, "bbox": [x0e, y0e, x1e, y1e]})
        else:
            # word-based path
            # page.get_text("words") -> list of [x0, y0, x1, y1, "word", block_no, line_no, word_no]
            words = page.get_text("words")
            if not words:
                continue

            if merge_lines:
                # group by (block_no, line_no) but only for words that match rx
                lines = {}
                for w in words:
                    if len(w) < 8:
                        continue
                    x0, y0, x1, y1, wtext, bno, lno, wno = w
                    if not wtext:
                        continue
                    if not rx.search(wtext):
                        continue
                    if (x1 - x0) < min_w or (y1 - y0) < min_h:
                        continue
                    key = (bno, lno)
                    if key not in lines:
                        lines[key] = [x0, y0, x1, y1]
                    else:
                        bx0, by0, bx1, by1 = lines[key]
                        lines[key] = [min(bx0, x0), min(by0, y0), max(bx1, x1), max(by1, y1)]
                for rect in lines.values():
                    x0, y0, x1, y1 = _expand_rect(*rect, margin=margin)
                    items.append({"page": page_ix, "bbox": [x0, y0, x1, y1]})
            else:
                # individual words
                for w in words:
                    if len(w) < 8:
                        continue
                    x0, y0, x1, y1, wtext, *_ = w
                    if not wtext:
                        continue
                    if not rx.search(wtext):
                        continue
                    if (x1 - x0) < min_w or (y1 - y0) < min_h:
                        continue
                    x0, y0, x1, y1 = _expand_rect(x0, y0, x1, y1, margin)
                    items.append({"page": page_ix, "bbox": [x0, y0, x1, y1]})

    doc.close()
    return items