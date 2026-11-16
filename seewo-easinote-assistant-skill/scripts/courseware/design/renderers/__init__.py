# -*- coding: utf-8 -*-
"""渲染层：把校验通过的页面计划绘制到 ENBX 画布。"""
from .page_renderer import (authored_manifest, render_authored_page,
                            write_authored_manifest)

__all__ = ["authored_manifest", "render_authored_page", "write_authored_manifest"]
