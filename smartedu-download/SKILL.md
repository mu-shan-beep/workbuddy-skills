---
name: smartedu-download
display_name: 国家中小学智慧教育平台资源下载
display_name_en: SmartEdu Resource Downloader
description: "下载国家中小学智慧教育平台（basic.smartedu.cn）及公开课直播（www.smartedu.cn/publiclive）资源：教材PDF、课程视频(mp4)、课件(pptx)、教学设计/学习任务单/课后练习(docx)、公开课直播回放(mp4)。支持免登录公开教材下载、登录后受保护资源下载、多CDN源自动切换、断点续传。触发词：下载智慧平台教材/课程/课件/视频/教案，或提供 activityId / contentId / 课程链接。"
description_zh: "一键下载国家中小学智慧教育平台（basic.smartedu.cn）的教材PDF、课程视频、课件、教学设计、学习任务单、课后练习，以及公开课直播（www.smartedu.cn/publiclive）回放视频。支持免登录公开教材与登录后受保护资源，自动处理双认证与AES-128加密HLS。"
description_en: "One-click download of textbooks (PDF), course videos, slides, lesson plans and public live-class replays from China's Smart Education Platform (basic.smartedu.cn / www.smartedu.cn). Handles dual-auth and AES-128 encrypted HLS."
category: 教育资源下载
version: "2.5.0"
author: WorkBuddy
license: MIT
agent_created: true
---

# 国家中小学智慧教育平台资源下载

一键下载国家中小学智慧教育平台资源，核心特点：

## 资源类型支持

| 类型 | 脚本 | 格式 | 认证需求 |
|------|------|------|----------|
| **电子教材** | `download_textbook.py` | PDF | 部分公开可免登录；受保护需 token |
| **视频课程** | `download_course.py` | mp4 | 需 token（Bearer 认证） |
| **课件** | `download_course.py` | pptx | 需 token（Bearer 认证） |
| **教学设计/任务单/练习** | `download_course.py` | docx | 需 token（Bearer 认证） |
| **公开课直播回放** | `download_publiclive.py` | mp4 | 需 token（Bearer + MAC 双认证） |

## 公开课直播下载（www.smartedu.cn/publiclive）

```bash
python "{skill_base}/scripts/download_publiclive.py" \
  --url "https://www.smartedu.cn/publiclive/{live_id}?sdp-app-id=..." \
  --out ./课程下载/公开课直播
```

或指定 live_id：
```bash
python "{skill_base}/scripts/download_publiclive.py" \
  --live-id "464a45be-f7a6-4d28-9f3b-b171fce7ff94"
```

**算法说明**：
- API 获取 m3u8：`https://x-api.ykt.eduyun.cn/proxy/live/v3/open_class_lives/{live_id}`
- AES 密钥通过 nonce+sign 认证获取（复用 smartedu_core.py 算法）：
  - GET `{key_uri}/signs` → nonce
  - sign = MD5(nonce + key_id)[:16]
  - GET `{key_uri}?nonce={nonce}&sign={sign}` → base64 加密 key
  - AES-ECB(sign) 解密 → PKCS7 unpad → 最终 AES-CBC key
- TS 分片用 Bearer 认证下载
- ffmpeg concat 合并为 mp4

**运行注意**：Python 输出缓冲可能导致进度不可见，建议加 `-u` 参数：
```bash
python -u "{skill_base}/scripts/download_publiclive.py" --url "..."
```

## 健壮性特性

1. **多CDN源自动切换**：s-file-1/2/3.ykt.cbern.com.cn 自动故障转移
2. **双认证机制**：API调用使用MAC认证，文件下载使用Bearer认证
3. **断点续传**：支持大文件下载中断后继续
4. **指数退避重试**：网络不稳定时自动重试 3-5 次
5. **Token 自动获取**：从 Edge Local Storage 直接读取，无需用户操作
6. **PDF 书签注入**：自动添加章节目录（需 PyMuPDF）
7. **后台资源分析**：当标准提取失败时，深度扫描所有字段查找资源URL
8. **智能完整性校验**：smart模式检查PDF头尾，自动重下载不完整文件

## 触发条件

当用户出现以下任一意图时使用本 skill：

- 给出智慧平台链接（教材/课程/课件）
- 要求「下载智慧平台教材/课程/课件/视频/教案」
- 提供 activityId 或 contentId

## 工作流程

### 1. 教材下载（PDF）

```bash
python "{skill_base}/scripts/download_textbook.py" \
  --url "https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=XXX" \
  --out ./教材下载
```

支持两种URL格式：
- 普通教材：`contentType=assets_document`
- 资源包教材：`contentType=thematic_course`

### 2. 课程资源下载（视频+课件+文档）

```bash
python "{skill_base}/scripts/download_course.py" \
  --activity-id {activityId} \
  --token-file ./smartedu_token.txt \
  --out ./课程下载
```

## 核心约束

1. **Token 自动获取**：脚本优先从 Edge Local Storage 读取，无需用户手动操作
2. **公开教材可免登录**：部分教材无需 token 即可下载
3. **受保护资源需 token**：视频/课件/文档需要有效的 access_token
4. **Token 有效期**：通常数小时至数天，过期后重新获取
5. **不要绕过脚本**：统一调用官方脚本，不使用外部工具

## 排错

| 现象 | 处理 |
|------|------|
| 教材解析 401 | 使用已登录浏览器的 token（脚本会自动读取） |
| 教材下载失败 | 检查网络；部分教材需登录才能下载 |
| 视频下载失败 | 密钥服务器需 X-ND-AUTH；脚本已内置重试 |
| Token 过期 | 重新登录平台后运行脚本，自动更新 token |

## 教材结构 DUMP（teachingmaterials 类，只 dump 不下载）

部分教材（如「道德与法治二年级上册」`08c775e6-...`）是 **teachingmaterials 类**，与单课时课程的 **national_lesson 类** 鉴权规则不同：

| 类型 | 资源清单接口 | 鉴权 |
|---|---|---|
| national_lesson | `/zxx/ndrv2/national_lesson/resources/details/{id}.json`（s-file CDN） | **公开无鉴权**，可直连 curl / Bearer |
| teachingmaterials | `teachingmaterials/{ID}/resources/...`（basic.smartedu.cn） | **必须带浏览器会话态**，裸 API（含 token / MAC）一律 403 |

> 实测：用裸 token（Bearer 或弱 MAC）直连 teachingmaterials 接口，无论 `trees` 还是 `resources` 全部 403；只有应用自身在已登录页面内导航才返回 200。所以**纯脚本无法 dump 此类教材结构**，必须捕获应用自身的 200 响应。

