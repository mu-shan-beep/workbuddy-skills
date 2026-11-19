#!/usr/bin/env python3
"""Extract one page into a reviewable request; never submits images or approves results."""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"重复 JSON 字段：{key}")
            obj[key] = value
        return obj
    def invalid_constant(value):
        raise ValueError(f"JSON 不允许数值：{value}")
    return json.loads(Path(path).read_text(), object_pairs_hook=unique, parse_constant=invalid_constant)


def nonempty(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"缺少有效字段：{field}")
    return value


def source_check(path, page):
    """Compare every text item with exact spans in the current approved source."""
    binding = page.get("source_binding", {})
    source = (Path(path).resolve().parent / nonempty(binding.get("path"), "source_binding.path")).resolve()
    raw = source.read_bytes()
    if digest(raw) != binding.get("sha256"):
        raise ValueError("定稿源文件已改变，须核对采用版后重新绑定")
    text = raw.decode("utf-8")
    confirmation = binding.get("confirmation", {})
    nonempty(confirmation.get("quote"), "source_binding.confirmation.quote")
    nonempty(confirmation.get("at"), "source_binding.confirmation.at")
    def span(value, bounds):
        if (not isinstance(value, list) or len(value) != 2 or
                any(type(x) is not int for x in value) or
                not bounds[0] <= value[0] < value[1] <= bounds[1]):
            raise ValueError("定稿文字选区越界或为空")
        return text[value[0]:value[1]]
    bounds = binding.get("page_span")
    span(bounds, [0, len(text)])
    groups = [(page["visible_text"], binding.get("visible_spans")),
              ([x["text"] for x in page.get("deferred_text", [])], binding.get("deferred_spans", []))]
    for texts, spans in groups:
        if not isinstance(spans, list) or len(texts) != len(spans):
            raise ValueError("定稿选区与首屏／后显文字数量不对应")
        if texts != [span(item, bounds) for item in spans]:
            raise ValueError("JSON 文案与已绑定的本页定稿原文不一致")
    return {"path": str(source), "sha256": digest(raw)}


def mapping_for(source):
    mapping = source.get("tool_mapping", {"prompt_key": "prompt", "attachments_key": "referenced_image_paths", "options": {}})
    pk = nonempty(mapping.get("prompt_key"), "tool_mapping.prompt_key")
    ak = nonempty(mapping.get("attachments_key"), "tool_mapping.attachments_key")
    options = mapping.get("options", {})
    if pk == ak or not isinstance(options, dict) or pk in options or ak in options:
        raise ValueError("工具参数映射冲突，不能用选项覆盖提示词或附件")
    if options.get("num_last_images_to_include"):
        raise ValueError("须明确绑定参考附件，不能自动附带未登记的聊天图片")
    return pk, ak, options


def prepare(path, page_id):
    source = load(path)
    project = nonempty(source.get("project_id"), "project_id")
    revision = nonempty(source.get("source_revision"), "source_revision")
    pages = source.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("pages 必须为非空数组")
    ids = [nonempty(p.get("page_id"), "page_id") for p in pages]
    if len(set(ids)) != len(ids):
        raise ValueError("page_id 在项目内重复")
    if page_id not in ids:
        raise ValueError(f"找不到页面：{page_id}")
    page = pages[ids.index(page_id)]
    title, task, composition, style = [nonempty(page.get(k), k) for k in
                                       ("title", "teaching_task", "composition", "style")]
    text = page.get("visible_text")
    if not isinstance(text, list) or not text or any(not isinstance(t, str) or not t.strip() for t in text):
        raise ValueError("visible_text 必须为非空字符串数组；含标题在内逐项保留定稿原文")
    if title not in text:
        raise ValueError("title 必须作为完整文本项包含在 visible_text 中")
    if not isinstance(page.get("deferred_text", []), list):
        raise ValueError("deferred_text 必须为数组，不能混入首屏文字")
    for item in page.get("deferred_text", []):
        nonempty(item.get("text"), "deferred_text.text")
        nonempty(item.get("trigger"), "deferred_text.trigger")
    approved = source_check(path, page)
    output = page.get("output", {})
    ratio = nonempty(output.get("aspect_ratio"), "output.aspect_ratio")
    fmt = nonempty(output.get("format"), "output.format")
    refs = page.get("references", [])
    if not isinstance(refs, list):
        raise ValueError("references 必须为数组")
    attachments, hashes, descriptions = [], {}, []
    for ref in refs:
        role = ref.get("role")
        if role not in ("style", "material", "layout"):
            raise ValueError("参考用途只能为 style、material 或 layout")
        use = nonempty(ref.get("use"), "references.use")
        file = (Path(path).resolve().parent / nonempty(ref.get("path"), "references.path")).resolve()
        if not file.is_file():
            raise ValueError(f"参考附件不存在：{file}")
        attachments.append(str(file))
        hashes[str(file)] = digest(file.read_bytes())
        descriptions.append(f"附件{len(attachments)}（{role}）：{use}")
    prompt = "\n".join([
        f"输出一张完整的 {ratio} 课堂页，独立高清 {fmt}。",
        "以下仅为当前页任务，内部编号不绘入图片。",
        "学习任务：" + task,
        "仅绘制以下定稿上屏文字，逐项保留原字、标点、注音与次序：",
        json.dumps(text, ensure_ascii=False),
        "整体构图：" + composition,
        "画风：" + style,
        *descriptions,
        "风格附件只沿用视觉语言，素材附件只按指定特征参考，布局附件只还原本页获批构图。",
        "不要复制参考中的文字，不绘制其他课件页或多页总览。",
    ])
    # The snapshot excludes review status and other pages; includes deferred data to detect stale edits.
    pk, ak, options = mapping_for(source)
    arguments = dict(options, **{pk: prompt})
    if attachments:
        arguments[ak] = attachments
    snapshot = {"project_id": project, "source_revision": revision,
                "page": {k: v for k, v in page.items() if k != "review"},
                "reference_sha256": hashes, "tool_arguments": arguments}
    fingerprint = digest(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode())
    return {"project_id": project, "page_id": page_id, "source_sha256": fingerprint,
            "prompt": prompt, "attachments": attachments, "reference_sha256": hashes,
            "approved_source": approved, "tool_arguments": arguments}


