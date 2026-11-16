#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
find_textbook.py —— 按名/学科/年级/版本/出版社检索国家中小学智慧教育平台教材

痛点：平台的搜索 API（/zxx/ndrv2/search/resources.json）返回 403，无法按关键词下载。
解法：tch_material 模块有「匿名 + 免浏览器」的整库索引：
    data_version.json → part_100/101/...json（每片 1000 条完整元数据）
本脚本拉取索引后在本地离线检索，输出命中教材的 id 与可直接用的下载命令。

用法：
  python find_textbook.py "道德与法治"                 # 模糊检索
  python find_textbook.py "二年级上册" --max-parts 4   # 限定索引分片数（调试快）
  python find_textbook.py "美术鉴赏" --download        # 命中后直接调用下载器

依赖：仅标准库 + 联网（拉取匿名索引，无需登录 token）。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import smartedu_core as core

# 教材下载器脚本（命中后给出命令或直接调用）
DL_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "download_textbook.py")


def main():
    ap = argparse.ArgumentParser(description="按名检索国家中小学智慧教育平台教材")
    ap.add_argument("keyword", help="检索关键词（标题/出版社/学科/年级/版本片段）")
    ap.add_argument("--max-parts", type=int, default=None, help="限定索引分片数（调试用，全量约 40 片/40MB）")
    ap.add_argument("--download", action="store_true", help="命中后直接用 download_textbook.py 下载第一个结果")
    ap.add_argument("--token-file", default=None, help="下载用的 token 文件路径")
    args = ap.parse_args()

    print(f"[索引] 拉取 tch_material 匿名整库索引（关键词={args.keyword}）…")
    try:
        index = core.fetch_tch_material_index(max_parts=args.max_parts)
    except Exception as e:
        print("[索引] 拉取失败：", e)
        print("       可能当前网络无法直连 s-file CDN；请在本机有网络时运行，或用 --token-file 带登录态。")
        sys.exit(1)
    print(f"[索引] 共 {len(index)} 条教材元数据")

    hits = core.search_tch_material(args.keyword, index=index)
    if not hits:
        print(f"[结果] 未命中「{args.keyword}」")
        sys.exit(0)

    print(f"[结果] 命中 {len(hits)} 条：")
    for i, h in enumerate(hits[:50]):
        title = (h.get("global_title") or {}).get("zh-CN") or h.get("title") or "未命名"
        rid = h.get("id")

        # provider 字段只是容器 UUID，真正的出版社名在 provider_list
        plist = h.get("provider_list") or []
        prov_name = ""
        if plist and isinstance(plist[0], dict):
            prov_name = plist[0].get("name") or ""
        prov = prov_name or (h.get("provider") or "")

        tags_raw = h.get("tag_list") or []
        tag_parts = []
        version = ""
        for t in tags_raw:
            if isinstance(t, dict):
                # 注意：字段是 tag_name，不是 name（历史 bug：写成 name 导致标签永远为空）
                nm = t.get("tag_name") or t.get("name") or ""
                if nm:
                    tag_parts.append(str(nm))
                    # zxxbb = 教材版本维度（人教版/青岛版/沪教版…）
                    if t.get("tag_dimension_id") == "zxxbb":
                        version = str(nm)
            elif t:
                tag_parts.append(str(t))
        tags = " ".join(tag_parts)
        print(f"  {i+1:>3}. [{rid}] {title}")
        # 版本在多版本教材里是关键区分维度，单独一行高亮
        if version:
            print(f"       版本：{version}")
        if prov:
            print(f"       出版社/提供方：{prov}")
        if tags:
            print(f"       标签：{tags}")

    top = hits[0]
    top_id = top.get("id")
    top_title = (top.get("global_title") or {}).get("zh-CN") or top.get("title") or "未命名"

    # 同标题不同 ID = 多版本教材，直接下首个极易下错
    norm_titles = {}
    for h in hits:
        t = (h.get("global_title") or {}).get("zh-CN") or h.get("title") or ""
        norm_titles.setdefault(t.strip(), []).append(h.get("id"))
    dup = {t: ids for t, ids in norm_titles.items() if len(ids) > 1}
    if dup:
        print(f"\n[注意] 检出 {len(dup)} 组同标题多版本，--download 只取首个可能下错版本：")
        for t, ids in dup.items():
            print(f"       《{t}》-> {len(ids)} 个 ID: {', '.join(ids[:4])}")
    top_id = top.get("id")
    top_title = (top.get("global_title") or {}).get("zh-CN") or top.get("title") or "未命名"
    if args.download:
        cmd = f'python "{DL_SCRIPT}" --content-id {top_id}'
        if args.token_file:
            cmd += f' --token-file "{args.token_file}"'
        print(f"\n[下载] 命中首个：{top_title}")
        print(f"       命令：{cmd}")
        os.system(cmd)
    else:
        print(f"\n[下载] 用以下命令下载首个命中《{top_title}》：")
        print(f'       python "{DL_SCRIPT}" --content-id {top_id}')


if __name__ == "__main__":
    main()