### 工具：`scripts/dump_textbook_structure.py`（只 dump 结构，不下载任何文件）

```bash
# 1) 捕获：启动已登录浏览器，监听 teachingmaterials 资源接口并落盘到 captures/
python dump_textbook_structure.py --capture \
  --teachingmaterial-id 08c775e6-83eb-7f05-ef45-3a8d03a0ceda \
  --url "https://basic.smartedu.cn/syncClassroom/teachingmaterial?teachingmaterialId=08c775e6-83eb-7f05-ef45-3a8d03a0ceda" \
  --user-data-dir "C:/Users/User/AppData/Local/Microsoft/Edge/User Data"   # 复用本机已登录会话，跳过扫码

# 2) 解析：把 captures/ 汇总成结构报告（离线、纯本地，无需浏览器）
python dump_textbook_structure.py --parse
```

- `--capture`：默认用 Playwright 启动 Chromium + 扫码登录；传 `--user-data-dir` 可复用本机已登录 Edge 会话（注意：若 Edge 正在运行会冲突，需先关闭）。监听所有含 `teachingmaterials`+`resources` 的 JSON 响应，自动存到 `captures/`。用户手动逐课点开（或加 `--auto` 实验性自动点选），结束后按 Enter。
- `--parse`：递归提取每课 5 类资源（`micro_lesson_video`/`coursewares`/`lesson_plandesign`/`learning_task`/`after_class_exercise`）及其直链，输出 `structure_report.json` + `structure_report.md`。
- 资源条目字段与 national_lesson 一致：`global_title.zh-CN` + `resource_type_code` + `ti_items[].ti_storages`（m3u8 / pdf）。

# 国家智慧教育平台资源下载

一键下载国家中小学智慧教育平台（basic.smartedu.cn）课程包，自动转换格式并归集到本地目录。核心特点：

- **视频课程**：AES-128 加密 HLS(m3u8) → mp4（默认 720p，可切 480/360）
- **课件**：PDF → pptx（整页保真）
- **教学设计 / 学习任务单 / 课后练习**：PDF → docx（文本可编辑；纯图页转嵌图）
- **一键取 TOKEN**：通过书签小工具（bookmarklet）自动把已登录浏览器里的 access_token 回传到本地，无需手动翻 DevTools → Local Storage
- **需求反馈**：下载互动中收集到的定制需求，自动发送至开发者邮箱（收件人已内置在 `scripts/feedback.py`，文档不公开明文）

## 触发条件

当用户出现以下任一意图时使用本 skill：

- 给出类似 `https://basic.smartedu.cn/syncClassroom/classActivity?activityId=...` 的课程链接
- 直接提供 `activityId`
- 要求「下载智慧平台课程 / 课件 / 视频 / 教案 / 学习任务单 / 课后练习」

## 首次交互引导（技能第一次被使用时，优先执行一次）

用户**第一次**使用本技能时，先给出下面这段简明引导（一次即可，后续无需重复），把用法说清再进流程：

> 欢迎使用「国家中小学智慧教育平台资源下载」。
> - **直接复制粘贴资源链接给我即可**：教材详情页、课程页（classActivity / qualityCourse）、课件、公开课直播回放（publiclive）等任意链接都支持。
> - **如果是课程**，你可以明确说「只要视频」或「只要课件 / 文档」；**不说明的话，默认下载该课程的全部资源**（视频 + 课件 + 教学设计 + 学习任务单 + 课后练习）。
> - 受保护资源（视频 / 课件 / 文档）需要登录态 token，脚本会自动从本机已登录浏览器读取，无需你手动操作。

（以下是链接形态最佳实践，可选阅读，不必每次重复）

为保证一次下载成功、少走弯路，**优先提供标准的课堂活动链接（classActivity）**，例如：
`https://basic.smartedu.cn/syncClassroom/classActivity?activityId=713d4809-e590-4f80-bc11-270dc87d01f5&chapterId=600df9c1-d9a1-3e92-9909-e5d77fa0f746&teachingmaterialId=948ac1e5-1586-4ca7-b0d5-14f6e52583b9&fromPrepare=1`
这类链接直接带 `activityId=`，脚本可一键解析资源清单并下载，最快最稳。若你手头是 `experimentLesson?courseId=...&classHourId=...`（实验教学课）或其他形态链接，也能下，但需先额外逆向解析出真实 activityId，耗时更长——所以优先用上面的标准链接。

判断逻辑（AI 执行）：

- 用户链接含 `activityId=` → 直接进入「工作流程」第 1 步。
- 用户链接不含 `activityId=`（如 `experimentLesson?courseId=...`）→ 先按上面话术提示，再视情况走「工作流程·第 1 步注」里的逆向解析；若逆向无把握，请用户改发标准 classActivity 链接。
- 用户未给链接、只说「下载课程」→ 给出标准链接范例，请其粘贴完整链接。
- 用户明确说「只要视频」→ 用 `--only-video`；说「只要课件/文档」→ 用 `--only courseware`（或 `plan,task,exercise`）；**未说明资源类型 → 全量下载所有资源**。

## 核心约束

1. **双认证机制**：视频资源使用不同认证方式
   - **m3u8 索引 + ts 分片**：Bearer 认证 (`Authorization: Bearer <token>`)
   - **密钥服务器**：MAC 认证 (`X-ND-AUTH: MAC id="<token>",nonce="0",mac="0"`)
   - **文档文件**：两种均可，推荐 Bearer
   - ⚠️ 混用会 401/403
2. **必须持有 access_token 才能下载受保护资源**。资源清单接口公开，但视频/文档文件托管在 CDN。
3. **token 有时效（通常数小时）**。若下载报 401 / 清单为空，引导用户重新取 token 后重跑。
4. **不要绕过本 skill 的脚本**。统一调用 `{skill_base}/scripts/download_course.py` 与 `{skill_base}/scripts/token_helper.py`。
5. 脚本仅依赖 Python 标准库，第三方库（PyMuPDF / python-pptx / python-docx / pycryptodome / imageio-ffmpeg）由 `ensure_deps()` 首次运行时自动联网安装；**不依赖 requests / mammoth / pdf2image / 系统 ffmpeg / poppler**。可用系统 Python 3.11 或 WorkBuddy 托管 Python 运行；若环境禁联网，先手动 `python -m pip install PyMuPDF python-pptx python-docx pycryptodome imageio-ffmpeg`。
6. **视频下载有重试机制**：网络不稳定时单个分片可能 IncompleteRead 或 400，脚本会自动重试最多 5 次，递增延迟（2s, 4s, 6s...）。

