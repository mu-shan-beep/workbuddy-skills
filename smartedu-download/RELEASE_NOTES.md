# smartedu-download v2.5.5 发布说明

## 版本信息
- **版本号**: 2.5.5
- **发布日期**: 2026-11-20
- **作者**: WorkBuddy
- **许可证**: MIT

## 本版重点：按课本搜索 → 整册下载

只需给出**课本名**（如「北师大版七年级上册数学」），技能会自动检索定位这本书，展开该册全部章节与课时，
批量下载整套关联课程资源：**视频课程 + 课件 + 教学设计 + 学习任务单 + 课后练习**，无需逐课给链接。

```bash
python scripts/download_course.py --whole-book "北师大版七年级上册数学"
python scripts/download_course.py --whole-book "北师大版七年级上册数学" --inspect   # 只看清单
```

### 新增能力
1. **按课本名搜索**（`--search`）：走 tch_material 匿名整库索引（约 3565 条），按
   版本 `zxxbb` / 学科 `zxxxk` / 年级 `zxxnj` / 册次 `zxxcc` / 学段 `zxxxd` 分词匹配；
   命中多条时优先「2022 年版新课标 / 新教材」。实测课本名 → 23 课时清单 7.7 秒。
2. **`--whole-book` 参数**：`download_course.py` 的整册入口，接受课本名 / 教材 ID / 课程包 ID / 教材 URL，
   内部委托 `download_full_volume.py`，并透传 `--only` / `--only-video` / `--limit` / `--workers` / `--out` / `--force`。
3. **备课快通道**：`prepare_lesson` + `prepare_sub_type` 接口匿名可读，无需全站索引、无需 token 即可解析结构；
   失败自动回退 `national_lesson` 分片。
4. **整册并发**：课时级默认 4 路并发（`--workers` 可调至 8），单课视频内部 16 线程拉 HLS 分片。
5. **增量跳过**：已存在的成品文件自动跳过，中断重跑只补缺；结束后写 `_volume_manifest.json` 清单。

### 修复
- `smartedu_core.search_tch_material()` 读错标签字段（`name` → `tag_name`），导致「北师大版 / 人教版」等
  版本标签永远匹配不到、按课本搜索失效。
- 整册下载并发任务把 source 硬编码为 `prepare`，回退 legacy 分片时会取错资源详情接口。
- `download_full_volume.py` 的 `main()` 改为 `main(argv=None)`，便于被其它脚本调用。

## 已验证功能

| 功能 | 状态 | 测试用例 |
|------|------|----------|
| 按课本名搜索 | ✓ | 「北师大版七年级上册数学」→ 命中 23 课时，7.7 秒 |
| 整册批量下载 | ✓ | 23 课时 × 5 类 = 115 项 / 696 MB，4 并发约 2 分钟，失败 0 |
| 增量重跑 | ✓ | 23/23 全部跳过，1.4 秒 |
| 教材PDF下载 | ✓ | 语文、数学、物理、化学 |
| 单课程下载 | ✓ | 视频 / 课件 / 教学设计 / 任务单 / 课后练习 |
| 公开课直播回放 | ✓ | 271 MB 回放 |

## 文件结构

```
smartedu-download/
├── SKILL.md                  # 技能定义（含完整 frontmatter，v2.5.5）
├── RELEASE_NOTES.md          # 本文件
├── requirements.txt          # 依赖清单
├── _icon.png                 # 512×512 图标
├── icons/                    # 文件类型图标（mp4/pdf/docx/pptx）
├── references/api_notes.md   # API 与解密算法参考
└── scripts/                  # 17 个 Python 脚本
```

## 依赖要求
- Python >= 3.10
- pycryptodome >= 3.19
- imageio-ffmpeg >= 0.5
- PyMuPDF / python-pptx / python-docx（首次运行自动安装）
- playwright >= 1.40（可选，用于 token 获取）

## 注意事项
- 建议运行时加 `-u`，避免 Python 输出缓冲导致进度不可见。
- 文件下载需要 access_token，可用 `python scripts/token_manager.py acquire` 获取/续期。
- 视频下载所需 ffmpeg 由 imageio-ffmpeg 自动提供，无需系统安装。
- 整册下载结束后会自动清理 `_ts_*` 临时分片目录。
