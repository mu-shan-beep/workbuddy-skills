#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国家中小学智慧教育平台 - 电子教材下载器 (v2.1)

支持：
1. 免登录下载公开教材（部分教材公开可下）
2. 登录后下载受保护教材（需 access_token）
3. 多CDN源自动切换
4. 断点续传 + 失败任务重跑（failed_tasks.json）
5. 文件完整性校验（smart模式：PDF头尾检查）
6. 热区音频提取（英语/语文听力MP3）
7. 自动添加PDF书签（目录结构）

用法：
  python download_textbook.py --url "https://basic.smartedu.cn/tchMaterial/detail?..."
  python download_textbook.py --url "https://basic.smartedu.cn/tchMaterial/detail?..." --token-file token.txt
  python download_textbook.py --url "https://basic.smartedu.cn/tchMaterial/detail?..." --out ./downloads
  python download_textbook.py --retry-failed  # 重跑上次失败的任务
  python download_textbook.py --batch urls.txt --no-multimedia  # 只下PDF，跳过音频
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import random

# 多CDN源列表（按优先级）
CDN_SOURCES = [
    "https://s-file-1.ykt.cbern.com.cn",
    "https://s-file-2.ykt.cbern.com.cn",
    "https://s-file-3.ykt.cbern.com.cn",
]

# 文件下载CDN节点
CDN_FILE_NODES = [
    "r1-ndr-private.ykt.cbern.com.cn",
    "r2-ndr-private.ykt.cbern.com.cn",
    "r3-ndr-private.ykt.cbern.com.cn",
]

# API端点
API_ENDPOINTS = {
    "textbook": "/zxx/ndrv2/resources/tch_material/details/{content_id}.json",
    "resource_pack": "/zxx/ndrs/special_edu/thematic_course/{content_id}/resources/list.json",
    "audios": "/zxx/ndrs/resources/{content_id}/relation_audios.json",
}

# 流式下载参数
CHUNK_SIZE = 8192  # 8KB 每块
DOWNLOAD_TIMEOUT = 300  # 5分钟超时


# ---------------------------------------------------------------------------
# IntegrityChecker：文件完整性校验（借鉴 wxaiway/smartedu-cn）
# ---------------------------------------------------------------------------
class IntegrityChecker:
    """文件完整性检查器，支持 strict/local/smart 三种模式"""

    def __init__(self, mode="smart"):
        self.mode = mode

    def check(self, file_path):
        """检查文件完整性，返回 (is_complete, reason)"""
        if not os.path.exists(file_path):
            return False, "文件不存在"

        size = os.path.getsize(file_path)

        if self.mode == "local":
            if size < 1024:
                return False, f"文件过小: {size} bytes"
            return True, "本地检查通过"

        if self.mode == "smart":
            if file_path.endswith(".pdf"):
                if size < 10 * 1024:
                    return False, f"PDF过小: {size} bytes"
                try:
                    with open(file_path, "rb") as f:
                        header = f.read(5)
                        if header != b"%PDF-":
                            return False, "无效的PDF文件头"
                        f.seek(-1024, 2)
                        tail = f.read()
                        if b"%%EOF" not in tail:
                            return False, "PDF可能不完整（缺少EOF标记）"
                except Exception as e:
                    return False, f"读取文件失败: {e}"
                return True, "智能检查通过"

            elif file_path.endswith(".mp3"):
                if size < 5 * 1024:
                    return False, f"音频过小: {size} bytes"
                try:
                    with open(file_path, "rb") as f:
                        header = f.read(3)
                        if header[:3] != b"ID3" and header[:2] != b"\xff\xfb":
                            f.seek(0)
                            data = f.read(min(4096, size))
                            if b"\xff\xfb" not in data and b"\xff\xfa" not in data:
                                return False, "无效的MP3文件格式"
                except Exception:
                    pass
                return True, "智能检查通过"

            else:
                if size < 100:
                    return False, f"文件过小: {size} bytes"
                return True, "智能检查通过"

        return True, "未检查"


