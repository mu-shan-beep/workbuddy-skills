#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""enbx_backend.py — 希沃 ENBX 原生绘图后端。

`components.py` 提供薄包装与文本适配算法；本文件负责生成 ENBX XML、
嵌入图片资源并保存课件包。

格式依据（已验证）：
- .enbx = 普通 ZIP：Document.xml / Board.xml / Slides/Slide_N.xml /
  Resources/<id>.<ext> / Reference.xml / SaveInfoMetadataFile.xml / thumbnail.png
- 坐标系 = 逻辑像素（1280×720），x/y 读写均 1:1，无 EMU 换算、无倍乘语义
- 颜色 = #AARRGGBB（原生支持 alpha，无需额外 XML 透明度处理）
- FontSize = px（pptx 侧要 ×0.75 转 pt，这里直写）
- 形状几何 = PresetGeometry（Custom_PPTX_* 类型名客户端照单全收）+ 显式 Path
"""
import hashlib
import io
import os
import sys
import uuid
import zipfile
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from rich_text import parse_rich  # noqa: E402

# ---------------------------------------------------------------- 基础工具


def _nid():
    """元素/页面 id：客户端惯例 32 位小写 hex。"""
    return uuid.uuid4().hex


def _n(v):
    """数字序列化：整数不带小数点，最多 3 位小数。"""
    f = float(v)
    if f == int(f):
        return str(int(f))
    return ("%.3f" % f).rstrip("0").rstrip(".")


def _argb(hex_color, alpha=None):
    """#RRGGBB + 不透明度%(0-100) → #AARRGGBB。"""
    h = hex_color.lstrip("#")
    if len(h) == 8:                      # 已是 AARRGGBB
        return "#" + h.upper()
    a = 255 if alpha is None else max(0, min(255, round(alpha * 255 / 100)))
    return "#%02X%s" % (a, h.upper())


def _esc(text):
    return escape(str(text), {'"': "&quot;"})


# ---------------------------------------------------------------- 几何 Path

def _path_rect(w, h):
    return "M0,0L%s,0 %s,%s 0,%s 0,0z" % (_n(w), _n(w), _n(h), _n(h))


def _path_round_rect(w, h, r):
    r = min(r, w / 2.0, h / 2.0)
    if r <= 0:
        return _path_rect(w, h)
    n = _n
    return ("M0,{r}A{r},{r},0,0,1,{r},0L{w1},0A{r},{r},0,0,1,{w},{r}"
            "L{w},{h1}A{r},{r},0,0,1,{w1},{h}L{r},{h}A{r},{r},0,0,1,0,{h1}z"
            ).format(r=n(r), w=n(w), h=n(h), w1=n(w - r), h1=n(h - r))


def _path_ellipse(w, h):
    rx, ry = _n(w / 2.0), _n(h / 2.0)
    return ("M0,{ry}A{rx},{ry},0,0,1,{w},{ry}A{rx},{ry},0,0,1,0,{ry}z"
            ).format(rx=rx, ry=ry, w=_n(w))


def _path_triangle(w, h):
    return "M%s,0L%s,%s 0,%s %s,0z" % (_n(w / 2.0), _n(w), _n(h), _n(h), _n(w / 2.0))


def _path_plus(w, h):
    a, b = w * 0.35, w * 0.65                     # 横臂 x 区间
    c, d = h * 0.35, h * 0.65                     # 竖臂 y 区间
    pts = [(a, 0), (b, 0), (b, c), (w, c), (w, d), (b, d), (b, h),
           (a, h), (a, d), (0, d), (0, c), (a, c)]
    return "M%s,%sL" % (_n(pts[0][0]), _n(pts[0][1])) + " ".join(
        "%s,%s" % (_n(x), _n(y)) for x, y in pts[1:]) + " %s,%sz" % (
        _n(pts[0][0]), _n(pts[0][1]))


