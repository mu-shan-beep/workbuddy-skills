# 更新日志

## v2.5.0（2026-09-20）

- 新增 **公开课直播下载**：支持 `www.smartedu.cn/publiclive` 子平台，新增脚本 `download_publiclive.py`
- 公开课直播回放为 AES-128 加密 HLS，密钥通过 `nonce + sign` 认证流程获取（复用核心算法）
- 实测下载 DeepSeek 公开课（吴飞主讲）回放，371 个分片全部成功，输出 271.61 MB mp4
- 同步将 publiclive 解析算法回传到 crawler-base 的 `smartedu.py`

## v2.4.3（2026-09-17）

- 下载前鉴权预检：拿到 token 后立即探测服务端，失效则提前退出不再浪费时间下载
- 文档下载补齐 MAC 强签名回退，根治「视频成功、文档 401」现象
- token 路径改为基于 `__file__` 绝对路径，避免读取到错误的 corrupt token
- 临时分片目录同步清理，零残留

## v2.4.0

- 新增 `smartedu_search.py`：用已登录浏览器触发站内搜索，解决「只给课程名不给链接」的定位问题
- `download_course.py` 新增 `--only video,courseware` 精确挑选资源类型；优先落盘原生 pptx/docx
- `smartedu_core.py` 媒体鉴权自适应：部分 CDN 对 Bearer 返回 400，自动回退 X-ND-AUTH MAC

## v2.3.0

- 收敛核心算法到 `scripts/smartedu_core.py`（源自 crawler-base）
- 并发 HLS 下载、文档多副本 × 主机变体 × 匿名回退
- `find_textbook.py` 匿名整库索引，免登录按名检索教材

## 核心能力

- **电子教材**：PDF（部分免登录，受保护需 token）
- **课程视频**：mp4（AES-128 加密 HLS，需 token + mac_key）
- **课件**：pptx
- **教学设计 / 学习任务单 / 课后练习**：docx
- **公开课直播回放**：mp4（www.smartedu.cn/publiclive）
- 多 CDN 源自动切换、双认证（Bearer / MAC）、断点续传、指数退避重试
- Token 自动从本机已登录 Edge 读取，支持内嵌登录窗口与无感续期


## v2.5.0 (发布定型)
- 新增 scripts/feedback.py：需求反馈收件人以 base64 内置，SKILL.md / references 不再出现明文邮箱，避免公开暴露。
- 重写「首次交互引导」：第一次使用技能时提醒用户可直接复制资源链接；课程可指定视频/课件文档，不明确则默认下载课程全部资源。
- 新增 publiclive 公开课直播回放下载支持（download_publiclive.py）。
