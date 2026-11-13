#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
课件文档统一排版入口（lesson-typeset · V1.0 · 2026-11-06 固化）
================================================================

一份规范（references/unified-spec.md）＋ 一支入口命令。
版式常量以规范第 1 章为准，本文不重复定义；四类文档的差异只剩 PROFILES 四行参数档；
独有构件按块语法按需启用。renderers/ 是已验证的内部渲染模块，不直接调用。

用法：
    python3 typeset.py --root "<课题目录>" \
        --input ".workbuddy/牛和鹅-教学设计-源.md" \
        --header "20 牛和鹅" --mode preview      # 只写 /tmp
    python3 typeset.py --root "<课题目录>" \
        --input ".workbuddy/牛和鹅-教学设计-源.md" \
        --header "20 牛和鹅" --mode commit       # 落「交付文件/」，旧版进废纸篓
    python3 typeset.py --dry-run                  # 命名推导与配图探测

不接受手填 --output；成品名一律由源稿名推导（见第 5 章命名规范）。
交付目录由 output_folder() 单点决定（2026-11-09 规则：课题根目录下新建「交付文件/」；
2026-11-10 加严：所有类型都进包，commit 后 sweep_copies() 清掉包外同名副本）。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RENDERERS = os.path.join(HERE, "renderers")
SPEC = os.path.join(os.path.dirname(HERE), "references", "unified-spec.md")

# 版式常量（色板／字号／间距／框线）只定义在 references/unified-spec.md 第 1 章，
# 渲染实现在 renderers/；本入口不重复定义第二份，避免两处数值漂移。

# ─────────────── 第三章 参数档差分表（只有这四行允许不同） ───────────────
# m = 上/下/左/右 mm；fs = 主标题 / 一级标题；extras = 独有构件开关
PROFILES = {
    "教学设计": dict(script="table_v32.py", m=(2.8, 2.0, 2.3, 2.3),
                 fs=(18.0, 13.0), extras="四列活动表 4:7:5:4、字段行、板书图版"),
    "逐字稿":   dict(script="zjg_typeset.py", m=(2.6, 2.0, 2.4, 2.4),
                 fs=(20.0, 15.0), needs_images=True, img_w=12.0,
                 extras="逐页标题、师/生/预设/提示分层、课件截图（自动配图）"),
    "学习清单": dict(script="xuexqingdan_typeset.py", m=(1.6, 1.6, 1.8, 1.8),
                 fs=(17.0, 12.5), extras="标题栏、作答横线、田字格、三星自评"),
    "制作笔记": dict(script="zhizuobiji_typeset.py", m=(1.8, 1.8, 2.0, 2.0),
                 fs=(20.0, 14.0), extras="一级标题分隔线、强调块、图配图注"),
}
PROFILE_BY_TYPE = {k: k for k in PROFILES}
# 规范 4.2（2026-11-10 改）：所有类型统一落课题根目录下新建的「交付文件/」，
# 制作笔记不再单独落 .workbuddy/——交付包是唯一成品出处，包外不留任何成品副本。
OUTPUT_SUBDIR = {}
DELIVERY_DIR = "交付文件"
# 兼容：用户可能把交付包改名（如「交付件」）。已存在的交付目录优先复用，
# 不再新建第二个交付文件夹——否则成品会被劈成两处。
DELIVERY_ALIASES = ("交付文件", "交付件", "交付")

# ─────────────── 第五章 命名与输出规范 ───────────────
TYPES = ["单元教学设计", "教学设计", "互动课件", "板书设计", "教学反思",
         "说课稿", "逐字稿", "学习清单", "作业设计", "评价量表", "资料卡",
         "制作笔记", "课件", "微课"]
KESHI = re.compile(r"第[一二三四五六七八九十]+课时")
BAD_WORDS = ("终稿", "草稿", "预览", "待确认", "自用版", "设计版", "标准版",
             "优化版", "修复版", "_V", "V2", "V3", "备份", "副本")


