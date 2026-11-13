#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开工前素材齐备预检（只读，不排版、不写任何文件）
================================================
2026-11-13 用户硬性要求：
  「教学设计中的板书设计，必须要使用板书设计图片；逐字稿中的 ppt 预览图必须使用
    PDF 中的；如果我没有提供，就暂停工作，向我询问，等我提供后再进行排版。」
用户补充：「有时候我会忘记提供这些文件，因此你需要提醒我。」

因此：任何排版委托的**第一步**（早于读规范、早于跑 typeset.py）都必须先跑本脚本，
把齐备状态主动报给用户；有缺失即暂停，等用户提供后再排版。
判定逻辑单点复用 typeset.py::asset_status()，禁止在本文件重写第二份口径。

用法：
    python3 check_assets.py --root "<课题目录>" [--courseware-pdf <路径>]

退出码：0 = 素材齐备，可排版；3 = 有缺失，必须暂停并提醒用户。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from typeset import asset_status  # noqa: E402  单点判定，禁止另写一份


def main():
    ap = argparse.ArgumentParser(description="开工前素材齐备预检（只读）")
    ap.add_argument("--root", default=os.getcwd(), help="课题根目录")
    ap.add_argument("--courseware-pdf", help="用户提供的课件 PDF（可选显式指定）")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    st = asset_status(root, a.courseware_pdf)

    print("=" * 62)
    print("开工前素材齐备预检｜%s" % root)
    print("=" * 62)
    print("  [1] 板书设计图片  ：%s  %s" %
          ("✅ 已提供" if st["board_ok"] else "❌ 缺失",
           st["board_ref"] or "（教学设计未引用图片）"))
    print("  [2] 课件 PDF      ：%s  %s" %
          ("✅ 已提供" if st["pdf_ok"] else "❌ 缺失",
           os.path.relpath(st["pdf"], root) if st["pdf"] else "（assets/ 或根目录名含「课件」）"))
    if st["pdf_ok"]:
        print("      课件页数      ：%d 页" % st["deck_pages"])
        print("      现有预览图    ：%d 张｜来源校验：%s" %
              (st["page_count"], "✅ 由该 PDF 导出" if st["source_ok"]
               else "⏳ 待排版时自动导出覆盖"))
    else:
        print("      现有预览图    ：%d 张（来源不合规，禁止使用）" % st["page_count"])
    print("-" * 62)

    if st["missing"]:
        print("⛔ 素材未齐备，排版必须暂停。请立即向用户报告下列缺失项并请求提供：")
        for i, m in enumerate(st["missing"], 1):
            print("   %d. %s" % (i, m))
        print()
        print("【提醒话术（直接在聊天中发给用户）】")
        need_board = any("板书" in m for m in st["missing"])
        need_pdf = any("课件 PDF" in m for m in st["missing"])
        names = []
        if need_board:
            names.append("板书设计图片")
        if need_pdf:
            names.append("课件 PDF")
        print("  排版前素材预检发现还缺：%s。" % "、".join(names))
        print("  按您定的硬性要求，我已暂停排版、未生成也未覆盖任何成品。")
        if need_pdf:
            print("  请把课件导出的 PDF 放到 assets/（或命名「<课题>-课件.pdf」）；")
        if need_board:
            print("  请把板书设计图片放到课题根目录，并在教学设计「板书设计」下引用；")
        print("  文件到位后我再继续排版。")
        print("=" * 62)
        return 3

    print("✅ 素材齐备，可以排版。")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
