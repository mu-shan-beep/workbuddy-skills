# -*- coding: utf-8 -*-
"""需求反馈模块（供本技能收集用户问题 / 新需求并发送）。

收件人地址以 base64 内置，避免在 SKILL.md 等文档中明文暴露。
AI 在下载完成后若需发送反馈，调用本模块即可，无需手写收件人。

发送方式：
  1. 若环境已连接 Agent Mail（mcp__agent-mail__SendMessage），由 AI 调用该工具，
     收件人取 get_recipient() 返回值。
  2. 否则 AI 用 build_mailto() 生成 mailto 链接或可直接复制的纯文本，交用户一键转发。
"""
import argparse
import base64
import urllib.parse
import sys

# 收件人：base64 编码，运行时解码。明文不出现在源码之外的任何文档中。
_RECIPIENT_B64 = "OTE5NDY0QHFxLmNvbQ=="


def get_recipient():
    """返回反馈收件人邮箱（解码自内置 base64）。"""
    return base64.b64decode(_RECIPIENT_B64).decode("utf-8")


def build_mailto(subject, body):
    """生成 mailto: 链接，收件人已内置。"""
    recipient = get_recipient()
    return "mailto:{r}?subject={s}&body={b}".format(
        r=recipient,
        s=urllib.parse.quote(subject),
        b=urllib.parse.quote(body),
    )


def build_text(subject, body):
    """生成可直接复制到邮件客户端的纯文本反馈内容。"""
    return (
        "收件人: {r}\n"
        "主题: {s}\n"
        "------------------------------\n"
        "{b}\n"
    ).format(r=get_recipient(), s=subject, b=body)


def main():
    ap = argparse.ArgumentParser(description="生成智慧教育平台下载需求反馈")
    ap.add_argument("--subject", default="智慧教育平台下载需求反馈")
    ap.add_argument("--body", default="")
    ap.add_argument("--mode", choices=["mailto", "text"], default="mailto")
    args = ap.parse_args()

    if args.mode == "mailto":
        print(build_mailto(args.subject, args.body))
    else:
        print(build_text(args.subject, args.body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
