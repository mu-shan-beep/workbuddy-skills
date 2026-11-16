#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smartedu_core.py —— 国家中小学智慧教育平台 解析/下载核心（提炼自首创 crawler-base cb-0.1.17x）

提炼自 crawler-base/crawler_base/smartedu_native.py 的成熟算法，并保留本技能已验证的
双认证（视频 m3u8/ts 用 Bearer、密钥服务器用 MAC），叠加以下健壮性增强：

1. 路由识别 detect_smartedu_url：精准按 URL 路径片段归类（classActivity/tchMaterial/
   experiment/qualityCourse/prepare/sedu/art/reading...），unknown 一律走全目录并发兜底。
2. NDR 详情路径映射表 DETAIL_CANDIDATES：每个资源类型对应正确的 details 路径模板
   （tch_material 属 ndrs/resources/tch_material/details/，classActivity 属 ndrv2/national_lesson/...）。
3. 候选并发探测 probe_first_hit：强命中(带 ti_items)立即返回，弱命中(只有元数据)暂存，
   防止「匿名请求偶发精简版导致解析成功却 0 资源」。
4. 资源提取 extract_resources：relations:<key> / single / auto 三形态自适应。
5. 标题 get_title：同时认 global_title(zh-CN) 与 title 字符串（tch_material 只有后者）。
6. 视频/文档挑选 pick_video_url / pick_pdf_url：按 ti_file_flag 优先级选清晰度；
   pick_pdf_url 返回全部副本（r1/r2/r3）供回退。
7. 文档下载 download_doc_to_file：多副本 × 主机变体(rN-ndr → rN-ndr-private) ×
   带 token 被拒再匿名，任一成功即返回。
8. 视频下载 download_hls：并发拉分片(默认16线程，env CB_HLS_WORKERS 可调) + 密钥仅取一次
   + 去 combined.ts(改用 ffmpeg concat demuxer) + ffmpeg 日志落盘防管道死锁 +
   mp4 封装失败降级交付 TS。
9. 免浏览器整库索引 fetch_tch_material_index / tch_index_lookup：匿名可读
   data_version.json → part_N.json，按名/学科/年级检索教材 contentId（解决搜索 API 403）。