def parse_stem(src):
    """从源稿名拆出 (课文标题, 课时段, 内容类型)，并推导成品名。"""
    stem = os.path.splitext(os.path.basename(src))[0]
    parts = stem.split("-")
    title = re.sub(r"^\d+", "", parts[0]).strip()
    keshi = next((p for p in parts if KESHI.fullmatch(p)), None)
    typ = next((t for t in TYPES if t in stem), None)
    if not title or not typ:
        raise ValueError("源稿名无法推导成品名（缺课文标题或内容类型）：" + stem)
    name = "-".join(x for x in (title, keshi, typ) if x) + ".docx"
    validate_name(name)
    return title, keshi, typ, name


def derive_output_path(src):
    """由源稿名自动推导成品名：课文标题[-课时段]-内容类型.docx"""
    return parse_stem(src)[3]


def derive_profile(src):
    """profile 由源稿名自动推导，不必手工指定。"""
    typ = parse_stem(src)[2]
    if typ not in PROFILE_BY_TYPE:
        raise ValueError("内容类型「%s」暂无渲染器（现有：%s）"
                         % (typ, "、".join(PROFILE_BY_TYPE)))
    return PROFILE_BY_TYPE[typ]


def validate_name(name):
    stem = os.path.splitext(name)[0]
    if re.search(r"\d", stem):
        raise ValueError("文件名含数字（课文编号／版本号都不允许）：" + name)
    if re.search(r"[《》〈〉\"'_\s|｜]", stem):
        raise ValueError("文件名含书名号／空格／下划线／竖线：" + name)
    for w in BAD_WORDS:
        if w in stem:
            raise ValueError("文件名含状态词「%s」：" % w + name)
    return True


# ─────────────── 第二章 构件库：逐字稿课件截图（自动配图） ───────────────
# 源稿用「## 第 N 页」分节，截图按 p01.jpg / p02.jpg … 与之一一对应。
# 目录约定：assets/ppt-<课时段>/ 优先；兼容长城等历史课题的 assets/ppt2/。
KESHI_IMG_DIRS = {
    "第一课时": ("assets/ppt-第一课时", "assets/ppt"),
    "第二课时": ("assets/ppt-第二课时", "assets/ppt2", "assets/ppt"),
}
GENERIC_IMG_DIRS = ("assets/ppt", "assets/ppt-第一课时",
                    "assets/ppt-第二课时", "assets/ppt2")


# ─── 关键图片素材来源硬门禁（2026-11-13 用户裁定：缺失即暂停，禁止 AI 造素材） ───
def find_courseware_pdf(root, explicit=None):
    """逐字稿 ppt 预览图的唯一合法来源 = 用户提供的课件 PDF。

    教材 PDF（只含课文正文，如 <课题>.pdf）不算；禁止 AI 用 ppt2png.py
    从 pptx 自行渲染替代。assets/ 下的 PDF 优先，其次根目录名含「课件」的 PDF。
    """
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    cands = []
    a = os.path.join(root, "assets")
    if os.path.isdir(a):
        cands += [os.path.join(a, n) for n in sorted(os.listdir(a))
                  if n.lower().endswith(".pdf")]
    for n in sorted(os.listdir(root)):
        if n.lower().endswith(".pdf") and "课件" in n:
            cands.append(os.path.join(root, n))
    return cands[0] if cands else None


def export_pdf_pages(pdf, outdir, dpi=110):
    """从用户提供的课件 PDF 逐页导出 pNN.jpg —— 逐字稿配图唯一合法的生成方式。

    同时写 .source.json 来源标记，供 check_assets.py 判定现有预览图是否合法来源。
    """
    import hashlib, json, datetime
    import pymupdf
    os.makedirs(outdir, exist_ok=True)
    doc = pymupdf.open(pdf)
    n = 0
    for i, page in enumerate(doc, 1):
        p = os.path.join(outdir, "p%02d.jpg" % i)
        page.get_pixmap(dpi=dpi).save(p)
        n += 1
    doc.close()
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    with open(os.path.join(outdir, ".source.json"), "w", encoding="utf-8") as f:
        json.dump({"source_pdf": os.path.basename(pdf), "sha256": sha,
                   "pages": n, "generator": "lesson-typeset/export_pdf_pages",
                   "exported_at": datetime.datetime.now().isoformat(timespec="seconds")},
                  f, ensure_ascii=False, indent=2)
    return n


SOURCE_MARKER = os.path.join("assets", "ppt", ".source.json")


