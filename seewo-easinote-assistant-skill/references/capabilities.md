# 希沃白板 MCP 能力清单（自动生成）

> 来源：希沃白板 MCP 服务 `EasiNote`，通过 `tools/list` 自动拉取。
> 本文件由 `tools/refresh_capabilities.py` 生成，希沃更新工具集后重跑即可刷新，请勿手工大改。
> 共 **60** 个工具。

## 使用约定（必须先懂）

- **Shell / 课件是操作入口**：几乎所有工具都需要先通过 `en_find_shells` 拿到 Shell Id，
  或用 `en_bind_shell` 绑定一个 Shell，之后多数工具可不传 `shellId`。
- **模式（UI）**：`en_goto_app_ui` 切换 Cloud（云课件页）/ Edit（备课编辑）/ Display（授课）。
  添加元素、编辑元素类工具通常要求处于 **Edit（备课）模式**；授课相关功能要求 **Display 模式**。
- **坐标系**：画布逻辑坐标，原点左上角，标准画布约 1280×720。
- **可读名称**：`get_slide_info` 会返回类似 `文本.1` / `图片.1` 的可读名称，可直接当 `elementId` 用。

## 课件与 Shell 导航

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `en_find_shells` | 查找要操作的 Shell；要操作 Shell，必须通过此方法获取 Id，因为所有 Shell 的 MCP 工具都需要传入 Id | searchingMode(必填,string); coursewareName(可选,string/null) |
| `en_bind_shell` | 绑定后续操作到指定 Shell，避免每个工具都传 shellId | shellId(可选,string/null) |
| `en_goto_app_ui` | 切换到指定的应用界面模式（Cloud/Edit/Display）（用户有可能会说成打开某个界面，其实指的是切换到这个界面） | ui(必填,string) |
| `ensys_open_file` | 用系统默认程序打开指定路径的文件 | filePath(必填,string) |
| `switch_to_display_board_mode` | 切换到显示端的指定板书模式 | mode(必填,string); color(可选,string/null); clearAllInks(可选,boolean/null) |
| `get_current_courseware_info` | 获取当前已打开课件的基本信息（标题、页数、页面尺寸、是否已同步等课件元数据） | shellId(可选,string/null) |
| `close_current_courseware` | 关闭当前课件 | shellId(可选,string/null) |
| `sync_current_courseware` | 触发当前课件的云同步（必须处于备课/Edit 界面，否则报错；可通过 get_current_courseware_info 工具获取课件当前是否已同步） | waitUntilSynced(可选,boolean); waitSeconds(可选,integer); shellId(可选,string/null) |
| `new_cloud_courseware` | 新建一份空白云课件并打开，等待课件加载完成后返回对应的备课 Shell；创建失败、未取得 Shell 或等待加载超时会报错 | title(可选,string/null) |
| `open_cloud_courseware` | 按名称模糊匹配打开云课件。匹配多个同名课件时自动选择最近更新的 | coursewareName(必填,string) |
| `search_cloud_courseware` | 搜索云端课件列表，返回候选项供 AI 选择（不打开） | keyword(必填,string); maxResults(可选,integer) |
| `new_cloud_courseware_from_pptx` | 将 PPTX 文件导入为希沃白板课件并打开，完成后，课件将保持打开状态（注意，用户可能切换了标签页，所以不一定是当前标签页） 本方法会返回 Shell 信息供你为导入的课件进行后续操作 | pptxPath(必填,string) |
| `analyze_courseware` | 分析课件，返回全部页面的 Markdown 信息和图片资源索引。 课件必须已打开且处于备课（编辑）模式。 | shellId(可选,string/null) |
| `recognition_document_and_goto_page` | 启动内容感知识别当前课件并打开到指定功能。需先打开一份课件并进入授课（Display）模式。 课件里可能包含多种类型的内容，如习题、诗词、汉字、单词等，内容感知可以针对课件内不同的内容，提供不同的学习功能。 如果没有指定 type，则会让用… | type(可选,string/null); page(可选,integer) |

