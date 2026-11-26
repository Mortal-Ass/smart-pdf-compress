"""Bounded PDF compression; never overwrites the input or an existing output."""
import argparse
import json
import math
import shutil
import tempfile
import importlib
import subprocess
import sys
import zlib
from io import BytesIO
from pathlib import Path


def load_pymupdf():
    """Install the missing dependency into this Python environment once."""
    try:
        return importlib.import_module("pymupdf")
    except ModuleNotFoundError as exc:
        if exc.name != "pymupdf":
            raise SystemExit(f"PyMuPDF 已安装，但其依赖缺失：{exc}") from exc
    command = [sys.executable, "-m", "pip", "install", "PyMuPDF"]
    print("未检测到 PyMuPDF，正在自动安装（首次运行需要联网）……", flush=True)
    try:
        subprocess.run(command, check=True, timeout=300)
        importlib.invalidate_caches()
        return importlib.import_module("pymupdf")
    except (subprocess.SubprocessError, OSError, ImportError) as exc:
        manual = subprocess.list2cmdline(command)
        raise SystemExit(
            f"PyMuPDF 自动安装或加载失败：{exc}\n"
            f"请在终端手动运行：\n{manual}\n"
            "若提示 No module named pip，先运行：\n"
            f'"{sys.executable}" -m ensurepip --upgrade\n'
            "安装成功后重新运行本程序。"
        ) from exc


fitz = load_pymupdf()

LIMIT = 1024 * 1024


def choose_pdf():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    name = filedialog.askopenfilename(title="选择待压缩 PDF", filetypes=[("PDF", "*.pdf")])
    root.destroy()
    if not name:
        raise ValueError("未选择 PDF")
    return Path(name)


def check(path, original, log=print, compare_text=True):
    with fitz.open(path) as doc:
        if doc.is_repaired or len(doc) != len(original):
            raise ValueError("PDF 修复警告或页数不一致")
        for i, page in enumerate(doc):
            log(f"  检查并渲染页面 {i + 1}/{len(doc)}", flush=True)
            ref = original[i]
            if page.rotation != ref.rotation or page.mediabox != ref.mediabox or page.cropbox != ref.cropbox:
                raise ValueError(f"第 {i+1} 页方向或尺寸变化")
            if compare_text and page.get_text() != ref.get_text():
                raise ValueError(f"第 {i+1} 页文字或顺序变化")
            zoom = min(0.75, 1600 / max(page.rect.width, page.rect.height))
            page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--output-dir", type=Path, help="输出目录，默认与原文件相同")
    parser.add_argument("--size-first", action="store_true", help="允许转为整页图片优先达标，会丢失文字选择、链接和交互功能")
    parser.add_argument("--focus-pages", default="", help="优先保留清晰度的页码，例如 3,11")
    parser.add_argument("--regions", default="", help="局部清晰区域，如 1:72,10,93,34；多个区域用英文分号隔开")
    args = parser.parse_args()
    compress_pdf(args.input or choose_pdf(), args.output_dir, size_first=args.size_first, focus_pages=args.focus_pages, regions=args.regions)


def raster_candidate(original, target, dpi, quality, log, focus_pages=(), focus_dpi=None):
    try:
        from PIL import Image
    except ModuleNotFoundError:
        log("正在安装图片编码依赖 Pillow……")
        subprocess.run([sys.executable, "-m", "pip", "install", "Pillow"], check=True, timeout=300)
        from PIL import Image
    with fitz.open() as result:
        for page in original:
            log(f"  优先达标：转换页面 {page.number + 1}/{len(original)}", flush=True)
            rotation = page.rotation
            try:
                page.set_rotation(0)
                focused = page.number + 1 in focus_pages
                page_dpi = (focus_dpi or max(180, round(dpi * 1.8))) if focused else dpi
                pix = page.get_pixmap(dpi=page_dpi, alpha=False)
            finally:
                page.set_rotation(rotation)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            stream = BytesIO()
            # Optimized Huffman tables and chroma subsampling save space without
            # reducing luminance resolution again.
            image.save(stream, format="JPEG", quality=max(75, quality) if focused else quality, optimize=True, subsampling=2)
            dest = result.new_page(width=page.mediabox.width, height=page.mediabox.height)
            dest.set_mediabox(page.mediabox)
            dest.set_cropbox(page.cropbox)
            dest.insert_image(dest.rect, stream=stream.getvalue())
            dest.set_rotation(rotation)
        result.save(target, garbage=3, deflate=True, use_objstms=1)


