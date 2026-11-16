# -*- coding: utf-8 -*-
"""校验层：内容槽提取 + 视觉契约校验（含 bgTone 自动实测）。"""
from .content_validator import (CANVAS_H, CANVAS_W, content_slots,
                                is_authored_visual)
from .visual_validator import (CONTRAST_ERROR, CONTRAST_WARN, IMAGE_STRATEGIES,
                               ILLUSTRATION_ROLES, extract_bg_tone,
                               illustration_caption_geometry,
                               resolve_auto_bg_tones, silhouette_similarity,
                               silhouette_tokens, text_contrast_report,
                               validate_authored_visual)

__all__ = [
    "CANVAS_H", "CANVAS_W", "content_slots", "is_authored_visual",
    "CONTRAST_ERROR", "CONTRAST_WARN", "IMAGE_STRATEGIES",
    "ILLUSTRATION_ROLES", "extract_bg_tone",
    "illustration_caption_geometry", "resolve_auto_bg_tones",
    "silhouette_similarity", "silhouette_tokens", "text_contrast_report",
    "validate_authored_visual",
]