# ---------------------------------------------------------------------------
# RateLimiter：请求限速（借鉴 wxaiway/smartedu-cn）
# ---------------------------------------------------------------------------
class RateLimiter:
    """简单的线程安全限速器"""

    def __init__(self, requests_per_second=2.0, enabled=True):
        self.rate = requests_per_second
        self.enabled = enabled
        self.last_request = 0

    def wait(self):
        if not self.enabled:
            return
        now = time.time()
        min_interval = 1.0 / self.rate
        elapsed = now - self.last_request
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self.last_request = time.time()


def http_get(url, headers=None, timeout=30, retries=3):
    """带重试的HTTP GET请求"""
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://basic.smartedu.cn/",
    }
    if headers:
        default_headers.update(headers)

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=default_headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt < retries - 1:
                time.sleep(1)
                continue
            raise
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
                continue
            raise
    raise Exception(f"Failed after {retries} retries")


def http_get_json(url, headers=None, timeout=30, retries=3):
    """带重试的HTTP GET请求，返回JSON"""
    data = http_get(url, headers, timeout, retries)
    return json.loads(data.decode("utf-8"))


def parse_textbook_url(url):
    """解析教材URL，提取contentId和类型"""
    match = re.search(r'contentId=([a-f0-9\-]+)', url)
    if not match:
        return None, None

    content_id = match.group(1)
    content_type = "assets_document" if "contentType=assets_document" in url else "thematic_course"
    return content_id, content_type


def get_token_from_edge_storage():
    """
    从Edge Local Storage读取token
    返回: (access_token, mac_key) 或 (None, None)
    """
    edge_profile = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Microsoft", "Edge", "User Data", "Default", "Local Storage", "leveldb"
    )

    if not os.path.exists(edge_profile):
        return None, None

    # 扫描所有文件
    all_data = b""
    for f in sorted(os.listdir(edge_profile)):
        fp = os.path.join(edge_profile, f)
        if os.path.isfile(fp):
            try:
                with open(fp, "rb") as fh:
                    all_data += fh.read()
            except:
                pass

    # 查找ND_UC_AUTH token
    # 格式: ND_UC_AUTH-{uuid}&ncet-xedu&token
    pattern = rb'ND_UC_AUTH-[\da-f-]+&ncet-xedu&token'
    matches = list(re.finditer(pattern, all_data))

    if not matches:
        return None, None

    # 解析每个匹配的token
    for m in matches[:5]:
        start = max(0, m.start() - 20)
        end = min(len(all_data), m.end() + 3000)
        ctx = all_data[start:end]

        # 提取JSON
        json_start = ctx.find(b'{')
        if json_start < 0:
            continue

        json_str = ctx[json_start:].decode("utf-8", errors="replace")
        brace_count = 0
        for i, c in enumerate(json_str):
            if c == '{':
                brace_count += 1
            elif c == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_str = json_str[:i + 1]
                    break

        try:
            obj = json.loads(json_str)
            if 'value' in obj and isinstance(obj['value'], str):
                inner = json.loads(obj['value'])
                access_token = inner.get("access_token", "")
                mac_key = inner.get("mac_key", "")
                if access_token:
                    return access_token, mac_key
        except:
            continue

    return None, None


