#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夸克网盘自动转存+自动分享 CLI。

用法:
  python3 quark_cli.py list [fid]                      # 列目录（默认根目录），验证登录态
  python3 quark_cli.py cap                             # 查容量
  python3 quark_cli.py save <pwd_id> [目标fid]          # 转存一个夸克分享
  python3 quark_cli.py save-djss <djss页码> [目标fid]   # 从 djss.cc 页码转存
  python3 quark_cli.py share <fid> [--no-pwd] [--days N]  # 分享网盘文件/目录
  python3 quark_cli.py watch [监控fid] [输出csv]        # 循环: 新文件夹自动分享并记录
  python3 quark_cli.py delete <fid|名字>... [--dir fid] [--hard] [--yes]
                                           # 删除: 默认进回收站; --hard=永久删; --yes=免确认
  python3 quark_cli.py mkdir <名字> [父fid]   # 新建文件夹
  python3 quark_cli.py rename <fid> <新名字>  # 重命名
  python3 quark_cli.py move <fid|名字>... --to <目标fid> [--yes]  # 移动文件/目录
  python3 quark_cli.py find <关键词>          # 全盘搜索文件名
  python3 quark_cli.py shares               # 列出我的全部分享（链接+密码+状态）
  python3 quark_cli.py unshare <pwd_id|all>  # 取消分享（all=全部，需确认）
  python3 quark_cli.py peek <分享链接|pwd_id> [子目录fid]  # 预览别人分享的内容（不转存）

环境变量:
  QUARK_COOKIE   登录态 Cookie（优先级最高）；也可放本目录 cookie.txt
  DEBUG=1        打印原始响应