## 工作流程（一键完成）

**调用方式**：`@skill:smartedu-download-4lhpzcgd` + 课程链接

```bash
python "{skill_base}/scripts/smart_download.py" \
  --activity-id {activityId} \
  --token-file ./smartedu_token.txt \
  --out ./下载输出目录
```

实验课模式：
```bash
python "{skill_base}/scripts/smart_download.py" \
  --experiment --course-id {courseId} \
  --class-hour-id lesson_1 \
  --token-file ./smartedu_token.txt
```

### 通用 URL 模式（推荐，覆盖 qualityCourse / 精品课等）

`download_course.py` 现支持直接吃**任意平台链接**，自动识别路由
（qualityCourse / classActivity / tchMaterial / experiment / prepare …），
不必再人工把链接反解成 activityId：

```bash
python "{skill_base}/scripts/download_course.py" \
  --url "https://basic.smartedu.cn/qualityCourse?courseId=XXX&chapterId=YYY" \
  --token-file ./smartedu_token.txt \
  --out ./下载输出目录 \
  [--only video,courseware] [--only-video] [--quality 720|480|360]
```

- `--url`：按 URL 路径片段归类（`detect_smartedu_url`），逐个试 `DETAIL_CANDIDATES`
  模板（匿名优先、带 token 兜底），命中即解析资源清单；主路由失败自动走全目录兜底。
  对 qualityCourse，`courseId=` 即真实 rid（`chapterId` / `teachingmaterialId` 会 403）。
- `--only-video`：只下视频。
- `--only`：按类型挑选，逗号分隔。支持别名 `video|courseware|plan|task|exercise`，
  也可直接写类型码 `micro_lesson_video|cousewares|lesson_plandesign|learning_task|after_class_exercise`。
  例：`--only video,courseware` = 只要视频+课件（常用组合）。
- 文档优先取**原生 Office 格式**（pptx/docx/xlsx…）直接落盘；只有 PDF 转码件时才走
  PDF→PPTX/DOCX 转换（`pick_doc_native`），避免可编辑文字被转成图片。
- 资源标题自带扩展名时会去重，避免 `快乐读书吧.mp4.mp4`。

### 取 TOKEN（统一入口：token_manager.py）

> 自 v2.4.0-patch4 起，token 相关逻辑统一收口到 `scripts/token_manager.py`，
> 取代原本散落的 `edge_login_token.py` / `token_helper.py` / `get_token_from_edge_storage()` 三套路径。
> 它同时解决两点：**获取便捷**（一个命令融合「已登录静默续期 / 扫码密码登录 / 手动粘贴」）与
> **持续性**（token 过期后优先用持久化 profile 的 Cookie 无感续期，无需重新扫码）。

```bash
pip install playwright        # 兜底弹窗登录（非必需，仅当 pywebview 不可用时）
pip install pywebview         # 内嵌登录窗口（推荐；Windows 自动复用内置 Edge WebView2）

# 获取/刷新 token（已登录则静默取回；否则弹出【工具自有内嵌窗口】：二维码 + 账号密码 合一界面）
python "{skill_base}/scripts/token_manager.py" acquire --token-file ./smartedu_token.txt

# 仅查看当前状态（有效期 / 是否含 mac_key / 服务端探测）
python "{skill_base}/scripts/token_manager.py" status --token-file ./smartedu_token.txt

# token 过期后，用持久化 profile 无头续期（不弹登录页、不重新扫码，前提是 .edge_profile Cookie 仍在）
python "{skill_base}/scripts/token_manager.py" refresh --token-file ./smartedu_token.txt
```

**登录界面是「独立内嵌显示窗口」而非「弹出系统 Edge」**：`acquire` 默认用 `scripts/login_window.py`（pywebview）
在**工具自有的窗口**里加载官方 UC 登录页（`uc.basic.smartedu.cn` 本就内置「二维码扫码 + 用户名密码」两种入口，天然合一），
不再弹出系统 Edge、也不借用用户默认浏览器。登录成功后脚本自动读取 `basic.smartedu.cn` 的 Local Storage 取回 `access_token + mac_key`。
若 pywebview 不可用，会**自动回退**到 Playwright 弹真实 Edge 窗口（旧行为）。

**持续性机制（关键）**：

- `acquire` / `refresh` 写入的 token 文件带 `expires_at`（默认按 2h 乐观门禁，可用环境变量 `SMARTEDU_TOKEN_TTL` 调整）。
- `download_*.py` 现在统一调用 `token_manager.get_valid_token(token_file)`，其优先级：
  1. 文件内 token 且未过期 → 直接返回（**零交互**）；
  2. 已过期 → 用 `.edge_profile` 的 Cookie **无头续期**（无需重新登录，只要平台登录态未退）；
  3. 仍无效 → 兜底读本机日常 Edge 的 Local Storage leveldb；
  4. 全失败 → 返回 None，脚本提示运行 `acquire`。
- 因此：只要 `.edge_profile` 的登录 Cookie 还在（通常比 access_token 活得久），token 过期后下载脚本会**自动无感续期**，不必每次手动取。

**编程接口**（供 `download_textbook.py` / `download_course.py` 调用）：

```python
from token_manager import get_valid_token
tok = get_valid_token(token_file)        # 返回 dict 或 None
access_token = tok["access_token"]
mac_key     = tok.get("mac_key") or ""   # 视频下载必须有 mac_key
```

> 注：`edge_login_token.py` 仍是底层引擎（Playwright 复用系统 Edge），`token_helper.py`（HTTP 接收器）仅作历史兼容保留，
> 但它**只抓裸 access_token、缺 mac_key**，视频下载会失败，不要再作为主路径使用。

4. **收集需求**：下载完成后询问用户是否有新需求，整理后通过 `scripts/feedback.py` 发送至开发者邮箱（收件人已内置，不在此公开）

### 第 3 步：运行下载脚本

```bash
python "{skill_base}/scripts/download_course.py" \
  --activity-id {activityId} \
  --token-file ./smartedu_token.txt \
  --out ./下载输出目录
```

可选参数：

- `--quality 720|480|360`：视频清晰度，默认 720
- `--no-pdf`：不保留平台原始 PDF 副本

脚本会：自动装依赖 → 拉取资源清单 → 下载并转换每个资源 → 打印成功/失败清单。

### 第 4 步：交付与说明

- 输出目录结构：`/<课程名>/视频课程/`、`/课件/`、`/教学设计/`、`/学习任务单/`、`/课后练习/`
- 向用户说明两点限制：
  - 课件 pptx 为「整页图片式」，视觉一致但文字不可直接选中编辑。
  - token 过期后再次下载需重新取。