def get_token_from_file(token_file):
    """从文件读取token（兼容旧格式）"""
    if not token_file or not os.path.exists(token_file):
        return None, None

    try:
        with open(token_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except:
        return None, None

    if not content:
        return None, None

    # 裸token
    if len(content.split()) == 1:
        return content, None

    # JSON包装：{"value": "..."} 旧格式
    try:
        obj = json.loads(content)
        if isinstance(obj, dict) and "value" in obj:
            inner = json.loads(obj["value"])
            return inner.get("access_token"), inner.get("mac_key")
    except:
        pass

    # JSON平铺：{"access_token": "...", "mac_key": "..."}（edge_login_token.py 写出的格式）
    try:
        obj = json.loads(content)
        if isinstance(obj, dict) and obj.get("access_token"):
            return obj.get("access_token"), obj.get("mac_key")
    except:
        pass

    return None, None


def get_auth_headers(access_token, mac_key=None, for_file_download=False):
    """构建认证头（支持静态和动态MAC两种模式）

    Args:
        access_token: 访问令牌
        mac_key: MAC密钥（用于API认证）
        for_file_download: 是否为文件下载场景（PDF等需要Bearer认证）
    """
    if not access_token:
        return None

    if mac_key and not for_file_download:
        # API调用使用MAC认证
        nonce = f"{int(time.time())}:{random.randint(0, 9999)}"
        mac_content = f"{nonce}\nGET\nbasic.smartedu.cn\n/\n"
        mac = hmac.new(mac_key.encode(), mac_content.encode(), hashlib.sha256).hexdigest()
        return {
            "X-ND-AUTH": f'MAC id="{access_token}",nonce="{nonce}",mac="{mac}"',
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://basic.smartedu.cn/",
        }
    else:
        # 文件下载使用Bearer认证
        return {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://basic.smartedu.cn/",
        }


def generate_mac_auth(access_token, mac_key, method="GET", host="basic.smartedu.cn", path="/"):
    """
    生成真实的MAC认证头（借鉴 smartedudownloader 技能）
    使用 HMAC-SHA256 动态签名，替代静态 mac="0"
    """
    if not mac_key:
        return None
    
    nonce = f"{int(time.time())}:{random.randint(0, 9999)}"
    mac_content = f"{nonce}\n{method}\n{host}\n{path}\n"
    mac = hmac.new(mac_key.encode(), mac_content.encode(), hashlib.sha256).hexdigest()
    
    return f'MAC id="{access_token}",nonce="{nonce}",mac="{mac}"'


def download_file_streaming(url, headers=None, timeout=DOWNLOAD_TIMEOUT):
    """
    流式下载文件，支持大文件和断点续传
    返回 (data, cdn_used, error_message)
    """
    import urllib.parse
    import re

    # URL编码处理（处理中文文件名）
    parsed = urllib.parse.urlparse(url)
    encoded_path = urllib.parse.quote(parsed.path, safe='/:_.-')
    test_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, encoded_path, '', '', ''))

    # 提取域名
    domain_match = re.match(r'https://([^/]+)', test_url)
    if not domain_match:
        return None, None, "Invalid URL"

    original_domain = domain_match.group(1)

    # 构建候选域名列表
    if "s-file" in original_domain:
        candidates = ["s-file-1.ykt.cbern.com.cn", "s-file-2.ykt.cbern.com.cn", "s-file-3.ykt.cbern.com.cn"]
    elif "r1-ndr-private" in original_domain or "r2-ndr-private" in original_domain or "r3-ndr-private" in original_domain:
        candidates = ["r1-ndr-private.ykt.cbern.com.cn", "r2-ndr-private.ykt.cbern.com.cn", "r3-ndr-private.ykt.cbern.com.cn"]
    else:
        candidates = [original_domain]

    # 尝试每个CDN节点
    for cdn in candidates:
        if cdn == original_domain:
            final_url = test_url
        else:
            final_url = re.sub(r'https://[^/]+', f'https://{cdn}', test_url)

        try:
            req = urllib.request.Request(final_url, headers=headers or {})
            resp = urllib.request.urlopen(req, timeout=timeout)

            # 流式读取并写入文件
            downloaded_chunks = []
            total_size = 0
            content_length = resp.headers.get('Content-Length')

            while True:
                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break
                downloaded_chunks.append(chunk)
                total_size += len(chunk)

                # 每10MB打印进度
                if content_length and total_size % (10 * 1024 * 1024) < CHUNK_SIZE:
                    mb_down = total_size // (1024 * 1024)
                    mb_total = int(content_length) // (1024 * 1024)
                    print(f"    下载中: {mb_down}MB / {mb_total}MB")

            data = b''.join(downloaded_chunks)
            return data, cdn, None

        except Exception as e:
            continue

    return None, None, "所有CDN源都失败"