def _path_right_arrow(w, h):
    hx = w * 0.55                                 # 箭身/箭头分界
    pts = [(0, h * 0.25), (hx, h * 0.25), (hx, 0), (w, h / 2.0), (hx, h),
           (hx, h * 0.75), (0, h * 0.75)]
    return "M0,%sL" % _n(h * 0.25) + " ".join(
        "%s,%s" % (_n(x), _n(y)) for x, y in pts[1:]) + " 0,%sz" % _n(h * 0.25)


def _path_callout(w, h, tail_right=False):
    """圆角对话气泡：主体圆角矩形占上 78%，尾巴三角甩向左/右下。"""
    r = min(w, h) * 0.12
    body_h = h * 0.78
    tx = w * (0.65 if tail_right else 0.25)       # 尾巴根 x
    tip_x = tx + (w * 0.12 if tail_right else -w * 0.06)
    n = _n
    parts = ["M0,%sA%s,%s,0,0,1,%s,0L%s,0A%s,%s,0,0,1,%s,%s"
             % (n(r), n(r), n(r), n(r), n(w - r), n(r), n(r), n(w), n(r)),
             "L%s,%sA%s,%s,0,0,1,%s,%s"
             % (n(w), n(body_h - r), n(r), n(r), n(w - r), n(body_h))]
    # 底边先走到尾巴根（尾巴在底边上）
    tail_base = min(tx + w * 0.14, w - r)
    parts.append("L%s,%s" % (n(tail_base), n(body_h)))
    parts.append("L%s,%s" % (n(tip_x), n(h)))     # 尾巴尖
    parts.append("L%s,%s" % (n(tx), n(body_h)))
    parts.append("L%s,%sA%s,%s,0,0,1,0,%sz"
                 % (n(r), n(body_h), n(r), n(r), n(body_h - r)))
    return "".join(parts)


# MSO_SHAPE 枚举名 → (enbx GeometryType, path 函数)
# GeometryType 名表来自 OfficeDocumentConverter.dll 字符串（Custom_PPTX_* 全集）：
# 名字不对客户端直接不渲染（IsoscelesTriangle→Triangle、
# RoundedRectangularCallout→WedgeRoundRectangleCallout（已验证）
def _geometry(kind_name, w, h, radius=0.08, adjusts=None):
    """返回 (GeometryType, path, adjusts_xml)。"""
    name = kind_name.rsplit(".", 1)[-1].upper()
    if name == "RECTANGLE":
        return "Rectangle", _path_rect(w, h), ""
    if name == "ROUNDED_RECTANGLE":
        adj = ('<Adjusts><Adjust><Id>adj</Id><ScaleX>%s</ScaleX>'
               '<ScaleY>0</ScaleY></Adjust></Adjusts>' % _n(radius))
        return ("Custom_PPTX_RoundRectangle",
                _path_round_rect(w, h, min(w, h) * radius), adj)
    if name == "OVAL":
        return "Custom_PPTX_Ellipse", _path_ellipse(w, h), ""
    if name == "ISOSCELES_TRIANGLE":
        return "Custom_PPTX_Triangle", _path_triangle(w, h), ""
    if name == "MATH_PLUS":
        return "Custom_PPTX_MathPlus", _path_plus(w, h), ""
    if name == "RIGHT_ARROW":
        return "Custom_PPTX_RightArrow", _path_right_arrow(w, h), ""
    if name == "ROUNDED_RECTANGULAR_CALLOUT":
        tail_right = bool(adjusts and adjusts.get(1))
        return ("Custom_PPTX_WedgeRoundRectangleCallout",
                _path_callout(w, h, tail_right), "")
    # 未知形状保守退化为矩形（宁可方不可丢）
    return "Rectangle", _path_rect(w, h), ""


# ---------------------------------------------------------------- 元素模板