### 第 5 步：收集需求并发送反馈

下载完成后，主动询问用户是否有新增需求或改进建议（如：增加某学科批量下载、调整输出格式、支持字幕等）。

若用户提出需求，整理成不超过 3 条 bullet，通过 `scripts/feedback.py` 发送（收件人已内置，**文档不公开明文地址**）：

- **收件人**：由 `feedback.get_recipient()` 提供（开发者邮箱，勿在文档/回复中写出明文）
- **主题**：智慧教育平台下载需求反馈 - activityId: {activityId}
- **正文**：
  1. 用户原话/需求要点
  2. 关联课程 activityId
  3. 期望优先级或联系方式（若用户补充）

发送方式优先顺序：

1. 若当前环境已连接 Agent Mail（`mcp__agent-mail__SendMessage`），调用该工具，收件人填 `feedback.get_recipient()` 的返回值。
2. 若 Agent Mail 不可用，由 AI 运行 `python scripts/feedback.py --subject "..." --body "..." --mode mailto`，把生成的 `mailto:` 链接交给用户一键转发；或 `--mode text` 生成可直接复制的纯文本。

## 排错

| 现象 | 处理 |
|---|---|
| 清单下载 401 / 空 | activityId 错误 或 token 失效，重取 token |
| 视频下载 HTTP 400 InvalidArgument | 该 CDN（如 r1-ndr-private 精品课）**不接受 Bearer**，返回 400 而非 401/403。core 现已把 400 也视为鉴权失败并自动回退 X-ND-AUTH MAC，且首个分片确定后全局复用该模式 |
| 视频失败 | 检查网络；密钥服务器需 X-ND-AUTH（非 Bearer）+ signs 流程；脚本已内置重试（5次递增延迟） |
| `No module named fitz/Crypto...` | 脚本应已自动安装；若沙箱禁联网，手动 `python -m pip install PyMuPDF python-pptx python-docx pycryptodome imageio-ffmpeg` |
| pptx/docx 打开为空 | 平台源 PDF 为扫描图，docx 会退化为嵌图，pptx 不受影响 |
| `--inspect` 却把资源全下下来了 | **v2.4.0-patch1 已修**：原先 `--inspect` 只在实验课路径 `run_experiment()` 里 return，标准课程路径不检查它 → 本想「只看清单」却全量下载。现已在清单打印后立即返回，配合 `--only` 使用更稳妥 |
| 视频下完残留 `_ts_*` 目录（甚至比 mp4 还大） | **v2.4.0-patch1 已修**：原先 `rmtree` 丢进 daemon 线程 fire-and-forget，进程退出时线程被强杀导致分片整包留存（实测 125 文件 / 92.7MB）。现已改为同步清理 |
| 搜出一堆同名教材，不知道下哪个 | **先看「版本」行再看学段**：`find_textbook.py`（patch2 起）会把 `zxxbb` 版本标签和人/出版社名单独列出。同名的一年级上册数学实测有 **9 个版本**（人教/北京/北师大/冀教/苏教/青岛/西南大学/沪教）。若命中里有多条同标题 ID，脚本会主动告警 |
| 用户说「统编版」数学/英语/科学等 | **不存在统编版**。教育部统编教材仅限**语文、道德与法治、历史**三科。其他学科须回问版本或学制（如五•四学制 → 青岛版/沪教版） |
| 标题里 `·` 和 `•` 混用，以为是两本书 | 平台录入不一致造成，**不代表不同版本**。真正的版本差异看 `zxxbb` 标签 + `provider_list`，不要凭中点符号判断 |
| 下载产物没落在 `--out` 指定目录 | 仅在显式传 `--out` 时生效；省略时脚本用「当前工作目录 + 课程名」。用驱动脚本调用 `main()` 时注意工作目录，或始终显式传 `--out` |
| 书签小工具点击后未收到 token | 确认当前页面是 `basic.smartedu.cn` 且已登录；确认本地接收器正在运行且端口未被占 |

详细接口、鉴权与解密算法见 `references/api_notes.md`。

## 算法提炼与增强（v2.3.0，源自 crawler-base cb-0.1.17x）

v2.3.0 把成熟项目 `crawler-base` 的 smartedu 解析/下载算法提炼进本技能，统一收敛到
`scripts/smartedu_core.py`，并保留本技能已验证的**双认证铁律**（视频 m3u8/ts 用 Bearer、密钥服务器用 MAC）。

### 1. 共享核心 `scripts/smartedu_core.py`
- **路由识别 `detect_smartedu_url`**：按 URL 路径片段精准归类
  （classActivity / tchMaterial / experiment / qualityCourse / prepare / sedu / art / reading / eliteLesson…），未知类型一律走全目录并发兜底，不再漏解析。
- **NDR 详情路径映射表 `DETAIL_CANDIDATES`**：每个资源类型对应正确 details 路径
  （tch_material 属 `ndrs/resources/tch_material/details/`、classActivity 属 `ndrv2/national_lesson/...`；注意 **ndrs 与 ndrv2 两套形态、写错即 403**）。
- **候选并发探测 `probe_first_hit` 思路**：强命中（带 `ti_items`）即返回，弱命中（仅元数据、匿名请求偶发精简版）暂存，杜绝「解析成功却 0 资源」。
- **资源提取三形态**：`relations:<key>` / `single` / `auto` 自适应。
- **标题 `get_title`**：同时认 `global_title.zh-CN` 与 `title` 字符串（tch_material 详情只有后者，此前标题退化为 `smartedu_{uuid}`）。
- **`pick_video_url` / `pick_pdf_url`**：按 `ti_file_flag` 优先级选清晰度；`pick_pdf_url` 返回 r1/r2/r3 全部副本供下载回退。

### 2. 视频下载增强（并发 + 防卡死 + 降级）
- **并发拉分片**：`download_hls` 默认 16 线程（env `CB_HLS_WORKERS` 可调，钳制 4–32），失败分片补抓 2 轮；密钥仅取一次（线程安全缓存）。比旧版顺序下载显著提速（百级分片场景）。
- **去 combined.ts**：改用 ffmpeg `concat demuxer` 流式封装，规避大文件合并卡死（旧版曾在 88 分片/95MB 处 100% 卡死）。
- **ffmpeg 日志落盘**：stderr 写文件而非 PIPE，规避 Windows 64KB 管道缓冲死锁。
- **TS 降级交付**：mp4 封装彻底失败时流式拼接出 `.ts` 交付（播放器可直读），不再判失败/永久卡 99%。
- **认证回退**：媒体(m3u8/ts) 优先 Bearer、失败回退 MAC；密钥永远 MAC（铁律）。

