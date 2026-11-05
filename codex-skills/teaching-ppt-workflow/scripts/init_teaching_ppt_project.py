#!/usr/bin/env python3
"""Initialize lightweight control files for a teaching PPT project."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


FOLDERS = [
    "00_项目管理",
    "01_客户资料",
    "02_内容与脚本",
    "03_风格与缩略图",
    "04_PPT工作稿",
    "05_媒体素材",
    "06_修改记录",
    "07_交付文件",
]

TEMPLATES = {
    "project-brief-template.md": ("00_项目管理", "项目总表.md"),
    "page-matrix-template.csv": ("00_项目管理", "页面矩阵.csv"),
    "change-log-template.csv": ("06_修改记录", "修改清单.csv"),
    "delivery-checklist-template.md": ("00_项目管理", "交付检查表.md"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create control files and optional folders for a teaching PPT project."
    )
    parser.add_argument("project_dir", type=Path, help="Project directory")
    parser.add_argument("--title", help="Course or project title")
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="Create only management and revision folders, not the full folder layout",
    )
    return parser.parse_args()


def copy_if_missing(source: Path, destination: Path) -> str:
    if destination.exists():
        return f"SKIP {destination}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return f"CREATE {destination}"


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.expanduser().resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    folders = ["00_项目管理", "06_修改记录"] if args.minimal else FOLDERS
    for folder in folders:
        (project_dir / folder).mkdir(parents=True, exist_ok=True)

    skill_dir = Path(__file__).resolve().parent.parent
    asset_dir = skill_dir / "assets"

    messages = []
    for source_name, (folder, target_name) in TEMPLATES.items():
        messages.append(
            copy_if_missing(asset_dir / source_name, project_dir / folder / target_name)
        )

    if args.title:
        brief = project_dir / "00_项目管理" / "项目总表.md"
        content = brief.read_text(encoding="utf-8")
        if "- 课题：" in content:
            content = content.replace("- 课题：", f"- 课题：{args.title}", 1)
            brief.write_text(content, encoding="utf-8")

    print("\n".join(messages))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
