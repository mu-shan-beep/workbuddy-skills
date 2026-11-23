#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
download_full_volume.py —— 教材整册课程资源批量下载（纯 API，无需浏览器）

【快路径 prepare】（默认优先，匿名可读，无需 token 即可解析结构）
  1) /zxx/ndrs/prepare_lesson/teachingmaterials/{pack}/resources/parts.json -> 分片清单
  2) /zxx/ndrs/prepare_lesson/teachingmaterials/{pack}/resources/part_*.json
     -> 每课条目，relations.national_course_resource 直接给出 5 类资源 ID
  3) /zxx/ndrv2/prepare_sub_type/resources/details/{resourceId}.json
     -> 单资源详情，含 ti_storages 直链（匿名可读）
  4) /zxx/ndrv2/national_lesson/trees/{pack}.json -> 章节树（匿名可读）

【兼容路径 legacy】（仅有教材 ID 时用）
  教材详情 tag_list -> national_lesson 全站索引按 tag 匹配课程包 -> 同上

  5) 复用 download_course.run_resources() 下载（视频 16 线程 HLS；文档 PDF->pptx/docx）

ID 说明：
  - --id 支持「教材 ID」和「课程包 ID」两种，脚本会自动探测（先试 prepare 接口）
  - 课程包 ID 可从任一课时详情页的浏览器 XHR 里看到：
       /zxx/ndrs/prepare_lesson/teachingmaterials/<这个ID>/resources/part_100.json

输出结构：
  <out>/<教材名>/<章标题>/<课时标题>/视频课程|课件|教学设计|学习任务单|课后练习/

用法：
  python download_full_volume.py --id <教材ID 或 课程包ID> --inspect
  python download_full_volume.py --id <id> --out ./北师大数学七上
  python download_full_volume.py --id <id> --only courseware,plan,task,exercise
  python download_full_volume.py --id <id> --limit 3          # 只下前 3 课（试跑）
