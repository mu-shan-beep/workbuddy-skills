#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夸克网盘 API 库：转存 + 分享 两条链路（基于网页端抓包）。

转存链路（已验证 3600+ 部）:
  get_stoken(pwd_id) -> save_share(...) -> poll_task(task_id)

分享链路（从 n8n 工作流提取）:
  create_share_task(fid_list) -> poll_task(task_id) 得 share_id
  -> set_share_password(share_id) -> 得 share_url + passcode

登录态: 优先读环境变量 QUARK_COOKIE，其次读本目录 cookie.txt，
都没有则用内置 COOKIES（会过期，过期后让用户重新抓包更新）。
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# ====== 登录态 ======
# 包内不内置任何真实 Cookie（账号凭据不入库）。
# 优先级: 环境变量 QUARK_COOKIE > 本目录 cookie.txt
# 获取方式: python3 get_cookie.py（自动开浏览器抓取并写入 cookie.txt），
# 或浏览器登录 pan.quark.cn -> F12 -> Network -> 复制任一请求的 Cookie 头整串存入 cookie.txt。
FALLBACK_COOKIES = ""


def _load_cookie():
    env = os.environ.get("QUARK_COOKIE")
    if env:
        return env.strip()
    f = os.path.join(HERE, "cookie.txt")
    if os.path.exists(f):
        return open(f, encoding="utf-8").read().strip()
    return FALLBACK_COOKIES


COOKIES = _load_cookie()

# 风控头（抓包备份；save 接口被拒时自动降级启用）
BX_HEADERS = {
    "bx-ua": "231!ymS35AmUzhG+jm/Bu+7j8y+jUqzVaiibY0fmDp4xx2j8ImTj432OeCgWcOEDl5hjZPgWQVoIVTJ1zmYY2c0geSrCMf/hIBUF3h2JdvoS88JCotHphCjkZIueFARvNWSlznATE5bbstbkae4EhBPKkMW61FUX/7OE0p2pXFLA3kTY4lkSZcnOsxDqIIi3rIyNgTmytTzpNb781v+Zw1wcs8baBEwjZCcGRRobbtMrIzKQcqTtuUafGQlka7A2dqtHS4+r+MMepADqk+I9xGdFhur6DJlCok+++4mWYi++6byOjOIzTIBDj+yt3IUA6nj0K4D/8UygrE9hrKG/807T9RDk3aiDSx9gPM+9jQc3SW3DDC0kGIZNbw493MEoaoJPnO8Iuq3XiCLRqRvNw9piXxo8os2rQN7sOspp+uQ4HH+MYJQFQIfDxURFMJYNdvnuZn4Fc2lZ89Yp1Ql9PmqMfo39jd4aAXepwl68BRO3b6VhYfdYgEfnaZSGCuwvqLQvLeNYYcbBBwKFVSK42jVhfCwPlWkYowYC2ng9OAP+aj/ddWhlbnaFaasIOuU6F7Apz7ukkk6PQ4Z/L5Qb8dNvdfQebXA8NdxO5B7bfFvPX0krjvK9rOA7dJjX+ZDP3kM57hoxQo33PRs1fHcR1A6K69ttBrQ9ckuh8/uuGJyMfADINk0GYBN9Bze1ss9/6OoyTInT/3nJUYl7aLlKnCB/8QF9bjjaeXw62R3SwaSqYdxKAZ5G1i4oNdRkuTn0T50b+qh8Jbs9HeBN+U95O/8hxW4kYW4WmmTbv1FvSjUSK2YrqEzLWPlMk6/435C3EEr8uxgk4qADKQjxzdE+XDwTQlU26Hbdg4eFocaj3BmvHKyvYJAuz4s/PZDubTSdcHKhXHHTsmoEYMD5Kqp+0tOBcxukkBn9OUbuIJvjsjGXs0EN30g5jxRly1nW7YmKhJzJrglQWtJ5xDEc0SxeZ5MHamP/orp1AIxZ0l5/EOn065fcBEEP2w8KMkGLJorPdm/uNmrnLb8KGhyOemfnWkIL2JCgb6qSIDEAJFlHdmGUscrjqHQ9aByi1iJ59BnVHNl5qXu4sZuh5C1jooHThGFAcIez5Fm5IVrnCirpIKpPfDJ2jEmRe87OskV0tx8fZATCxsRvH01Bo0vYC+v2C7Oa1GQ0iwDWvBQn6lRfHDid9qA6JULDD+wmoWiLXNh8JBmUxHfiMa4phwfY09Mi4Iuhr34waK2wIuxgNRdUq149c5w2AY5Cp5hYY1mmevLuXRvGifpF+MR5WVIbcBVJYytOLRCyuEvCfifeQKlsnTmAF2ieSS4KcId4vgLSZPnth3XPZjhqM7cFOTQkY4TFcvB1ASkEOkVTlywYcsYFh0lziwO7lB8d6oZfvhiymraO9ytL58haYL1JGUOzq/SzTsVSH7rSm9CU6NcUp/GanJvfDSSsBSMhYccwO8Z3bMw4hdxskXlf59dhYFO1hTwWsnRp0k0lUKkbcD2aRvicvZfN0kK8Tblxthhc+FLar8ym7rcehNGVQpBcDYXlHp5Z51TXbDU6btwlZ8S=",
    "bx-umidtoken": "T2gAPQTUQPaw7ILWpL8qHdHHN3kqRHxMR1uRMuwTzE1IlHfT6hxR0zVlYE9IaCDnWvc=",
    "bx_et": "gv2oVlvPFqTsyoTVIek5RuI0IvCYFYMIlypKJv3FgqujJgZLYvJUJkH-TaZLo2uqADydVa6qKy4wT2uFrrj3yk9Kz4eKKXztUXN-J43nKkaGDNBOBuZSdY7OWOnSC3DEC3JrLeh2ucMn42ij_0ZSdv79Dp5OIualM6wZ8vSm3Dm98vlrLISmvDuEL4leuIoZu2kU8b-V3Dii8eoEzmSmAquELbuEuimIu0kELyrVmDTz1FuoLAwVZy6M0Sm3r-muRpqc1pJnldhr7q3V7tpK4bA84qveL-VIaIsSStYqkkr_Tj2hFLHQD543TrSeL2VqjPmTytJoLSz0IfrfSLgugzwnef6HxmVg0z2-K1xSD8q4CX25rKuuloPtFR7XKPrYX8GbKNYqR7ns30VcYIurTgyMgCuQcpiVv-RBObojmVED02oC00PYvijDsnGrcmLOmiABxbojqVIcmBdmamivl",
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

DEBUG = os.environ.get("DEBUG") == "1"


def _headers():
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "content-type": "application/json",
        "origin": "https://pan.quark.cn",
        "referer": "https://pan.quark.cn/",
        "user-agent": UA,
        "cookie": COOKIES,
    }