def asset_status(root, explicit_pdf=None):
    """只读素材齐备预检 —— 唯一判定源，check_assets.py 与 preflight_assets() 共用。

    返回 dict：board_ref / board_ok / pdf / pdf_ok / source_ok / page_count /
    deck_pages / missing[]。绝不修改任何文件。
    """
    import hashlib, json
    st = {"board_ref": None, "board_ok": False, "pdf": None, "pdf_ok": False,
          "source_ok": False, "page_count": 0, "deck_pages": 0, "missing": []}

    # ① 板书设计图片：自动定位教学设计源稿中的引用
    for n in sorted(os.listdir(root)):
        if n.endswith("-教学设计-源.md"):
            md = open(os.path.join(root, n), encoding="utf-8").read()
            seg = re.search(r"###\s*板书设计([\s\S]{0,300})", md)
            m = re.search(r"!\[[^\]]*\]\(([^)]+)\)", seg.group(1)) if seg else None
            if m:
                rel = m.group(1).strip()
                st["board_ref"] = rel
                p = rel if os.path.isabs(rel) else os.path.join(root, rel)
                st["board_ok"] = os.path.isfile(p)
            break
    if not st["board_ok"]:
        st["missing"].append(
            "板书设计图片：教学设计「板书设计」必须引用用户提供的板书设计图片"
            "（如 `### 板书设计` + `![](板书设计.png)`），禁止纯文本／ASCII 板书。")

    # ② 课件 PDF：逐字稿预览图唯一合法来源
    pdf = find_courseware_pdf(root, explicit_pdf)
    st["pdf"] = pdf
    st["pdf_ok"] = bool(pdf)
    if not pdf:
        st["missing"].append(
            "课件 PDF：逐字稿 ppt 预览图必须从用户提供的课件 PDF 导出，"
            "禁止 AI 自行用 ppt2png.py 从 .pptx 渲染。请放进 assets/、"
            "或命名「<课题>-课件.pdf」、或用 --courseware-pdf 指定。")
    else:
        import pymupdf
        try:
            st["deck_pages"] = pymupdf.open(pdf).page_count
        except Exception:
            st["deck_pages"] = 0

    # ③ 预览图来源标记与页数一致性
    img_dir = os.path.join(root, "assets", "ppt")
    if os.path.isdir(img_dir):
        st["page_count"] = len([x for x in os.listdir(img_dir)
                                if re.fullmatch(r"p\d+\.(jpg|jpeg|png)", x, re.I)])
    marker = os.path.join(root, SOURCE_MARKER)
    if os.path.isfile(marker) and pdf:
        try:
            meta = json.load(open(marker, encoding="utf-8"))
            sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
            st["source_ok"] = (meta.get("sha256") == sha
                               and meta.get("pages") == st["page_count"]
                               and meta.get("pages") == st["deck_pages"])
        except Exception:
            pass
    # source_ok=False 不是阻塞项：PDF 到位后引擎会自动重导出并覆盖，
    # check_assets.py 只把它显示为「待重导出」状态。
    return st


def preflight_assets(root, src, typ, args):
    """返回 (问题清单, 配图目录)。问题非空时调用方必须暂停排版，不产出任何成品。"""
    st = asset_status(root, getattr(args, "courseware_pdf", None))
    problems, img_dir = [], None

    if typ == "教学设计":
        md = open(src, encoding="utf-8").read()
        seg = re.search(r"###\s*板书设计([\s\S]{0,300})", md)
        m = re.search(r"!\[[^\]]*\]\(([^)]+)\)", seg.group(1)) if seg else None
        if not m:
            problems.append(
                "教学设计「板书设计」未引用板书图片：必须使用用户提供的板书设计图片，"
                "禁止纯文本／ASCII 板书。请提供图片后再排版。")
        else:
            rel = m.group(1).strip()
            p = rel if os.path.isabs(rel) else os.path.join(root, rel)
            if not os.path.isfile(p):
                problems.append("板书设计图片不存在：%s（请用户提供后重排）" % rel)

    if PROFILES.get(typ, {}).get("needs_images") and not args.no_images:
        if not st["pdf_ok"]:
            problems.append(
                "逐字稿缺少用户提供的课件 PDF：ppt 预览图必须从该 PDF 导出，"
                "禁止 AI 自行从 pptx 渲染。请把课件 PDF 放进 assets/，"
                "或命名为「<课题>-课件.pdf」，或用 --courseware-pdf 指定路径。")
        else:
            outdir = os.path.join(root, "assets", "ppt")
            n = export_pdf_pages(st["pdf"], outdir)
            img_dir = outdir
            print("课件 PDF 来源：%s → 导出 %d 张逐页图" %
                  (os.path.relpath(st["pdf"], root), n))

    return problems, img_dir