### 3. 文档下载增强（多副本 × 主机变体 × 匿名回退）
- `download_doc_to_file`：依次尝试 r1/r2/r3 副本 × `rN-ndr → rN-ndr-private` 主机变体 × 带 token 被拒再匿名。教材/文档多为「明文公开」，过期 token 反而会让其 403，故带 token 失败后再匿名重试一次，任一成功即返回。已接入 `download_textbook.py` 与 `download_course.py` 的文档分支。

### 4. 按名检索教材（解决搜索 API 403）——`scripts/find_textbook.py`
- 平台搜索 API（`/zxx/ndrv2/search/resources.json`）返回 403，无法按关键词下载。
- 解法：tch_material 模块有**匿名 + 免浏览器**整库索引
  `data_version.json → part_100/101/...json`（每片 1000 条完整元数据，全量约 4000 条/40MB）。
- 本脚本拉取索引后本地离线检索，输出命中教材的 id 与可直接用的下载命令；可加 `--download` 直接下载首个命中。

```bash
# 按名/学科/年级/版本模糊检索（无需登录）
python "{skill_base}/scripts/find_textbook.py" "道德与法治二年级上册"
python "{skill_base}/scripts/find_textbook.py" "美术鉴赏" --download --token-file ./smartedu_token.txt
```

> 实测：检索「美术」命中 283 条、「道德与法治」68 条（含二年级上册 `cfdc0cbb-...`、「数学」261 条。
> 注意：此索引仅覆盖 **tch_material（备课资源/教材）** 模块；其余模块（national_lesson 课程、experiment 等）该路径 403，仍需按 activityId 直接下。

### 5. 按标题搜索课程（用户只给了课程名、没有链接）——`scripts/smartedu_search.py`

**痛点**：用户常只说「下载《XXX》课程中的视频和课件」，不给 URL；而课程（national_lesson /
qualityCourse）没有像 tch_material 那样的匿名整库索引，`find_textbook.py` 查不到。

**解法**：站内搜索真实接口是 `https://x-search.ykt.eduyun.cn/v1/resources/combine/search`
（不是文档里那个 403 的 `/zxx/ndrv2/search/resources.json`）。用 Playwright 复用已登录的
`.edge_profile` 打开首页 → 在搜索框输入关键词 → 监听 `response`，即可拿到结构化结果：

- `items[].title`（含 `<b>` 高亮，需剥标签）、`resource_id` / `src_content_id`、
  `resource_type`（`national_lesson` / `micro_lesson_video` / `coursewares` / `lesson_plandesign` / …）、
  `extra.rel_course_title`（所属课程名，**用它判断资源归属哪个课程包**）。
- 拿到课程包的 `src_content_id`（`resource_type=national_lesson` / `elite_lesson`）
  即可拼 `https://basic.smartedu.cn/qualityCourse?courseId=<id>` 交给 `download_course.py --url`。

```bash
python "{skill_base}/scripts/smartedu_search.py" "以工匠精神雕琢时代品质"
python "{skill_base}/scripts/smartedu_search.py" "XXX" --json-out hits.json   # 存响应体便于人工核对
```

实测要点：
- 首页搜索框选择器 `input[placeholder*="搜索"]`，填词后 `Enter` 即可，无需登录跳转。
- 搜索结果 25 条里通常混着多个课程包（同名课文有「国家精品课」「学科课程精品课」等不同版本），
  **必须按 `extra.rel_course_title` 精确匹配用户给的标题**，否则会下错版本。
- 命中后下一步：`download_course.py --url "...qualityCourse?courseId=<id>" --only video,courseware`。

---

## 部署 / 迁移到新设备（本地技能测试）

本技能为**用户级本地技能**，目录即技能根。迁移 = 复制目录 + 重装依赖 + 重新取 token（**不要跨设备复用本机 token**）。

### 1. 打包（排除敏感 / 缓存 / 开发产物）
- **保留**：`SKILL.md`、`_icon.png`、`scripts/`、`references/`、`requirements.txt`
- **排除**：
  - `smartedu_token.txt`（本机登录态，敏感凭据，**必须每台设备重新取**）
  - `.edge_profile/`（Playwright 持久化浏览器 profile，含登录 Cookie，体积大且敏感）
  - `scripts/__pycache__/`
  - `morality_tree.json`、`structure_report*`、`structure_preview.md`（开发期产物，非运行必需）
- 做法：zip 整个技能目录后手动删掉上述文件，或用 `robocopy` / `cp` 选择性复制。
- **依赖体积提示**：`playwright` 只是 Python 包（很小）；脚本用 `channel="msedge"` 复用系统已装 Edge，
  **不需要** `playwright install chromium`（省 ~150MB）。目标设备若没装 Edge/Chromium，
  则 `smartedu_search.py` 与 `edge_login_token.py` 不可用，但纯下载脚本不受影响。

### 2. 部署到目标设备
解压到目标设备的用户级技能目录，WorkBuddy 重启后自动识别（跨项目可用）：
- Windows：`C:/Users/<用户名>/.workbuddy/skills/smartedu-download-4lhpzcgd/`
- macOS / Linux：`~/.workbuddy/skills/smartedu-download-4lhpzcgd/`

### 3. 安装依赖（关键，必须做）
`pycryptodome`（视频 HLS AES-128 解密）、`pymupdf`（PDF 书签注入/校验）、`imageio-ffmpeg`（自带 ffmpeg 二进制，视频封装）、`python-pptx`（课件→pptx）、`python-docx`（文档→docx）、`playwright`（v2.4 起用于 `edge_login_token.py` 取 token 与 `smartedu_search.py` 站内搜索）。
```bash
# 用你实际运行脚本的 python 对应的 pip
python -m pip install -r requirements.txt
```
- 若用 **WorkBuddy 对话触发**技能，则装在 WorkBuddy 托管 Python 的 venv：
  `~/.workbuddy/binaries/python/envs/default/Scripts/pip install -r requirements.txt`
- 若目标设备**禁联网**：离线下载上述三个 wheel 后 `pip install *.whl`。

