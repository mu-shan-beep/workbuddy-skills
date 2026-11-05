#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单文件离线课件校验器（阶段 6）

用法:
    python3 check_offline.py 课件.html
    python3 check_offline.py 课件.html --max-mb 8

检查项:
    1. 是否存在 http(s) 外链（CDN、外部字体、在线图片、在线语音）
    2. 是否存在相对路径引用（说明资源没内联）
    3. 统计内联媒体数量与体积
    4. 报告文件体积，超阈值告警

退出码: 0 通过 / 1 存在阻断项
"""

import argparse
import os
import re
import sys

BLOCKING_HOSTS = (
    "cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com", "esm.sh",
    "fonts.googleapis.com", "fonts.gstatic.com", "code.jquery.com",
    "cdn.bootcdn.net", "lib.baomitu.com", "at.alicdn.com",
)

ATTR_SRC = re.compile(
    r"""<(script|link|img|source|audio|video|iframe|embed)\b[^>]*?
        \b(src|href)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE | re.VERBOSE,
)
CSS_URL = re.compile(r"""url\(\s*["']?([^"')]+)["']?\s*\)""", re.IGNORECASE)
CSS_IMPORT = re.compile(r"""@import\s+(?:url\()?["']([^"']+)["']""", re.IGNORECASE)
HTTP_ANY = re.compile(r"""https?://[^\s"'<>()]+""", re.IGNORECASE)


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"


def is_inline(url: str) -> bool:
    return url.startswith("data:") or url.startswith("#") or url.startswith("javascript:")


def is_external(url: str) -> bool:
    return url.lower().startswith(("http://", "https://", "//"))


def main() -> int:
    ap = argparse.ArgumentParser(description="单文件离线课件校验器")
    ap.add_argument("html", help="待校验的 HTML 文件")
    ap.add_argument("--max-mb", type=float, default=8.0,
                    help="体积上限（MB），超出告警，默认 8")
    args = ap.parse_args()

    path = os.path.abspath(args.html)
    if not os.path.isfile(path):
        print(f"[错误] 文件不存在: {path}")
        return 1

    size = os.path.getsize(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        src = f.read()

    blocking, warnings = [], []

    # 1. 标签属性里的外链 / 相对路径
    for m in ATTR_SRC.finditer(src):
        tag, attr, url = m.group(1).lower(), m.group(2).lower(), m.group(3).strip()
        if is_inline(url) or url.startswith("blob:"):
            continue
        if is_external(url):
            blocking.append(f"<{tag} {attr}=\"{url[:90]}\">")
        elif tag == "link" and attr == "href" and url.startswith(("mailto:", "tel:")):
            continue
        else:
            line = src[: m.start()].count("\n") + 1
            warnings.append(f"第 {line} 行为相对路径引用: <{tag} {attr}=\"{url[:80]}\">")

    # 2. CSS 里的 url() 与 @import
    for rx, label in ((CSS_URL, "url()"), (CSS_IMPORT, "@import")):
        for m in rx.finditer(src):
            url = m.group(1).strip()
            if is_inline(url) or url.startswith("blob:"):
                continue
            if is_external(url):
                blocking.append(f"CSS {label}: {url[:90]}")
            else:
                warnings.append(f"CSS {label} 相对路径: {url[:80]}")

    # 3. 纯文本中的裸外链（排除注释与示例字符串）
    for m in HTTP_ANY.finditer(src):
        url = m.group(0)
        if any(h in url.lower() for h in BLOCKING_HOSTS):
            if not any(url[:90] in b for b in blocking):
                blocking.append(f"命中 CDN 域名: {url[:90]}")

    # 4. 内联媒体统计
    data_uris = re.findall(r"""data:([a-z]+/[a-z0-9.+-]+);base64,""", src, re.IGNORECASE)
    media = [m for m in data_uris if m.split("/")[0] in ("image", "audio", "video", "font")]
    inline_bytes = sum(len(x) for x in re.findall(r"base64,([A-Za-z0-9+/=]+)", src)) * 3 // 4

    print("=" * 56)
    print(f"文件      {os.path.basename(path)}")
    print(f"体积      {human(size)}" + ("  [超出上限] " if size > args.max_mb * 1024 * 1024 else ""))
    print(f"内联媒体  {len(media)} 项，解码后约 {human(inline_bytes)}")
    print(f"外链阻断  {len(blocking)} 项")
    print(f"相对路径  {len(warnings)} 项")
    print("=" * 56)

    if blocking:
        print("\n[阻断] 以下引用会让课件脱离网络后失效：")
        for b in blocking[:20]:
            print("  - " + b)
        if len(blocking) > 20:
            print(f"  ... 另有 {len(blocking) - 20} 项")

    if warnings:
        print("\n[警告] 以下资源未内联，换机器可能丢失：")
        for w in warnings[:20]:
            print("  - " + w)
        if len(warnings) > 20:
            print(f"  ... 另有 {len(warnings) - 20} 项")

    if size > args.max_mb * 1024 * 1024:
        print(f"\n[警告] 体积 {human(size)} 超过 {args.max_mb} MB，首屏可能超过 5 秒。"
              f"建议压缩贴图或降低网格精度。")

    if blocking:
        print("\n结论：不通过。请把上述资源全部内联后重跑。")
        return 1

    if warnings:
        print("\n结论：可离线运行，但仍有相对路径引用，建议一并内联。")
        return 0

    print("\n结论：通过。单文件、无外链，可离线运行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