_ELEM_TAIL = """<Rotation>0</Rotation>
      <IsLocked>False</IsLocked>
      <CanClone>False</CanClone>
      <HasMask>False</HasMask>
      <RotateOrigin>0.5,0.5</RotateOrigin>
      <SaveInfoMetadata>
        <SupportsFallback>True</SupportsFallback>
        <ImportanceLevel>Important</ImportanceLevel>
      </SaveInfoMetadata>"""


def _shape_xml(kind_name, x, y, w, h, fill, alpha=None, line=None,
               radius=0.08, adjusts=None):
    geo_type, path, adj_xml = _geometry(kind_name, w, h, radius, adjusts)
    fill_brush = _argb(fill, alpha) if fill else "#00FFFFFF"
    line_brush = _argb(line) if line else "#00FFFFFF"
    thickness = "1.3333333333333333" if line else "0"
    line_type = "Normal" if line else "None"
    return """<Shape>
      <Geometry>
        <PresetGeometry>
          <GeometryType>%s</GeometryType>%s
        </PresetGeometry>
      </Geometry>
      <Path>%s</Path>
      <Background>
        <ColorBrush>%s</ColorBrush>
      </Background>
      <Foreground>
        <ColorBrush>%s</ColorBrush>
      </Foreground>
      <Thickness>%s</Thickness>
      <LineType>%s</LineType>
      <Opacity>1</Opacity>
      <TextWidth>%s</TextWidth>
      <TextMargin>0,0,0,0</TextMargin>
      <TextContainerMargin>0,0,0,0</TextContainerMargin>
      <IsTextLocationCustomize>True</IsTextLocationCustomize>
      <PenSetting></PenSetting>
      <Id>%s</Id>
      <X>%s</X>
      <Y>%s</Y>
      <Width>%s</Width>
      <Height>%s</Height>
      %s
    </Shape>""" % (geo_type, ("\n          " + adj_xml) if adj_xml else "",
                   path, fill_brush, line_brush, thickness, line_type,
                   _n(w), _nid(), _n(x), _n(y), _n(w), _n(h), _ELEM_TAIL)


_ALIGN = {"left": "Left", "center": "Center", "right": "Right"}
_ANCHOR = {"top": "Top", "middle": "Center", "bottom": "Bottom"}


def _run_xml(text, size, color, bold=False, italic=False, font="Microsoft YaHei"):
    return """<TextRun>
                <Text>%s</Text>
                <FontSize>%s</FontSize>
                <FontVariants>Normal</FontVariants>
                <FontStyle>%s</FontStyle>
                <FontWeight>%s</FontWeight>
                <FontFamily>
                  <Source>%s</Source>
                </FontFamily>
                <Background>
                  <ColorBrush>#00FFFFFF</ColorBrush>
                </Background>
                <Foreground>
                  <ColorBrush>%s</ColorBrush>
                </Foreground>
                <Opacity>1</Opacity>
              </TextRun>""" % (_esc(text), _n(size),
                               "Italic" if italic else "Normal",
                               "Bold" if bold else "Normal",
                               _esc(font), _argb(color))


def _segment_line(text, size, width):
    """把段落文本按估宽切成视觉行分段（字符偏移 StartOffset/Length 序列）。

    已验证的 ENBX 文本规则：应用的布局引擎只认
    `<Lines>/<LineProperty>` 的视觉分段——省略 Lines 时它会把所有 TextLine
    拼接成一整段再按框宽重排，**TextLine 段落边界全部丢失**（封面三行诗并成
    一行、<br> 强制换行失效）；而「单段 Lines 冲出画布」的旧结论只适用于
    分段错误的情况。正解 = 原生格式：每个 TextLine 都带 Lines，分段由我们
    按估宽预先算好。估宽保守取向（×0.98、CJK≈1.0em / ASCII≈0.55em，
    与 rich_text 估宽一致）：宁可早折行，不可溢出。
    """
    if not text:
        return [(0, 0)]
    limit = max(float(width), 1.0) * 0.98
    segs, start, acc = [], 0, 0.0
    for i, ch in enumerate(text):
        wch = size if ord(ch) >= 0x2E80 else size * 0.55
        if acc + wch > limit and i > start:
            segs.append((start, i - start))
            start, acc = i, 0.0
        acc += wch
    segs.append((start, len(text) - start))
    return segs