### 4. 获取目标设备自己的 token（不要拷本机 token）
token 含登录态、有时效，跨设备失效。统一用 `token_manager.py` 获取（默认内嵌窗口 pywebview，兜底复用系统 Edge）：
```bash
python scripts/token_manager.py acquire --token-file ./smartedu_token.txt
```
- 已登录（`.edge_profile` 的 Cookie 还在）→ **静默取回**，不弹窗；否则弹出**工具自有内嵌登录窗口**（`login_window.py` / pywebview，加载官方 UC 登录页，**二维码 + 账号密码合一界面**），扫码或输密码后脚本自动抓 `access_token + mac_key` 写入 JSON（pywebview 不可用时回退 Playwright 弹 Edge）。
- **视频下载必须有 `mac_key`**，所以务必走 `acquire`（不要用只抓裸 token 的旧 `token_helper.py`）。
- 登录态落在技能目录 `.edge_profile/`，下次复用；token 过期后下载脚本会自动用该 profile **无感续期**（见「取 TOKEN」节）。
- macOS 上若 `channel="msedge"` 失败，可把 `token_manager.py` 里 `_launch_pw()` 的 `channel="msedge"` 换成 `channel="chrome"`。
- **纯手动兜底**：从 Edge DevTools → Application → Local Storage 复制含 `access_token`+`mac_key` 的 value，存成 `{"access_token":"...","mac_key":"..."}` 文件，再 `--token-file` 传入。

### 5. 验证测试
```bash
# 按标题搜索课程（验证 x-search 接口 + 浏览器登录态）
python scripts/smartedu_search.py "以工匠精神雕琢时代品质"
# 免登录检索教材（验证匿名整库索引遍历）
python scripts/find_textbook.py "数学六年级下册"
# PDF 下载（验证双认证 + 多副本回退 + 中文 URL 编码）
python scripts/download_textbook.py --content-id 7babfb85-3808-4789-8b6c-0ddd66feb85b --token-file ./smartedu_token.txt --out ./教材下载
# 视频下载（验证并发 HLS + 密钥 MAC，需 mac_key）
python scripts/download_course.py --activity-id e3881dc5-1c4e-4bb4-9b08-f22a9eb05311 --token-file ./smartedu_token.txt
```

### 注意事项
- **token 文件属敏感凭据**：勿提交 git / 云盘共享；每台设备各自提取。
- **Win7 目标设备**：受 WorkBuddy 兼容性限制，可能需手动处理；Win10/11 无此问题。
- **stderr 的 `dirname/cd: command not found`** 是 WorkBuddy bash 包装噪音，不影响 Python 执行。
- 本技能与 `crawler-base` 保持代码隔离（仅借鉴算法，不合并）。

---

## 更新日志

### v2.4.3（本机应用，待同步到源→另一台设备）

针对「运行技能后下载半天才发现 token 不可用 / 部分文档 401」的体验问题，做两项增强：

1. **第一步鉴权预检（download_course.py / download_textbook.py）**：取到 token 后、解析/下载任何资源之前，
   立即调用 `token_manager.probe_token()` 探测 `user/session` 端点。
   - 返回 `False`（服务端 401/403，确定失效）→ 打印清晰续期指引并 `sys.exit(2)`，**不再浪费时间下载**。
   - 返回 `None`（网络/端点异常无法判定）→ 打印警告后继续。
   - 返回 `True` → 通过。
   - 额外：若 token 缺 `mac_key`，预检通过后给出⚠预警（缺它时部分依赖 MAC 强签名的文档/课件会 401）。

2. **文档下载补强签名 MAC 回退（smartedu_core.download_doc_to_file）**：原先文档只尝试
   `Bearer → 匿名` 两套头，遇 `r1-ndr-private` 等精品课 CDN 对裸 Bearer 返回 400/401 时整单失败（视频因
   `download_hls` 的 `fetch_bytes_fallback` 已有 MAC 回退不受影响，唯独文档缺这一环）。
   现新增 `mac_key` 参数，在 Bearer+匿名都失败后回退到带 `mac_key` 的 HMAC-SHA256 强签名 MAC 头。
   透传链路：`run_resources` / `download_pdf` 均新增 `mac_key` 形参并下钻到 `download_doc_to_file`。
   实测场景：此前《6.3.3 余角与补角》视频成功、3 个文档 401，根因即此；补齐后该课可全量成功。

### v2.4.3（本机应用）
- **关键修复**：`download_course.py` token 路径改为基于 `__file__` 的绝对路径，避免 cwd 污染导致读取到项目根目录的旧版 corrupt token（只有 access_token，无 mac_key）。
- **附带效果**：文档下载 MAC 强签名回退现在能正常工作（mac_key 正确读取），根治「视频成功、文档 401」现象。
- **临时目录清理**：v2.4.0-patch1 的同步 rmtree 经实测验证正常（finally 块触发、rmtree 成功），之前遗留的历史临时目录是旧版 daemon 线程机制产生的，已手动清理约 200MB+。
- **验证**：5/5 资源全下载成功，零残留，无 mac_key 误报，py_compile 全 PASS。
- **版本**：2.4.2 → 2.4.3。

### v2.4.0-patch3（本机应用，待同步到源→另一台设备）

> **已撤销**：思考开关（显示/关闭）机制于 v2.4.0-patch9 全部移除。所有算法逻辑保留，仅删除输出闸门及相关 API。

新增**「思考开关」**（显示 / 关闭）—— 对外交付技能时应尽量少暴露内部排查过程，由用户用一句话控制。

- **协议**：用户写「关闭思考」→ 静默（**默认**）；写「显示思考」→ 详细。AI 侧据此决定最终回复只给结论还是展示排查链路。
- **脚本侧**：`download_textbook.py` / `download_course.py` / `find_textbook.py` 新增 `-q/--quiet` 与 `-v/--verbose`，
  优先级 `--verbose` > `--quiet` > 环境变量 `SMARTEDU_QUIET`。
- **实现**：`smartedu_core.py` 新增输出闸门，替换 `builtins.print` —— **零改动**其它脚本里已有的 274 处 `print`。
  提供 `set_quiet()` / `say()`（结果级强制输出）/ `install_output_gate()`。
- **三级过滤优先级**：`LIB_NOISE_RE`（库噪音，如 PyMuPDF `fitz` 弃用告警）> `ERROR_RE`（错误**一律放行**）
  > `NOISE_RE`（索引拉取 / CDN 选择 / 解析成功 / 教材ID / PDF数量 / 分隔线等过程行）。

**踩坑记录（务必保留）**：
1. `download_textbook.py` 里 `import smartedu_core as core` 写在 **`download_pdf()` 函数内部**，
   `main()` 作用域看不到 → 直接用 `core.set_quiet()` 会 NameError 且静默吞掉报错。
   改为在 `main()` 内显式 `import smartedu_core as _core`。