"""

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import smartedu_core as core
from download_course import run_resources, resolve_only_set, ensure_deps, DIRMAP

HOSTS = ["s-file-1", "s-file-2", "s-file-3"]
BASE = "https://s-file-1.ykt.cbern.com.cn"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
REF = "https://basic.smartedu.cn/"

# 匹配课程包时使用的标签维度（学段/学科/版本/年级/册次）
MATCH_DIMS = ["zxxxd", "zxxxk", "zxxbb", "zxxnj", "zxxcc"]

_PRINT_LOCK = threading.Lock()


def log(msg, prefix=""):
    with _PRINT_LOCK:
        print((prefix + msg) if prefix else msg, flush=True)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def http_json(path_or_url, token=None, timeout=60, retries=3):
    """请求 JSON：支持相对路径（自动换 s-file-1/2/3 主机）或绝对 URL。"""
    if path_or_url.startswith("http"):
        urls = [path_or_url]
    else:
        urls = [f"https://{h}.ykt.cbern.com.cn{path_or_url}" for h in HOSTS]

    headers = {"User-Agent": UA, "Referer": REF, "Accept": "application/json, text/plain, */*"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    last_err = None
    for attempt in range(retries):
        for u in urls:
            try:
                req = urllib.request.Request(u, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                last_err = f"HTTP {e.code} @ {u[:90]}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:60]} @ {u[:90]}"
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(last_err or "unknown http error")


def http_bytes(url, token=None, timeout=120):
    headers = {"User-Agent": UA, "Referer": REF}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------
def load_token(args, skill_root):
    token = args.token
    mac_key = ""
    if not token:
        tf = args.token_file or os.path.join(skill_root, "smartedu_token.txt")
        if os.path.exists(tf):
            raw = Path(tf).read_text(encoding="utf-8").strip()
            try:
                obj = json.loads(raw)
                token = obj.get("access_token") or obj.get("token")
                mac_key = obj.get("mac_key") or ""
            except Exception:
                token = raw
            log(f"[token] 已加载 {os.path.basename(tf)}（长度 {len(token or '')}）")
        else:
            log(f"[token] 未找到 token 文件：{tf}")
    return token, mac_key


# ---------------------------------------------------------------------------
# Step 1-2: 教材 -> 课程包
# ---------------------------------------------------------------------------
def textbook_tags(tid, token):
    d = http_json(f"/zxx/ndrv2/resources/tch_material/details/{tid}.json", token)
    title = (d.get("global_title") or {}).get("zh-CN") or str(d.get("title") or "")
    tags = {}
    for t in d.get("tag_list") or []:
        dim = t.get("tag_dimension_id")
        if dim:
            tags[dim] = t.get("tag_id")
    return title, tags


def find_course_pack(tags, token):
    """在 national_lesson 索引里按标签匹配课程包，返回 (pack_id, pack_title, all_candidates)。"""
    dv = http_json("/zxx/ndrs/national_lesson/teachingmaterials/version/data_version.json", token)
    urls = dv.get("urls")
    if isinstance(urls, str):
        urls = urls.split(",")

    want = {d: tags[d] for d in MATCH_DIMS if tags.get(d)}
    candidates = []
    for u in urls:
        try:
            arr = http_json(u.strip(), token, timeout=90)
        except Exception as e:
            log(f"[index] 分片失败 {u[-30:]}: {e}")
            continue
        for it in arr or []:
            itags = {t.get("tag_dimension_id"): t.get("tag_id") for t in (it.get("tag_list") or [])}
            if all(itags.get(k) == v for k, v in want.items()):
                candidates.append(it)

    if not candidates:
        return None, None, []

    # 优先「新教材」，其次第一个
    def rank(it):
        names = [t.get("tag_name", "") for t in (it.get("tag_list") or [])]
        return (0 if any("新教材" in n for n in names) else 1, it.get("title") or "")

    candidates.sort(key=rank)
    best = candidates[0]
    return best.get("id"), best.get("title") or "", candidates


# ---------------------------------------------------------------------------
# Step 3-4: 章节树 + 课时列表
# ---------------------------------------------------------------------------
def fetch_tree_chapters(pack_id, token):
    """返回 {node_id: (章标题, 节标题)} 与有序结构。"""
    nodes = http_json(f"/zxx/ndrv2/national_lesson/trees/{pack_id}.json", token)
    mapping = {}

    def walk(items, parent_title=""):
        for n in items or []:
            nid = n.get("id")
            title = n.get("title") or n.get("rich_title") or ""
            children = n.get("child_nodes") or []
            if children:
                mapping[nid] = (title, "")
                walk(children, title)
            else:
                mapping[nid] = (parent_title, title)

    walk(nodes if isinstance(nodes, list) else [nodes])
    return mapping


def fetch_lesson_entries(pack_id, token):
    parts = http_json(
        f"/zxx/ndrs/national_lesson/teachingmaterials/{pack_id}/resources/parts.json", token)
    urls = parts if isinstance(parts, list) else parts.get("urls")
    if isinstance(urls, str):
        urls = urls.split(",")
    entries = []
    for u in urls:
        try:
            arr = http_json(u.strip(), token, timeout=120)
            if isinstance(arr, list):
                entries.extend(arr)
            elif isinstance(arr, dict):
                entries.append(arr)
        except Exception as e:
            log(f"[resources] 分片失败 {str(u)[-30:]}: {e}")
    return entries


# ---------------------------------------------------------------------------
# Step 5: 单课资源详情
# ---------------------------------------------------------------------------
def fetch_lesson_resources(lesson_id, token):
    d = http_json(f"/zxx/ndrv2/national_lesson/resources/details/{lesson_id}.json", token)
    rel = (d.get("relations") or {}).get("national_course_resource") or []
    return [r for r in rel if r.get("ti_items")]


# ---------------------------------------------------------------------------
# 快路径：备课资源（prepare_lesson / prepare_sub_type，匿名可读）
# ---------------------------------------------------------------------------
def probe_prepare_pack(given_id, timeout=20):
    """判断给定 ID 是否为「课程包 ID」（prepare_lesson 分片存在即为真）。"""
    try:
        parts = http_json(
            f"/zxx/ndrs/prepare_lesson/teachingmaterials/{given_id}/resources/parts.json",
            None, timeout=timeout, retries=1)
        return True, parts
    except Exception:
        return False, None


def fetch_lesson_entries_prepare(pack_id):
    """备课分片 -> 课时条目列表（含 relations.national_course_resource 的资源 ID）。"""
    ok, parts = probe_prepare_pack(pack_id)
    if not ok:
        raise RuntimeError(f"备课分片不可用：{pack_id}")
    urls = parts if isinstance(parts, list) else parts.get("urls")
    if isinstance(urls, str):
        urls = urls.split(",")
    entries = []
    for u in urls or []:
        try:
            arr = http_json(u.strip(), None, timeout=120)
            if isinstance(arr, list):
                entries.extend(arr)
            elif isinstance(arr, dict):
                entries.append(arr)
        except Exception as e:
            log(f"[prepare] 分片失败 {str(u)[-30:]}: {e}")
    return entries


def fetch_lesson_resources_prepare(entry, only_set=None):
    """按资源 ID 逐个请求 prepare_sub_type 详情（匿名），返回带 ti_items 的资源列表。

    只请求 only_set 内的类型，避免仅为拿课件而去拉视频详情。
    """
    rel = (entry.get("relations") or {}).get("national_course_resource") or []
    wanted = [r for r in rel
              if r.get("id") and (only_set is None or r.get("resource_type_code") in only_set)]
    if not wanted:
        return []

    def one(r):
        rid = r.get("id")
        try:
            d = http_json(
                f"/zxx/ndrv2/prepare_sub_type/resources/details/{rid}.json",
                None, timeout=45, retries=2)
        except Exception as e:
            return {"resource_type_code": r.get("resource_type_code"),
                    "global_title": r.get("title"), "_error": str(e), "ti_items": []}
        tis = d.get("ti_items") or []
        if not tis:
            return None
        return {
            "id": d.get("id") or rid,
            "resource_type_code": d.get("resource_type_code") or r.get("resource_type_code"),
            "global_title": d.get("global_title") or {"zh-CN": r.get("title") or ""},
            "ti_items": tis,
        }

    out = []
    if len(wanted) <= 1:
        res = [one(x) for x in wanted]
    else:
        with ThreadPoolExecutor(max_workers=min(5, len(wanted))) as ex:
            res = list(ex.map(one, wanted))
    for x in res:
        if x:
            out.append(x)
    return out


# ---------------------------------------------------------------------------
# 收获：跳过已下载 + 兜底清理临时目录
# ---------------------------------------------------------------------------
def filter_existing(resources, lesson_dir, args):
    """剔除目标文件已存在且非空的资源，返回 (需要下载的, 已跳过数)。"""
    pending, skipped = [], 0
    for r in resources:
        rtitle = r.get("global_title", {}).get("zh-CN") if isinstance(r.get("global_title"), dict) \
            else (r.get("global_title") or "")
        rtype = r.get("resource_type_code", "")
        sub, ext = DIRMAP.get(rtype, (rtype, ".bin"))
        title = rtitle or "未命名"
        if isinstance(title, str) and title.lower().endswith(ext.lower()):
            title = title[: -len(ext)]
        dest = os.path.join(lesson_dir, sub, title + ext)
        if os.path.exists(dest) and os.path.getsize(dest) > 1024:
            skipped += 1
            continue
        pending.append(r)
    return pending, skipped


def cleanup_leftover_ts(root):
    """兜底清理 _ts_* 临时分片目录（rmtree 被安全策略拦截时会残留）。"""
    import shutil
    removed, freed = 0, 0
    for dp, dirs, _files in os.walk(root):
        for d in list(dirs):
            if not d.startswith("_ts_"):
                continue
            p = os.path.join(dp, d)
            size = sum(os.path.getsize(os.path.join(a, f))
                       for a, _b, fs in os.walk(p) for f in fs if os.path.exists(os.path.join(a, f)))
            try:
                shutil.rmtree(p)
                removed += 1
                freed += size
            except Exception:
                pass
            dirs.remove(d)
    if removed:
        log(f"[清理] 移除 {removed} 个临时目录，释放 {freed/1024/1024:.1f} MB")
    return removed, freed


# ---------------------------------------------------------------------------
# 下载单课
# ---------------------------------------------------------------------------
def download_one_lesson(idx, total, entry, chapter_of, out_root, args, token, ffmpeg, mac_key,
                        source="prepare"):
    lesson_id = entry.get("id")
    raw_title = entry.get("title") or (entry.get("global_title") or {}).get("zh-CN") or lesson_id
    title = re.sub(r'[\\/:*?"<>|]', "_", raw_title).strip()
    chap_id = (entry.get("chapter_ids") or [None])[-1]
    chap_title = chapter_of.get(chap_id, ("", "")) if chap_id else ("", "")
    dir_chapter = re.sub(r'[\\/:*?"<>|]', "_", chap_title[0] or "未分章").strip()

    lesson_dir = os.path.join(out_root, dir_chapter, title)
    only = resolve_only_set(args)
    try:
        if source == "prepare":
            resources = fetch_lesson_resources_prepare(entry, only)
            errs = [r for r in resources if r.get("_error")]
            if errs and not [r for r in resources if r.get("ti_items")]:
                raise RuntimeError(errs[0].get("_error") or "资源详情全部失败")
        else:
            resources = fetch_lesson_resources(lesson_id, token)
    except Exception as e:
        log(f"[{idx}/{total}] {title} —— 详情获取失败: {e}")
        return title, [], [(title, "detail", str(e))]

    if not resources:
        log(f"[{idx}/{total}] {title} —— 无资源条目")
        return title, [], [(title, "none", "无资源")]

    picked = [r for r in resources if only is None or r.get("resource_type_code") in only]
    os.makedirs(lesson_dir, exist_ok=True)

    if not args.force:
        picked, skipped = filter_existing(picked, lesson_dir, args)
        if not picked:
            log(f"[{idx}/{total}] {title} —— 已存在，跳过（{skipped} 项）")
            return title, [], []

    kinds = "/".join(sorted({r.get("resource_type_code", "?") for r in picked}))
    log(f"[{idx}/{total}] {title}  ({len(picked)} 项: {kinds})")

    succ, failed = run_resources(picked, lesson_dir, args, token, ffmpeg, mac_key)
    return title, succ, failed


# ---------------------------------------------------------------------------
# 资源定位：ID 自动识别 + 统一取 pack / 章节 / 课时
# ---------------------------------------------------------------------------
def extract_tid(text):
    if not text:
        return None
    m = re.search(r"teachingmaterialId=([0-9a-fA-F-]{36})", text)
    if m:
        return m.group(1)
    if re.fullmatch(r"[0-9a-fA-F-]{36}", text.strip()):
        return text.strip()
    return None


def infer_book_title(entries):
    """从课时条目的 tag_list 拼教材名（版本+学科+年级+册次）。"""
    tags = {}
    for e in entries[:8]:
        for t in e.get("tag_list") or []:
            tags.setdefault(t.get("tag_dimension_id"), t.get("tag_name") or "")
    parts = [tags.get("zxxbb"), tags.get("zxxxk"), tags.get("zxxnj"), tags.get("zxxcc")]
    name = "".join(p for p in parts if p).strip()
    return name


# 版本简称 → 索引里的标签全称（用户口语常省略「版」字）
_VERSION_ALIAS = {
    "北师大": "北师大版", "人教": "人教版", "部编": "统编版", "统编": "统编版",
    "沪教": "沪教版", "苏教": "苏教版", "外研": "外研版", "冀教": "冀教版",
    "湘教": "湘教版", "粤教": "粤教版", "沪科": "沪科版", "浙教": "浙教版",
    "青岛": "青岛版", "西师": "西师大版", "华师": "华东师大版",
    "人美": "人民美术出版社", "人音": "人民音乐出版社",
}


def _textbook_hay(r):
    title = (r.get("global_title") or {}).get("zh-CN") or r.get("title") or ""
    tags = " ".join(str(t.get("tag_name") or "") for t in (r.get("tag_list") or [])
                    if isinstance(t, dict))
    return title + " " + tags


def _tokens_from_keyword(kw, vocab):
    """把「北师大版七年级上册数学」这类连写口语拆成索引里的标签词。"""
    s = re.sub(r"[\s　·、,，]+", "", kw or "")
    vocab_sorted = sorted(vocab, key=len, reverse=True)
    toks, i = [], 0
    while i < len(s):
        hit = next((v for v in vocab_sorted if s.startswith(v, i)), None)
        if hit:
            toks.append(hit)
            i += len(hit)
            continue
        alias = next((a for a in sorted(_VERSION_ALIAS, key=len, reverse=True)
                      if s.startswith(a, i)), None)
        if alias:
            toks.append(_VERSION_ALIAS[alias])
            i += len(alias)
        else:
            i += 1
    # 去重保序
    return list(dict.fromkeys(toks))


def search_textbook(keyword, list_n=0):
    """按课本名搜索教材（书名/版本/学科/年级/册次），返回最佳命中的教材元数据。

    平台搜索 API 对匿名请求返回 403，因此这里走 tch_material 匿名整库索引
    （data_version.json → part_*.json），本地离线检索。索引约 3500 条，1~2 秒。
    """
    kw = (keyword or "").strip()
    if not kw:
        raise RuntimeError("搜索关键词为空")
    log(f"[搜索] 在教材索引中检索「{kw}」…")
    idx = core.fetch_tch_material_index()
    if not idx:
        raise RuntimeError("教材索引拉取失败（网络或 CDN 不可达）")

    # 用索引自身的标签构建词表（版本/学科/年级/册次/学段），再按最长匹配切词
    vocab = set()
    for r in idx:
        for t in r.get("tag_list") or []:
            if isinstance(t, dict) and t.get("tag_dimension_id") in MATCH_DIMS:
                if t.get("tag_name"):
                    vocab.add(str(t["tag_name"]))
    toks = _tokens_from_keyword(kw, vocab)

    hits = [r for r in idx if all(t in _textbook_hay(r) for t in toks)] if toks else []
    if not hits:  # 兜底：整串模糊匹配
        hits = core.search_tch_material(kw, index=idx)
    if not hits:
        raise RuntimeError(f"未检索到与「{kw}」相关的教材"
                           + (f"（已识别词：{'/'.join(toks)}）" if toks else ""))

    def _title(r):
        return (r.get("global_title") or {}).get("zh-CN") or r.get("title") or ""

    def _score(r):
        title = _title(r)
        s = sum(20 for t in toks if t in title)
        if "新教材" in _textbook_hay(r):
            s += 15
        # 新版课标教材优先
        if "2022年版" in title or "2024" in title or "2025" in title:
            s += 12
        s -= max(0, len(title) - 40) // 10
        return s

    hits.sort(key=_score, reverse=True)
    if list_n and list_n > 0:
        print(f"\n[搜索] 命中 {len(hits)} 条，前 {min(list_n, len(hits))} 条：")
        for i, h in enumerate(hits[:list_n], 1):
            tags = " ".join(str(t.get("tag_name") or "") for t in (h.get("tag_list") or [])
                            if isinstance(t, dict))
            print(f"  {i:>3}. {_title(h)}")
            print(f"       id={h.get('id')}  标签={tags}")
    best = hits[0]
    log(f"[搜索] 采用：《{_title(best)}》  id={best.get('id')}"
        + (f"（另有 {len(hits)-1} 条候选）" if len(hits) > 1 else ""))
    return best


def resolve_source(given_id, token, source="auto"):
    """返回 (pack_id, book_title, chapter_of, entries, mode)。

    mode=prepare: given_id 本身即课程包 ID，直接走备课分片（无全站索引）
    mode=legacy : given_id 是教材 ID，先按 tag 匹配课程包，再走备课分片
    """
    if source in ("auto", "prepare"):
        ok, _ = probe_prepare_pack(given_id)
        if ok:
            log(f"[识别] {given_id} = 课程包 ID，使用备课快通道（匿名解析）")
            entries = fetch_lesson_entries_prepare(given_id)
            entries = [e for e in entries
                       if e.get("resource_type_code") in (None, "national_lesson")]
            title = infer_book_title(entries) or f"smartedu_{given_id[:8]}"
            chapter_of = fetch_tree_chapters(given_id, None)
            return given_id, title, chapter_of, entries, "prepare"
        if source == "prepare":
            raise RuntimeError("--source prepare 指定了快通道，但该 ID 不是课程包 ID")

    log(f"[识别] {given_id} 不是课程包 ID，按教材 ID 处理（需按标签匹配课程包）")
    book_title, tags = textbook_tags(given_id, token)
    pack_id, pack_title, cands = find_course_pack(tags, token)
    if not pack_id:
        raise RuntimeError("未在索引中匹配到课程包（标签不匹配）")
    log(f"[识别] 课程包：{pack_title}  ({pack_id})"
        + (f"，候选 {len(cands)} 个" if len(cands) > 1 else ""))
    # 拿到 pack 后统一走备课快通道取数据（比 national_lesson 分片更全且匿名）
    try:
        entries = fetch_lesson_entries_prepare(pack_id)
        entries = [e for e in entries
                   if e.get("resource_type_code") in (None, "national_lesson")]
        chapter_of = fetch_tree_chapters(pack_id, None)
    except Exception as e:
        log(f"[回退] 备课分片不可用（{e}），改用 national_lesson 分片")
        entries = fetch_lesson_entries(pack_id, token)
        entries = [e for e in entries
                   if e.get("resource_type_code") in (None, "national_lesson")]
        chapter_of = fetch_tree_chapters(pack_id, token)
    # 书名优先取「版本+学科+年级+册次」（如「北师大版数学七年级上册」），
    # 比教材详情里的官方全称更适合做目录名
    short_title = infer_book_title(entries) or book_title
    return pack_id, short_title, chapter_of, entries, "legacy"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description="教材整册课程资源批量下载（纯 API）")
    ap.add_argument("--url", help="教材详情页 URL（含 teachingmaterialId）")
    ap.add_argument("--id", dest="teachingmaterial_id",
                    help="教材 ID 或 课程包 ID（自动识别，两种都支持）")
    ap.add_argument("--search", help="按课本名搜索（书名/版本/学科/年级/册次），如「北师大版七年级上册数学」")
    ap.add_argument("--list", dest="list_n", type=int, default=0,
                    help="配合 --search：打印前 N 条候选（仍取最佳一条下载）")
    ap.add_argument("--pack-id", help="显式指定课程包 ID（备课分片 ID）")
    ap.add_argument("--source", default="auto", choices=["auto", "prepare", "legacy"],
                    help="auto=自动识别（默认）；prepare=强制当课程包 ID；legacy=强制当教材 ID")
    ap.add_argument("--out", help="输出根目录（默认 ./<教材名>）")
    ap.add_argument("--inspect", action="store_true", help="仅列出章节/课时/资源数量，不下载")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个课时（试跑）")
    ap.add_argument("--workers", type=int, default=4, help="课时并发数（默认 4，范围 1-8）")
    ap.add_argument("--only-video", action="store_true", help="只下载视频")
    ap.add_argument("--only", help="只下载指定类型：video,courseware,plan,task,exercise")
    ap.add_argument("--quality", default="720", choices=["720", "480", "360"], help="视频清晰度")
    ap.add_argument("--no-pdf", action="store_true", help="转换后删除中间 PDF")
    ap.add_argument("--force", action="store_true", help="强制重下（默认跳过已存在的成品文件）")
    ap.add_argument("--keep-ts", action="store_true", help="保留 _ts_ 临时分片目录（默认结束后清理）")
    ap.add_argument("--token", help="access_token")
    ap.add_argument("--token-file", help="token 文件路径")
    args = ap.parse_args(argv)

    tid = (extract_tid(args.url)
           or extract_tid(args.pack_id)
           or extract_tid(args.teachingmaterial_id))
    if args.search and not tid:
        try:
            hit = search_textbook(args.search, args.list_n)
        except Exception as e:
            print(f"搜索失败: {e}")
            sys.exit(1)
        tid = hit.get("id")
    if not tid:
        print("请提供 --search（按课本名搜索）、--url（含 teachingmaterialId）、--id 或 --pack-id。")
        sys.exit(2)

    skill_root = os.path.dirname(SCRIPT_DIR)
    ensure_deps()  # 惰性导入 fitz/pptx/docx/Crypto，run_resources 依赖这些全局
    token, mac_key = load_token(args, skill_root)
    if not token:
        log("[token] 未找到 access_token —— 课时结构仍可解析（匿名），"
            "但文件下载大概率 403，建议先运行 token_manager.py acquire")

    # Step 1-4: 一次性解析出 pack / 章节 / 课时
    log("\n[1/3] 解析教材结构…")
    try:
        pack_id, book_title, chapter_of, entries, mode = resolve_source(tid, token, args.source)
    except Exception as e:
        print(f"解析失败: {e}")
        sys.exit(1)

    chapters = sorted({v[0] for v in chapter_of.values() if v[0]})
    log(f"      书名：{book_title}")
    log(f"      课程包：{pack_id}  [{mode}]")
    log(f"      章节：{len(chapters)} 章 / {len(chapter_of)} 个节点；课时：{len(entries)} 个")

    if args.limit and args.limit > 0:
        entries = entries[: args.limit]
        log(f"      --limit {args.limit}，本次只处理 {len(entries)} 个")

    # 输出目录
    safe_book = re.sub(r'[\\/:*?"<>|]', "_", book_title).strip() or f"smartedu_{tid[:8]}"
    out_root = args.out or os.path.join(os.getcwd(), safe_book)
    os.makedirs(out_root, exist_ok=True)
    log(f"      输出目录：{os.path.abspath(out_root)}")

    # Step 5: 下载
    if args.inspect:
        print("\n[预览] 课时清单（不下载）")
        for i, e in enumerate(entries, 1):
            cid = (e.get("chapter_ids") or [None])[-1]
            ch, sec = chapter_of.get(cid, ("?", e.get("title") or "?"))
            rel = (e.get("relations") or {}).get("national_course_resource") or []
            kinds = {}
            for r in rel:
                k = r.get("resource_type_code", "?")
                kinds[k] = kinds.get(k, 0) + 1
            kstr = ",".join(f"{k}×{v}" for k, v in sorted(kinds.items())) or "无"
            print(f"  [{i:>2}/{len(entries)}] {ch} / {sec}\n"
                  f"        资源：{kstr}   id={e.get('id')}")
        print(f"\n合计 {len(entries)} 课。去掉 --inspect 即开始下载。")
        return

    print(f"\n[2/3] 开始下载（{args.workers} 课并发，视频内部 16 线程 HLS）\n" + "=" * 70)
    t0 = time.time()
    all_ok, all_fail = [], []
    done = 0
    total = len(entries)

    def task(i, e):
        return download_one_lesson(i, total, e, chapter_of, out_root, args, token,
                                   ffmpeg, mac_key, source=mode)

    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as ex:
        futures = {ex.submit(task, i, e): e for i, e in enumerate(entries, 1)}
        for fut in as_completed(futures):
            try:
                title, ok, fail = fut.result()
            except Exception as e:
                log(f"[异常] {e}")
                continue
            all_ok.extend(ok)
            all_fail.extend(fail)
            done += 1
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            log(f"[进度] {done}/{total} 课完成 | {rate:.2f} 课/分 | ETA ~{eta/60:.1f} 分 "
                f"| 文件 {len(all_ok)} 成功 / {len(all_fail)} 失败")

    print("=" * 70)
    print(f"完成：{done}/{total} 课，成功 {len(all_ok)} 个文件，失败 {len(all_fail)} 个")
    print(f"输出目录：{os.path.abspath(out_root)}")
    print(f"耗时：{(time.time()-t0)/60:.1f} 分钟")

    if not args.keep_ts:
        cleanup_leftover_ts(out_root)

    if all_fail:
        print("\n失败明细：")
        for t, k, e in all_fail[:40]:
            print(f"  - {t} [{k}] {e}")

    # 落盘清单
    manifest = os.path.join(out_root, "_volume_manifest.json")
    Path(manifest).write_text(json.dumps({
        "input_id": tid, "textbook_title": book_title,
        "course_pack": {"id": pack_id, "mode": mode},
        "lessons": total,
        "success_files": all_ok, "failed": [{"title": t, "type": k, "error": e} for t, k, e in all_fail],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"清单：{manifest}")


if __name__ == "__main__":
    main()
