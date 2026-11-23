#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下载 www.smartedu.cn 公开课直播回放视频

算法来源：smartedu_core.py 的 HLS 密钥获取逻辑（nonce+sign 认证）
"""

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

def _resolve_ffmpeg():
    """优先用 imageio-ffmpeg 自带的 ffmpeg，其次退回系统 PATH，避免硬编码本机路径。"""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG_PATH = _resolve_ffmpeg()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
REF = "https://www.smartedu.cn/"


def http_get_bytes(url, headers=None, timeout=30, retries=3):
    """获取 URL 字节内容，支持重试"""
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (401, 403):
                raise
            time.sleep(1 * (i + 1))
        except Exception as e:
            last_err = e
            if i < retries - 1:
                time.sleep(1 * (i + 1))
    raise last_err


def http_get_text(url, headers=None, timeout=30):
    return http_get_bytes(url, headers, timeout).decode('utf-8', errors='ignore')


def http_get_json(url, headers=None, timeout=30):
    return json.loads(http_get_bytes(url, headers, timeout).decode('utf-8'))


def mac_headers(token):
    """MAC 认证头（密钥服务器用）"""
    return {
        "X-ND-AUTH": f'MAC id="{token}",nonce="0",mac="0"',
        "User-Agent": UA,
        "Referer": REF,
        "Origin": "https://www.smartedu.cn",
    }


def bearer_headers(token):
    """Bearer 认证头（媒体下载用）"""
    return {
        "User-Agent": UA,
        "Referer": REF,
        "Authorization": f"Bearer {token}",
        "Origin": "https://www.smartedu.cn",
    }


def get_token():
    """从技能目录的 token 文件读取 access_token"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    token_file = os.path.join(script_dir, 'smartedu_token.txt')
    try:
        data = json.loads(Path(token_file).read_text(encoding='utf-8'))
        return data.get('access_token', ''), data.get('mac_key', '')
    except Exception:
        return '', ''


def fetch_aes_key(key_uri, token):
    """
    获取 AES 解密密钥（复用 smartedu_core.py 的 nonce+sign 算法）

    步骤：
    1. GET {key_uri}/signs  拿 nonce
    2. sign = MD5(nonce + key_id)[:16]
    3. GET {key_uri}?nonce={nonce}&sign={sign} 拿 base64 加密的 key
    4. AES-ECB(sign) 解密 → PKCS7 unpad → 最终 AES-CBC key
    """
    key_id = key_uri.rstrip('/').split('/')[-1]

    # Step 1: 拿 nonce
    signs_url = key_uri + '/signs'
    sj = http_get_json(signs_url, mac_headers(token), timeout=15)
    nonce = sj['nonce']

    # Step 2: 计算 sign
    sign = hashlib.md5((nonce + key_id).encode()).hexdigest()[:16]

    # Step 3: 拿加密的 key
    key_resp_url = f'{key_uri}?nonce={nonce}&sign={sign}'
    kj = http_get_json(key_resp_url, mac_headers(token), timeout=15)
    enc_key = base64.b64decode(kj['key'])

    # Step 4: AES-ECB 解密 + PKCS7 unpad
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    dec_key = unpad(AES.new(sign.encode(), AES.MODE_ECB).decrypt(enc_key), 16)
    return dec_key


def parse_m3u8(m3u8_content, m3u8_url):
    """解析 m3u8，返回 (key_uri, iv_hex, ts_urls)"""
    lines = m3u8_content.strip().split('\n')
    key_uri = None
    iv_hex = None

    for line in lines:
        line = line.strip()
        if '#EXT-X-KEY' in line:
            uri_m = re.search(r'URI="([^"]+)"', line)
            iv_m = re.search(r'IV=0x([0-9A-Fa-f]+)', line)
            if uri_m:
                key_uri = uri_m.group(1)
                if not key_uri.startswith('http'):
                    key_uri = m3u8_url.rsplit('/', 1)[0] + '/' + key_uri
            if iv_m:
                iv_hex = iv_m.group(1)

    base_url = m3u8_url.rsplit('/', 1)[0] + '/'
    ts_urls = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#'):
            ts_urls.append(base_url + line if not line.startswith('http') else line)

    return key_uri, iv_hex, ts_urls


def download_ts(ts_url, output_path, key, iv, headers):
    """下载并解密单个 TS 分片"""
    data = http_get_bytes(ts_url, headers, timeout=60)
    from Crypto.Cipher import AES
    iv_bytes = bytes.fromhex(iv) if iv else b'\x00' * 16
    cipher = AES.new(key, AES.MODE_CBC, iv=iv_bytes)
    plaintext = cipher.decrypt(data)
    with open(output_path, 'wb') as f:
        f.write(plaintext)
    return len(plaintext)