def audit(path, page_id, request_path, call_path=None):
    expected = prepare(path, page_id)
    if load(request_path) != expected:
        raise ValueError("请求、页面数据、定稿源件或附件已改变，须重新提取并审核")
    if call_path and load(call_path) != expected["tool_arguments"]:
        raise ValueError("最终工具参数与单页请求不一致：文字、附件、顺序或选项有变动")
    return expected


def record(path, page_id, request_path, result_path):
    """Persist observed results without treating a file as a visual reviewer."""
    request = audit(path, page_id, request_path)
    result = load(result_path)
    allowed = {"page_id", "source_sha256", "status", "output_file", "checks", "issues", "reviewer", "tool_call_id"}
    if not isinstance(result, dict) or set(result) - allowed:
        raise ValueError("结果记录含未知字段，不能覆盖历史或用户确认")
    if result.get("page_id") != page_id or result.get("source_sha256") != request["source_sha256"]:
        raise ValueError("结果记录的页面或请求指纹不匹配")
    status = result.get("status")
    if status not in ("pending", "generated", "repair", "passed"):
        raise ValueError("状态须为 pending、generated、repair 或 passed")
    issues, checks = result.get("issues", []), result.get("checks", [])
    if not isinstance(issues, list) or not isinstance(checks, list):
        raise ValueError("issues 与 checks 必须为数组")
    saved = dict(result)
    if status in ("generated", "passed") or result.get("output_file"):
        output = (Path(result_path).resolve().parent / nonempty(result.get("output_file"), "output_file")).resolve()
        if not output.is_file() or not output.stat().st_size:
            raise ValueError("返回文件缺失或为空")
        saved.update(output_file=str(output), output_sha256=digest(output.read_bytes()))
    if status == "passed":
        nonempty(result.get("reviewer"), "reviewer")
        if issues or not checks:
            raise ValueError("未提交实际检查记录或仍有未解决问题，不能登记通过")
        for check in checks:
            nonempty(check.get("item"), "checks.item")
            nonempty(check.get("evidence"), "checks.evidence")
            if check.get("result") != "pass":
                raise ValueError("有未通过的检查项，不能登记通过")
    if status == "repair" and not issues:
        raise ValueError("待修状态须写明具体问题")
    # Recheck the source immediately before replacing the single authoritative JSON.
    audit(path, page_id, request_path)
    old = Path(path).read_bytes()
    source = load(path)
    page = next(p for p in source["pages"] if p["page_id"] == page_id)
    review = page.setdefault("review", {})
    history = review.setdefault("history", [])
    if not history or history[-1] != saved:
        history.append(saved)
    confirmation = review.get("user_confirmation") if review.get("source_sha256") == request["source_sha256"] else None
    review.update(saved, user_confirmation=confirmation)
    body = json.dumps(source, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".pages-", dir=Path(path).resolve().parent)
    try:
        with os.fdopen(fd, "w") as out:
            out.write(body)
        if Path(path).read_bytes() != old:
            raise ValueError("页面记录被其他操作修改，停止写回以免覆盖")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "audit", "record"))
    parser.add_argument("--pages", required=True)
    parser.add_argument("--page-id", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--call", help="准备实际提交的工具参数 JSON；prepare 导出，audit 核对")
    parser.add_argument("--result", help="实际生成／检查结果 JSON；record 写回当前页")
    args = parser.parse_args()
    try:
        if args.mode == "prepare":
            expected = prepare(args.pages, args.page_id)
            if args.call and Path(args.call).resolve() in (Path(args.pages).resolve(), Path(args.request).resolve()):
                raise ValueError("工具参数输出路径不能覆盖页面数据或请求记录")
            if Path(args.request).resolve() == Path(args.pages).resolve():
                raise ValueError("请求输出路径不能覆盖页面数据")
            Path(args.request).write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n")
            if args.call:
                Path(args.call).write_text(json.dumps(expected["tool_arguments"], ensure_ascii=False, indent=2) + "\n")
            print("已核对定稿原文并生成独立单页请求及工具参数；未提交绘图。")
        elif args.mode == "audit":
            audit(args.pages, args.page_id, args.request, args.call)
            print("PASS：定稿、页面数据、请求及附件一致" + ("，所提供的最终工具参数一致。" if args.call else "；尚未提供最终工具参数。"))
        else:
            if not args.result:
                raise ValueError("record 必须提供 --result")
            record(args.pages, args.page_id, args.request, args.result)
            print("已将实际结果与状态写回当前页；未自动确认成果。")
    except (ValueError, TypeError, AttributeError, OSError) as exc:
        parser.exit(1, f"FAIL：{exc}\n")


if __name__ == "__main__":
    main()