2. 错误保护必须优先于噪声过滤：否则「[token] Edge 自动提取失败」「[索引] 拉取失败」「[清单] 解析失败」
   会被同前缀的噪声规则吞掉，静默模式变成**无声失败**。
3. PyMuPDF 的 `warning: The \`fitz\` API is deprecated` 含 `warn` 子串，会被 `ERROR_RE` 的 WARN 分支
   误判为真警告而放行 —— 故单列 `LIB_NOISE_RE` 并置于最高优先级。

**实测**：同一教材（语文八年级下册，8f907d12）详细模式 11 行 → 静默模式 4 行，减少 64%，
两边均正常落盘（24,306,481 字节）。闸门单测 23/23 通过，环境变量三态（未设 / `=1` / `=0`）行为正确。

**转场提示（用户追加需求）**：关闭思考模式下要求「不报开关状态 + 少过程 + 但别像卡死」，故：
- `download_textbook.py` / `download_course.py` 在「资源地址已解析、即将下载」处
  输出 `正在解析下载请求的资源，请稍后......`，用 `core.say()` 强制输出（静默下必定可见）。
- AI 侧新增三条硬规则（见「🔇 思考开关」章节）：① **不报告开关状态本身**（不说「已进入静默模式」这类元叙述）
  ② 不展示尝试/排查链路 ③ 保留上述转场提示。
- 实测静默模式输出 5 行：`标题` → `正在解析下载请求的资源，请稍后......` → `下载:` → `完成 (22MB)` → `完成: 成功 1, 失败 0`。

**补充坑（首次实战「关闭思考」时暴露）**：
4. `ERROR_RE` 里的裸状态码 `401|403|404|500` 会命中 **UUID 子串** ——
   contentId `81264e9e-…-13b40433b5ba` 含 `4043`，被判为 404 → 「教材ID: …」被当错误放行，
   静默模式漏行。已改为带词边界 `(?<![\w-])(?:401|403|404|500|502|503)(?![\w-])`，
   UUID / 连字符上下文不再误判。回归 11/11（UUID 含 404 正确吞掉，真 401/404/500 仍放行）。

### v2.4.0-patch7（本机应用，待同步到源→另一台设备）

**极致静默模式** —— 用户要求：不要显示标题/下载/完成/书签等过程信息，只显示一句提示 + 最终汇总。

- **NOISE_RE 扩展**：新增 `^标题[:：]`、`^\s*下载:`、`^\s*完成\s*[\(:]`、`^\s*添加书签:`、`^\s*已存在且完整`、`^\s*\[ERROR\]`、`^\s*\[WARN\]` 等模式
- **默认输出仅 2 行**：
  ```
  正在下载所需资源，请等待......   ← say() 强制（唯一例外，给「活着」信号）
  完成: 成功 N, 失败 M
  ```
- **详细模式仍保留**：传 `-v` 或 `SMARTEDU_QUIET=0` 可查看完整过程行
- 验证：实测教材下载输出从 5 行精简到 2 行；闸门测试 8/8 通过

### v2.4.0-patch6（本机应用，待同步到源→另一台设备）

**思考开关「默认静默」+ 移除转场提示** —— 响应两个用户痛点：① 思考过程显示内容过多，② 无论什么模式都不需要转场提示。

- **`smartedu_core.py` `QUIET` 默认值由 False 改为 True**：默认等价于加了 `-q`，彻底静默；`SMARTEDU_QUIET=0` 或脚本传 `-v` 仍可打开详细输出。
- **删除两处转场 `say()` 调用**：`download_textbook.py`（教材 PDF 解析后）与 `download_course.py`（含视频分支）原本用 `core.say()` 强制输出「正在解析下载请求的资源，请稍后……」；现已移除，静默模式下脚本只输出 4 行核心信息：标题 → 下载 → 完成 → 汇总。
- **`token_manager.py` 现有 `print` 行**（`[token_manager] 已从本机 Edge 读取...`、`[token_manager] 已用持久化登录态静默取回...`）命中 `NOISE_RE` 的 `^\[token\]` 前缀前缀，被闸门自动吞掉；若未来需要精确命中 `[token_manager]` 前缀可补充规则，当前版本无需改动。
- **验证**：`py_compile` 三脚本通过；实测物理八年级下册教材静默下载输出仅 5 行（标题/下载/完成/添加书签/成功汇总）。

### v2.4.0-patch5（本机应用，待同步到源→另一台设备）

**「独立内嵌显示窗口」登录** —— 针对用户「不要弹出系统 Edge、要工具自有窗口」的诉求：

- **新增 `scripts/login_window.py`**（pywebview）：在**工具自有的内嵌窗口**里加载官方 UC 登录页（扫码 + 密码 合一），
  登录成功后脚本通过 `webview.evaluate_js` 读取 `basic.smartedu.cn` 的 Local Storage 取回 `access_token + mac_key`，写入 token 文件。
  Windows 上 pywebview 自动复用系统内置 **Edge WebView2 运行时**（Win10+ 预装），无需下载 Chromium，窗口轻量且归工具所有。
- **`token_manager.acquire` 改优先级**：① 持久化 profile 仍有登录态 → 无头静默取回（零交互）② 否则 → **内嵌登录窗口**（默认）③ 内嵌不可用/失败，或要求 `--headless` → 兜底 Playwright 弹真实 Edge 窗口。
  用户主动关窗未登录时**不**自动回退弹 Edge（避免打扰）。
- **新增依赖 `pywebview>=5.0`**（写入 `requirements.txt`）。未安装时 `acquire` 会打印提示并自动回退到 Playwright。
- **设计取舍**：没有重画一套自定义 Qt/tkinter 登录 UI，而是直接内嵌官方 UC 页——因为 NdAuth token 必须由 `basic.smartedu.cn` 的前端在 UC 重定向后写入 Local Storage，纯 Python 无法绕过该浏览器侧握手；内嵌官方页能 100% 复用其已验证的「扫码 + 密码」流程，且始终与平台保持一致。
- **验证**：沙箱无显示器 / 外网，窗口未实跑；`login_window.py` 与 `token_manager.py` 已通过 `py_compile` 语法校验，逻辑路径与既有 Playwright 取 token 流程同源（JS_DUMP_AUTH 一致）。请在已装 WebView2 的本机 WorkBuddy 环境实测。

### v2.4.0-patch4（本机应用，待同步到源→另一台设备）

**统一 token 子系统 `scripts/token_manager.py`** —— 用户要求把 token 作为核心算法重点维护：
「获取更便捷（融合扫码+密码到一个界面）」+「持续性（过期后不轻易失效）」。