def resolve_images_dir(src, root, explicit=None):
    """返回课件截图目录；找不到返回 None（由调用方显式告警，绝不静默出无图稿）。"""
    if explicit:
        return explicit
    stem = os.path.splitext(os.path.basename(src))[0]
    m = KESHI.search(stem)
    cands = KESHI_IMG_DIRS.get(m.group(0) if m else "", GENERIC_IMG_DIRS)
    for rel in cands:
        d = os.path.join(root, rel)
        if os.path.isdir(d) and any(
                os.path.exists(os.path.join(d, "p01." + e))
                for e in ("jpg", "jpeg", "png")):
            return d
    return None


def render(src, out, profile, header, images_dir=None, cwd=None):
    """调用 renderers/ 下已验证的渲染模块；cwd 固定为课题根目录，
    使源稿里的相对图片路径（assets/…）稳定可解析。"""
    cmd = [sys.executable, os.path.join(RENDERERS, PROFILES[profile]["script"]),
           "--input", src, "--output", out, "--header", header]
    if PROFILES[profile].get("needs_images") and images_dir:
        cmd += ["--images", images_dir]
    subprocess.run(cmd, check=True, cwd=cwd)


def _trash_bin():
    for p in ("/usr/bin/trash", shutil.which("trash"), shutil.which("trash-put")):
        if p and os.path.exists(p):
            return p
    raise RuntimeError("未找到系统废纸篓命令，拒绝直接覆盖或删除旧成品")


def commit(tmp_docx, dst):
    """原子覆盖：旧成品移入系统废纸篓；先写同目录暂存文件再 os.replace。
    返回是否替换了旧成品，供调用方如实汇报。"""
    parent = os.path.dirname(dst)
    os.makedirs(parent, exist_ok=True)
    replaced = os.path.exists(dst)
    staging = os.path.join(parent, ".staging-" + os.path.basename(dst))
    try:
        shutil.copy2(tmp_docx, staging)
        if replaced:
            subprocess.run([_trash_bin(), dst], check=True)
        os.replace(staging, dst)       # 同目录，原子且不受跨卷影响
    finally:
        if os.path.exists(staging):
            os.remove(staging)
    return replaced


def output_folder(root, typ):
    """按规范 4.2（2026-11-10 改）：所有成品统一落课题根目录下的「交付文件/」。

    OUTPUT_SUBDIR 保留为扩展点，现为空——制作笔记也进交付包，包外不留成品。
    """
    if typ in OUTPUT_SUBDIR:
        return os.path.join(root, OUTPUT_SUBDIR[typ])
    for alias in DELIVERY_ALIASES:       # 已存在的交付目录优先，避免劈成两个
        cand = os.path.join(root, alias)
        if os.path.isdir(cand):
            return cand
    return os.path.join(root, DELIVERY_DIR)


def sweep_copies(root, name):
    """把 交付文件/ 之外的同名成品副本一律移入系统废纸篓。

    规范 4.3 第 7 条（2026-11-10 用户新增）：整理成交付文件包之后，
    包外的副本必须清掉。检查两处历史落位：
      · 课题根目录          —— 2026-11-09 之前的落位
      · .workbuddy/<name>   —— 制作笔记 2026-11-10 之前的内部落位
    只清同名成品，绝不动 `-源.md` 源稿；移交系统废纸篓，可恢复。
    返回被移走的相对路径列表，供调用方如实汇报。
    """
    moved = []
    for folder in (root, os.path.join(root, ".workbuddy")):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            subprocess.run([_trash_bin(), p], check=True)
            moved.append(os.path.relpath(p, root))
    return moved



def assert_single_output(folder, name, typ):
    """落地后校验：同类型＋同课时段、符合新命名规范的成品只有一个。"""
    m = KESHI.search(name)
    keshi = m.group(0) if m else ""
    peers = [n for n in os.listdir(folder)
             if n.endswith(".docx") and typ in n and not n.startswith("~$")
             and not re.search(r"\d", os.path.splitext(n)[0])
             and (not keshi or keshi in n)]
    if len(peers) > 1:
        raise RuntimeError("课题目录出现同类副本，违反防副本第 2 条：" + "、".join(peers))


