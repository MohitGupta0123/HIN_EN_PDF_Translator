import fitz, subprocess, shutil, os

def rasterize_pdf_to_image_pdf(input_path: str, dpi: int = 300) -> str:
    doc = fitz.open(input_path); tmp_dir = "temp"; os.makedirs(tmp_dir, exist_ok=True)
    out_path = os.path.join(tmp_dir, "rasterized.pdf")
    out = fitz.open(); zoom = dpi/72.0; mat = fitz.Matrix(zoom, zoom)
    try:
        for pno in range(len(doc)):
            page = doc[pno]; pix = page.get_pixmap(matrix=mat, alpha=False)
            po = out.new_page(width=page.rect.width, height=page.rect.height)
            po.insert_image(po.rect, stream=pix.tobytes("png"))
        out.save(out_path)
    finally:
        out.close(); doc.close()
    return out_path

def ocr_fix_pdf(input_path: str, lang: str, dpi: str, optimize: str) -> str:
    if shutil.which("ocrmypdf") is None:
        print("[ocrmypdf] not found; using original.")
        return input_path
    out_dir = "temp"; os.makedirs(out_dir, exist_ok=True)
    output_path = os.path.join(out_dir, "ocr_fixed.pdf")
    cmd = [
        "ocrmypdf", "--language", lang, "--deskew", "--rotate-pages", "--force-ocr",
        "--image-dpi", dpi, "--oversample", dpi, "--optimize", optimize,
        os.fspath(input_path), os.fspath(output_path)
    ]
    print("[ocrmypdf]", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        print("[ocrmypdf] success ->", output_path); return output_path
    print("[ocrmypdf] failed; fallback to rasterize.\nSTDERR:\n", proc.stderr)
    try:
        image_pdf = rasterize_pdf_to_image_pdf(input_path, dpi=300)
    except Exception as e:
        print("[fallback] rasterize failed:", e); return input_path
    output_path2 = os.path.join(out_dir, "ocr_fixed_from_image.pdf")
    cmd2 = [
        "ocrmypdf", "--language", lang, "--deskew", "--rotate-pages",
        "--image-dpi", dpi, "--oversample", dpi, "--optimize", optimize,
        os.fspath(image_pdf), os.fspath(output_path2)
    ]
    print("[ocrmypdf fallback]", " ".join(cmd2))
    proc2 = subprocess.run(cmd2, capture_output=True, text=True)
    if proc2.returncode == 0:
        print("[ocrmypdf] success via rasterize ->", output_path2); return output_path2
    print("[ocrmypdf] fallback failed; using original.\nSTDERR:\n", proc2.stderr)
    return input_path