def compress_pdf(source, output_dir=None, log=print, size_first=False, focus_pages="", regions=""):
    print = log
    source = Path(source).resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ValueError("请选择存在的 PDF 文件")
    gs = next((shutil.which(n) for n in ("gswin64c", "gswin32c", "gs") if shutil.which(n)), None)
    print("Ghostscript:", gs or "未在 PATH 中找到；本程序可独立使用 PyMuPDF")
    with fitz.open(source) as original, tempfile.TemporaryDirectory(prefix="pdf_compress_") as temp:
        if original.needs_pass or original.is_repaired or not len(original):
            raise ValueError("加密、需修复或空 PDF 不进行自动压缩")
        if any(original.get_sigflags() > 0 for _ in [0]):
            raise ValueError("检测到签名字段；压缩可能使数字签名失效，请先提供无签名副本")
        candidates = []
        focus_pages = {int(p.strip()) for p in focus_pages.replace("，", ",").split(",") if p.strip()}
        if any(p < 1 or p > len(original) for p in focus_pages):
            raise ValueError("重点清晰页的页码超出文件范围")
        from detail_compress import parse_regions, detail_candidate
        regions = parse_regions(regions, len(original))
        if regions and not size_first:
            raise ValueError("局部区域保护需要勾选优先达标")
        detail_path = None
        qr_count = None
        # Index placements once, including every occurrence of shared images.
        placements = {}
        print(f"共 {len(original)} 页，正在建立图片索引……", flush=True)
        for page in original:
            print(f"  索引页面 {page.number + 1}/{len(original)}", flush=True)
            for item in page.get_image_info(xrefs=True):
                xref = item.get("xref", 0)
                rect = fitz.Rect(item["bbox"])
                if xref and rect.width > 0 and rect.height > 0:
                    placements.setdefault(xref, []).append(rect)
        # Preserve vector text, tables, annotations, page geometry and page order.
        profiles = [(None, None), (200, 85), (160, 80), (130, 75), (110, 70),
                    (110, 55), (110, 40), (100, 40), (90, 40), (90, 32)]
        for index, (dpi, quality) in enumerate(profiles):
            print(f"开始方案 {index}：DPI={dpi}, JPEG={quality}", flush=True)
            target = Path(temp) / f"candidate_{index}.pdf"
            with fitz.open(source) as doc:
                if dpi:
                    seen = set()
                    for page in doc:
                        print(f"  压缩页面 {page.number + 1}/{len(doc)}", flush=True)
                        for info in page.get_images(full=True):
                            xref, mask = info[:2]
                            if xref in seen or mask:
                                continue
                            seen.add(xref)
                            rects = placements.get(xref, [])
                            if not rects:
                                continue
                            print(f"    处理图片 {xref}（{info[2]}×{info[3]}）", flush=True)
                            pix = fitz.Pixmap(doc, xref)
                            if pix.alpha or pix.width * pix.height < 40000:
                                continue
                            if pix.colorspace is None:
                                continue
                            if pix.colorspace.n != 3:
                                pix = fitz.Pixmap(fitz.csRGB, pix)
                            scale = min(1, max(max(r.width / pix.width, r.height / pix.height) for r in rects) * dpi / 72)
                            if scale < 1:
                                pix = fitz.Pixmap(pix, max(1, math.ceil(pix.width * scale)), max(1, math.ceil(pix.height * scale)))
                            data = pix.tobytes("jpeg", jpg_quality=quality)
                            raw = pix.samples
                            lossless = zlib.compress(raw)
                            use_lossless = len(lossless) < len(data)
                            if min(len(lossless), len(data)) < len(doc.xref_stream_raw(xref)):
                                # Replace the existing stream directly: replace_image also
                                # adds a second resource holding the same image bytes.
                                doc.update_stream(xref, raw if use_lossless else data,
                                                  compress=use_lossless)
                                for key, value in {"Width": str(pix.width), "Height": str(pix.height),
                                                   "ColorSpace": "/DeviceRGB", "BitsPerComponent": "8",
                                                   "Filter": "/FlateDecode" if use_lossless else "/DCTDecode",
                                                   "DecodeParms": "null", "Decode": "null"}.items():
                                    doc.xref_set_key(xref, key, value)
                print("  保存文件，正在清理冗余对象……", flush=True)
                # Level 4 compares stream contents; avoid its expensive image comparisons.
                doc.save(target, garbage=3, deflate=True, deflate_images=True, deflate_fonts=True)
            check(target, original, log)
            size = target.stat().st_size
            candidates.append((size, target, dpi, quality))
            print(f"方案 {index}: {size / 1024:.1f} KB; DPI={dpi}, JPEG={quality}; 全部页面已重新打开并渲染")
            if size_first and index == 0 and size > LIMIT:
                detail_path = Path(temp) / "detail.pdf"
                qr_count = detail_candidate(original, detail_path, LIMIT, focus_pages, regions, log)
                check(detail_path, original, log, compare_text=False)
                candidates.append((detail_path.stat().st_size, detail_path, None, None))
                if detail_path.stat().st_size <= LIMIT or qr_count or regions:
                    break
            if size <= LIMIT:
                break
        raster_paths = {detail_path} if detail_path else set()
        raster_choice = None
        if size_first and not qr_count and not regions and not any(c[0] <= LIMIT for c in candidates):
            print("结构保留方案未达标，开始有限的整页图片方案；文字选择、链接和交互功能将丢失。")
            previous = None
            for dpi, quality in [(300, 85), (240, 85), (200, 85), (160, 85),
                                 (130, 65), (110, 50), (100, 40), (90, 32),
                                 (90, 20), (85, 20), (80, 20)]:
                target = Path(temp) / f"raster_{dpi}_{quality}.pdf"
                raster_candidate(original, target, dpi, quality, log, focus_pages)
                check(target, original, log, compare_text=False)
                size = target.stat().st_size
                raster_paths.add(target)
                candidates.append((size, target, dpi, quality))
                print(f"整页图片方案：{dpi} DPI，JPEG {quality}，{size / 1024:.1f} KB", flush=True)
                if size <= LIMIT:
                    raster_choice = candidates[-1]
                    # Refine the boundary, retaining only validated candidates.
                    # Fixed JPEG quality makes DPI the quality-ranking criterion.
                    if previous and previous[1] == quality:
                        low, high = dpi, previous[0]
                        for _ in range(6):
                            mid = (low + high) // 2
                            if mid <= low:
                                break
                            refined = Path(temp) / f"refined_{mid}_{quality}.pdf"
                            print(f"利用剩余空间提高画质：{mid} DPI，JPEG {quality}", flush=True)
                            raster_candidate(original, refined, mid, quality, log, focus_pages)
                            refined_size = refined.stat().st_size
                            if refined_size <= LIMIT:
                                check(refined, original, log, compare_text=False)
                                raster_paths.add(refined)
                                raster_choice = (refined_size, refined, mid, quality)
                                low = mid
                            else:
                                high = mid
                    break
                previous = (dpi, quality)
        selected_focus_dpi = None
        if raster_choice and focus_pages:
            _, _, base_dpi, base_quality = raster_choice
            low, high = max(180, round(base_dpi * 1.8)), 240
            selected_focus_dpi = low
            for _ in range(6):
                mid = (low + high) // 2
                if mid <= low:
                    break
                refined = Path(temp) / f"focus_refined_{mid}.pdf"
                print(f"利用剩余空间提升重点页：{mid} DPI", flush=True)
                raster_candidate(original, refined, base_dpi, base_quality, log, focus_pages, mid)
                size = refined.stat().st_size
                if size <= LIMIT:
                    check(refined, original, log, compare_text=False)
                    raster_paths.add(refined)
                    raster_choice = (size, refined, base_dpi, base_quality)
                    low = selected_focus_dpi = mid
                else:
                    high = mid
        best = raster_choice or next((c for c in candidates if c[0] <= LIMIT), min(candidates))
        size, path, dpi, quality = best
        rasterized = path in raster_paths
        status = "compressed" if size <= LIMIT else "best_effort_OVER_LIMIT"
        output_dir = Path(output_dir or source.parent).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / (source.stem + f"_{status}.pdf")
        counter = 1
        while output.exists():
            output = output_dir / (source.stem + f"_{status}_{counter}.pdf")
            counter += 1
        with output.open("xb") as dest, path.open("rb") as src:
            shutil.copyfileobj(src, dest)
        check(output, original, log, compare_text=not rasterized)
        report = {"input": str(source), "output": str(output), "pages": len(original), "bytes": size,
                  "limit_bytes": LIMIT, "within_limit": size <= LIMIT, "dpi": dpi, "jpeg_quality": quality,
                  "all_pages_rendered": True, "geometry_rotation_checked": True,
                  "text_preserved": not rasterized, "rasterized": rasterized,
                  "focus_pages": sorted(focus_pages) if rasterized else [],
                  "method": "page_budget_jpeg2000" if path == detail_path else "standard",
                  "verified_qr_codes": qr_count if path == detail_path else None,
                  "focus_dpi": selected_focus_dpi if rasterized else None,
                  "risk": ("已转为整页图片，文字无法选中复制，链接和交互功能丢失；小字、照片、印章可能模糊，二维码需实际扫码验证。"
                           if rasterized else "图片有损压缩可能影响照片、印章和扫描小字；请人工放大复核。" if dpi else "无图片有损重编码。")}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if size > LIMIT:
            print("已用完预设的有限压缩方案，停止降低画质；以上为本次方案中的最小文件，并非理论最小值或已验证的清晰度下限。")
        return report


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("已取消，原始 PDF 未修改。")
    except Exception as exc:
        raise SystemExit(f"失败：{exc}")