def call(url, body=None, extra_headers=None):
    """请求夸克接口，返回解析后的 JSON。GET 无 body，POST 传 body。"""
    headers = _headers()
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8")
        except Exception:
            return {"http_error": e.code, "message": f"HTTP {e.code}"}
    if DEBUG:
        print(f"[DEBUG] {url.split('?')[0].rsplit('/', 1)[-1]} -> {raw[:500]}")
    try:
        return json.loads(raw)
    except Exception:
        return {"message": f"非JSON响应: {raw[:200]}"}


# ============================================================
# 通用任务轮询（转存/分享共用）
# ============================================================

def poll_task(task_id, max_retry=60, interval=1.5):
    """轮询任务直到完成。
    status: 2=成功; 3=终态失败（顶层 code/message 给原因，如 41009 分享文件已删除）; <0=失败; 其他=进行中。
    成功返回 data（含 share_id / save_as 等），失败/超时抛 RuntimeError。"""
    for i in range(max_retry):
        url = (f"https://drive-pc.quark.cn/1/clouddrive/task"
               f"?pr=ucpro&fr=pc&uc_param_str=&task_id={task_id}&retry_index={i}")
        r = call(url)
        d = r.get("data") or {}
        st = d.get("status")
        if st == 2:
            return d
        if st == 3:
            raise RuntimeError(f"任务终态失败: code={r.get('code')} msg={r.get('message')}")
        if st is not None and st < 0:
            raise RuntimeError(f"任务失败: {json.dumps(r, ensure_ascii=False)[:300]}")
        time.sleep(interval)
    raise RuntimeError("任务轮询超时")


# ============================================================
# 链路一：转存（别人的分享 -> 我的网盘）
# ============================================================