def download_with_cdn_fallback(url, headers=None, timeout=30):
    """多CDN源自动切换下载

    支持的CDN格式：
    - s-file-1/2/3.ykt.cbern.com.cn（API接口）
    - r1/r2/r3-ndr-private.ykt.cbern.com.cn（文件下载）
    """
    import urllib.parse

    # URL编码（处理中文文件名）
    parsed = urllib.parse.urlparse(url)
    encoded_path = urllib.parse.quote(parsed.path, safe='/:_.-')
    url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, encoded_path, '', '', ''))

    # 提取域名
    domain_match = re.match(r'https://([^/]+)', url)
    if not domain_match:
        raise Exception("Invalid URL")

    original_domain = domain_match.group(1)

    # 构建候选域名列表
    if "s-file" in original_domain:
        # API域名
        candidates = [
            "s-file-1.ykt.cbern.com.cn",
            "s-file-2.ykt.cbern.com.cn",
            "s-file-3.ykt.cbern.com.cn",
        ]
    elif "r1-ndr-private" in original_domain or "r2-ndr-private" in original_domain or "r3-ndr-private" in original_domain:
        # 文件下载域名
        candidates = [
            "r1-ndr-private.ykt.cbern.com.cn",
            "r2-ndr-private.ykt.cbern.com.cn",
            "r3-ndr-private.ykt.cbern.com.cn",
        ]
    else:
        # 其他域名，原样尝试
        candidates = [original_domain]

    for cdn in candidates:
        if cdn == original_domain:
            test_url = url
        else:
            test_url = re.sub(r'https://[^/]+', f'https://{cdn}', url)

        try:
            data = http_get(test_url, headers, timeout)
            return data, cdn
        except Exception as e:
            pass

    raise Exception("所有CDN源都失败")


def parse_textbook_api(content_id, access_token=None, extra_headers=None):
    """解析教材API，返回教材信息

    Args:
        content_id: 教材ID
        access_token: 访问令牌
        extra_headers: 额外的请求头（如MAC认证头）
    """
    # 优先使用传入的headers（MAC认证），否则自行构建
    headers = extra_headers if extra_headers else get_auth_headers(access_token)

    # 尝试不同的CDN源
    for cdn in CDN_SOURCES:
        url = f"{cdn}/zxx/ndrv2/resources/tch_material/details/{content_id}.json"
        try:
            data = http_get_json(url, headers, 30)
            return data, cdn
        except Exception as e:
            pass

    raise Exception("无法解析教材信息")


def extract_pdf_info(data):
    """从API响应中提取PDF信息"""
    pdf_urls = []
    audio_urls = []  # 新增：热区音频

    # 教材页使用扁平结构：title + ti_items
    if "title" in data:
        title = data.get("title", data.get("global_title", {}).get("zh-CN", "未命名教材"))
        for item in data.get("ti_items", []):
            # PDF 资源
            if item.get("ti_format") == "pdf":
                for storage in item.get("ti_storages", []):
                    if storage:
                        pdf_urls.append(storage)
            # 热区数据（含音频）
            if item.get("ti_file_flag") == "hot_zone":
                hot_zone_urls = item.get("ti_storages", [])
                if hot_zone_urls:
                    audio_urls.extend(hot_zone_urls)
        return title, pdf_urls, audio_urls

    # 课程资源包使用嵌套结构：relations.national_course_resource
    title = data.get("global_title", {}).get("zh-CN", "未命名教材")
    relations = data.get("relations", {})

    if "direct_download" in relations:
        for item in relations["direct_download"]:
            for storage in item.get("ti_storages", []):
                if storage and storage.endswith(".pdf"):
                    pdf_urls.append(storage)

    if "national_course_resource" in relations:
        for rel in relations["national_course_resource"]:
            for item in rel.get("ti_items", []):
                if item.get("ti_format") == "pdf":
                    for storage in item.get("ti_storages", []):
                        if storage:
                            pdf_urls.append(storage)
                # 热区音频
                if item.get("ti_file_flag") == "hot_zone":
                    for storage in item.get("ti_storages", []):
                        if storage:
                            audio_urls.append(storage)

    # 兜底：正则匹配PDF URL
    if not pdf_urls:
        json_str = json.dumps(data)
        matches = re.findall(r'https://[^"\s]+\.pdf[^"\s]*', json_str)
        for m in matches:
            if "ykt.cbern.com.cn" in m or "cbern.com.cn" in m:
                pdf_urls.append(m)

    return title, pdf_urls, audio_urls