def _text_xml(x, y, w, h, lines_of_runs, size, color, align="left",
              anchor="top", font="Microsoft YaHei", line_spacing=1.4):
    """lines_of_runs: [[{text,bold,color},...],...]（color 已是最终色）。

    已验证的 ENBX 文本规则有两项要求：
    1. 段落分隔符是 run 文本末尾的 `&#xD;`（CR 实体，必须写成实体——字面 CR
       会被 XML 解析器规范化成 LF）。除最后一个 TextLine 外每个 TextLine 的
       末个 run 都要以 `&#xD;` 收尾，`<Text>` 纯文本镜像同样用 `&#xD;` 连接。
       没有它，客户端把所有 TextLine 拼成一段重排，段落边界（<br>）全丢。
    2. 每个 TextLine 必须带 `<Lines>/<LineProperty>` 视觉分段（_segment_line
       按估宽预切，分段只覆盖可见文本、不含 CR）。不写 Lines 客户端同样重排。
    """
    line_xmls = []
    plain_all = []
    last_idx = len(lines_of_runs) - 1
    for li, runs in enumerate(lines_of_runs):
        plain = "".join(r.get("text", "") for r in runs)
        plain_all.append(plain)
        if runs:
            runs_xml = "".join(
                _run_xml(r.get("text", ""), size,
                         r.get("color") or color, bold=bool(r.get("bold")),
                         italic=bool(r.get("italic")), font=font)
                for r in runs)
        else:
            runs_xml = _run_xml("", size, color, font=font)
        if li < last_idx:
            # 段落分隔：在末个 run 的 </Text> 前插入 CR 实体（不参与估宽分段）
            cut = runs_xml.rfind("</Text>")
            runs_xml = runs_xml[:cut] + "&#xD;" + runs_xml[cut:]
        default_run = _run_xml("", size, color, font=font)
        segs_xml = "".join("""<LineProperty>
                <StartOffset>%d</StartOffset>
                <Length>%d</Length>
              </LineProperty>""" % (off, ln)
                           for off, ln in _segment_line(plain, size, w))
        line_xmls.append("""<TextLine>
            <LineSpacing>%s</LineSpacing>
            <FixedLineSpacing>NaN</FixedLineSpacing>
            <TextAlignment>%s</TextAlignment>
            <TextRuns>
              %s
            </TextRuns>
            <DefaultRunProperty>
              %s
            </DefaultRunProperty>
            <MarginLeft>0</MarginLeft>
            <Indent>0</Indent>
            <TextMarkerStyle>
              <FontSize>0</FontSize>
            </TextMarkerStyle>
            <SpaceBefore>0</SpaceBefore>
            <SpaceAfter>0</SpaceAfter>
            <Lines>
              %s
            </Lines>
            <Direction>LeftToRight</Direction>
            <IndentLevel>0</IndentLevel>
            <TextMarker>None</TextMarker>
            <IndentType>FirstLine</IndentType>
          </TextLine>""" % (_n(line_spacing), _ALIGN[align], runs_xml,
                            default_run, segs_xml))
    return """<Text>
      <RichText>
        <SizeToContent>Manual</SizeToContent>
        <ArrangingType>Horizontal</ArrangingType>
        <VerticalTextAlignment>%s</VerticalTextAlignment>
        <TextLines>
          %s
        </TextLines>
        <Text>%s</Text>
      </RichText>
      <BorderThickness>0</BorderThickness>
      <BorderType>None</BorderType>
      <Id>%s</Id>
      <X>%s</X>
      <Y>%s</Y>
      <Width>%s</Width>
      <Height>%s</Height>
      %s
    </Text>""" % (_ANCHOR[anchor], "\n          ".join(line_xmls),
                  "&#xD;".join(_esc(p) for p in plain_all), _nid(),
                  _n(x), _n(y), _n(w), _n(h), _ELEM_TAIL)