def get_stoken(pwd_id, passcode=""):
    """取分享 stoken。pwd_id = 夸克分享链接 /s/ 后面那串。"""
    url = ("https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token"
           "?pr=ucpro&fr=pc&uc_param_str=")
    r = call(url, {"pwd_id": pwd_id, "passcode": passcode})
    if r.get("code") != 0:
        raise RuntimeError(f"取stoken失败 code={r.get('code')} msg={r.get('message')}")
    return r["data"]["stoken"]


def save_share(pwd_id, stoken, to_pdir_fid, use_bx=False):
    """提交转存任务，返回 (task_id, resp)。"""
    url = "https://drive-h.quark.cn/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc&uc_param_str="
    body = {
        "pwd_id": pwd_id,
        "stoken": stoken,
        "pdir_fid": "0",
        "to_pdir_fid": to_pdir_fid,
        "pdir_save_all": True,
        "scene": "link",
    }
    r = call(url, body, extra_headers=BX_HEADERS if use_bx else None)
    if r.get("code") != 0:
        return None, r
    return (r.get("data") or {}).get("task_id"), r


def do_save(pwd_id, to_fid, label="", log=print):
    """完整转存：stoken -> save（被拒自动带风控头重试）-> 轮询。"""
    log(f"== 转存: {label or pwd_id}")
    stoken = get_stoken(pwd_id)
    task_id, resp = save_share(pwd_id, stoken, to_fid, use_bx=False)
    if task_id is None:
        log(f"   无风控头被拒: code={resp.get('code')} {resp.get('message')}，带风控头重试")
        task_id, resp = save_share(pwd_id, stoken, to_fid, use_bx=True)
        if task_id is None:
            raise RuntimeError(f"转存失败: code={resp.get('code')} msg={resp.get('message')}")
    poll_task(task_id)
    log("   ✅ 转存成功")
    return True


# ============================================================
# 链路二：分享（我的网盘 -> 生成分享链接）
# 来源: 老板 n8n 工作流抓包提取 + 实测修正
# ============================================================

# expired_type 有效期枚举: 1=永久 2=1天 3=7天 4=30天
# url_type: 1=公开链接 2=私密链接（必须同时传 4 位 passcode，服务端不随机生成）

import random as _random
import string as _string


def _rand_passcode():
    """随机 4 位提取码（去掉易混淆的 i/l/o/0/1）。"""
    chars = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(_random.choice(chars) for _ in range(4))


def create_share_task(fid_list, url_type=1, expired_type=1, passcode=None):
    """对网盘文件/文件夹创建分享任务，返回 task_id。
    fid_list: [fid, ...] 可一次分享多个。
    url_type=2（私密）时必须传 4 位 passcode，否则报 41000 提取码不符合规范。"""
    url = "https://drive-pc.quark.cn/1/clouddrive/share?pr=ucpro&fr=pc&uc_param_str="
    body = {"fid_list": fid_list, "url_type": url_type, "expired_type": expired_type}
    if url_type == 2:
        body["passcode"] = passcode or _rand_passcode()
    r = call(url, body)
    if r.get("code") != 0:
        raise RuntimeError(f"创建分享任务失败 code={r.get('code')} msg={r.get('message')}")
    return (r.get("data") or {}).get("task_id")


def get_share_id(task_id):
    """轮询分享任务，拿到 share_id。"""
    d = poll_task(task_id)
    share_id = d.get("share_id")
    if not share_id:
        raise RuntimeError(f"任务成功但无 share_id: {json.dumps(d, ensure_ascii=False)[:300]}")
    return share_id


def get_share_detail(share_id):
    """查自己某个分享的真实状态（url_type/passcode/share_url/过期时间等）。"""
    r = call(f"https://drive-pc.quark.cn/1/clouddrive/share/mypage/detail"
             f"?pr=ucpro&fr=pc&uc_param_str=&share_id={share_id}")
    if r.get("code") != 0:
        raise RuntimeError(f"查分享详情失败 code={r.get('code')} msg={r.get('message')}")
    items = (r.get("data") or {}).get("list") or []
    return items[0] if items else {}


