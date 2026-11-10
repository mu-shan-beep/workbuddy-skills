# quark-drive — 夸克网盘自动化工具包（给 Agent 的完整上手指南）

> 版本：2026-09-11 · 适用对象：任何能执行 shell/Python 的 AI Agent 或开发者
> 全部接口来自夸克网页端（pan.quark.cn）真实抓包，已在本机实测：**3600+ 部批量转存零风控**、分享/删除/移动/搜索全链路验证通过。

---

## 1. 这个包是什么

夸克网盘没有公开 API，本包把网页端抓包接口封装成了两层：

| 文件 | 作用 | 行数 |
|---|---|---|
| `scripts/quark_api.py` | Python 库（所有接口的函数封装） | ~410 |
| `scripts/quark_cli.py` | 命令行入口（14 个命令，可直接 shell 调用） | ~250 |
| `scripts/get_cookie.py` | Cookie 自动获取（开浏览器检测登录态/等扫码） | ~160 |
| `references/api_reference.md` | 底层 API 文档（端点/参数/风控要点） | ~130 |
| `SKILL.md` | WorkBuddy/Claude 格式的 skill 描述文件 | — |

核心能力：
- **转存**：别人的夸克分享链接 → 一条命令存入自己网盘（含风控头自动降级重试）
- **分享**：自己网盘的文件/目录 → 私密链接（带 4 位提取码）或公开链接
- **文件管理**：列目录/搜索/新建/删除/重命名/移动/容量
- **分享管理**：列出我的全部分享（含链接+密码）/ 批量取消 / 预览别人的分享
- **监控分享**：`watch` 常驻循环，目录里出现新文件夹自动创建分享并记 CSV

---

## 2. 安装（30 秒）

```bash
# 解压到任意位置（若作为 WorkBuddy/Claude skill 安装，解压到 ~/.workbuddy/skills/ 下）
unzip quark-drive.zip -d ~/.workbuddy/skills/
cd ~/.workbuddy/skills/quark-drive/scripts

# 依赖：仅 Python 3 标准库，无需 pip install 任何东西
python3 quark_cli.py cap   # 能打印容量 = Cookie 有效、环境就绪
```

唯一可选依赖：`get_cookie.py` 需要 agent-browser（仅当 Cookie 过期需要自动重新获取时才用）：
```bash
npm install -g agent-browser && agent-browser install
```

---

## 3. 登录态配置（最关键的一步）

所有接口的鉴权全靠 Cookie，无签名。读取优先级：

```
环境变量 QUARK_COOKIE  >  scripts/cookie.txt  >  脚本内置 Cookie（必定过期）
```

**拿到有效 Cookie 的三种方式：**

1. **自动获取（推荐）**：跑 `python3 get_cookie.py`
   - 自动打开浏览器访问 pan.quark.cn
   - 已登录 → 直接抓 Cookie 验证落盘
   - 未登录 → 弹出二维码等你扫码（默认等 300 秒，`--timeout 600` 可延长）
   - 完成后自动验证并写入 `scripts/cookie.txt`

2. **手动抓包**：浏览器登录 pan.quark.cn → F12 → Network → 任一 drive-pc 请求 → 复制请求头里 Cookie 整串 → 存入 `scripts/cookie.txt`（或 `export QUARK_COOKIE='...'`）

3. **直接跑一次 `cap` 试试**：包里自带的 Cookie 是作者账号的（2026-09-09 抓取），可能还有效——先跑 `python3 quark_cli.py cap`，有输出就直接能用。

**Cookie 过期的特征**：所有接口返回 `code != 0` 或 HTTP 403/302。
**Cookie 有效标志**：包含 `__pus / __puus / __kp / __kps` 四个关键字段，且 member 接口验证通过。

---

## 4. CLI 快速上手（14 个命令）