## 页面操作

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `add_slide` | 在指定页后新增空白页，并返回新增页的信息 | slideNumber(可选,integer/null); shellId(可选,string/null) |
| `delete_slide` | 删除指定页面，并返回被删除页和删除后当前页的信息 | slideNumber(可选,integer/null); shellId(可选,string/null) |
| `duplicate_slide` | 复制指定页（含所有元素），插入到其后 | slideNumber(可选,integer/null); shellId(可选,string/null) |
| `move_slide` | 移动页面到新位置 | fromNumber(必填,integer); toNumber(必填,integer); shellId(可选,string/null) |
| `goto_slide` | 跳转到指定页，并返回跳转后的页面信息。AI 不需区分备课/授课，工具内部自动处理（授课时补过渡动画） | slideNumber(必填,integer); shellId(可选,string/null) |
| `goto_next_slide` | 跳转到下一页 | shellId(可选,string/null) |
| `goto_prev_slide` | 跳转到上一页 | shellId(可选,string/null) |
| `get_slide_properties` | 获取指定页（或当前页）所有属性集合。只查询页面本身的所有属性，不涉及内部元素。 | slideNumber(可选,integer/null); shellId(可选,string/null) |
| `set_slide_properties` | 设置指定 Id 的元素，或指定 Id 表达式的元素部件的指定属性为指定值，或清除指定属性。 | slideNumber(可选,integer/null); propertyGroups(可选,object/null); shellId(可选,string/null) |
| `RenderSlideML` | 将 SlideML XML 渲染为课件页面预览图，返回回填后的 XML 与渲染警告。 课件必须已打开且处于备课（编辑）模式。 | slideId(必填,string/null); slideXml(必填,string); shellId(可选,string/null) |
| `get_slide_info` | 获取页面综合信息，返回 Markdown 格式的自然语言文本，包含页面尺寸、页码、元素树形简要信息（可读名称、位置、尺寸）及元素细节（文本内容、字号字体等）。 元素使用可读名称（如"文本.1""图片.1"）标识，可直接作为其他工具的 ele… | slideNumber(可选,integer/null); shellId(可选,string/null) |
| `get_slide_screenshot` | 获取页面渲染截图 | slideNumber(可选,integer/null); expectedPngImageFilePath(可选,string/null); shellId(可选,string/null) |
| `get_element_screenshot` | 获取单个元素的截图 | elementId(必填,string); slideNumber(可选,integer/null); expectedPngImageFilePath(可选,string/null); shellId(可选,string/null) |

## 元素查询与编辑

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `get_elements` | 按条件查询元素的详细信息（含锁定状态、完整文本内容等）。只读不改变选中状态。 输入参数中的所有条件同时满足的元素才会被查询到：不传表示不参与查询条件，传空表示按空值来查询。 | slideNumber(可选,integer/null); elementIds(可选,array/null); elementTypes(可选,array/null); containsTextRegex(可选,string/null); onlySelected(可选,boolean); shellId(可选,string/null) |
| `select_elements` | 按条件选择页面上的元素。 输入参数中的所有条件同时满足的元素才会被选择：不传表示不参与查询条件，传空表示按空值来查询。 | slideNumber(可选,integer/null); elementIds(可选,array/null); elementTypes(可选,array/null); containsTextRegex(可选,string/null); includeLocked(可选,boolean); selectionType(可选,string); shellId(可选,string/null) |
| `set_element_layer` | 选中指定元素并修改这些元素的层级（由于内部代码限制，本工具必定会先选中元素再执行层级操作） | layer(必填,string); slideNumber(可选,integer/null); elementIds(可选,array/null); shellId(可选,string/null) |
| `group_elements` | 对元素进行分组或取消分组 | slideNumber(可选,integer/null); elementIds(可选,array/null); type(可选,string); shellId(可选,string/null) |
| `edit_element` | 修改元素的通用属性（位置、尺寸、锁定），所有元素类型共用 | slideNumber(可选,integer/null); elementIds(可选,array/null); x(可选,number/null); y(可选,number/null); width(可选,number/null); height(可选,number/null); isLocked(可选,boolean/null); shellId(可选,string/null) |
| `delete_elements` | 删除指定元素。不传 elementIds 时删除当前选中的所有元素。 遵循与右键菜单/快捷键一致的可删性规则：锁定元素与不可删除的元素会被跳过（如需删除锁定元素，请先用 edit_element 解锁）。 诸如课堂活动中的多个元素部件等，是… | slideNumber(可选,integer/null); elementIds(可选,array/null); shellId(可选,string/null) |
| `get_element_properties` | 获取指定 Id 的元素，或指定 Id 表达式的元素部件的所有属性集合。 | id(必填,string); slideNumber(可选,integer/null); shellId(可选,string/null) |
| `set_element_properties` | 设置指定 Id 的元素，或指定 Id 表达式的元素部件的指定属性为指定值，或清除指定属性。 | id(必填,string); slideNumber(可选,integer/null); propertyGroups(可选,object/null); shellId(可选,string/null) |
| `get_properties_schema` | 为了让智能体知道可以给指定的元素/元素部件设置哪些属性，可使用此工具获取所有可供设置的属性集合的 Schema。 | id(必填,string); slideNumber(可选,integer/null); propertyGroupNames(可选,array/null); shellId(可选,string/null) |
| `edit_text_element` | 修改文本或任何含文本的元素内文本的样式（字号/颜色/字体/粗斜/下划线等）。不传 elementIds 时操作所有选中的、含文本的元素。 如果文本或任何含文本的元素内单独选择了一段文本，那么将只操作选择的这一段文本。 注意：此工具不能修改文… | slideNumber(可选,integer/null); elementIds(可选,array/null); fontSize(可选,number/null); fontFamily(可选,string/null); color(可选,string/null); bold(可选,boolean/null); italic(可选,boolean/null); underline(可选,boolean/null); lineSpacing(可选,number/null); opacity(可选,number/null); shellId(可选,string/null) |
| `edit_image_element` | 修改图片元素的属性。 | elementId(可选,string/null); source(可选,string/null); opacity(可选,number/null); hasMask(可选,boolean/null); shadow(可选,object/null); reflection(可选,object/null); border(可选,object/null); crop(可选,object/null); shellId(可选,string/null) |
| `get_image_element_properties` | 获取图片元素的当前属性信息，包含当前图片的像素大小、不透明度，阴影、倒影、边框、裁剪区域、蒙层等。 | elementId(必填,string); slideNumber(可选,integer/null); shellId(可选,string/null) |

