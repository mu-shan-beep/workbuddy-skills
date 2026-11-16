# 已有课件调整指南

仅在调整、丰富、打开或同步已有课件时读取。新建课件的内容与视觉规划不使用本文件。

前提：客户端 MCP 已就绪，并且目标课件可以唯一确定。多个同名课件或多个候选 shell 时先让用户确认，不自动选取。

## 先回读再修改

```powershell
python scripts/courseware/courseware_ops.py --port 7916 info
```

修改前确认课件标题、shell、当前页和目标元素。元素修改后再次回读，核对文本、位置、尺寸和页面归属。需要精确工具参数时再查 [capabilities.md](capabilities.md)。

## 打开已有云课件

先搜索候选，不直接打开模糊名称：

```powershell
python scripts/courseware/courseware_ops.py --port 7916 search --keyword "题西林壁" --max 10
python scripts/courseware/courseware_ops.py --port 7916 open --name "题西林壁"
```

打开后用 `info` 核对实际标题和页数。

## 常用修改

通用前缀：

```powershell
python scripts/courseware/courseware_ops.py --port 7916 <子命令>
```

添加内容：

```powershell
... add-text --text "核心概念" --x 400 --y 300 --fontSize 36
... add-image --source "C:/img/diagram.png" --width 600
... add-table --markdown "| 项目 | 结论 |\n|---|---|\n| A | B |"
... add-mindmap --markdown "- 主题\n  - 分支"
```

原生学科组件：

```powershell
... add-poem --title "静夜思" --author "李白"
... add-wordcard --word "apple"
... add-plot --expression "x^2-2*x+1"
... add-hanzi --characters "静思"
... add-pinyin --pinyin "jìng yè sī"
... add-ruled --content "Moon moon"
```

编辑和导航：

```powershell
... edit-text --contains "明月" --fontSize 40 --color "#C00000" --bold
... edit-text --elementIds "文本.1" --fontSize 28
... add-slide
... goto --slide 2
... undo
... redo
```

课堂活动会接管当前页。只在确认可被替换的空白页添加 `choice / classify / judge / match`，不能覆盖已有正文、背景或组件。

## 脚本未封装的能力

先从 `capabilities.md` 定位工具名和关键参数，再通过 `mcp_client.py` 或当前 MCP 连接调用。稳定顺序为：

1. `en_find_shells` 获取目标 shell；
2. `en_bind_shell` 绑定唯一目标；
3. `en_goto_app_ui` 进入 Edit；
4. 调用具体 `add_* / edit_* / get_*` 工具；
5. 用 `get_slide_info`、`get_elements` 或 `get_current_courseware_info` 回读。

不要把 Display 模式当成普通编辑入口。

## 设置原生页面背景

```powershell
... set-bg --slide 2 --source "C:/img/lesson-background.png"
```

`set-bg` 调用 `set_slide_background_image` 写入页面自身背景，不创建图片元素，也不接受位置、尺寸、透明度或置底参数。`source` 必须是希沃客户端所在主机可读取的本地图片；调用后必须由 `get_slide_info` 回读到“背景图片”才算成功。正式构建会把图片背景物理裁切、把纯色背景转为无损 PNG，再走同一原生背景门禁；失败时不会回退成全画布 Picture 或色块。

## 同步

只有用户要求时才同步：

```powershell
... sync --wait
```

同步前确认目标 shell、页数、编辑模式和最近一次修改均已回读。同步失败时停止，不切换到其他同名课件重试。

## 已知边界

- 调整已有课件时尊重原视觉语言，不自动套用新建课件的视觉规划。
- 图片源必须真实存在或可访问；失败时不替换成占位图。
- 古诗组件未收录或标题、作者模糊命中多首时，正式构建使用 spec 中完整 `lines` 显式文本兜底并告警；调整已有课件时仍须先核对原文，不静默换内容。
- 原生组件具有客户端尺寸和坐标特性；需要规划新工具页时读取 [subject_tool_guide.md](subject_tool_guide.md)。
- MCP 返回成功不等于客户端已落地，回读是正式完成条件。