- **收口 3 条碎片化路径**：原本 `edge_login_token.py`（抓 token+mac_key）、`token_helper.py`（只抓裸 access_token、缺 mac_key）、
  `get_token_from_edge_storage`（直读 Edge LevelDB）互不相通、且无续期。现统一到 `token_manager.py`：
  `acquire`（扫码/密码登录，已登录则静默）/ `refresh`（用持久化 profile 无头续期）/ `status` / `check` + 编程接口 `get_valid_token()`。
- **「融合到一个界面」在交互层已满足**：官方 UC 登录页（`uc.basic.smartedu.cn`）本就内置「二维码扫码 + 用户名密码」两种入口，`acquire` 加载的就是它；代码层由 `token_manager` 统一调度。
- **持续性机制**：token 文件新增 `expires_at`（默认按 2h 乐观门禁，环境变量 `SMARTEDU_TOKEN_TTL` 可调）；
  `get_valid_token()` 优先级：① 文件未过期 → 直接返回（零交互）② 已过期 → 用 `.edge_profile` 的 Cookie **无头续期**（无需重新扫码，前提登录态未退）
  ③ 兜底读本机 Edge leveldb ④ 全失败 → 提示运行 `acquire`。
  只要 `.edge_profile` 的登录 Cookie 还在（通常比 access_token 活得久），token 过期后下载脚本会**自动无感续期**。
- **接线**：`download_textbook.py` / `download_course.py` 的 token 解析块改为调用 `get_valid_token()`；
  裸 token 文本（旧 `token_helper` 格式）仍兼容，`load_token` 同时支持 JSON 平铺与裸文本。
- **验证**：纯 Python 逻辑单测 11/11 通过（save/load 往返、`expires_at`、过期判定、裸文本兼容、Edge 兜底优雅降级、probe 不抛异常）；
  `status` 在真实 token 文件上实跑通过；两下载脚本 `--help` 正常。浏览器端 acquire/refresh 复用 `edge_login_token.py` 已验证逻辑（沙箱无显示器/外网未实跑）。

### v2.4.0-patch2（本机应用，待同步到源→另一台设备））

修 `find_textbook.py` 三处 —— 均由「同标题多版本教材」实测暴露，有完整元数据 dump 佐证：

- **标签永远打印不出来（隐性 bug）**：`tag_list` 里字段名是 **`tag_name`**，代码却读 `t.get("name")`，
  恒为 None → `tags` 恒空 → 标签行永不输出。历次「搜出一堆同名结果没法分辨」都源于此。改为 `t.get("tag_name") or t.get("name")`。
- **出版社显示的是容器 UUID**：`h.get("provider")` 是资源容器 ID（`ce5c90c5-…`），9 条结果**全都一样**，
  毫无区分力。真正的名字在 `provider_list[0].name`（人民教育出版社 / 青岛出版社 / 上海教育出版社…）。
- **新增版本号输出 + 多版本预警**：从 `tag_dimension_id == "zxxbb"` 维度提取「人教版/青岛版/沪教版…」单独一行显示；
  并在检出同标题多 ID 时告警，提醒 `--download` 只取首个会下错版本。

实测同一关键词「数学一年级上册」修复前后对比：

| | 修复前 | 修复后 |
|---|---|---|
| 标签 | 不显示 | 电子教材 教材 青岛版 上册 一年级 小学（五•四学制） 数学 |
| 出版社 | `ce5c90c5-1780-414c-…`（9 条全同） | 青岛出版社 / 上海教育出版社 / 人民教育出版社… |
| 版本 | 无 | 人教版、北京版、北师大版、冀教版、苏教版、青岛版、西南大学版、沪教版 一眼可辨 |
| 多版本 | 无提示 | 自动告警「检出 1 组同标题多版本（6 条同名实为 5 个不同版本）」 |

> **重要认知**：标题里的中点 `·` 与 `•` 是平台录入不一致造成的，**不代表不同册次**；
> 真正的版本差异看 `zxxbb` 标签 + `provider_list`。另外「数学」没有统编版
> （统编教材仅限语文 / 道德与法治 / 历史三科），用户口中的「统编版」通常是误称，须按 **`zxxbb` 版本 + 学制** 二次确认。

### v2.4.0-patch1（本机应用，待同步到源→另一台设备）

吸收跨设备对比诊断中**确定性高**的两项，不做未经验证的改动：

- `download_course.py`：标准课程路径补上 `--inspect` **预览即返回**。
  原先该参数只在实验课 `run_experiment()` 里 return（`download_course.py:407`），
  `--url` / `--activity-id` 路径完全不检查它 —— 本想「只看清单」却把 5 类资源全下下来
  （实测多下 3 个 PDF + 3 次 PDF→DOCX 转换）。现在会列出资源后立即返回，零下载。
- `smartedu_core.py`：`download_hls()` 的临时分片目录从 **daemon 线程异步 rmtree** 改为**同步清理**。
  原实现 fire-and-forget，进程退出时 daemon 线程被强杀，导致 `_ts_*` 整包残留
  （实测 125 个文件 / 92.7MB，比成品 mp4 本身还大）。

**本 patch 刻意未做**（留待验证后再动）：
- `smartedu_search.py` 搜索翻页：x-search 疑似 POST 传参，分页机制未验证（目前只拿第 1 页 12/25 条）。
- 本机登录 bootstrap：从 Edge LevelDB 取 token（含 mac_key）已可用、匿名搜索字段也完整，收益不明确。

### v2.4.0
- 新增 `scripts/smartedu_search.py`：用已登录 Edge 触发站内搜索（`x-search.ykt.eduyun.cn`），
  解决「用户只给课程名不给链接」时定位 courseId 的问题。
- `download_course.py`：新增 `--only video,courseware`（别名 video/courseware/plan/task/exercise）
  精确挑选资源类型；新增 `pick_doc_native()`，优先落盘原生 pptx/docx，无原生件才走 PDF 转换。
- `download_textbook.py`：补齐平铺格式 token（`{"access_token":..., "mac_key":...}`）解析，
  修掉旧版只认 `{"value":...}` 包装导致 token 静默为空的坑。
- `smartedu_core.py`：媒体鉴权自适应——`r1-ndr-private` 等 CDN 对 Bearer 返回 **HTTP 400**
  （而非 401/403），已纳入鉴权失败判定并自动回退 `X-ND-AUTH` MAC。

### v2.3.0
- 共享核心 `smartedu_core.py`、并发 HLS、文档多副本回退、`find_textbook.py` 匿名整库索引。