## 添加内容元素

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `add_text_element` | 在当前课件页添加一个文本元素。 课件必须已打开且处于备课（编辑）模式，否则工具会返回错误。 坐标系为画布逻辑坐标，原点在画布左上角，标准画布尺寸约为 1280×720。 不指定坐标时，文本将居中放置于画布；不指定样式时使用合理默认值。  注… | text(必填,string); x(可选,number/null); y(可选,number/null); fontSize(可选,number/null); fontFamily(可选,string/null); color(可选,string/null); bold(可选,boolean); italic(可选,boolean); shellId(可选,string/null) |
| `add_image_element` | 在当前课件页添加一张图片元素。 课件必须已打开且处于备课（编辑）模式，否则工具会返回错误。 坐标系为画布逻辑坐标，原点在画布左上角，标准画布尺寸约为 1280×720。 不指定坐标时，图片将居中放置；不指定尺寸时，图片按原始比例缩放到画布宽… | source(必填,string); x(可选,number/null); y(可选,number/null); width(可选,number/null); height(可选,number/null); shellId(可选,string/null) |
| `add_table_element` | 在当前课件页添加一个表格元素。 课件必须已打开且处于备课（编辑）模式。 坐标系为画布逻辑坐标，原点在画布左上角，标准画布尺寸约为 1280×720。 表格数据以标准 Markdown 表格格式传入，例如：   | 姓名 | 语文 | 数学 … | markdownTable(必填,string); x(可选,number/null); y(可选,number/null); width(可选,number/null); height(可选,number/null); shellId(可选,string/null) |
| `add_mind_map_element` | 在当前课件页添加一个思维导图元素（树形脑图）。 课件必须已打开且处于备课（编辑）模式。 坐标系为画布逻辑坐标，原点在画布左上角，标准画布尺寸约为 1280×720。 思维导图数据以多级 Markdown 列表格式传入，例如：   - 细胞结… | markdownList(必填,string); x(可选,number/null); y(可选,number/null); width(可选,number/null); height(可选,number/null); shellId(可选,string/null) |

## 添加学科组件

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `add_classical_poem_element` | 在当前课件页添加古诗词学习组件（ClassicalWork）。 古诗词组件是希沃白板内置的语文学科元素，包含原文、译文、释义、朗读音频等内容，数据来自本地内置古诗词资源库（收录数百首常见古诗词）。 通过标题（必填）和作者（可选）进行模糊查找… | title(必填,string); author(可选,string/null); shellId(可选,string/null) |
| `add_english_word_card_element` | 在当前课件页添加英语单词卡（EnglishWordCard，词典组件英文名 EnglishDict）学科元素。 英语单词卡是希沃白板内置的英语学科组件，可展示单词的音标、词性、释义、例句等，数据优先从本地离线词典查询。 课件必须已打开且处于… | word(必填,string); x(可选,number/null); y(可选,number/null); isCollapsed(可选,boolean); width(可选,number/null); height(可选,number/null); shellId(可选,string/null) |
| `add_function_plot_element` | 在当前课件页添加函数图像组件（MathFunction）。 函数图像组件是希沃白板内置的数学学科元素，可显示带坐标系的函数曲线。 表达式使用标准数学记法，变量必须为 x，支持：   - 多项式：x^2-2x+1、2x+3   - 三角函数：… | expression(必填,string); x(可选,number/null); y(可选,number/null); shellId(可选,string/null) |
| `add_hanzi_card_element` | 在当前课件页添加汉字卡（HanziCard）学科元素。 汉字卡是希沃白板内置的语文学科组件，可展示汉字的笔顺、部首、笔画数等信息，数据来自本地汉字数据库（常用 3500 字范围内）。 课件必须已打开且处于备课（编辑）模式，否则工具会返回错误… | characters(必填,string); x(可选,number/null); y(可选,number/null); shellId(可选,string/null) |
| `add_pinyin_card_element` | 在当前课件页添加拼音卡（PinyinCard）学科元素。 拼音卡是希沃白板内置的语文学科组件，可展示带声调的拼音，并可播放发音音频。 课件必须已打开且处于备课（编辑）模式，否则工具会返回错误。 坐标系为画布逻辑坐标，原点在画布左上角，标准画… | pinyin(必填,string); x(可选,number/null); y(可选,number/null); shellId(可选,string/null) |
| `add_ruled_paper_element` | 在当前课件页添加四线三格（RuledPaper）学科元素。 四线三格是希沃白板内置的英语学科组件，用于展示英文字母或单词的标准书写格式，适合英语书写教学。 课件必须已打开且处于备课（编辑）模式，否则工具会返回错误。 坐标系为画布逻辑坐标，原… | content(必填,string); x(可选,number/null); y(可选,number/null); shellId(可选,string/null) |

