#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render and validate AI-authored ENBX page geometry.

兼容外观（facade）：实际实现已拆分为——
  validators/content_validator.py   内容槽提取（title/kicker/lead/body/item.N…）
  validators/visual_validator.py    视觉契约校验（几何/背景池/对比度/imageStrategy/bgTone）
  renderers/page_renderer.py        ENBX 页面绘制与 visual-plan 清单输出

本模块只做重导出，保持 build_v2.py、enbx_renderer.py、validate_deck.py、
inspect_visual_blocks.py 及全部测试的既有导入路径不变。

This module intentionally contains no subject, lesson-type, theme, or layout
catalog.  The model authors each page's background and foreground geometry;
the renderer only resolves content bindings and enforces production safety.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validators.content_validator import (CANVAS_H, CANVAS_W,  # noqa: E402,F401
                                          content_slots, is_authored_visual)
from validators.visual_validator import (CONTRAST_ERROR, CONTRAST_WARN,  # noqa: E402,F401
                                         ILLUSTRATION_ROLES, extract_bg_tone,
                                         illustration_caption_geometry,
                                         resolve_auto_bg_tones,
                                         silhouette_similarity,
                                         silhouette_tokens,
                                         text_contrast_report,
                                         validate_authored_visual)
from renderers.page_renderer import (authored_manifest,  # noqa: E402,F401
                                     render_authored_page,
                                     write_authored_manifest)

__all__ = [
    "CANVAS_W", "CANVAS_H",
    "CONTRAST_ERROR", "CONTRAST_WARN", "ILLUSTRATION_ROLES",
    "is_authored_visual", "content_slots",
    "extract_bg_tone", "resolve_auto_bg_tones", "text_contrast_report",
    "illustration_caption_geometry", "silhouette_tokens",
    "silhouette_similarity", "validate_authored_visual",
    "render_authored_page", "authored_manifest", "write_authored_manifest",
]