def extract_audio_from_hot_zone(hot_zone_url, headers):
    """从热区数据中提取音频URL（借鉴 wxaiway/smartedu-cn）"""
    audio_list = []
    try:
        data = http_get(hot_zone_url, headers, 30)
        text = data.decode("utf-8", errors="replace")

        # 尝试JSON解析
        try:
            items = json.loads(text)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and "audio_src" in item:
                        audio_list.append({
                            "url": item["audio_src"],
                            "name": item.get("audio_name", f"audio_{len(audio_list)+1}"),
                        })
        except json.JSONDecodeError:
            # 正则提取MP3 URL
            mp3_pattern = r'https?://[^\s"]+\.mp3'
            for url in re.findall(mp3_pattern, text):
                audio_list.append({
                    "url": url,
                    "name": f"audio_{len(audio_list)+1}",
                })
    except Exception as e:
        print(f"  [WARN] 热区音频提取失败: {e}")

    return audio_list


def download_pdf(pdf_urls, dest, token=None, integrity_mode="smart", mac_key=""):
    """下载PDF文件，支持多副本回退、多CDN和完整性校验。

    pdf_urls: 副本 URL 列表（r1/r2/r3），任一成功即返回；
    单副本被拒(token过期/节点故障)自动换下一个 + 主机变体(rN-ndr→rN-ndr-private)
    + 匿名回退 + 强签名MAC回退(需 mac_key)。
    """
    # 复用提炼后的核心：多副本 × 主机变体 × 匿名回退
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import smartedu_core as core

    checker = IntegrityChecker(mode=integrity_mode)
    print(f"  下载: {os.path.basename(dest)}")

    # 检查是否已存在且完整
    if os.path.exists(dest):
        is_complete, reason = checker.check(dest)
        if is_complete:
            size_kb = os.path.getsize(dest) // 1024
            print(f"  已存在且完整 ({size_kb}KB)，跳过")
            return True
        else:
            print(f"  文件不完整({reason})，重新下载")

    if isinstance(pdf_urls, str):
        pdf_urls = [pdf_urls]

    for attempt in range(3):
        try:
            core.download_doc_to_file(pdf_urls, dest, token, DOWNLOAD_TIMEOUT, mac_key=mac_key)
            # 完整性校验
            is_complete, reason = checker.check(dest)
            if not is_complete:
                print(f"  [WARN] 完整性校验失败: {reason}")
                continue
            size_mb = os.path.getsize(dest) // 1024 // 1024
            print(f"  完成 ({size_mb}MB)")
            return True
        except Exception as e:
            print(f"  [ERROR] 下载失败 (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(2 ** attempt + random.uniform(0, 1))
            else:
                return False

    return False


def add_pdf_bookmarks(pdf_path, title, chapters=None):
    """为PDF添加书签"""
    try:
        import fitz
    except ImportError:
        print("  [WARN] PyMuPDF未安装，跳过书签添加")
        return

    try:
        doc = fitz.open(pdf_path)
        toc = doc.get_toc()

        if toc and len(toc) > 0:
            print(f"  添加书签: {len(toc)} 个章节")
        else:
            if doc.page_count > 0:
                doc.set_toc([(1, title, 1)])

        # 修复：同源 incremental 保存会因 "changing encryption" 失败；
        # 改为非增量写临时文件，再覆盖原文件（规避加密字典限制）。
        import shutil as _sh
        tmp = pdf_path + ".bookmark.tmp.pdf"
        doc.save(tmp)
        doc.close()
        _sh.move(tmp, pdf_path)
    except Exception as e:
        print(f"  [WARN] 书签添加失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="国家中小学智慧教育平台 - 电子教材下载器")
    parser.add_argument("--url", nargs="+", help="教材页面URL（可多个）")
    parser.add_argument("--content-id", help="教材contentId（从URL提取）")
    parser.add_argument("--token-file", help="token文件路径")
    parser.add_argument("--out", default=".", help="输出目录")
    parser.add_argument("--no-bookmark", action="store_true", help="不添加PDF书签")
    parser.add_argument("--batch", help="从文件读取URL列表")
    args = parser.parse_args()

    # 获取 token（统一走 token_manager：文件读取 → 过期无感续期 → 本机 Edge 兜底）
    import token_manager as _tm
    token_file = args.token_file or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "smartedu_token.txt"
    )
    tok = _tm.get_valid_token(token_file)
    if tok:
        access_token = tok["access_token"]
        mac_key = tok.get("mac_key") or ""
    else:
        access_token, mac_key = None, None
        print("缺少有效 access_token。请先运行：")
        print(f"  python token_manager.py acquire --token-file {token_file}")
        sys.exit(2)

    # 【第一步】鉴权预检：确认 token 真的能被服务端接受，避免解析/下载半天才发现 401。
    # probe_token 探测 user/session 端点（Bearer）；返回 False=确定失效，None=网络异常无法判定。
    alive = _tm.probe_token(access_token)
    if alive is False:
        print()
        print("✗ 第一步鉴权预检失败：token 已失效（服务端返回 401/403）。")
        print("  请先续期或重新登录后再下载：")
        print(f"    python token_manager.py refresh --token-file {token_file}")
        print(f"    python token_manager.py acquire --token-file {token_file}")
        sys.exit(2)
    elif alive is None:
        print("⚠ 无法连接服务端做鉴权预检（网络/端点异常），将直接尝试下载。")
    else:
        print("✓ token 鉴权预检通过")

    # mac_key 缺失预警：缺它时部分依赖 MAC 强签名的 PDF 会 401
    if not mac_key:
        print("⚠ 当前 token 缺少 mac_key：部分依赖 MAC 强签名的 PDF 可能返回 401。")
        print("  建议重新登录获取完整 token：")
        print(f"    python token_manager.py acquire --token-file {token_file}")

    headers = get_auth_headers(access_token, mac_key)

    # 收集所有URL
    urls = args.url or []
    if args.batch and os.path.exists(args.batch):
        with open(args.batch, "r", encoding="utf-8") as f:
            urls.extend([line.strip() for line in f if line.strip()])

    if not urls and not args.content_id:
        print("错误：请提供 --url 或 --content-id")
        sys.exit(1)

    # 创建输出目录
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    # 处理每个教材
    success_count = 0
    fail_count = 0

    for url_or_id in (urls or [args.content_id]):
        if url_or_id.startswith("http"):
            content_id, content_type = parse_textbook_url(url_or_id)
            if not content_id:
                print(f"错误：无法解析URL: {url_or_id}")
                fail_count += 1
                continue
        else:
            content_id = url_or_id
            content_type = "assets_document"

        print(f"\n{'='*60}")
        print(f"教材ID: {content_id}")
        print(f"类型: {'资源包教材' if content_type == 'thematic_course' else '普通教材'}")

        try:
            # API调用使用MAC认证（如果有mac_key）
            api_headers = get_auth_headers(access_token, mac_key, for_file_download=False)
            data, cdn_used = parse_textbook_api(content_id, access_token, api_headers)
            print(f"✓ 解析成功 (CDN: {cdn_used})")

            title, pdf_urls, audio_urls = extract_pdf_info(data)
            print(f"标题: {title}")
            print(f"PDF数量: {len(pdf_urls)}")
            if audio_urls and not args.no_multimedia:
                print(f"音频源数量: {len(audio_urls)}")

            if not pdf_urls:
                print("错误：未找到PDF下载链接")
                fail_count += 1
                continue

            # 走到这里说明资源地址已解析到、基本确认可下载 —— 给一句转场提示
            print("正在下载所需资源，请等待......")
            safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)
            dest = os.path.join(out_dir, f"{safe_title}.pdf")

            # 文件下载使用Bearer认证（多副本回退在 smartedu_core.download_doc_to_file 内处理）
            if download_pdf(pdf_urls, dest, access_token, mac_key=mac_key):
                success_count += 1

                if not args.no_bookmark:
                    add_pdf_bookmarks(dest, title)

                # 输出绝对路径，方便用户定位
                abs_path = os.path.abspath(dest)
                size_mb = round(os.path.getsize(dest) / 1024 / 1024, 2)
                print(f"完成 ({size_mb}MB): {abs_path}")

        except Exception as e:
            print(f"错误：{e}")
            fail_count += 1

    print(f"\n{'='*60}")
    print(f"完成: 成功 {success_count}, 失败 {fail_count}")


if __name__ == "__main__":
    main()
