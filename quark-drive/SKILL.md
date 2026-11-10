---
name: quark-drive
version: 1.0.0
display_name: 夸克网盘助手
display_name_en: Quark Drive
description_zh: 夸克网盘自动化工具：自动转存（别人的分享链接存入自己网盘）、自动分享（生成链接和提取码）、目录监控自动分享，以及列目录/搜索/删除/重命名/移动等文件管理，附 Cookie 自动获取。基于网页端抓包 API，已实测 3600+ 部批量转存零风控。
description_en: Quark cloud drive automation save (others' share links to your drive), share (generate links with passcodes), directory monitoring with auto-sharing, and file management (list/search/delete/rename/move), with auto Cookie acquisition. Based on real web-capture APIs, battle-tested with 3600+ batch saves without risk control.
description: 夸克网盘自动化工具：自动转存（别人的分享链接存入自己网盘）+ 自动分享（把自己的文件/目录生成分享链接和提取码）+ 目录监控自动分享。触发词：夸克网盘、转存、夸克分享、分享链接、pan.quark.cn、自动分享、监控网盘目录。基于网页端抓包 API，已实测 3600+ 部批量转存零风控。
agent_created: true
---

# Quark Drive — 夸克网盘自动转存+自动分享

## Overview

两条已实测的抓包 API 链路封装：

1. **转存**：夸克分享链接 → stoken → 提交任务 → 轮询 → 文件落入自己网盘（批量验证 3600+ 部）
2. **分享**：网盘 fid → 创建分享任务 → 轮询得 share_id → 链接 + 提取码
3. **监控**：定时扫目录，新文件夹自动分享并记 CSV（老板原 n8n 工作流的本地版）

## 核心脚本

`scripts/quark_api.py`（库）+ `scripts/quark_cli.py`（命令行入口）+ `scripts/get_cookie.py`（Cookie 自动获取）。

登录态优先级：环境变量 `QUARK_COOKIE` > `scripts/cookie.txt` > 内置 Cookie（会过期）。

### Cookie 自动获取（get_cookie.py）

打开浏览器自动检测夸克登录状态：已登录直接抓 Cookie，未登录弹出窗口等用户扫码（默认等 300 秒），登录完成自动抓取并调 member 接口验证有效性。

```bash
cd <skill目录>/scripts
python3 get_cookie.py              # 检测+抓取+验证，写入同目录 cookie.txt
python3 get_cookie.py --check      # 只检测，不写文件
python3 get_cookie.py --timeout 600   # 延长扫码等待
python3 get_cookie.py --out /path/cookie.txt  # 指定输出路径
```

依赖：`npm install -g agent-browser && agent-browser install`（首次用需装）。
判定逻辑：页面出现「全部文件」=已登录；出现「扫码登录」=未登录；Cookie 含 `__pus/__puus/__kp/__kps` 才算完整；最后必须过 member 接口验证。

Cookie 过期特征：所有接口 code!=0 或 403。更新方法：跑 `python3 get_cookie.py`，或浏览器登录 pan.quark.cn → F12 → Network → 复制 Cookie 整串存入 cookie.txt。

## CLI 用法

```bash
cd <skill目录>/scripts

python3 quark_cli.py list [fid]            # 列目录（fid 默认根目录），验证登录态
python3 quark_cli.py cap                   # 查容量（used/total/percent）
python3 quark_cli.py save <pwd_id> [目标fid]        # 转存：pwd_id = 分享链接 /s/ 后那串
python3 quark_cli.py save-djss <页码> [目标fid]     # 从 djss.cc 页码解析并转存
python3 quark_cli.py share <fid> [--no-pwd] [--days 1|2|3|4] [--code ab12]
                                           # 分享：默认私密+随机4位提取码+永久
python3 quark_cli.py watch [监控fid] [输出csv]      # 每10分钟扫目录，新文件夹自动分享
  python3 quark_cli.py delete <fid|名字>... [--dir fid] [--hard] [--yes]
                                           # 删除：默认进回收站；--hard=永久删；--yes=免确认
  python3 quark_cli.py mkdir <名字> [父fid]   # 新建文件夹
  python3 quark_cli.py rename <fid> <新名字>  # 重命名
  python3 quark_cli.py move <fid|名字>... --to <目标fid> [--yes]  # 移动文件/目录
  python3 quark_cli.py find <关键词>          # 全盘搜索文件名
  python3 quark_cli.py shares               # 列出我的全部分享（链接+密码+状态）
  python3 quark_cli.py unshare <pwd_id|all>  # 取消分享（all=全部，需确认）
  python3 quark_cli.py peek <分享链接|pwd_id> [子目录fid]  # 预览别人分享内容（不转存）
```

删除安全机制（`delete`）：
- **默认进回收站**（`to_trash=True`，可在网盘网页回收站恢复）；`--hard` 才是永久删除（不可恢复，慎用）
- 支持 fid（32位hex）或目录第一层的精确名字（`--dir` 指定父目录，默认根目录）
- 删除前打印目标清单要求输入 `yes` 确认；自动化场景才加 `--yes`
- 一次可传多个目标批量删

默认转存目标 fid=`f0ccb8f1c1a14f189563614c8bafb313`（「来自：分享」目录）。
默认监控 fid=`87bba317d61843c98307a0bc6604adb2`（来自老板 n8n 工作流）。

## Python API 用法

```python
import quark_api as q

# —— 转存 ——
q.do_save("分享pwd_id", "目标fid", label="剧名")   # 全链路，含风控头自动降级

# —— 分享 ——
r = q.do_share("文件fid", with_password=True)     # 返回 share_url + passcode
r = q.do_share("文件fid", with_password=False)    # 公开链接无密码

# —— 文件管理 ——
files, meta = q.list_dir(fid)                     # files[].fid/file_name/dir/size
u, t, p = q.get_capacity()                        # 已用GB/总GB/百分比
hits = q.find_by_name("剧名", pdir_fid)           # 目录第一层按名字精确找
found, meta = q.search("关键词")                  # 全盘模糊搜索
fid = q.mkdir("新目录名", pdir_fid)               # 新建文件夹
q.delete([fid], to_trash=True)                    # 删除（默认进回收站，False=永久）
q.rename(fid, "新名字")                           # 重命名
q.move([fid], "目标目录fid")                      # 移动

# —— 分享管理 ——
items = q.list_my_shares()                        # 我的全部分享（含链接/密码/状态）
q.cancel_share(["pwd_id1", "pwd_id2"])            # 批量取消分享
listing = q.peek_share("别人分享的pwd_id")        # 预览别人分享内容（不转存）

# —— 底层 ——
q.call(url, body=None)                            # 任意接口，GET/POST 自动判断
q.poll_task(task_id)                              # status 2=成功 3=终态失败 <0=失败
```

## 批量转存模式（断点续跑）

参考工作目录 `quark_save/`（save_latest.py + retry_failed.py 模式）：

- `saved_pages.txt` 记成功页码防重跑；`failed_pages.txt` 待重试；`dead_pages.txt` 死链归档
- 死链判定：错误含「任务终态失败/41009/已删除/违规/已取消/分享不存在/已失效」→ 归档不重试
- 串行 + 每部间隔 2 秒 + 连续异常等 20 秒；转存次数限制 `file_save_to_remains` 200/日
- 完整 API 文档见 `references/api_reference.md`（含全部端点、参数、风控要点）

## 实测踩坑（重要）

1. **`/share/password` 不生成密码**——只回显分享信息。n8n 工作流靠它拿链接+密码是误解：密码来自创建时 `url_type=2 + passcode`。
2. **私密分享必须带提取码**——`url_type=2` 不传 passcode 报 `41000 提取码不符合规范`；服务端不会随机生成，客户端自己随机 4 位。
3. **`/share/update` 改不动密码**——返回 ok 但 url_type/passcode 不落地（要 pwd_id 不吃 share_id）。改密码 = 删掉重分享。
4. **不能转存自己的分享**——报 `41017 用户禁止转存自己的分享`（链路此时已通）。
5. **转存接口域名是 drive-h**，其余都是 drive-pc。
6. **同目录重复转存**产生 `(1)` 后缀重复文件夹，上游要做好去重记录。

## 安全红线

- Cookie/风控头是账号凭据，不写入任何对外产物，不打印到日志；`cookie.txt` 已是 skill 私有文件，勿拷贝到工作目录
- 批量操作保持 ≥2 秒间隔，勿并发
- 分享链接一旦发给他人即视为公开，涉密内容分享前三思
- get_cookie.py 会打开真实浏览器等扫码，跑批时注意别在无人值守场景误触发等待
