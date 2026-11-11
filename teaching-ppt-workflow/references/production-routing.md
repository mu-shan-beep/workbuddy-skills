# 课件制作路线

本用户固定规则：永远不直接制作可编辑PPTX。默认完成课时页面后按大纲全部导入可画，一页一张原图。需要可编辑对象时也在可画处理，不因模板、动画、WPS/PowerPoint使用场景或工具便利性自动改走原生PPTX制作。

## Canva route

本用户的教案包已指定“完整课时图片绘制 → 按大纲顺序全部导入可画 → 一页一张原图”的路线。直接沿用，不因用户简称“PPT”而改交本地PPTX，不调用生成设计或图层恢复来替代整图导入。中转文件可用于可靠导入，但不是最终交付；最终核对可画presentation类型、画幅、页数与顺序并提供真实设计链接。

先区分“整图展示组装”与“分层编辑”。用户只要求把批准预览图按顺序导入，或明确不要拆层时，按 [teaching-resources.md](teaching-resources.md) 第15条原图导入，一页一图；不调用图层恢复、不改字或重新设计。以下分层规则仅适用于实际需要可编辑对象的任务。

Choose Canva when most of these are true:

- the deck is visual-first and mostly static;
- cards, images and typography carry the design;
- the customer wants continued Canva editing;
- there is no complex official slide master to preserve;
- native PowerPoint animation, triggers and embedded media are limited.

When no finished preview exists and no route is specified, build editable pages from confirmed content with the Canva connector; use `imagegen` for needed illustrations or backgrounds. Keep text, functional shapes and page structure editable.

When the user selects preview-image-to-Canva layer recovery, use the approved images rather than redesigning them. Use the currently available image-to-design/layer-recovery capability, preserve page order and verify actual destination type and dimensions before merging pages. Read [canva-layer-repair.md](canva-layer-repair.md) for recovered text, typography fidelity, missing or fragmented elements, image repairs, local redrawing and real editability checks. Layer recovery is a legitimate selected route, not a reason to reject the user's workflow.

Read the destination first and preserve its existing pages unless their replacement or removal is in the user's scope. Do not assume image previews, recovered Canva layers and exported PPTX have identical editability; check the actual requested deliverable.

## 可画项目归档与二次处理

- 新建、组装或二次处理课件前，先按课文名称查找对应文件夹；没有则创建，同名且归属正确的文件夹复用。
- 在该文件夹下创建并命名对应课时的 presentation 工程，再按大纲加入对应页面。若工具只能在根目录创建，先建空白命名工程并立即移入目标文件夹，核对位置后才加入页面；整套导入不可分步时，先建目标文件夹，导入后立即归档，再进行二次处理。
- 已有正确工程直接读取、原位处理；未归档工程先移入对应文件夹，不另复制。不同课时用明确名称区分，不以未命名单页代替完整演示文稿。
- 交付前实际核对文件夹归属、工程名称与类型、页数和顺序，不能只证明上传成功。必要中转散页不留在根目录，只有获得清理授权才移入回收站，不因归档自动删除素材或其他版本。
- 回归案例：用户发现课件散落并要求按课文归类；应先有文件夹、再有工程、最后组装。正常复用已有工程不受影响。本条已核对流程逻辑，后续新工程仍需实际验证。

## 本地文件的边界

- 仅含原始整页图片的临时PPTX可作为可画导入容器；不添加可编辑文字、形状或图表，不作为成品交付。
- 用户已有PPT的明确局部修改可按原文件处理，不以此新建整套可编辑PPTX。
- 可画不能保留的功能应如实说明具体限制，不能据此自行改为原生PPTX制作或宣称功能已实现。

## Verify uncertain capabilities before scaling

If dimensions, export, fonts, masters, layer recovery or playback present a real uncertainty, validate one page or a small representative set before batch work. Choose pages that exercise the actual risk, not a mandatory cover/content/transition trio. Reuse verified results when conditions are unchanged; a bounded fix does not need a new prototype phase.

If the selected route cannot preserve a required feature, explain that specific limitation and use an authorized alternative where possible. A route change that alters the user's deliverable or locked design needs their decision; ordinary implementation choices within the chosen route do not.