仅依赖标准库 + pycryptodome + imageio-ffmpeg(ffmpeg 路径由调用方传入)。
"""

import base64
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import tempfile
import shutil

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
except Exception:  # noqa
    ThreadPoolExecutor = None
    as_completed = None


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
BASE = "https://s-file-1.ykt.cbern.com.cn"
BASE2 = "https://s-file-2.ykt.cbern.com.cn"
BASE3 = "https://s-file-3.ykt.cbern.com.cn"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
REF = "https://basic.smartedu.cn/"
ANON_HEADERS = {"User-Agent": UA, "Referer": REF}
ANON_DOC_HEADERS = {"User-Agent": UA, "Referer": REF, "Accept-Encoding": "identity"}

DETAIL_CANDIDATES = {
    "classActivity": [
        (BASE + "/zxx/ndrv2/national_lesson/resources/details/{rid}.json", "relations:national_course_resource"),
    ],
    "experiment": [
        (BASE2 + "/zxx/ndrs/experiment/resources/details/{rid}.json", "relations:experiment_work_information"),
        (BASE + "/zxx/ndrs/experiment/resources/details/{rid}.json", "relations:experiment_work_information"),
    ],
    "qualityCourse": [
        (BASE2 + "/zxx/ndrv2/resources/{rid}.json", "relations:course_resource"),
        (BASE + "/zxx/ndrv2/resources/{rid}.json", "relations:course_resource"),
    ],
    "eliteLesson": [
        (BASE + "/competitive/elite_lesson/resources/{rid}.json", "relations:course_resource"),
        (BASE2 + "/competitive/elite_lesson/resources/{rid}.json", "relations:course_resource"),
        (BASE + "/competitive/elite_lesson/resources/details/{rid}.json", "relations:course_resource"),
        (BASE2 + "/competitive/elite_lesson/resources/details/{rid}.json", "relations:course_resource"),
        (BASE + "/zxx/ndrv2/resources/{rid}.json", "relations:course_resource"),
        (BASE2 + "/zxx/ndrv2/resources/{rid}.json", "relations:course_resource"),
        (BASE + "/zxx/ndrs/special_edu/resources/details/{rid}.json", "single"),
    ],
    "prepare": [
        (BASE2 + "/zxx/ndrv2/prepare_lesson/resources/details/{rid}.json", "relations:course_resource"),
    ],
    "prepareSubType": [
        (BASE2 + "/zxx/ndrv2/prepare_sub_type/resources/details/{rid}.json", "relations:course_resource"),
        (BASE + "/zxx/ndrv2/prepare_sub_type/resources/details/{rid}.json", "relations:course_resource"),
    ],
    "tchMaterial": [
        # 正确路径：ndrs/resources/tch_material/details/{rid}.json（无多余 resources/ 层，否则 403）
        (BASE + "/zxx/ndrs/resources/tch_material/details/{rid}.json", "single"),
        (BASE2 + "/zxx/ndrs/resources/tch_material/details/{rid}.json", "single"),
        (BASE + "/zxx/ndrv2/resources/tch_material/details/{rid}.json", "single"),
        (BASE2 + "/zxx/ndrv2/resources/tch_material/details/{rid}.json", "single"),
        (BASE + "/zxx/ndrs/resources/tch_material/details/{rid}.json", "relations:course_resource"),
        (BASE2 + "/zxx/ndrs/resources/tch_material/details/{rid}.json", "relations:course_resource"),
    ],
    "onlineJudge": [
        (BASE + "/zxx/ndrs/online_judge/resources/details/{rid}.json", "relations:course_resource"),
        (BASE2 + "/zxx/ndrs/online_judge/resources/details/{rid}.json", "relations:course_resource"),
        (BASE + "/zxx/ndrs/online_judge/resources/details/{rid}.json", "single"),
    ],
    "questions": [
        (BASE + "/zxx/ndrs/questions/resources/details/{rid}.json", "relations:course_resource"),
        (BASE2 + "/zxx/ndrs/questions/resources/details/{rid}.json", "relations:course_resource"),
        (BASE + "/zxx/ndrs/questions/resources/details/{rid}.json", "single"),
    ],
    "sedu": [
        (BASE + "/zxx/ndrs/special_edu/resources/details/{rid}.json", "single"),
        (BASE2 + "/zxx/ndrs/special_edu/resources/details/{rid}.json", "single"),
    ],
    "art": [
        (BASE + "/zxx/ndrs/special_edu/resources/details/{rid}.json", "single"),
        (BASE2 + "/zxx/ndrs/special_edu/resources/details/{rid}.json", "single"),
        (BASE + "/zxx/ndrv2/resources/{rid}.json", "relations:course_resource"),
        (BASE2 + "/zxx/ndrv2/resources/{rid}.json", "relations:course_resource"),
    ],
    "eduReform": [
        (BASE + "/zxx/ndrs/special_edu/resources/details/{rid}.json", "single"),
        (BASE2 + "/zxx/ndrs/special_edu/resources/details/{rid}.json", "single"),
        (BASE + "/zxx/ndrv2/resources/{rid}.json", "relations:course_resource"),
        (BASE2 + "/zxx/ndrv2/resources/{rid}.json", "relations:course_resource"),
    ],
    "reading": [
        ("https://s-file-1.ykt.cbern.com.cn/reading/ndrs/special_edu/resources/details/{rid}.json", "single"),
    ],
}


def _all_detail_candidates():
    """汇总所有候选（去重保序），用于泛化路由并行兜底探测。"""
    out, seen = [], set()

    def add(tpl, shp):
        if (tpl, shp) not in seen:
            seen.add((tpl, shp))
            out.append((tpl, shp))

    for key in ("classActivity", "experiment", "qualityCourse", "eliteLesson",
                "prepare", "prepareSubType", "tchMaterial", "sedu", "art", "eduReform",
                "onlineJudge", "questions"):
        for tpl, shp in DETAIL_CANDIDATES.get(key, []):
            add(tpl, shp)
    # 每个 relations 模板再补 single 形态（同一 URL 两种解析方式都试）
    for tpl, shp in list(out):
        if shp.startswith("relations:") and "special_edu" not in tpl:
            add(tpl, "single")
    return out


ALL_DETAIL_CANDIDATES = _all_detail_candidates()

TYPE_LABEL = {
    "micro_lesson_video": "视频课程",
    "assets_video": "视频",
    "coursewares": "课件",
    "lesson_plandesign": "教学设计",
    "learning_task": "学习任务单",
    "after_class_exercise": "课后练习",
    "experiment_video": "实验教学视频",
    "experiment_courseware": "课件",
    "experiment_lesson_plandesign": "实验教学设计",
    "assets_document": "文档",
    "assets_audio": "音频",
    "assets_image": "图片",
    "assets_article": "文章",
    "x_document": "教材",
}


# ---------------------------------------------------------------------------
# 认证头（保留本技能已验证的双认证：媒体 Bearer，密钥 MAC；并加 MAC/匿名回退）
# ---------------------------------------------------------------------------
def bearer_headers(token):
    return {"User-Agent": UA, "Referer": REF, "Authorization": f"Bearer {token}"}


def mac_headers(token):
    return {"X-ND-AUTH": f'MAC id="{token}",nonce="0",mac="0"', "User-Agent": UA, "Referer": REF}


def mac_headers_strong(token, mac_key):
    """带 mac_key 的强签名 MAC 头（动态 nonce + HMAC-SHA256）。

    用于 Bearer / 匿名 都被拒的文档 CDN（如 r1-ndr-private 精品课资源，对裸 Bearer
    返回 400/401），作为 download_doc_to_file 的最后一道回退。无 mac_key 时调用方
    不应把它加入 hdr_sets。
    """
    import hmac as _hmac
    import random as _random
    nonce = f"{int(time.time())}:{_random.randint(0, 9999)}"
    mac_content = f"{nonce}\nGET\nbasic.smartedu.cn\n/\n"
    mac = _hmac.new(mac_key.encode(), mac_content.encode(), hashlib.sha256).hexdigest()
    return {
        "X-ND-AUTH": f'MAC id="{token}",nonce="{nonce}",mac="{mac}"',
        "User-Agent": UA,
        "Referer": REF,
    }


def _is_auth_error(e):
    return isinstance(e, urllib.error.HTTPError) and e.code in (401, 403)


def _is_auth_ish(e):
    """可切换鉴权重试的错误码。

    实测：部分 CDN（如 r1-ndr-private 上的精品课资源）对 Bearer 返回
    HTTP 400 InvalidArgument 而非 401/403，此时必须回退 MAC，否则整课失败。
    """
    return isinstance(e, urllib.error.HTTPError) and e.code in (400, 401, 403)


# 媒体鉴权自适应：首个分片确定用 Bearer 还是 MAC，后续复用，避免每个分片都试错
_MEDIA_AUTH_PREF = {"mode": "bearer"}


def _enc_url(u):
    """对含中文/特殊字符的 URL 做 path 段编码（先 unquote 归一化，避免二次编码）。
    仅编码 path，保留 scheme/host/query/fragment。"""
    p = urllib.parse.urlsplit(u)
    path = urllib.parse.quote(urllib.parse.unquote(p.path), safe="/")
    return urllib.parse.urlunsplit((p.scheme, p.netloc, path, p.query, p.fragment))


def http_get_bytes(url, headers, timeout=60, retries=3):
    """带重试的字节下载（单一 header 集）。"""
    last = None
    url = _enc_url(url)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            if attempt < retries - 1:
                time.sleep(min(2 ** attempt, 4))
    if last:
        raise last
    raise RuntimeError("download failed")


def fetch_bytes_fallback(url, token, timeout=60, key=False, retries=3):
    """媒体(key=False)优先 Bearer、失败回退 MAC；密钥(key=True)用 MAC。
    解决本技能「m3u8/ts 必须 Bearer、密钥必须 MAC」的铁律，同时兼容其它场景。"""
    if key:
        return http_get_bytes(url, mac_headers(token), timeout, retries)
    pref = _MEDIA_AUTH_PREF["mode"]
    order = ("mac", "bearer") if pref == "mac" else ("bearer", "mac")
    last = None
    for i, mode in enumerate(order):
        hdrs = mac_headers(token) if mode == "mac" else bearer_headers(token)
        try:
            data = http_get_bytes(url, hdrs, timeout, retries if i == 0 else 1)
            if mode != pref:
                _MEDIA_AUTH_PREF["mode"] = mode
                print(f"[auth] 媒体鉴权切换为 {mode.upper()}（原 {pref.upper()} 被拒）")
            return data
        except Exception as e:  # noqa
            last = e
            if not _is_auth_ish(e):
                raise
    raise last


def fetch_json(url, headers, timeout=60, retries=3):
    return json.loads(http_get_bytes(url, headers, timeout, retries).decode("utf-8"))


def fetch_json_tolerant(url, token, timeout=60):
    """清单接口匿名优先、带 token 兜底（crawler-base 思路）。"""
    try:
        return fetch_json(url, ANON_HEADERS, timeout)
    except Exception:
        if token:
            return fetch_json(url, mac_headers(token), timeout)
        raise


def detect_smartedu_url(url):
    """从 URL 识别资源类型与 ID。返回 (api_key, rid)。"""
    lower = (url or "").lower()
    if "reading.smartedu.cn" in lower or ("/reading" in lower and "smartedu" in lower):
        m = re.search(r"[?&]contentId=([0-9a-fA-F\-]+)", url)
        return "reading", (m.group(1) if m else None)
    if "higher.smartedu.cn" in lower:
        m = re.search(r"([0-9a-fA-F]{24})", url)
        return "higher", (m.group(1) if m else None)
    if "vocational.smartedu.cn" in lower:
        m = re.search(r"([0-9a-fA-F\-]{8,64})", url)
        return "vocational", (m.group(1) if m else None)
    if "jpk.basic.smartedu.cn" in lower or "jpk.smartedu.cn" in lower:
        for pat in (r"[?&]id=([\w\-]{4,80})", r"[?&]contentId=([\w\-]{4,80})",
                    r"[?&]courseId=([\w\-]{4,80})", r"([0-9a-fA-F\-]{36})"):
            m = re.search(pat, url)
            if m:
                return "eliteLesson", m.group(1)
        return "eliteLesson", None
    for token, key in (("experimentLesson", "experiment"),
                       ("qualityCourse", "qualityCourse"),
                       ("prepare", "prepare"),
                       ("classActivity", "classActivity"),
                       ("tchMaterial", "tchMaterial"),
                       ("tresource", "tResource")):
        if token in url:
            for pat in (r"[?&]contentId=([0-9a-fA-F\-]{8,64})",
                        r"[?&]courseId=([0-9a-fA-F\-]{8,64})",
                        r"[?&]resourceId=([0-9a-fA-F\-]{8,64})",
                        r"[?&]activityId=([0-9a-fA-F\-]{8,64})",
                        r"[?&]lessonId=([0-9a-fA-F\-]{8,64})",
                        r"/([0-9a-fA-F\-]{36})"):
                m = re.search(pat, url)
                if m:
                    return (key if key != "tResource" else "tResource"), m.group(1)
    m = re.search(r"([0-9a-fA-F\-]{36})", url)
    return "classActivity", (m.group(1) if m else None)


def get_title(detail):
    """标题：同时认 global_title(zh-CN) 与 title 字符串（tch_material 只有后者）。"""
    if not isinstance(detail, dict):
        return ""
    for k in ("global_title", "title"):
        t = detail.get(k)
        if isinstance(t, dict):
            v = t.get("zh-CN") or t.get("zh") or ""
            if v:
                return v.strip()
            continue
        if isinstance(t, str) and t.strip():
            return t.strip()
    return ""


def pick_video_url(r, quality="720"):
    flag_pri = {"href-720p-m3u8": 5, "href-480p-m3u8": 4, "href-360p-m3u8": 3,
                "href-m3u8": 2, "href": 1}
    qflag = {"720": "href-720p-m3u8", "480": "href-480p-m3u8", "360": "href-360p-m3u8"}
    best = None
    for ti in r.get("ti_items", []):
        if ti.get("ti_format") != "m3u8":
            continue
        f = ti.get("ti_file_flag", "")
        if f not in flag_pri:
            continue
        if best is None or flag_pri[f] > best[0]:
            best = (flag_pri[f], ti.get("ti_storages", []))
    if not best or not best[1]:
        return None
    if quality in qflag:
        for ti in r.get("ti_items", []):
            if ti.get("ti_file_flag") == qflag[quality] and ti.get("ti_storages"):
                return ti["ti_storages"][0]
    return best[1][0]


def pick_pdf_url(r):
    """返回 (副本URL列表, 格式)。保留 r1/r2/r3 全部副本供下载回退。"""
    doc_formats = ("pdf", "doc", "docx", "ppt", "pptx", "ofd", "word", "xls", "xlsx", "txt")
    doc_flags = ("pdf", "doc", "ppt", "ofd", "word", "excel", "xls")
    for ti in r.get("ti_items", []):
        if ti.get("ti_format") in doc_formats:
            return list(ti.get("ti_storages") or []), ti.get("ti_format")
    for ti in r.get("ti_items", []):
        f = (ti.get("ti_file_flag") or "").lower()
        if any(k in f for k in doc_flags):
            return list(ti.get("ti_storages") or []), (ti.get("ti_format") or "pdf")
    return None, None


def storage_host_variants(url):
    """rN-ndr → rN-ndr-private 主机变体（教材/文档多为私有主机+token 才可读）。"""
    out = [url]
    m = re.match(r"^(https://r\d+-ndr)(\.ykt\.cbern\.com\.cn)(/.*)?$", url or "")
    if m:
        out.append(m.group(1) + "-private" + m.group(2) + (m.group(3) or ""))
    return out


def download_doc_to_file(urls, dest_path, token, timeout=120, progress_cb=None, mac_key=""):
    """多副本 × 主机变体 × (Bearer→匿名→强签名MAC) 下载文档到文件，任一成功即返回路径。

    crawler-base 关键经验：ti_storages 恒给 r1/r2/r3 三副本，单副本被拒就整单失败；
    且过期 token 反而会让「明文公开」的教材/文档 403，故带 token 失败后再匿名重试一次。
    实测部分 CDN（r1-ndr-private 精品课资源）对裸 Bearer 返回 400/401，必须再用
    带 mac_key 的强签名 MAC 头回退一次，否则文档整单失败（视频因走 download_hls 的
    fetch_bytes_fallback 已有 MAC 回退不受影响，唯独文档此前缺这一环）。
    """
    last_err = None
    tried = []
    auth_hdrs = bearer_headers(token) if token else None
    hdr_sets = []
    if auth_hdrs:
        hdr_sets.append(("auth", auth_hdrs))
    if not auth_hdrs or auth_hdrs != ANON_DOC_HEADERS:
        hdr_sets.append(("anon", ANON_DOC_HEADERS))
    if mac_key:
        hdr_sets.append(("mac", mac_headers_strong(token, mac_key)))
    for u in urls:
        if not u:
            continue
        for v in storage_host_variants(u):
            for tag, hd in hdr_sets:
                try:
                    data = http_get_bytes(v, hd, timeout, retries=2)
                    with open(dest_path, "wb") as f:
                        f.write(data)
                    return dest_path
                except Exception as e:  # noqa
                    last_err = e
                    tried.append("%s(%s)" % (v, tag))
    if last_err is not None:
        raise RuntimeError("文档下载失败，已尝试 %d 次：%s。最后错误：%s"
                           % (len(tried), "、".join(tried[:6]), last_err))
    raise RuntimeError("文档下载失败：没有可用的下载地址")


# ---------------------------------------------------------------------------
# 视频 HLS 下载（并发 + 密钥缓存 + 去 combined.ts + ffmpeg 日志落盘 + TS 降级）
# ---------------------------------------------------------------------------
def _pick_variant(master_url, text):
    base = master_url[: master_url.rfind("/") + 1]
    best = None
    for line in text.splitlines():
        if line.startswith("#EXT-X-STREAM-INF"):
            m = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            if m:
                h = int(m.group(2))
                if best is None or h > best[0]:
                    best = (h, None)
            # 下一行即 URI
            # 这里只记录分辨率，真正配对在调用处
    # 重新配对：取最高分辨率对应的 URI
    lines = text.splitlines()
    cand = []
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            m = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            uri = lines[i + 1].strip() if i + 1 < len(lines) else None
            if m and uri:
                cand.append((int(m.group(2)), uri))
    if not cand:
        return None
    cand.sort(key=lambda x: x[0], reverse=True)
    uri = cand[0][1]
    return uri if uri.startswith("http") else base + uri


def download_hls(manifest_url, dest_path, token, ffmpeg, quality="720", timeout=45,
                 progress_cb=None):
    """加密 HLS 下载：并发拉分片→解密→ffmpeg concat 封装；密钥仅取一次。

    - 媒体(m3u8/ts) 优先 Bearer、回退 MAC；密钥服务器永远 MAC（本技能铁律）。
    - 并发度 CB_HLS_WORKERS（默认 16，钳制 4–32）；失败分片补抓 2 轮。
    - 去 combined.ts：用 ffmpeg concat demuxer（规避大文件合并卡死）。
    - ffmpeg stderr 落盘（规避 Windows 管道缓冲 64KB 死锁）。
    - mp4 封装失败降级交付 .ts（播放器可直读）。
    """
    m3u8_text = fetch_bytes_fallback(manifest_url, token, 60).decode("utf-8")
    if "#EXT-X-STREAM-INF" in m3u8_text:
        variant = _pick_variant(manifest_url, m3u8_text)
        if variant:
            manifest_url = variant
            m3u8_text = fetch_bytes_fallback(manifest_url, token, 60).decode("utf-8")
    base = manifest_url[: manifest_url.rfind("/") + 1]
    segs = [l for l in m3u8_text.splitlines() if l and not l.startswith("#")]
    if not segs:
        raise ValueError("m3u8 未解析到任何分片（可能 token 失效或地址过期）")
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="_ts_", dir=os.path.dirname(dest_path) or ".")
    try:
        total = len(segs)

        def _decrypt(data, index):
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad
            cache = _decrypt.cache
            if "key" not in cache:
                with _decrypt.lock:
                    if "key" not in cache:
                        # 重新拉 m3u8 解析密钥（处理主/变体差异）
                        mt = fetch_bytes_fallback(manifest_url, token, 60).decode("utf-8")
                        if "#EXT-X-STREAM-INF" in mt:
                            v2 = _pick_variant(manifest_url, mt)
                            if v2:
                                mt = fetch_bytes_fallback(v2, token, 60).decode("utf-8")
                        key_lines = [l for l in mt.splitlines() if l.startswith("#EXT-X-KEY")]
                        if not key_lines or "METHOD=NONE" in key_lines[0]:
                            cache["key"] = None
                            cache["iv"] = bytes(16)
                        else:
                            kl = key_lines[0]
                            muri = re.search(r'URI="([^"]+)"', kl).group(1)
                            miv = re.search(r"IV=0x([0-9A-Fa-f]+)", kl)
                            iv = bytes.fromhex(miv.group(1)) if miv else bytes(16)
                            key_id = muri.rstrip("/").split("/")[-1]
                            sj = fetch_json(muri + "/signs", mac_headers(token), 30)
                            nonce = sj["nonce"]
                            sign = hashlib.md5((nonce + key_id).encode()).hexdigest()[:16]
                            kj = fetch_json(f"{muri}?nonce={nonce}&sign={sign}", mac_headers(token), 30)
                            enc_key = base64.b64decode(kj["key"])
                            dec_key = unpad(AES.new(sign.encode(), AES.MODE_ECB).decrypt(enc_key), 16)
                            cache["key"] = dec_key
                            cache["iv"] = iv
            key = cache.get("key")
            iv = cache.get("iv", bytes(16))
            if key is None:
                return data
            return unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(data), 16)

        _decrypt.cache = {}
        _decrypt.lock = threading.Lock()

        ts_files = [None] * total
        counter = [0]
        plock = threading.Lock()
        errs = {}

        def _dl(i, seg, to=timeout):
            try:
                if not seg.startswith("http"):
                    seg = base + seg
                data = fetch_bytes_fallback(seg, token, to, retries=2)
                data = _decrypt(data, i)
                tf = os.path.join(tmpdir, f"{i:05d}.ts")
                with open(tf, "wb") as f:
                    f.write(data)
                ts_files[i] = tf
                with plock:
                    counter[0] += 1
                    d = counter[0]
                if progress_cb:
                    progress_cb(f"下载分片 {d}/{total}")
                return True
            except Exception as e:  # noqa
                errs[i] = str(e)[:160]
                return False

        try:
            workers = int(os.environ.get("CB_HLS_WORKERS", "16") or 16)
        except Exception:
            workers = 16
        workers = max(4, min(32, workers))
        conc = min(workers, max(1, total))

        if ThreadPoolExecutor is not None:
            with ThreadPoolExecutor(max_workers=conc) as ex:
                futs = [ex.submit(_dl, i, segs[i]) for i in range(total)]
                for fu in as_completed(futs):
                    fu.result()
            # 失败补抓 2 轮
            for rnd in (1, 2):
                missing = [i for i in range(total) if ts_files[i] is None]
                if not missing:
                    break
                time.sleep(0.6 * rnd)
                rc = min(6, max(1, len(missing)))
                with ThreadPoolExecutor(max_workers=rc) as ex2:
                    futs2 = [ex2.submit(_dl, i, segs[i], 60) for i in missing]
                    for fu in as_completed(futs2):
                        fu.result()
        else:  # 退化顺序
            for i in range(total):
                _dl(i, segs[i])

        missing = [i for i in range(total) if ts_files[i] is None]
        if missing:
            raise RuntimeError("分片下载失败 %d/%d：%s" % (len(missing), total,
                                                           errs.get(missing[0], "")))

        # 合并：ffmpeg concat demuxer（不再落 combined.ts）
        ts_files = [ts_files[i] for i in range(total)]
        list_path = os.path.join(tmpdir, "concat.txt")
        with open(list_path, "w", encoding="utf-8") as lf:
            for tf in ts_files:
                lf.write("file '%s'\n" % tf.replace("\\", "/").replace("'", "'\\''"))
        combined_sz = sum(os.path.getsize(t) for t in ts_files)
        log_path = dest_path + ".ffmpeg.log"
        base_cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                    "-c", "copy", "-fflags", "+genpts"]
        attempts = [
            base_cmd + ["-movflags", "+faststart", "-avoid_negative_ts", "make_zero",
                        "-bsf:a", "aac_adtstoasc"],
            base_cmd,
        ]
        proc = None
        for cmd in attempts:
            try:
                with open(log_path, "wb") as logf:
                    proc = __import__("subprocess").run(cmd + [dest_path], stdout=logf,
                                                          stderr=__import__("subprocess").STDOUT,
                                                          timeout=300)
            except __import__("subprocess").TimeoutExpired:
                proc = None
                continue
            if proc.returncode == 0 or (os.path.exists(dest_path) and os.path.getsize(dest_path) > 0):
                break
        if proc is None or (proc.returncode != 0 and not (os.path.exists(dest_path) and os.path.getsize(dest_path) > 0)):
            # TS 降级交付
            ts_out = os.path.splitext(dest_path)[0] + ".ts"
            if combined_sz >= 1024:
                try:
                    with open(ts_out, "wb") as out:
                        for tf in ts_files:
                            with open(tf, "rb") as f:
                                shutil.copyfileobj(f, out, 1024 * 1024)
                    if os.path.getsize(ts_out) >= 1024:
                        try:
                            os.remove(log_path)
                        except Exception:
                            pass
                        if progress_cb:
                            progress_cb("已降级交付 TS（mp4 封装失败）")
                        return ts_out
                except Exception:
                    pass
            raise RuntimeError("HLS 封装失败")
        try:
            os.remove(log_path)
        except Exception:
            pass
    finally:
        # v2.4.0-patch1：原实现把 rmtree 丢进 daemon 线程「发出去就不管」——进程结束时
        # daemon 线程会被强杀，导致 _ts_* 临时分片目录整包残留
        # （实测遗留 125 个文件 / 92.7MB，比成品 mp4 本身还大）。改为同步清理。
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
    if not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
        raise RuntimeError("未产出有效文件（分片链接可能已过期）")
    return dest_path


# ---------------------------------------------------------------------------
# 免浏览器整库索引遍历（tch_material，匿名可读）
# ---------------------------------------------------------------------------
TCH_INDEX_VERSION = BASE + "/zxx/ndrs/resources/tch_material/version/data_version.json"
TCH_INDEX_VERSION_BAK = BASE2 + "/zxx/ndrs/resources/tch_material/version/data_version.json"
_TCH_INDEX_CACHE = {"key": None, "data": None}


def fetch_tch_material_index(max_parts=None, timeout=90, refresh=False):
    """拉取备课资源(tch_material)全量索引（匿名可读）。返回 list[dict] 带进程内缓存。"""
    key = "all" if max_parts is None else str(max_parts)
    if not refresh and _TCH_INDEX_CACHE["key"] == key and _TCH_INDEX_CACHE["data"]:
        return _TCH_INDEX_CACHE["data"]
    urls = None
    for vurl in (TCH_INDEX_VERSION, TCH_INDEX_VERSION_BAK):
        try:
            d = fetch_json_tolerant(vurl, None, 30)
            u = (d or {}).get("urls") or ""
            parts = [x for x in u.split(",") if x.strip()]
            if parts:
                urls = parts
                break
        except Exception:
            continue
    if not urls:
        return []
    if max_parts:
        urls = urls[:max_parts]

    def _one(u):
        try:
            return fetch_json_tolerant(u, None, timeout) or []
        except Exception:
            return []

    if ThreadPoolExecutor is not None:
        with ThreadPoolExecutor(max_workers=min(6, len(urls))) as ex:
            out = []
            for lst in ex.map(_one, urls):
                if isinstance(lst, list):
                    out.extend([x for x in lst if isinstance(x, dict) and x.get("id")])
    else:
        out = []
        for u in urls:
            out.extend([x for x in _one(u) if isinstance(x, dict) and x.get("id")])
    _TCH_INDEX_CACHE["key"] = key
    _TCH_INDEX_CACHE["data"] = out
    return out


def tch_index_lookup(rid, index=None):
    """在索引里按 id 查元数据。"""
    if not rid:
        return None
    idx = index if index is not None else fetch_tch_material_index()
    for r in idx:
        if r.get("id") == rid:
            return r
    return None


def search_tch_material(keyword, index=None, max_parts=None):
    """按关键词（标题/出版社/学科/年级/版本片段）检索教材，返回匹配元数据列表。

    解决「搜索 API 403 无法按名下载」的痛点：用匿名整库索引离线检索。
    """
    kw = (keyword or "").strip().lower()
    if not kw:
        return []
    idx = index if index is not None else fetch_tch_material_index(max_parts=max_parts)
    hits = []
    for r in idx:
        title = (r.get("global_title") or {}).get("zh-CN") or r.get("title") or ""
        # tag_list 可能含 dict（{name:...}）或 str，且字段可能缺失/为 None
        tags = r.get("tag_list") or []
        parts = []
        for t in tags:
            if isinstance(t, dict):
                parts.append(str(t.get("name") or t.get("title") or ""))
            else:
                parts.append(str(t))
        tag_str = " ".join(p for p in parts if p)
        hay = (title + " " + (r.get("provider") or "") + " " + tag_str).lower()
        if kw in hay:
            hits.append(r)
    return hits
