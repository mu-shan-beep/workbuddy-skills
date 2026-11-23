#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国家中小学智慧教育平台（basic.smartedu.cn）课程包下载器

功能：
  - 通过 activityId 拉取课程资源清单（公开接口，无需登录）
  - 使用用户提供的 access_token 通过 X-ND-AUTH 头下载受保护资源
  - 视频课程：AES-128 加密 HLS(m3u8) -> 取密钥 -> 逐分片解密 -> ffmpeg 合并为 mp4
  - 课件：PDF -> pptx（整页图片保真）
  - 教学设计/学习任务单/课后练习：PDF -> docx（文本可编辑；纯图页转嵌图）

用法：
  python download_course.py --activity-id <ID> --token <ACCESS_TOKEN> [--out DIR] [--quality 720] [--keep-pdf]
  python download_course.py --activity-id <ID> --token-file token.txt [--out DIR] [--quality 720]

说明：
  - token 来自已登录浏览器：推荐用 token_helper.py 一键书签自动获取。
    手动路径：DevTools -> Application -> Local Storage -> 找含 access_token 的键。
  - token 有时效（通常数小时），失效后重取即可。
"""

import argparse
import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
import shutil

# 复用提炼后的核心算法（并发HLS、多副本文档回退、路由识别、标题/视频/文档挑选）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import smartedu_core as core

SKILL_BASE = os.path.dirname(os.path.abspath(__file__))
DETAIL_URL = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/resources/details/{activity_id}.json"

# resource_type_code -> (中文子目录, 目标扩展名)
DIRMAP = {
    "micro_lesson_video": ("视频课程", ".mp4"),
    "coursewares": ("课件", ".pptx"),
    "lesson_plandesign": ("教学设计", ".docx"),
    "learning_task": ("学习任务单", ".docx"),
    "after_class_exercise": ("课后练习", ".docx"),
}


def extract_access_token(raw):
    """兼容裸 token 或 JSON 包装 value。"""
    raw = raw.strip()
    if not raw:
        return None
    # 裸 token：无空白
    if len(raw.split()) == 1:
        return raw
    # 外层 JSON 包装
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "value" in obj and isinstance(obj["value"], str):
            inner = json.loads(obj["value"])
            if isinstance(inner, dict) and "access_token" in inner:
                return inner["access_token"]
    except Exception:
        pass
    # 直接是内层 JSON
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "access_token" in obj:
            return obj["access_token"]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 依赖自动安装
# ---------------------------------------------------------------------------
def ensure_deps():
    mod_to_pkg = {
        "fitz": "PyMuPDF",
        "pptx": "python-pptx",
        "docx": "python-docx",
        "Crypto": "pycryptodome",
        "imageio_ffmpeg": "imageio-ffmpeg",
    }
    missing = []
    for mod in mod_to_pkg:
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    if missing:
        print(f"[依赖] 缺少 {missing}，正在自动安装（需联网）...")
        pkgs = [mod_to_pkg[m] for m in missing]
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *pkgs])
        except subprocess.CalledProcessError as e:
            print("[依赖] 安装失败，请手动执行：")
            print(f"        {sys.executable} -m pip install {' '.join(pkgs)}")
            raise
    # 惰性导入（安装完成后才可用）
    global fitz, Presentation, Inches, Document, AES, unpad, imageio_ffmpeg
    import fitz  # PyMuPDF
    from pptx import Presentation
    from pptx.util import Inches
    from docx import Document
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    import imageio_ffmpeg


# ---------------------------------------------------------------------------
# 网络请求（支持 X-ND-AUTH 和 Bearer 两种鉴权）
# ---------------------------------------------------------------------------
def make_headers(token, use_bearer=False):
    """
    生成请求头。
    - use_bearer=False: 使用 X-ND-AUTH MAC 弱签名（适用于清单接口等）
    - use_bearer=True:  使用 Authorization: Bearer（适用于视频/文件下载）
    """
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ref = "https://basic.smartedu.cn/"
    if use_bearer:
        return {
            "User-Agent": ua,
            "Referer": ref,
            "Authorization": f"Bearer {token}",
        }
    else:
        auth = f'MAC id="{token}",nonce="0",mac="0"'
        return {
            "X-ND-AUTH": auth,
            "User-Agent": ua,
            "Referer": ref,
        }


def http_get_bytes(url, headers, timeout=60):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_get_json(url, headers, timeout=60):
    return json.loads(http_get_bytes(url, headers, timeout).decode("utf-8"))


# ---------------------------------------------------------------------------
# 清单解析
# ---------------------------------------------------------------------------
def get_course_title(detail):
    for key in ("global_title", "title"):
        v = detail.get(key)
        if isinstance(v, dict):
            return v.get("zh-CN") or v.get("zh") or v.get("en") or ""
    return ""


def pick_video_url(r, quality):
    """按用户指定的清晰度（720/480/360）或默认优先级选择 m3u8 地址。"""
    flag_pri = {
        "href-720p-m3u8": 5,
        "href-480p-m3u8": 4,
        "href-360p-m3u8": 3,
        "href-m3u8": 2,
        "href": 1,
    }
    qflag = {"720": "href-720p-m3u8", "480": "href-480p-m3u8", "360": "href-360p-m3u8"}
    best = None
    for ti in r.get("ti_items", []):
        if ti.get("ti_format") != "m3u8":
            continue
        f = ti.get("ti_file_flag", "")
        if f not in flag_pri:
            continue
        pri = flag_pri[f]
        if best is None or pri > best[0]:
            best = (pri, ti.get("ti_storages", []))
    if not best or not best[1]:
        return None
    stores = best[1]
    if quality in qflag and any(qflag[quality] == ti.get("ti_file_flag") for ti in r.get("ti_items", [])):
        for ti in r.get("ti_items", []):
            if ti.get("ti_file_flag") == qflag[quality] and ti.get("ti_storages"):
                return ti["ti_storages"][0]
    return stores[0]


def pick_pdf_url(r):
    for ti in r.get("ti_items", []):
        if ti.get("ti_format") == "pdf":
            return ti.get("ti_storages")
    for ti in r.get("ti_items", []):
        if "pdf" in (ti.get("ti_file_flag") or ""):
            return ti.get("ti_storages")
    return None


# ---------------------------------------------------------------------------
# PDF -> PPTX / DOCX
# ---------------------------------------------------------------------------
def pdf_to_pptx(pdf_path, pptx_path):
    doc = fitz.open(pdf_path)
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        bio = io.BytesIO(pix.tobytes("png"))
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_picture(bio, 0, 0, width=prs.slide_width, height=prs.slide_height)
    prs.save(pptx_path)
    doc.close()


def pdf_to_docx(pdf_path, docx_path):
    doc = fitz.open(pdf_path)
    wd = Document()
    for i, page in enumerate(doc):
        txt = page.get_text("text")
        if txt.strip():
            for line in txt.split("\n"):
                if line.strip():
                    wd.add_paragraph(line)
        else:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            bio = io.BytesIO(pix.tobytes("png"))
            wd.add_picture(bio, width=Inches(6.0))
        if i < len(doc) - 1:
            wd.add_page_break()
    wd.save(docx_path)
    doc.close()


# ---------------------------------------------------------------------------
# 加密视频：取密钥 -> 解密分片 -> 合并 mp4
# ---------------------------------------------------------------------------
def download_video(m3u8_url, dest, token, ffmpeg):
    """
    下载并解密 AES-128 加密的 HLS 视频。

    认证分离：
    - m3u8 索引 + ts 分片：使用 Bearer 认证 (Authorization: Bearer <token>)
    - 密钥服务器：使用 X-ND-AUTH 认证 (MAC id="<token>",nonce="0",mac="0")

    Args:
        m3u8_url: 视频播放列表 URL
        dest: 输出 mp4 文件路径
        token: access_token 字符串（裸值，非 JSON）
        ffmpeg: ffmpeg 可执行文件路径
    """
    import hashlib, base64
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad

    print("   拉取 m3u8 索引...")
    # Bearer 认证获取 m3u8 和 ts 分片
    bearer_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://basic.smartedu.cn/",
        "Authorization": f"Bearer {token}",
    }
    m3u8_text = http_get_bytes(m3u8_url, bearer_headers, 60).decode("utf-8")

    keyline = next(l for l in m3u8_text.splitlines() if l.startswith("#EXT-X-KEY"))
    muri = re.search(r'URI="([^"]+)"', keyline).group(1)
    miv = re.search(r"IV=0x([0-9A-Fa-f]+)", keyline)
    iv = bytes.fromhex(miv.group(1)) if miv else bytes(16)
    key_id = muri.rstrip("/").split("/")[-1]

    # X-ND-AUTH 认证访问密钥服务器
    mac_headers = {
        "X-ND-AUTH": f'MAC id="{token}",nonce="0",mac="0"',
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://basic.smartedu.cn/",
    }

    print("   获取解密密钥（signs -> MD5 sign -> key -> AES-ECB 解真密钥）...")
    sign_json = http_get_json(muri + "/signs", mac_headers, 30)
    nonce = sign_json["nonce"]
    sign = hashlib.md5((nonce + key_id).encode()).hexdigest()[:16]
    key_json = http_get_json(f"{muri}?nonce={nonce}&sign={sign}", mac_headers, 30)
    enc_key = base64.b64decode(key_json["key"])
    dec_key = unpad(AES.new(sign.encode(), AES.MODE_ECB).decrypt(enc_key), 16)
    print(f"   密钥就绪 (sign={sign[:8]}...)，解密 {len([l for l in m3u8_text.splitlines() if l and not l.startswith('#')])} 个分片...")

    base = m3u8_url[: m3u8_url.rfind("/") + 1]
    segs = [l for l in m3u8_text.splitlines() if l and not l.startswith("#")]
    tmpdir = os.path.join(os.path.dirname(dest), "_ts_" + os.path.basename(dest).replace(".", "_"))
    os.makedirs(tmpdir, exist_ok=True)
    ts_files = []
    for i, seg in enumerate(segs):
        if not seg.startswith("http"):
            seg = base + seg
        print(f"   下载分片 {i+1}/{len(segs)}...", end=" ", flush=True)
        # 重试机制：网络不稳定时可能 IncompleteRead 或 400
        max_retries = 5
        for attempt in range(max_retries):
            try:
                data = http_get_bytes(seg, bearer_headers, 120)
                pt = unpad(AES.new(dec_key, AES.MODE_CBC, iv).decrypt(data), 16)
                tf = os.path.join(tmpdir, f"{i:05d}.ts")
                with open(tf, "wb") as f:
                    f.write(pt)
                print(f"OK ({len(data)//1024}KB)")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 2 * (attempt + 1)  # 递增延迟：2s, 4s, 6s, 8s
                    print(f"失败，{delay}s后重试...", end=" ", flush=True)
                    time.sleep(delay)
                else:
                    print(f"最终失败: {e}")
                    raise
        ts_files.append(tf)

    combined = os.path.join(tmpdir, "combined.ts")
    with open(combined, "wb") as out:
        for tf in ts_files:
            with open(tf, "rb") as f:
                out.write(f.read())

    print("   封装为 mp4（不重编码）...")
    subprocess.run(
        [ffmpeg, "-i", combined, "-c", "copy", "-bsf:a", "aac_adtstoasc",
         "-fflags", "+genpts", "-y", dest],
        check=True, capture_output=True, timeout=900,
    )
    # 清理临时分片目录（自动，无需用户确认）
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 实验课（/syncClassroom/experimentLesson?courseId=&classHourId=）
#   该页面为 SPA，真实资源经以下链路加载：
#     jK(courseId) -> GET /ndrs/experiment/teachingmaterials/<courseId>/resources/parts.json
#     parts.json 为分部件 URL 列表，逐个 GET 其 detail（含 ti_items / m3u8）
#   接口同样走 X-ND-AUTH 弱签名（仅需 access_token），与标准课程一致。
# ---------------------------------------------------------------------------
def find_m3u8_urls(obj, path="", out=None):
    """递归收集 JSON 中所有以 .m3u8 结尾的字符串。"""
    if out is None:
        out = []
    if isinstance(obj, str):
        if ".m3u8" in obj:
            out.append((path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            find_m3u8_urls(v, path + "/" + str(k), out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_m3u8_urls(v, path + f"[{i}]", out)
    return out


def pick_best_m3u8(m3s, quality):
    """m3s: list of (path, url)。优先匹配清晰度，否则取第一个。"""
    qmap = {"720": "720p", "480": "480p", "360": "360p"}
    for _path, url in m3s:
        if quality in qmap and qmap[quality] in url:
            return url
    # ti_items 结构里常以 href-720p-m3u8 为 file_flag，url 含 720p
    return m3s[0][1]


def run_experiment(args, headers, ffmpeg):
    cid = args.course_id
    chid = args.class_hour_id or "lesson_1"
    hosts = [
        f"https://basic.smartedu.cn/ndrs/experiment/teachingmaterials/{cid}/resources/parts.json",
        f"https://bdcs-file-2.ykt.cbern.com.cn/zxx_secondary/ndrs/experiment/teachingmaterials/{cid}/resources/parts.json",
    ]
    parts = None
    last_err = None
    for u in hosts:
        try:
            parts = http_get_json(u, headers, 60)
            print(f"[实验课] parts.json 取自 {u}")
            break
        except urllib.error.HTTPError as e:
            last_err = e
            print(f"[实验课] {u} -> HTTP {e.code}")
        except Exception as e:
            last_err = e
            print(f"[实验课] {u} -> {e}")
    if parts is None:
        print("[实验课] 无法获取 parts.json（鉴权失败或 courseId 错误）。")
        if last_err:
            print("  最后错误:", last_err)
        sys.exit(1)

    out_root = args.out or os.path.join(os.getcwd(), f"smartedu_exp_{cid}")
    os.makedirs(out_root, exist_ok=True)
    with open(os.path.join(out_root, "_exp_parts.json"), "w", encoding="utf-8") as f:
        json.dump(parts, f, ensure_ascii=False, indent=2)
    print(f"[实验课] parts.json 类型: {type(parts).__name__}，已转储 _exp_parts.json")

    if args.inspect:
        print(json.dumps(parts, ensure_ascii=False, indent=2)[:4000])
        return

    # parts.json 通常为分部件 URL 列表
    urls = parts if isinstance(parts, list) else (parts.get("data") or parts.get("items") or [])
    if not isinstance(urls, list):
        print("[实验课] parts.json 不是预期的列表结构，请查看 _exp_parts.json")
        sys.exit(1)
    print(f"[实验课] 共 {len(urls)} 个分部件，开始匹配 classHourId={chid}")

    candidates = []  # (idx, det, m3s, is_match)
    for idx, u in enumerate(urls):
        try:
            det = http_get_json(u, headers, 60) if isinstance(u, str) else u
        except Exception as e:
            print(f"  分部件 #{idx} 获取失败: {e}")
            continue
        with open(os.path.join(out_root, f"_exp_part_{idx}.json"), "w", encoding="utf-8") as f:
            json.dump(det, f, ensure_ascii=False, indent=2)
        m3s = find_m3u8_urls(det)
        blob = json.dumps(det, ensure_ascii=False)
        is_match = bool(chid and chid in blob)
        print(f"  分部件 #{idx}: m3u8={len(m3s)}, 命中[{chid}]={is_match}")
        if m3s:
            candidates.append((idx, det, m3s, is_match))

    if not candidates:
        print("[实验课] 未找到任何含视频的分部件。已转储 _exp_part_*.json 供排查。")
        sys.exit(1)

    match = [c for c in candidates if c[3]]
    chosen = match[0] if match else candidates[0]
    idx, det, m3s, _ = chosen
    print(f"[实验课] 选定分部件 #{idx}（共 {len(m3s)} 个 m3u8 候选）")
    m3u8 = pick_best_m3u8(m3s, args.quality)
    print(f"[实验课] 视频源: {m3u8[:100]}")
    dest = os.path.join(out_root, f"{chid}.mp4")
    download_video(m3u8, dest, headers, ffmpeg)
    print("[实验课] 完成 ->", dest)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def extract_by_shape(detail, shape):
    """按 shape 从详情 JSON 中提取资源列表。

    shape 形态：
      - "relations:<key>"  -> detail["relations"][key]
      - "single"           -> 详情本身即资源
      - "auto"             -> 自适应（ti_items 优先，否则扫 relations 首个有效列表）
    """
    if not isinstance(detail, dict):
        return []
    if shape.startswith("relations:"):
        key = shape.split(":", 1)[1]
        rel = detail.get("relations") or {}
        v = rel.get(key)
        return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []
    if shape == "single":
        return [detail] if detail.get("ti_items") else []
    return extract_auto(detail)


def extract_auto(detail):
    """自适应提取：自身带 ti_items 则单资源，否则取 relations 中首个有效列表。"""
    if not isinstance(detail, dict):
        return []
    if detail.get("ti_items"):
        return [detail]
    for _k, v in (detail.get("relations") or {}).items():
        if isinstance(v, list) and v and isinstance(v[0], dict) \
                and ("ti_items" in v[0] or "resource_type_code" in v[0]):
            return [x for x in v if isinstance(x, dict)]
    return []


def resolve_detail_from_url(url, token):
    """由任意智慧平台 URL 解析 (detail_json, resources)。

    支持 qualityCourse / classActivity / tchMaterial / experiment 等路由，
    逐个尝试 DETAIL_CANDIDATES 模板（匿名优先，带 token 兜底），
    命中即返回；全部失败再对 rid 走全目录兜底探测。
    """
    api_key, rid = core.detect_smartedu_url(url)
    if not rid:
        raise RuntimeError("无法从 URL 解析出资源 ID：%s" % url)
    print(f"[路由] 识别为 {api_key}，rid={rid}")

    tried = []
    for tpl, shape in (core.DETAIL_CANDIDATES.get(api_key) or []):
        u = tpl.format(rid=rid)
        try:
            data = core.fetch_json_tolerant(u, token, 60)
        except Exception as e:
            tried.append((u, str(e)[:80]))
            continue
        res = extract_by_shape(data, shape) or extract_auto(data)
        if res:
            print(f"[清单] 命中 {u}")
            return data, res
        tried.append((u, "无资源"))

    # 兜底：全目录并发探测
    print(f"[清单] 主路由未命中，转全目录兜底探测（{len(core.ALL_DETAIL_CANDIDATES)} 候选）")
    for tpl, shape in core.ALL_DETAIL_CANDIDATES:
        u = tpl.format(rid=rid)
        try:
            data = core.fetch_json_tolerant(u, token, 30)
        except Exception:
            continue
        res = extract_by_shape(data, shape) or extract_auto(data)
        if res:
            print(f"[清单] 兜底命中 {u}")
            return data, res
    raise RuntimeError("所有候选接口均未解析到资源。最近尝试：%s" % tried[-3:])


# 原生（非 PDF 转码）文档格式：命中则直接落盘，不再走 PDF→Office 的有损转换
NATIVE_DOC_EXT = {"pptx", "ppt", "docx", "doc", "xlsx", "xls", "txt", "ofd"}

# --only 别名 → resource_type_code
ONLY_ALIAS = {
    "video": ("micro_lesson_video", "assets_video", "experiment_video"),
    "courseware": ("coursewares",),
    "plan": ("lesson_plandesign",),
    "task": ("learning_task",),
    "exercise": ("after_class_exercise",),
}


def pick_doc_native(r):
    """优先挑原生 Office 格式(pptx/docx/...)，其次退回 PDF 转码副本。

    平台 ti_items 常同时给出原生文件与 PDF 预览件；直接取原生可避免
    「PDF→PPTX 逐页转图片」导致的文字丢失与体积膨胀。
    """
    for ti in (r.get("ti_items") or []):
        f = (ti.get("ti_format") or "").lower()
        if f in NATIVE_DOC_EXT and ti.get("ti_storages"):
            return list(ti["ti_storages"]), f
    return core.pick_pdf_url(r)


def resolve_only_set(args):
    """把 --only / --only-video 解析成允许的 resource_type_code 集合（None=不限制）。"""
    if args.only:
        wanted = set()
        for part in args.only.split(","):
            key = part.strip().lower()
            if not key:
                continue
            if key in ONLY_ALIAS:
                wanted.update(ONLY_ALIAS[key])
            else:
                wanted.add(key)
        return wanted
    if getattr(args, "only_video", False):
        return set(ONLY_ALIAS["video"])
    return None


def count_video_resources(resources, args=None):
    """统计「--only 过滤后」仍会下载的视频资源数量。

    过滤发生在 run_resources() 内部，所以这里必须同步应用 only_set，
    否则 --only courseware（只要课件）时也会把全集的视频算进来而误报。
    """
    only_set = resolve_only_set(args) if args is not None else None
    n = 0
    for r in resources:
        if not isinstance(r, dict):
            continue
        rtype = r.get("resource_type_code") or ""
        if only_set is not None and rtype not in only_set:
            continue
        if rtype in ONLY_ALIAS["video"] or "video" in str(rtype).lower():
            n += 1
    return n


def run_resources(resources, out_root, args, token, ffmpeg, mac_key=""):
    """按 DIRMAP 下载/转换资源列表，返回 (success, failed)。"""
    only_set = resolve_only_set(args)
    success, failed = [], []
    for r in resources:
        rtitle = r.get("global_title", {}).get("zh-CN", "未命名") if isinstance(r.get("global_title"), dict) \
            else (r.get("global_title") or "未命名")
        rtype = r.get("resource_type_code", "")
        if only_set is not None and rtype not in only_set:
            print(f"\n=== 跳过（非指定类型）: {rtitle} [{rtype}]")
            continue
        sub, ext = DIRMAP.get(rtype, (rtype, ".bin"))
        # 标题本身常带扩展名（如「快乐读书吧.mp4」），去掉避免出现 xxx.mp4.mp4
        if isinstance(rtitle, str) and rtitle.lower().endswith(ext.lower()):
            rtitle = rtitle[: -len(ext)]
        ddir = os.path.join(out_root, sub)
        os.makedirs(ddir, exist_ok=True)
        dest = os.path.join(ddir, rtitle + ext)
        print(f"\n=== {rtitle} [{rtype}] -> {dest}")
        try:
            if rtype in ("micro_lesson_video", "assets_video", "experiment_video"):
                m3u8 = core.pick_video_url(r, args.quality)
                if not m3u8:
                    raise Exception("未找到 m3u8 视频地址")
                print("   视频源:", m3u8[:80])
                # 并发HLS：16线程 + 密钥缓存 + 去 combined.ts + TS 降级
                core.download_hls(m3u8, dest, token, ffmpeg, args.quality)
            else:
                stores, fmt = pick_doc_native(r)
                if not stores:
                    raise Exception("未找到文档地址")
                fmt = (fmt or "").lower()
                if fmt in NATIVE_DOC_EXT:
                    # 原生 pptx/docx：直接落盘，保留可编辑性
                    native_path = os.path.join(ddir, rtitle + "." + fmt)
                    core.download_doc_to_file(stores, native_path, token, 120, mac_key=mac_key)
                    print(f"   原生 {fmt} 下载 {os.path.getsize(native_path)} 字节")
                    success.append(native_path)
                    continue
                pdf_path = os.path.join(ddir, rtitle + ".pdf")
                # 多副本 × 主机变体 × 匿名回退
                core.download_doc_to_file(stores, pdf_path, token, 120, mac_key=mac_key)
                print(f"   PDF 下载 {os.path.getsize(pdf_path)} 字节")
                if rtype == "coursewares":
                    pdf_to_pptx(pdf_path, dest)
                else:
                    pdf_to_docx(pdf_path, dest)
                print(f"   已转换 -> {ext}")
                if args.no_pdf:
                    try:
                        os.remove(pdf_path)
                    except Exception:
                        pass
            success.append(dest)
        except Exception as e:
            print("   失败:", e)
            failed.append((rtitle, rtype, str(e)))
    return success, failed


def main():
    ap = argparse.ArgumentParser(description="国家中小学智慧教育平台课程包下载器")
    ap.add_argument("--activity-id", help="课程 activityId（URL 中 activityId= 后的字符串）；或改用 --experiment 模式")
    ap.add_argument("--url", help="任意智慧平台资源 URL（qualityCourse/classActivity/tchMaterial 等），自动识别路由")
    ap.add_argument("--only-video", action="store_true", help="只下载视频类资源，跳过课件/文档")
    ap.add_argument("--only", default=None,
                    help="只下载指定类型，逗号分隔。支持别名 video/courseware/plan/task/exercise "
                         "或原始类型码 micro_lesson_video/coursewares/lesson_plandesign/...")
    ap.add_argument("--experiment", action="store_true", help="实验课模式：解析 /syncClassroom/experimentLesson?courseId= 链接")
    ap.add_argument("--course-id", help="实验课 courseId（URL 中 courseId= 后的字符串）")
    ap.add_argument("--class-hour-id", default="lesson_1", help="实验课课时 id，默认 lesson_1（对应 URL 中 classHourId=）")
    ap.add_argument("--inspect", action="store_true", help="仅转储接口 JSON 结构不下载（用于排查 schema）")
    ap.add_argument("--token", help="access_token；也可通过 --token-file 传入")
    ap.add_argument("--token-file", help="存放 access_token 的文本文件路径")
    ap.add_argument("--out", default=None, help="输出根目录（默认 ./<课程名> 或 ./smartedu_<activity_id>）")
    ap.add_argument("--quality", default="720", choices=["720", "480", "360"], help="视频清晰度，默认 720")
    ap.add_argument("--no-pdf", action="store_true", help="不保留平台原始 PDF 副本")
    # ---- 整册批量下载（委托 download_full_volume，按课本搜索后整册拉取）----
    ap.add_argument("--whole-book", nargs="?", const="", default=None, metavar="课本名|ID|URL",
                    help="整册下载：可传课本名（如「北师大版七年级上册数学」）、教材 ID 或教材 URL；"
                         "不传值时使用 --url 指向的教材")
    ap.add_argument("--workers", type=int, default=4, help="整册下载的课时并发数（默认 4，上限 8）")
    ap.add_argument("--limit", type=int, default=0, help="整册下载时只处理前 N 课（试跑）")
    ap.add_argument("--force", action="store_true", help="整册下载时强制重下（默认增量跳过已存在文件）")
    ap.add_argument("--keep-ts", action="store_true", help="整册下载时保留 _ts_ 临时分片目录")
    args = ap.parse_args()

    # ---- 整册批量下载：早期分流，内部复用本文件的 run_resources ----
    if args.whole_book is not None:
        import download_full_volume as _fv
        book = (args.whole_book or args.url or "").strip()
        if not book:
            print("--whole-book 需要课本名、教材 ID 或教材 URL。")
            sys.exit(2)
        fv_argv = []
        if _fv.extract_tid(book):
            fv_argv += ["--id", book]
        elif book.lower().startswith("http"):
            fv_argv += ["--url", book]
        else:
            fv_argv += ["--search", book]
        if args.out:
            fv_argv += ["--out", args.out]
        if args.workers:
            fv_argv += ["--workers", str(args.workers)]
        if args.limit:
            fv_argv += ["--limit", str(args.limit)]
        if args.only_video:
            fv_argv += ["--only-video"]
        elif args.only:
            fv_argv += ["--only", args.only]
        if args.quality:
            fv_argv += ["--quality", args.quality]
        if args.no_pdf:
            fv_argv += ["--no-pdf"]
        if args.force:
            fv_argv += ["--force"]
        if args.keep_ts:
            fv_argv += ["--keep-ts"]
        if args.inspect:
            fv_argv += ["--inspect"]
        if args.token:
            fv_argv += ["--token", args.token]
        else:
            fv_argv += ["--token-file", args.token_file or os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "smartedu_token.txt")]
        _fv.main(fv_argv)
        return

    # 取 token（统一走 token_manager：支持 --token / 文件 / 过期无感续期 / 本机 Edge 兜底）
    import token_manager as _tm
    token = None
    mac_key = ""
    # 使用 __file__ 定位技能目录，避免 cwd 影响（项目根目录可能有旧版 token.txt）
    _skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tf = args.token_file or os.path.join(_skill_root, "smartedu_token.txt")
    if args.token:
        token = args.token
    else:
        tok = _tm.get_valid_token(tf)
        if tok:
            token = tok["access_token"]
            mac_key = tok.get("mac_key") or ""
        else:
            print("缺少有效 access_token。请先运行：")
            print(f"  python token_manager.py acquire --token-file {tf}")
            sys.exit(2)

    # 【第一步】鉴权预检：确认 token 真的能被服务端接受，避免解析/下载半天才发现 401。
    # probe_token 探测 user/session 端点（Bearer）；返回 False=确定失效，None=网络异常无法判定。
    alive = _tm.probe_token(token)
    if alive is False:
        print()
        print("✗ 第一步鉴权预检失败：token 已失效（服务端返回 401/403）。")
        print("  请先续期或重新登录后再下载：")
        print(f"    python token_manager.py refresh --token-file {tf}")
        print(f"    python token_manager.py acquire --token-file {tf}")
        sys.exit(2)
    elif alive is None:
        print("⚠ 无法连接服务端做鉴权预检（网络/端点异常），将直接尝试下载。")
    else:
        print("✓ token 鉴权预检通过")

    # mac_key 缺失预警：缺它时部分依赖 MAC 强签名的文档/课件会 401（视频走 Bearer 不受影响）
    if not mac_key:
        print("⚠ 当前 token 缺少 mac_key：视频通常可下载，但部分依赖 MAC 强签名的文档/课件可能返回 401。")
        print("  建议重新登录获取完整 token：")
        print(f"    python token_manager.py acquire --token-file {tf}")

    if args.experiment:
        if not args.course_id:
            print("[实验课] 需要 --course-id 参数（URL 中 courseId= 后的字符串）")
            sys.exit(2)
        ensure_deps()
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        print("ffmpeg:", ffmpeg)
        run_experiment(args, make_headers(token), ffmpeg)
        return

    if not args.activity_id and not args.url:
        print("缺少 --activity-id 或 --url（也可改用 --experiment 模式并传入 --course-id）。")
        sys.exit(2)

    ensure_deps()
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    print("ffmpeg:", ffmpeg)

    headers = make_headers(token)  # X-ND-AUTH for all requests (works for both list and files)

    # 拉取清单：--url 自动识别路由，否则按 activityId 走 national_lesson 传统路径
    if args.url:
        print(f"[清单] 解析 URL ...")
        try:
            detail, resources = resolve_detail_from_url(args.url, token)
        except Exception as e:
            print(f"[清单] 解析失败：{e}")
            sys.exit(1)
        title = core.get_title(detail) or get_course_title(detail) or "smartedu_download"
    else:
        print(f"[清单] 下载资源清单 {args.activity_id} ...")
        try:
            detail = http_get_json(DETAIL_URL.format(activity_id=args.activity_id), headers, 60)
        except urllib.error.HTTPError as e:
            print(f"[清单] 失败 HTTP {e.code}，可能 activityId 错误或 token 失效。")
            sys.exit(1)
        resources = detail.get("relations", {}).get("national_course_resource", [])
        title = get_course_title(detail) or f"smartedu_{args.activity_id}"

    if not resources:
        print("[清单] 未解析到任何资源，请检查链接/ID。")
        sys.exit(1)

    out_root = args.out or os.path.join(os.getcwd(), title)
    os.makedirs(out_root, exist_ok=True)
    # 缓存清单便于排查
    with open(os.path.join(out_root, "_detail.json"), "w", encoding="utf-8") as f:
        json.dump(detail, f, ensure_ascii=False, indent=2)
    print(f"[清单] 课程《{title}》，共 {len(resources)} 个资源，输出至 {out_root}")

    # v2.4.0-patch1：标准课程路径此前不检查 --inspect（只有实验课 run_experiment() 里 return），
    # 结果本想「只看清单」却把全部资源都下载了。此处补上「预览即返回」。
    if getattr(args, "inspect", False):
        print("\n[预览] --inspect：仅列出资源清单，不下载任何文件")
        for i, r in enumerate(resources, 1):
            if not isinstance(r, dict):
                print("  %2d. (非预期结构) %r" % (i, r))
                continue
            rtype = r.get("resource_type_code") or r.get("resource_type") or "?"
            rtitle = core.get_title(r) or r.get("title") or ""
            if not isinstance(rtitle, str):
                rtitle = str(rtitle)
            print("  %2d. [%-22s] %s" % (i, rtype, rtitle))
        print("\n[预览] 共 %d 个资源。去掉 --inspect 即下载；"
              "可加 --only video,courseware 只挑需要的类型。" % len(resources))
        return

    # 资源地址已解析到、基本确认可下载 —— 给一句转场提示（say 强制输出，不被闸门过滤）。
    # 静默模式下没有这句，长时间并发下载会让用户以为进程卡死。
    #
    # 判断是否含视频必须基于「--only 过滤后」的集合（详见 count_video_resources 注释）
    video_cnt = count_video_resources(resources, args)

    # 转场提示：给用户活着信号（大文件下载时长可能较长）
    if video_cnt:
        print(f"正在解析下载的资源包含视频（{video_cnt} 个），容量较大，请耐心下载......")
    else:
        print("正在下载所需资源，请等待......")

    success, failed = run_resources(resources, out_root, args, token, ffmpeg, mac_key)

    print("\n===== 完成 =====")
    print(f"成功 {len(success)} 个，失败 {len(failed)} 个")
    for s in success:
        abs_path = os.path.abspath(s)
        print(f"  ✓ {abs_path}")
    for f in failed:
        print("  ✗", f)


if __name__ == "__main__":
    main()