def set_share_password(share_id):
    """回显分享信息（n8n 工作流里的 POST /share/password）。
    ⚠️ 实测：此接口只回显 share_url 等信息，不生成也不修改密码。
    要密码分享，在 create_share_task 时用 url_type=2 + passcode。"""
    url = "https://drive-pc.quark.cn/1/clouddrive/share/password?pr=ucpro&fr=pc&uc_param_str="
    r = call(url, {"share_id": share_id})
    if r.get("code") != 0:
        raise RuntimeError(f"查分享信息失败 code={r.get('code')} msg={r.get('message')}")
    return r.get("data") or {}


def update_share(pwd_id, url_type=None, expired_type=None, passcode=None, title=None):
    """修改已有分享（接口要 pwd_id 不吃 share_id）。
    ⚠️ 实测：返回 ok 但 url_type/passcode 改不动（服务端不落地），仅标题等可改。
    改密码/公开互转请删掉重分享。"""
    url = "https://drive-pc.quark.cn/1/clouddrive/share/update?pr=ucpro&fr=pc&uc_param_str="
    body = {"pwd_id": pwd_id}
    if url_type is not None:
        body["url_type"] = url_type
    if expired_type is not None:
        body["expired_type"] = expired_type
    if passcode is not None:
        body["passcode"] = passcode
    if title is not None:
        body["title"] = title
    r = call(url, body)
    if r.get("code") != 0:
        raise RuntimeError(f"更新分享失败 code={r.get('code')} msg={r.get('message')}")
    return r.get("data") or {}


def do_share(fid, expired_type=1, with_password=True, passcode=None, log=print):
    """完整分享链路: 创建任务 -> 轮询得 share_id -> 查详情拿真实链接+密码。
    with_password=True 时走私密分享（url_type=2），提取码自动随机或用传入值。
    返回 dict: share_id / pwd_id / share_url / passcode / fid。"""
    log(f"== 分享: fid={fid} ({'私密' if with_password else '公开'})")
    task_id = create_share_task([fid], url_type=2 if with_password else 1,
                                expired_type=expired_type, passcode=passcode)
    share_id = get_share_id(task_id)
    detail = get_share_detail(share_id)
    result = {
        "share_id": share_id,
        "pwd_id": detail.get("pwd_id"),
        "share_url": detail.get("share_url"),
        "passcode": detail.get("passcode"),
        "fid": fid,
    }
    log(f"   ✅ {result['share_url']}  密码: {result['passcode'] or '无'}")
    return result


# ============================================================
# 网盘文件操作（列表/容量）
# ============================================================

def list_dir(fid="0", page=1, size=100):
    """列目录，返回 (list, metadata)。"""
    q = urllib.parse.urlencode({
        "pr": "ucpro", "fr": "pc", "uc_param_str": "", "pdir_fid": fid,
        "_page": str(page), "_size": str(size), "_fetch_total": "1",
        "_sort": "file_type:asc,updated_at:desc",
    })
    r = call(f"https://drive-pc.quark.cn/1/clouddrive/file/sort?{q}")
    if r.get("code") != 0:
        raise RuntimeError(f"列目录失败 code={r.get('code')} msg={r.get('message')}")
    d = r.get("data") or {}
    return d.get("list", []), d.get("_metadata") or {}


def get_capacity():
    """查容量，返回 (used_gb, total_gb, percent)。"""
    r = call("https://drive-pc.quark.cn/1/clouddrive/member?pr=ucpro&fr=pc"
             "&uc_param_str=&_ch=home&fetch_share=true&fetch_shop=true&fetch_subscribe=true")
    data = r.get("data") or {}
    t = data.get("total_capacity") or 0
    u = data.get("use_capacity") or 0
    if not t:
        raise RuntimeError("容量查询失败")
    return u / 1024**3, t / 1024**3, u / t * 100


def find_by_name(name, pdir_fid="0", max_pages=50):
    """按名字在目录（含子层可选）里找文件/文件夹，返回 list[dict]。
    精确匹配 file_name；找不到返回 []。"""
    hits = []
    for page in range(1, max_pages + 1):
        items, meta = list_dir(pdir_fid, page=page, size=100)
        if not items:
            break
        for it in items:
            if it.get("file_name") == name:
                hits.append(it)
    return hits


def mkdir(name, pdir_fid="0"):
    """在指定目录下新建文件夹，返回 fid。"""
    r = call("https://drive-pc.quark.cn/1/clouddrive/file?pr=ucpro&fr=pc&uc_param_str=",
             {"pdir_fid": pdir_fid, "file_name": name,
              "dir_path": "", "dir_init_lock": False})
    if r.get("code") != 0:
        raise RuntimeError(f"新建目录失败 code={r.get('code')} msg={r.get('message')}")
    return (r.get("data") or {}).get("fid")