## 添加课堂活动

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `add_choice_activity_element` | 在当前课件页添加「趣味选择」课堂活动。 活动以弹出卡片形式逐题展示选择题，学生选择正确答案，结束后显示得分与解析。 注意：该活动会替换当前课件页的内容与背景，请在新建页面上使用，或确认当前页可被覆盖。 课件必须已打开且处于备课（编辑）模式。 | questions(必填,array); shellId(可选,string/null) |
| `add_classify_activity_element` | 在当前课件页添加「超级分类」课堂活动。 活动将各分类的词语随机散落在页面，学生拖动词语将其归入正确的分类框，结束后显示得分与正确答案。 支持 2-8 个分类，每个分类建议 3-8 个词语。 注意：该活动会替换当前课件页的内容与背景，请在新建… | categories(必填,array); shellId(可选,string/null) |
| `add_judge_activity_element` | 在当前课件页添加「判断对错」课堂活动。 活动以弹出卡片的方式依次展示判断题，学生举手/抢答表示「对」或「错」，结束后展示正确答案。 注意：该活动会替换当前课件页的内容与背景，请在新建页面上使用，或确认当前页可被覆盖。 课件必须已打开且处于备… | statements(必填,array); answers(必填,array); shellId(可选,string/null) |
| `add_match_activity_element` | 在当前课件页添加「知识配对」课堂活动。 活动将左右两组卡片随机排列，学生将左侧项拖动到对应的右侧项完成配对，结束后显示正确答案。 建议 3-8 组配对项。 注意：该活动会替换当前课件页的内容与背景，请在新建页面上使用，或确认当前页可被覆盖。… | pairs(必填,array); shellId(可选,string/null) |

## AI 生成

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `generate_scripts_from_current_courseware` | 基于当前打开的课件生成逐页讲稿（此方法会请求其他 AI，可能需要非常久的时间） | shellId(可选,string/null) |
| `generate_video_from_current_courseware` | 基于当前打开的课件直接生成讲稿视频 | speaker(可选,string/null); watermarkText(可选,string/null); shellId(可选,string/null) |
| `generate_video_from_pptx` | 根据 PPTX 文件生成逐页讲稿视频 | pptxPath(必填,string); speaker(可选,string/null); watermarkText(可选,string/null) |

## 撤销/重做

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `en_undo` | 撤销上一步操作，并返回操作后的当前页面信息 | shellId(可选,string/null) |
| `en_redo` | 重做上一步被撤销的操作，并返回操作后的当前页面信息 | shellId(可选,string/null) |

## 其它

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `set_slide_background_image` | 将本地图片设置为指定单页的背景，并返回修改后的页面信息 | imagePath(必填,string); slideNumber(可选,integer/null); shellId(可选,string/null) |
| `add_shape_element` | 在当前课件页添加一个形状元素（矩形、圆、三角形、五角星等基础几何图形）。 课件必须已打开且处于备课（编辑）模式，否则工具会返回错误。 坐标系为画布逻辑坐标，原点在画布左上角，标准画布尺寸约为 1280×720。 不指定坐标时形状居中放置；不… | shapeType(必填,string); x(可选,number/null); y(可选,number/null); width(可选,number/null); height(可选,number/null); fillColor(可选,string/null); strokeColor(可选,string/null); strokeThickness(可选,number/null); cornerRadius(可选,number/null); shellId(可选,string/null) |