```bash
cd <skill目录>/scripts

# ── 基本信息 ──
python3 quark_cli.py list [fid]          # 列目录（fid=0 或省略 = 根目录），顺带验证登录态
python3 quark_cli.py cap                 # 容量: 已用GB / 总GB / 百分比
python3 quark_cli.py find <关键词>        # 全盘文件名搜索

# ── 转存（别人的分享 → 我的网盘）──
python3 quark_cli.py save <pwd_id> [目标fid]
#   pwd_id = 分享链接 https://pan.quark.cn/s/abcdefg 里最后那串 "abcdefg"
#   目标fid 省略时存入内置默认目录（见下文「内置 fid」）

python3 quark_cli.py peek <分享链接|pwd_id>          # 先预览分享内容，不转存
python3 quark_cli.py peek <pwd_id> <子目录fid>        # 进入子目录预览

# ── 分享（我的网盘 → 生成链接）──
python3 quark_cli.py share <fid>                    # 私密分享，自动随机4位提取码，永久有效
python3 quark_cli.py share <fid> --no-pwd           # 公开链接，无密码
python3 quark_cli.py share <fid> --days 3           # 7天有效（1=永久 2=1天 3=7天 4=30天）
python3 quark_cli.py share <fid> --code ab12        # 指定提取码（必须4位）
#   输出末尾有一行 JSON:{"share_url":...,"passcode":...} 供上游脚本解析

# ── 文件管理 ──
python3 quark_cli.py mkdir <名字> [父fid]            # 新建文件夹（父fid省略=根目录）
python3 quark_cli.py rename <fid> <新名字>           # 重命名
python3 quark_cli.py move <fid|名字>... --to <目标fid> [--yes]   # 批量移动
python3 quark_cli.py delete <fid|名字>... [--dir fid] [--hard] [--yes]
#   默认进回收站（可恢复）；--hard = 永久删除（不可恢复！）
#   交互确认输入 yes；自动化场景加 --yes 跳过确认

# ── 分享管理 ──
python3 quark_cli.py shares               # 列出我的全部分享（标题/链接/密码/状态）
python3 quark_cli.py unshare <pwd_id>     # 取消单个分享
python3 quark_cli.py unshare all          # 取消全部分享（需输入 yes）

# ── 常驻监控 ──
python3 quark_cli.py watch [监控fid] [输出csv]   # 每10分钟扫目录，新文件夹自动私密分享并记 CSV
```

 fid 从哪来？`list` / `find` / `shares` 的输出里都带 `fid=xxx`。32 位小写 hex 串即 fid。

### 内置 fid（原作者账号的目录，其他账号请自行 list 根目录后替换）

| 用途 | fid |
|---|---|
| 默认转存目标「来自：分享」 | `f0ccb8f1c1a14f189563614c8bafb313` |
| 默认监控目录（watch 用） | `87bba317d61843c98307a0bc6604adb2` |

---

## 5. Python API 用法

```python
import sys
sys.path.insert(0, "<skill目录>/scripts")
import quark_api as q

# ── 转存 ──
q.do_save("pwd_id", "目标目录fid", label="剧名")
#   内部: get_stoken → save_share（被风控拒时自动带 bx 头重试）→ poll_task

# ── 分享 ──
r = q.do_share("文件fid")                    # 私密+随机码+永久
#   返回 {"share_id","pwd_id","share_url","passcode","fid"}
r = q.do_share("fid", with_password=False)   # 公开链接
r = q.do_share("fid", expired_type=3)        # 7天有效

# ── 文件管理 ──
files, meta = q.list_dir(fid)                # files[].fid/file_name/dir/size/pdir_fid
u, t, p = q.get_capacity()                   # 已用GB/总GB/百分比
hits = q.find_by_name("精确名字", pdir_fid)   # 目录第一层精确找，返回 []
found, meta = q.search("关键词")              # 全盘模糊搜索
fid = q.mkdir("新目录", pdir_fid)
q.delete([fid], to_trash=True)               # True=回收站(默认) False=永久!
q.rename(fid, "新名字")
q.move([fid1, fid2], "目标目录fid")

# ── 分享管理 ──
items = q.list_my_shares()                   # 全部分享列表
q.cancel_share(["pwd_id1", "pwd_id2"])       # 批量取消
listing = q.peek_share("别人的pwd_id")        # 预览别人分享（返回文件列表）

# ── 底层（自己拼任意接口）──
r = q.call(url, body=None)                   # body=None 则 GET，否则 POST JSON
d = q.poll_task(task_id)                     # status 2=成功 3=终态失败 <0=失败
```

---

## 6. 批量转存实战模式（断点续跑、防风控）

单次转存直接用 CLI；**上千次批量**请遵循以下已验证的模式：

```python
import quark_api as q, time, json

SAVE_FID = "你的目标目录fid"
done = set(open("saved_pages.txt").read().split())   # 断点：已成功的
pages = [...]                                        # 待转存清单

for p in pages:
    if str(p) in done: continue
    try:
        q.do_save(pwd_id_of(p), SAVE_FID, label=f"[{p}]")
        done.add(str(p))
        open("saved_pages.txt", "w").write("\n".join(sorted(done)))
    except RuntimeError as e:
        msg = str(e)
        if any(k in msg for k in ("任务终态失败", "41009", "已删除", "已失效",
                                   "违规", "已取消", "分享不存在")):
            # 死链：重试无意义，归档跳过
            open("dead_pages.txt", "a").write(f"{p}\t{msg}\n")
        else:
            open("failed_pages.txt", "a").write(f"{p}\n")
    time.sleep(2)          # ★ 每部间隔 ≥2 秒
```