"""
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quark_api as q  # noqa: E402

# 默认监控这个目录（n8n 工作流里的 fid：87bba317...）
DEFAULT_WATCH_FID = "87bba317d61843c98307a0bc6604adb2"
# 默认转存目标（老板抓包时的「来自：分享」目录）
DEFAULT_SAVE_FID = "f0ccb8f1c1a14f189563614c8bafb313"

HERE = os.path.dirname(os.path.abspath(__file__))


def cmd_list(fid):
    files, meta = q.list_dir(fid)
    print(f"目录 {fid} 共 {meta.get('total', '?')} 项:")
    for f in files:
        tag = "目录" if f.get("dir") else "文件"
        print(f"  [{tag}] {f.get('file_name')}  fid={f.get('fid')}")


def cmd_cap():
    u, t, p = q.get_capacity()
    print(f"容量: {u:.0f}GB / {t:.0f}GB ({p:.1f}%)")


def cmd_save(pwd_id, to_fid):
    q.do_save(pwd_id, to_fid)


def cmd_save_djss(page_no, to_fid):
    import re
    import urllib.request
    url = f"https://www.djss.cc/d/{int(page_no):05d}.html"
    req = urllib.request.Request(url, headers={"user-agent": q.UA})
    html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    t = re.search(r"<title>([^<]+)</title>", html)
    m = re.search(r"pan\.quark\.cn/s/([0-9a-zA-Z]+)", html)
    if not m:
        print(f"页面 {page_no} 未找到夸克链接")
        sys.exit(1)
    title = t.group(1).replace(" - 短剧搜搜", "") if t else f"第{page_no}部"
    q.do_save(m.group(1), to_fid, label=f"[{page_no}] {title}")


def cmd_share(fid, with_pwd=True, expired_type=1, passcode=None):
    r = q.do_share(fid, expired_type=expired_type, with_password=with_pwd,
                   passcode=passcode)
    # 机器可读输出一行 JSON（方便上游脚本解析）
    print("JSON:" + json.dumps(r, ensure_ascii=False))


def cmd_watch(watch_fid, out_csv):
    """n8n 工作流的本地版：定时扫目录，新文件夹自动分享，结果记 CSV。
    状态存 .watch_seen.json（fid 列表），重启续跑不重复分享。"""
    seen_file = os.path.join(HERE, ".watch_seen.json")
    seen = set()
    if os.path.exists(seen_file):
        seen = set(json.load(open(seen_file)))
    new_file = not os.path.exists(out_csv)
    print(f"开始监控目录 {watch_fid}，每 10 分钟扫一次，记录 -> {out_csv}")
    while True:
        try:
            files, _ = q.list_dir(watch_fid, size=100)
            fresh = [f for f in files if f["fid"] not in seen]
            for f in fresh:
                print(f"[发现] {f['file_name']} fid={f['fid']}")
                try:
                    r = q.do_share(f["fid"], with_password=True)
                    with open(out_csv, "a", newline="", encoding="utf-8-sig") as fp:
                        w = csv.writer(fp)
                        if new_file:
                            w.writerow(["文件夹ID", "文件夹名称", "父目录ID", "创建时间",
                                        "分享链接", "分享密码"])
                            new_file = False
                        w.writerow([f["fid"], f["file_name"], f["pdir_fid"],
                                    f["created_at"], r.get("share_url", ""),
                                    r.get("passcode", "")])
                    print(f"[分享] ✅ {r.get('share_url')}")
                except Exception as e:
                    print(f"[分享] ❌ {f['file_name']}: {e}")
                seen.add(f["fid"])
                json.dump(sorted(seen), open(seen_file, "w"))
                time.sleep(3)
        except Exception as e:
            print(f"[扫描异常] {e}（可能 Cookie 过期），60 秒后重试")
        time.sleep(600)


def cmd_delete(fids_or_names, pdir_fid, to_trash, assume_yes):
    """按 fid 或（目录内精确）名字删除。安全措施：
    1) 默认进回收站；2) 先列出目标让用户确认，--yes 跳过；3) 永久删需 --hard 显式指定。"""
    resolved = []
    for x in fids_or_names:
        if len(x) == 32 and all(c in "0123456789abcdef" for c in x):
            resolved.append({"fid": x, "file_name": x})
        else:
            hits = q.find_by_name(x, pdir_fid)
            if not hits:
                print(f"❌ 没找到名为「{x}」的文件/目录（在 {pdir_fid} 第一层）")
                sys.exit(1)
            resolved.extend(hits)
    if not resolved:
        print("没有要删除的目标")
        sys.exit(1)
    print("将删除以下目标:")
    for it in resolved:
        print(f"  - {it['file_name']}  fid={it['fid']}")
    print(f"方式: {'进回收站（可恢复）' if to_trash else '⚠️ 永久删除（不可恢复）'}")
    if not assume_yes:
        ans = input("确认删除？输入 yes 继续: ").strip()
        if ans != "yes":
            print("已取消")
            sys.exit(0)
    d = q.delete([it["fid"] for it in resolved], to_trash=to_trash)
    print(f"✅ 删除完成，共 {d.get('affected_file_num', '?')} 项")


def main():
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd == "list":
        cmd_list(a[1] if len(a) > 1 else "0")
    elif cmd == "cap":
        cmd_cap()
    elif cmd == "save" and len(a) > 1:
        cmd_save(a[1], a[2] if len(a) > 2 else DEFAULT_SAVE_FID)
    elif cmd == "save-djss" and len(a) > 1:
        cmd_save_djss(a[1], a[2] if len(a) > 2 else DEFAULT_SAVE_FID)
    elif cmd == "share" and len(a) > 1:
        with_pwd = "--no-pwd" not in a
        days = 1
        if "--days" in a:
            days = int(a[a.index("--days") + 1])
        code = None
        if "--code" in a:
            code = a[a.index("--code") + 1]
        cmd_share(a[1], with_pwd=with_pwd, expired_type=days, passcode=code)
    elif cmd == "watch":
        cmd_watch(a[1] if len(a) > 1 else DEFAULT_WATCH_FID,
                  a[2] if len(a) > 2 else os.path.join(HERE, "shares.csv"))
    elif cmd == "delete" and len(a) > 1:
        # 用法: delete <fid或名字>... [--dir fid] [--hard] [--yes]
        targets = [x for x in a[1:] if not x.startswith("--")]
        to_trash = "--hard" not in a
        pdir = a[a.index("--dir") + 1] if "--dir" in a else "0"
        cmd_delete(targets, pdir, to_trash, "--yes" in a)
    elif cmd == "mkdir" and len(a) > 1:
        fid = q.mkdir(a[1], a[2] if len(a) > 2 else "0")
        print(f"✅ 已创建 fid={fid}")
    elif cmd == "rename" and len(a) > 2:
        q.rename(a[1], a[2])
        print(f"✅ 已重命名为 {a[2]}")
    elif cmd == "move" and len(a) > 2:
        # 用法: move <fid|名字>... --to <目标目录fid> [--yes]
        targets = [x for x in a[1:] if not x.startswith("--")]
        dest = a[a.index("--to") + 1] if "--to" in a else None
        if not dest:
            print("需要 --to <目标目录fid>")
            sys.exit(1)
        assume = "--yes" in a
        resolved = []
        for x in targets:
            if len(x) == 32 and all(c in "0123456789abcdef" for c in x):
                resolved.append({"fid": x, "file_name": x})
            else:
                hits = q.find_by_name(x, a[a.index("--dir") + 1] if "--dir" in a else "0")
                resolved.extend(hits)
        print(f"将移动 {len(resolved)} 项到 {dest}:")
        for it in resolved[:10]:
            print(f"  - {it['file_name']}")
        if not assume:
            if input("确认移动？输入 yes: ").strip() != "yes":
                print("已取消"); sys.exit(0)
        d = q.move([it["fid"] for it in resolved], dest)
        print(f"✅ 移动完成，共 {d.get('affected_file_num', '?')} 项")
    elif cmd == "find" and len(a) > 1:
        items, _ = q.search(a[1], size=30)
        print(f"搜「{a[1]}」{len(items)} 条:")
        for it in items:
            tag = "目录" if it.get("dir") else "文件"
            print(f"  [{tag}] {it['file_name']}  fid={it['fid']}")
    elif cmd == "shares":
        items = q.list_my_shares()
        print(f"我的分享共 {len(items)} 条:")
        for it in items:
            pwd = it.get("pwd_id")
            code = it.get("passcode")
            st = "有效" if it.get("status") == 1 else "失效"
            print(f"  [{st}] {it.get('title')}  https://pan.quark.cn/s/{pwd}  密码:{code or '无'}")
    elif cmd == "unshare" and len(a) > 1:
        # 用法: unshare <pwd_id|all|url片段>
        x = a[1]
        if x == "all":
            items = q.list_my_shares(size=100)
            ids = [it["pwd_id"] for it in items]
            if input(f"确认取消全部 {len(ids)} 个分享？输入 yes: ").strip() != "yes":
                print("已取消"); sys.exit(0)
            q.cancel_share(ids)
            print(f"✅ 已取消 {len(ids)} 个分享")
        else:
            q.cancel_share(x)
            print(f"✅ 已取消分享 {x}")
    elif cmd == "peek" and len(a) > 1:
        # 用法: peek <分享pwd_id或链接> [子目录fid]
        pwd = a[1].rstrip("/").split("/")[-1]
        items = q.peek_share(pwd, a[2] if len(a) > 2 else "0")
        print(f"分享 {pwd} 顶层 {len(items)} 项:")
        for it in items:
            tag = "目录" if it.get("dir") else "文件"
            sz = it.get("size", 0) / 1024**3
            print(f"  [{tag}] {it['file_name']}  fid={it['fid']}{'  ' + format(sz, '.1f') + 'GB' if sz > 0.01 else ''}")
        print("（要转存整包: python3 quark_cli.py save " + pwd + "）")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