def delete(fids, to_trash=True):
    """删除文件/文件夹（异步任务）。
    to_trash=True  进回收站（默认，可恢复）——安全默认
    to_trash=False 永久删除（不可恢复！）
    fids: [fid, ...] 可批量。返回轮询后的任务 data（含 affected_file_num）。"""
    if isinstance(fids, str):
        fids = [fids]
    r = call("https://drive-pc.quark.cn/1/clouddrive/file/delete?pr=ucpro&fr=pc&uc_param_str=",
             {"action": 2, "filelist": fids, "to_trash": to_trash})
    if r.get("code") != 0:
        raise RuntimeError(f"删除失败 code={r.get('code')} msg={r.get('message')}")
    task_id = (r.get("data") or {}).get("task_id")
    return poll_task(task_id) if task_id else {}


def rename(fid, new_name):
    """重命名文件/文件夹。"""
    r = call("https://drive-pc.quark.cn/1/clouddrive/file/rename?pr=ucpro&fr=pc&uc_param_str=",
             {"fid": fid, "file_name": new_name})
    if r.get("code") != 0:
        raise RuntimeError(f"重命名失败 code={r.get('code')} msg={r.get('message')}")
    return r.get("data") or {}


def move(fids, to_pdir_fid):
    """移动文件/文件夹到目标目录（异步任务）。fids 可批量。"""
    if isinstance(fids, str):
        fids = [fids]
    r = call("https://drive-pc.quark.cn/1/clouddrive/file/move?pr=ucpro&fr=pc&uc_param_str=",
             {"action": 1, "filelist": fids, "to_pdir_fid": to_pdir_fid})
    if r.get("code") != 0:
        raise RuntimeError(f"移动失败 code={r.get('code')} msg={r.get('message')}")
    task_id = (r.get("data") or {}).get("task_id")
    return poll_task(task_id) if task_id else {}


def search(keyword, page=1, size=20):
    """全盘文件名搜索。返回 (list, _metadata)。"""
    from urllib.parse import quote
    r = call(f"https://drive-pc.quark.cn/1/clouddrive/file/search"
             f"?pr=ucpro&fr=pc&uc_param_str=&q={quote(keyword)}&_page={page}&_size={size}")
    if r.get("code") != 0:
        raise RuntimeError(f"搜索失败 code={r.get('code')} msg={r.get('message')}")
    d = r.get("data") or {}
    return d.get("list", []), d.get("_metadata") or {}


def list_my_shares(page=1, size=50):
    """列出我创建的所有分享（含链接/提取码/状态）。"""
    r = call(f"https://drive-pc.quark.cn/1/clouddrive/share/mypage/detail"
             f"?pr=ucpro&fr=pc&uc_param_str=&_page={page}&_size={size}")
    if r.get("code") != 0:
        raise RuntimeError(f"查分享列表失败 code={r.get('code')} msg={r.get('message')}")
    return (r.get("data") or {}).get("list") or []


def cancel_share(pwd_ids):
    """取消分享（失效链接）。pwd_ids: [pwd_id, ...] 可批量。"""
    if isinstance(pwd_ids, str):
        pwd_ids = [pwd_ids]
    r = call("https://drive-pc.quark.cn/1/clouddrive/share/delete?pr=ucpro&fr=pc&uc_param_str=",
             {"pwd_ids": pwd_ids})
    if r.get("code") != 0:
        raise RuntimeError(f"取消分享失败 code={r.get('code')} msg={r.get('message')}")
    return r.get("data") or {}


def peek_share(pwd_id, pdir_fid="0"):
    """预览别人分享的内容（不转存）。返回顶层文件列表。
    内部先取 stoken。pdir_fid 可逐层进入子目录。"""
    import urllib.parse
    stoken = get_stoken(pwd_id)
    st = urllib.parse.quote(stoken)
    r = call(f"https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"
             f"?pr=ucpro&fr=pc&uc_param_str=&pwd_id={pwd_id}&pdir_fid={pdir_fid}&stoken={st}")
    if r.get("code") != 0:
        raise RuntimeError(f"预览失败 code={r.get('code')} msg={r.get('message')}")
    return (r.get("data") or {}).get("list") or []