def _picture_xml(res_id, iw, ih, fsize, name, x, y, w, h, ext, element_id=None):
    element_id = element_id or _nid()
    return """<Picture>
      <Source>id://%s</Source>
      <PictureName>%s</PictureName>
      <Alpha>1</Alpha>
      <DisplayRegion>
        <Rectangle>0,0,%s,%s</Rectangle>
      </DisplayRegion>
      <Style>
        <StyleType>None</StyleType>
        <PicturePresetStyle>None</PicturePresetStyle>
      </Style>
      <MetaData>
        <PictureSize>%s,%s</PictureSize>
        <FileSize>%d</FileSize>
      </MetaData>
      <Id>%s</Id>
      <X>%s</X>
      <Y>%s</Y>
      <Width>%s</Width>
      <Height>%s</Height>
      %s
    </Picture>""" % (res_id, _esc(name), _n(ih), _n(iw), _n(iw), _n(ih),
                     fsize, element_id, _n(x), _n(y), _n(w), _n(h), _ELEM_TAIL)


# ---------------------------------------------------------------- Slide/Deck

class EnbxSlide:
    """enbx 画布页：components 叶子函数按鸭子类型识别（_is_enbx_slide）。"""

    _is_enbx_slide = True

    def __init__(self, deck, bg="#FFFFFFFF"):
        self.deck = deck
        self.id = _nid()
        self.background = bg
        self.elements = []          # 元素 XML 片段（z 序 = 追加序）
        self.label_contracts = []   # 客户端截图中的字形光学居中验收契约


