#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
课件转图片
==========

把 .pptx 逐页渲染成 PNG，供逐字稿排版时作「页面定位图」使用。

用法：
    python3 ppt2png.py --pptx 课件.pptx --outdir assets/ppt [--dpi 110] [--format jpg|png]

输出：默认 outdir/p01.jpg、p02.jpg …… 与课件页码一一对应（从 1 起）。
      jpg 为默认格式（体积约为 png 的 1/10），--format png 可切回无损。
同一课件只渲染一次即可，后续排版直接复用这些图。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile


def find_soffice():
    """探测 LibreOffice 可执行文件，覆盖 macOS / Windows / Linux。"""
    cands = [
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/local/bin/soffice",
        "/opt/libreoffice/program/soffice",
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    return None


def convert(pptx, outdir, dpi=110, fmt="jpg", quality=88, quiet=False):
    if not os.path.exists(pptx):
        sys.exit("找不到课件：%s" % pptx)
    soffice = find_soffice()
    if not soffice:
        sys.exit("未找到 LibreOffice，请先安装（它负责把 pptx 渲染成 PDF）。")

    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            sys.exit("缺少 pymupdf，请先执行：pip3 install pymupdf")

    os.makedirs(outdir, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", td, pptx],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        stem = os.path.splitext(os.path.basename(pptx))[0]
        pdf = os.path.join(td, stem + ".pdf")
        if not os.path.exists(pdf):
            found = [f for f in os.listdir(td) if f.lower().endswith(".pdf")]
            if not found:
                sys.exit("LibreOffice 未能生成 PDF，请检查课件是否损坏。")
            pdf = os.path.join(td, found[0])

        doc = pymupdf.open(pdf)
        paths = []
        for i in range(doc.page_count):
            path = os.path.join(outdir, "p%02d.%s" % (i + 1, fmt))
            pix = doc[i].get_pixmap(dpi=dpi)
            if fmt == "jpg":
                # 课件多为照片背景，PNG 无损会让体积失控（15 页能到 60MB+）
                pix.save(path, jpg_quality=quality)
            else:
                pix.save(path)
            paths.append(path)
        doc.close()

    if not quiet:
        total = sum(os.path.getsize(p) for p in paths) / 1024 / 1024
        print("已渲染 %d 页 → %s（%d dpi，共 %.1f MB）"
              % (len(paths), outdir, dpi, total))
        if paths:
            print("命名：p01.%s … p%02d.%s" % (fmt, len(paths), fmt))
    return paths


def main():
    ap = argparse.ArgumentParser(description="把 pptx 课件逐页渲染为图片")
    ap.add_argument("--pptx", required=True, help="课件路径")
    ap.add_argument("--outdir", required=True, help="图片输出目录")
    ap.add_argument("--dpi", type=int, default=110,
                    help="渲染分辨率，默认 110（约 1900px 宽，插入 6cm 仍超 300dpi）")
    ap.add_argument("--format", default="jpg", choices=("jpg", "png"),
                    help="图片格式，默认 jpg（体积约为 png 的 1/10）")
    ap.add_argument("--quality", type=int, default=88, help="jpg 质量，默认 88")
    a = ap.parse_args()
    convert(a.pptx, a.outdir, a.dpi, a.format, a.quality)


if __name__ == "__main__":
    main()
