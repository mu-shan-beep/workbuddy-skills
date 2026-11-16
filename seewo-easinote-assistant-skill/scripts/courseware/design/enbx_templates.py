#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""enbx_templates.py — enbx 包的静态部件模板。

SAVE_INFO_METADATA：元素类型元数据契约清单，内容为静态模板数据，与课件内容无关。
thumbnail_png：课件列表缩略图（纯底色块，生成期零成本；应用打开后
自行重存会刷新为真实首页截图）。
"""
import base64

SAVE_INFO_METADATA = """<SaveInfoMetadataFile>
  <MetadataContract>
    <MetadataContract>
      <SaveInfoName>Board</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>CopyrightExtension</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>ThemeForBoard</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>Slide</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>Shape</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Element</SaveInfoType>
      <FallbackSaveInfo>Fallback</FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>Picture</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Element</SaveInfoType>
      <FallbackSaveInfo>Fallback</FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>PictureStyle</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>PictureMetaData</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>SaveInfoMetadata</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>Text</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Element</SaveInfoType>
      <FallbackSaveInfo>Fallback</FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>RichText</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>TextLine</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>TextRun</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>TextMarker</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>LineProperty</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>Document</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>DocumentExtraInfo</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>Reference</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
    <MetadataContract>
      <SaveInfoName>Relationship</SaveInfoName>
      <SaveInfoFriendlyName></SaveInfoFriendlyName>
      <SaveInfoType>Unset</SaveInfoType>
      <FallbackSaveInfo></FallbackSaveInfo>
    </MetadataContract>
  </MetadataContract>
</SaveInfoMetadataFile>"""


def thumbnail_png(bg="#FBF9F2"):
    """320×180 纯底色缩略图（PIL 生成；PIL 不可用时退 1×1 白图）。"""
    try:
        from PIL import Image
        import io
        h = bg.lstrip("#")[-6:]
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        im = Image.new("RGB", (320, 180), rgb)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()
    except Exception:
        # 1×1 白 PNG（保底，客户端打开重存后会自行刷新缩略图）
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            "2mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