def download_m3u8(m3u8_url, output_file, title, token):
    """下载并合并 m3u8 视频（带 AES 解密）"""
    print(f'正在解析 m3u8: {m3u8_url[:80]}...')

    m3u8_content = http_get_text(m3u8_url, bearer_headers(token), timeout=30)
    key_uri, iv_hex, ts_urls = parse_m3u8(m3u8_content, m3u8_url)

    if not key_uri:
        print('无加密，直接下载 TS')
    else:
        print(f'获取 AES 密钥: {key_uri[:60]}...')
        try:
            aes_key = fetch_aes_key(key_uri, token)
            print(f'密钥获取成功 ({len(aes_key)} bytes)')
        except Exception as e:
            print(f'密钥获取失败: {e}')
            return False

    print(f'找到 {len(ts_urls)} 个分片')

    temp_dir = tempfile.mkdtemp(prefix=f'_ts_{title[:10]}_')
    print(f'临时目录: {temp_dir}')

    downloaded = 0
    ts_files = []
    headers = bearer_headers(token)

    for i, ts_url in enumerate(ts_urls):
        ts_path = os.path.join(temp_dir, f'{i:05d}.ts')
        ts_files.append(ts_path)
        try:
            size = download_ts(ts_url, ts_path, aes_key, iv_hex, headers)
            downloaded += 1
            if downloaded % 50 == 0:
                print(f'  进度: {downloaded}/{len(ts_urls)} ({round(os.path.getsize(output_file)/1024/1024,1) if os.path.exists(output_file) else 0}MB)')
        except Exception as e:
            print(f'  分片 {i} 失败: {e}，跳过')
            # 写空文件占位
            with open(ts_path, 'wb') as f:
                pass

    print(f'下载完成: {downloaded}/{len(ts_urls)}')

    if downloaded == 0:
        print('没有成功下载任何分片')
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    print('正在合并视频...')
    concat_file = os.path.join(temp_dir, 'concat.txt')
    with open(concat_file, 'w') as f:
        for ts_file in ts_files[:downloaded]:
            f.write(f"file '{ts_file}'\n")

    cmd = [
        FFMPEG_PATH, '-y',
        '-f', 'concat', '-safe', '0',
        '-i', concat_file,
        '-c', 'copy',
        '-bsf:a', 'aac_adtstoasc',
        output_file
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode == 0:
            size_mb = round(os.path.getsize(output_file) / 1024 / 1024, 2)
            print(f'成功！文件大小: {size_mb} MB')
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            return True
        else:
            print(f'合并失败: {result.stderr[-300:]}')
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False
    except Exception as e:
        print(f'合并错误: {e}')
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False


def download_publiclive(live_id, output_dir='./课程下载/公开课直播'):
    """下载公开课直播"""
    api_url = f'https://x-api.ykt.eduyun.cn/proxy/live/v3/open_class_lives/{live_id}'

    print(f'正在获取直播信息: {live_id}')
    try:
        data = http_get_json(api_url, timeout=15)
    except Exception as e:
        print(f'API 请求失败: {e}')
        return False

    live_name = data.get('live_name', '未知课程')
    lecturer = data.get('lecture_user_name', '未知讲师')
    m3u8_url = data.get('replay_url', '')

    if not m3u8_url:
        print('未找到视频源')
        return False

    print(f'课程: {live_name}')
    print(f'讲师: {lecturer}')
    print(f'视频源: {m3u8_url[:80]}...')

    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f'{live_name}.mp4')

    token, _ = get_token()
    if not token:
        print('错误：未找到 access_token，请先登录 smartedu')
        return False

    return download_m3u8(m3u8_url, output_file, live_name, token)


def main():
    parser = argparse.ArgumentParser(description='下载 smartedu.cn 公开课直播')
    parser.add_argument('--url', help='公开课直播 URL')
    parser.add_argument('--live-id', help='直播 ID（URL 中的 UUID）')
    parser.add_argument('--out', default='./课程下载/公开课直播', help='输出目录')

    args = parser.parse_args()

    if args.url:
        match = re.search(r'publiclive/([a-f0-9-]+)', args.url)
        if match:
            live_id = match.group(1)
        else:
            print('无法从 URL 提取 live_id')
            return 1
    elif args.live_id:
        live_id = args.live_id
    else:
        print('请提供 --url 或 --live-id')
        return 1

    success = download_publiclive(live_id, args.out)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