class EnbxDeck:
    """整册：slide 列表 + 图片资源登记表（id:// 引用 → Resources/ 实体）。"""

    def __init__(self, title="未命名课件"):
        self.title = title
        self.slides = []
        self.resources = {}         # res_id -> (bytes, ext)

    def new_slide(self, bg="#FFFFFFFF"):
        s = EnbxSlide(self, bg)
        self.slides.append(s)
        return s

    def add_resource(self, data, ext):
        rid = hashlib.md5(data).hexdigest()
        self.resources[rid] = (data, ext.lstrip("."))
        return rid

    # ---- 打包 ----

    def _slide_xml(self, slide):
        return ("<Slide>\n  <Id>%s</Id>\n  <Width>1280</Width>\n"
                "  <Height>720</Height>\n  <KeepIndependentSize>False</KeepIndependentSize>\n"
                "  <Background>\n    <ColorBrush>%s</ColorBrush>\n  </Background>\n"
                "  <Elements>\n    %s\n  </Elements>\n  <Duration>5000000</Duration>\n"
                "  <ThemeForSlide>\n    <ThemeId>-1</ThemeId>\n  </ThemeForSlide>\n</Slide>"
                % (slide.id, slide.background,
                   "\n    ".join(slide.elements)))

    def _board_xml(self):
        items = "\n".join("    <Item>%s</Item>" % s.id for s in self.slides)
        return ("<Board>\n  <SlideWidth>1280</SlideWidth>\n  <SlideHeight>720</SlideHeight>\n"
                "  <Slides>\n%s\n  </Slides>\n  <CopyrightExtension>\n"
                "    <SaveInfoMetadata>\n      <SupportsFallback>True</SupportsFallback>\n"
                "      <ImportanceLevel>None</ImportanceLevel>\n    </SaveInfoMetadata>\n"
                "  </CopyrightExtension>\n  <ThemeForBoard>\n    <ThemeId>-1</ThemeId>\n"
                "  </ThemeForBoard>\n</Board>" % items)

    def _document_xml(self):
        from datetime import datetime
        now = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        return ("<Document>\n  <Name>%s</Name>\n  <Creator></Creator>\n"
                "  <LastModifiedBy></LastModifiedBy>\n  <CreatedDateTime>%s</CreatedDateTime>\n"
                "  <ModifiedDateTime>%s</ModifiedDateTime>\n"
                "  <CreatedDocumentVersion>1.0</CreatedDocumentVersion>\n"
                "  <DocumentVersion>1.0</DocumentVersion>\n"
                "  <CreatedAppVersion>5.2.4.10420</CreatedAppVersion>\n"
                "  <AppVersion>5.2.4.10420</AppVersion>\n</Document>"
                % (_esc(self.title), now, now))

    def _reference_xml(self):
        rels = []
        for rid, (data, ext) in self.resources.items():
            rels.append("""<Relationship>
      <Id>%s</Id>
      <Target>Resources\\%s.%s</Target>
      <Hash>%s</Hash>
    </Relationship>""" % (rid, rid, ext, hashlib.md5(data).hexdigest()))
        return ("<Reference>\n  <Relationships>\n    %s\n  </Relationships>\n</Reference>"
                % "\n    ".join(rels))

    def save(self, out_path):
        import enbx_templates as T
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("Document.xml", b"\xef\xbb\xbf" +
                       self._document_xml().encode("utf-8"))
            z.writestr("Board.xml", b"\xef\xbb\xbf" +
                       self._board_xml().encode("utf-8"))
            for i, s in enumerate(self.slides):
                z.writestr("Slides/Slide_%d.xml" % i, b"\xef\xbb\xbf" +
                           self._slide_xml(s).encode("utf-8"))
            for rid, (data, ext) in self.resources.items():
                z.writestr("Resources/%s.%s" % (rid, ext), data)
            z.writestr("Reference.xml", b"\xef\xbb\xbf" +
                       self._reference_xml().encode("utf-8"))
            z.writestr("SaveInfoMetadataFile.xml", b"\xef\xbb\xbf" +
                       T.SAVE_INFO_METADATA.encode("utf-8"))
            z.writestr("thumbnail.png", T.thumbnail_png())
        return out_path


# ---------------------------------------------------------------- 绘图原语
# 与 components.py 同签名；分派由 components 完成。

def add_shape(slide, kind, x, y, w, h, fill, alpha=None, line=None,
              radius=0.08, adjusts=None):
    kind_name = getattr(kind, "name", None) or str(kind)
    xml = _shape_xml(kind_name, x, y, w, h, fill, alpha=alpha, line=line,
                     radius=radius, adjusts=adjusts)
    slide.elements.append(xml)
    return None


def add_rect(slide, x, y, w, h, fill, line=None, rounded=False, radius=0.08,
             alpha=None):
    kind = "ROUNDED_RECTANGLE" if rounded else "RECTANGLE"
    return add_shape(slide, kind, x, y, w, h, fill, alpha=alpha, line=line,
                     radius=radius)


def add_line(slide, x, y, w, h, color, weight=1.0):
    return add_rect(slide, x, y, w, max(h, 1), color)


def add_text(slide, x, y, w, h, text, size, color, bold=False, align="left",
             anchor="top", font="Microsoft YaHei", line_spacing=1.4,
             italic=False, margin=(0, 0, 0, 0), min_size=None):
    import components as C
    left, top, right, bottom = C.normalize_margin(margin)
    inner_w = max(1, w - left - right)
    inner_h = max(1, h - top - bottom)
    lines = [[{"text": ln}] for ln in str(text).split("\n")]
    floor = (min(int(size), max(12, int(size) - 8)) if min_size is None
             else min(int(size), int(min_size)))
    new_size, overflow = C.fit_font_size(lines, inner_w, inner_h, size, line_spacing,
                                         floor=floor)
    C._log_shrink("文本", size, new_size, overflow, text)
    xml = _text_xml(x + left, y + top, inner_w, inner_h,
                    [[dict(r, bold=bold, italic=italic) for r in ln] for ln in lines],
                    new_size, color, align=align, anchor=anchor, font=font,
                    line_spacing=line_spacing)
    slide.elements.append(xml)
    return None