def main():
    ap = argparse.ArgumentParser(description="课件文档统一排版（唯一入口）")
    ap.add_argument("--root", default=os.getcwd(), help="课题根目录")
    ap.add_argument("--input", help="源稿路径（相对 --root 或绝对路径）")
    ap.add_argument("--profile", choices=list(PROFILES), help="省略则由源稿名推导")
    ap.add_argument("--header", help="页眉课题名；省略则取课文标题")
    ap.add_argument("--mode", default="preview", choices=("preview", "commit"))
    ap.add_argument("--images", help="显式指定课件截图目录（跨课题样张时用）")
    ap.add_argument("--no-images", action="store_true", help="明确跳过配图")
    ap.add_argument("--courseware-pdf", help="用户提供的课件 PDF（逐字稿预览图唯一合法来源）")
    ap.add_argument("--dry-run", action="store_true", help="只打印命名推导与配图探测")
    a = ap.parse_args()

    if a.dry_run:
        samples = [
            ".workbuddy/牛和鹅-教学设计-源.md",
            ".workbuddy/牛和鹅-第一课时-学习清单-源.md",
            ".workbuddy/牛和鹅-第二课时-学习清单-源.md",
            ".workbuddy/牛和鹅-制作笔记-源.md",
            ".workbuddy/长城-第二课时-逐字稿-源.md",
        ]
        print("源稿 → 成品（自动推导）：")
        for s in samples:
            print("  %-44s → %-34s profile=%s"
                  % (os.path.basename(s), derive_output_path(s), derive_profile(s)))
        d = resolve_images_dir(samples[-1], a.root)
        print("\n逐字稿自动配图探测（--root=%s）：%s"
              % (a.root, d or "⚠️ 未找到，需导出 p01.jpg… 或用 --images 指定"))
        return

    if not a.input:
        ap.error("需要 --input 指定源稿")
    root = os.path.abspath(a.root)
    src = a.input if os.path.isabs(a.input) else os.path.join(root, a.input)
    if not os.path.isfile(src):
        raise FileNotFoundError(src)
    if not os.path.isfile(SPEC):
        raise FileNotFoundError("唯一规范缺失：" + SPEC)

    title, keshi, typ, name = parse_stem(src)
    profile = a.profile or derive_profile(src)
    header = a.header or title

    # 关键图片素材来源硬门禁：素材未齐备立即暂停，绝不产出/覆盖任何成品
    problems, img_dir = preflight_assets(root, src, typ, a)
    if problems:
        print("\n⛔ 排版已暂停（关键图片素材未齐备，按项目铁律不得擅自造素材）：")
        for i, p in enumerate(problems, 1):
            print("  %d. %s" % (i, p))
        print("\n请提供上述素材后再执行排版；本次未生成、未覆盖任何交付成品。")
        sys.exit(2)
    if a.images:
        img_dir = a.images

    preview_dir = os.path.join("/tmp", "lesson-typeset-preview",
                               os.path.basename(root))
    os.makedirs(preview_dir, exist_ok=True)
    tmp_docx = os.path.join(preview_dir, name)
    render(src, tmp_docx, profile, header, img_dir, cwd=root)
    print("推导成品名：%s" % name)
    print("profile：%s ｜ 页眉：%s" % (profile, header))
    if img_dir:
        print("自动配图目录：%s" % img_dir)
    print("预览输出：%s" % tmp_docx)

    if a.mode == "commit":
        folder = output_folder(root, typ)
        dst = os.path.join(folder, name)
        replaced = commit(tmp_docx, dst)
        moved = sweep_copies(root, name)
        assert_single_output(folder, name, typ)
        note = []
        if replaced:
            note.append("旧成品已移入系统废纸篓")
        if moved:
            note.append("包外副本已清理：" + "、".join(moved))
        print("已落地：%s%s" % (dst, "（%s）" % "；".join(note) if note else ""))
    else:
        print("预览模式：课题目录未改动；确认后改用 --mode commit")


if __name__ == "__main__":
    main()