**防风控三原则**（3600+ 部实测零翻车的关键）：
1. **串行，绝不并发**；每部之间 `time.sleep(2)` 以上
2. 连续异常时等 20 秒再继续
3. 转存接口有**每日 200 次额度**（`member` 接口 `data.member.file_save_to_remains` 可查），按天刷新，跑批前先查额度

---

## 7. 实测踩坑合集（不看必踩）

1. **`POST /share/password` 不生成密码**——它只回显分享信息。私密分享必须在创建时 `url_type=2 + passcode`（4位，服务端不会随机生成，缺了报 `41000 提取码不符合规范`）。
2. **`/share/update` 改不动密码**——返回 ok 但 url_type/passcode 不落地。改密码 = 取消重分享。
3. **不能转存自己的分享**——报 `41017 用户禁止转存自己的分享`（分享自己的文件给同一账号的两个目录也不行，只能用 move）。
4. **转存接口域名是 drive-h**，其余全是 drive-pc——手写接口别搞混。
5. **重复转存产生 `(1)` 目录**——同一分享转存两次，第二次会生成 `xxx (1)` 文件夹，上游务必记断点防重跑。
6. **异步任务都要轮询**——删除/移动/分享/转存全部返回 `task_id`，用 `q.poll_task()` 等完成；status=3 是终态失败（顶层 code/message 给原因），重试无意义。
7. **回收站接口摸不到**——`/trash/*` 全 404，恢复文件只能去网页端回收站；所以 `delete` 默认 `to_trash=True` 留后路。
8. **pds 下载域对 Cookie 校验更严**——用 `file/download` 拿 download_url 下载文件时，JSON 接口能用的旧 Cookie 可能报 "auth expired"，此时用 get_cookie.py 刷新 Cookie 即可（headers 记得带 `Referer: https://pan.quark.cn/`）。
9. **离线下载没有接口**——磁力/链接离线路由不在 drive-pc，未摸到。
10. **fid 是 32 位小写 hex**——CLI 的 delete/move 支持传名字（在指定父目录第一层精确匹配），但传 fid 最稳。

---

## 8. 安全红线（给 Agent 的硬约束）

- **Cookie = 账号钥匙**。`cookie.txt` 是 skill 私有文件，不要拷贝到工作目录、不要写进任何对外产物（报告/日志/代码示例）、不要打印到对话里。
- 批量操作保持 ≥2 秒间隔，**勿并发**，否则可能触发风控连累账号。
- `delete --hard` 是永久删除，Agent 在自动化场景调用前必须获得用户明确确认。
- 分享链接一旦发给他人即视为公开，涉密内容分享前三思。
- `watch` 是死循环常驻进程，跑批环境注意用 nohup/后台任务管理，别卡住交互会话。

---

## 9. 常见问题排查

| 症状 | 原因 | 处理 |
|---|---|---|
| 所有命令报 code!=0 / 403 | Cookie 过期 | 跑 `python3 get_cookie.py` 或手动更新 cookie.txt |
| 转存报 41008 | 触发风控 | 库已自动带 bx 风控头重试；仍失败就等几分钟 |
| 转存报 41009 | 分享已被删除/失效 | 死链，归档跳过，别重试 |
| 分享报 41000 | 私密分享缺 passcode | 传 4 位提取码，或用 do_share 默认流程 |
| 转存报 41017 | 转存自己的分享 | 用 move 代替 |
| 任务轮询超时 | 网络慢/任务大 | poll_task 默认 60 次×1.5s，可加大 max_retry |
| 下载文件报 auth expired | 下载域 Cookie 校验严 | 刷新 Cookie，带 Referer 头 |

---

## 10. 给 Agent 的建议工作流

1. **第一次接触**：先跑 `cap` 验证 Cookie → `list` 看根目录结构 → 建立 fid 认知
2. **转存任务**：`peek` 确认内容 → `save` 转存 → `list` 目标目录确认落位
3. **整理任务**：`find`/`list` 收集 fid → 批量 `move`（50 个/批）→ **移动后重新列目录终验**（分页边界会漏项，务必终验不要信清单算术）
4. **分享任务**：`share <fid>` → 解析输出里的 JSON 行拿链接+密码 → 交付用户
5. **出问题**：查第 9 节对照表；Cookie 类问题一律先 `get_cookie.py` 刷新