def add_rich_text(slide, x, y, w, h, markup, size, color, accent,
                  align="left", anchor="top", font="Microsoft YaHei",
                  line_spacing=1.4, margin=(0, 0, 0, 0), min_size=None,
                  fit=True):
    import components as C
    left, top, right, bottom = C.normalize_margin(margin)
    inner_w = max(1, w - left - right)
    inner_h = max(1, h - top - bottom)
    lines = parse_rich(markup)
    if not lines:
        lines = [[]]
    if fit:
        floor = 20 if min_size is None else min(int(size), int(min_size))
        new_size, overflow = C.fit_font_size(
            lines, inner_w, inner_h, size, line_spacing, floor=floor)
        C._log_shrink("富文本", size, new_size, overflow)
    else:
        new_size = size
    norm = []
    for runs in lines:
        norm.append([{"text": r.get("text", ""), "bold": bool(r.get("bold")),
                      "color": accent if r.get("color") else color}
                     for r in runs])
    xml = _text_xml(x + left, y + top, inner_w, inner_h, norm, new_size, color,
                    align=align,
                    anchor=anchor, font=font, line_spacing=line_spacing)
    slide.elements.append(xml)
    return None


def cover_image_bytes(path, w, h):
    """Return center-cropped image bytes matching the requested aspect ratio."""
    from PIL import Image
    with Image.open(path) as im:
        im.load()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        iw, ih = im.size
        target = w / h
        src = iw / ih
        if abs(src - target) > 0.01:
            if src > target:        # 原图更宽 → 裁左右
                nw = int(ih * target)
                x0 = (iw - nw) // 2
                im = im.crop((x0, 0, x0 + nw, ih))
            else:                   # 原图更高 → 裁上下
                nh = int(iw / target)
                y0 = (ih - nh) // 2
                im = im.crop((0, y0, iw, y0 + nh))
        ext = os.path.splitext(path)[1].lower()
        buf = io.BytesIO()
        if ext in (".jpg", ".jpeg") and im.mode == "RGB":
            im.save(buf, "JPEG", quality=92)
            ext = "jpg"
        else:
            im.save(buf, "PNG")
            ext = "png"
        data = buf.getvalue()
        cw, ch = im.size
    return data, ext, cw, ch


def write_cover_image(path, output_path, w, h):
    """Write a deterministic cover-cropped asset for a client-native background."""
    data, ext, _cw, _ch = cover_image_bytes(path, w, h)
    expected_ext = ".%s" % ext
    if os.path.splitext(output_path)[1].lower() != expected_ext:
        output_path = os.path.splitext(output_path)[0] + expected_ext
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as stream:
        stream.write(data)
    return os.path.abspath(output_path)


def write_solid_image(color, output_path, w, h):
    """Write an exact RGB solid-color asset for a client-native background."""
    from PIL import Image
    output_path = os.path.splitext(output_path)[0] + ".png"
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    Image.new("RGB", (int(w), int(h)), color).save(output_path, "PNG")
    return os.path.abspath(output_path)


def add_picture_cover(slide, path, x, y, w, h):
    """图片（cover 语义）：生成期物理裁切后作为前景 Picture 写入。"""
    data, ext, cw, ch = cover_image_bytes(path, w, h)
    rid = slide.deck.add_resource(data, ext)
    name = os.path.splitext(os.path.basename(path))[0]
    element_id = _nid()
    slide.elements.append(_picture_xml(rid, cw, ch, len(data), name,
                                       x, y, w, h, ext, element_id=element_id))
    return element_id
