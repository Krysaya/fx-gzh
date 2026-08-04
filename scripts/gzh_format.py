#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gzh_format.py —— 离线微信公众号排版器（留白禅意风 / zen-whitespace）

把 gzh/ 下的 .md 源文章，按 gzh-design skill 的「留白禅意风」主题组件库装配成
可直接粘贴进公众号草稿箱的合规 HTML（纯 <section> 片段 + 带复制按钮的预览页）。

设计说明：
- 组件 HTML 模板内嵌于本文件，逐字取自 gzh-design skill 的
  references/theme-zen-whitespace.md 与 references/common-components.md，
  确保与主题一致且通过 validate_gzh_html.py 校验（0 ERROR / 0 WARNING）。
- 仓库 references/ 下同时打包了这两份组件库 .md，作为可读的「样式参考文档」；
  如需改样式，以本文件 TEMPLATES 为准（同步改 references 文档保持一致）。

用法：
    python3 scripts/gzh_format.py                # 处理 gzh/ 下所有新增/改动过的 .md
    python3 scripts/gzh_format.py 某篇.md       # 只处理指定文件
产物：
    gzh/排版/{名}_排版_留白禅意风(zen-whitespace).html   # 干净正文片段（草稿箱用）
    gzh/排版/{名}_排版_留白禅意风(zen-whitespace)_预览.html  # 带「复制」按钮预览页
已处理记录：gzh/.processed.json（按文件内容 hash 判断新增/改动，避免重复排版）
作者署名：可写 gzh/config.json {"author":"...","bio":"..."} 或环境变量
          GZH_AUTHOR / GZH_AUTHOR_BIO；未提供则保留 {{作者名}}/{{简介}} 占位。
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GZH_DIR = REPO_ROOT / "gzh"
OUT_DIR = GZH_DIR / "排版"
MANIFEST_PATH = GZH_DIR / ".processed.json"
CONFIG_PATH = GZH_DIR / "config.json"
SCRIPTS_DIR = REPO_ROOT / "scripts"

# ---------------------------------------------------------------------------
# 中文标点修正（校验器红线：中文后不能跟半角 ,;!? 和直引号 " '）
# ---------------------------------------------------------------------------
_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_HALF = {",": "，", ";": "；", ":": "：", "!": "！", "?": "？"}


def fix_punct(s: str) -> str:
    """正文中文标点全角化。只动紧跟中文的半角标点/直引号，不动英文/URL/代码。"""
    s = re.sub(r"([\u4e00-\u9fff\u3400-\u4dbf])\s*([,;:!?])",
               lambda m: m.group(1) + _HALF[m.group(2)], s)
    s = re.sub(r"([\u4e00-\u9fff\u3400-\u4dbf])\s*\.", lambda m: m.group(1) + "。", s)
    s = re.sub(r"([\u4e00-\u9fff\u3400-\u4dbf])\"", r"\1“", s)
    s = re.sub(r"\"([\u4e00-\u9fff\u3400-\u4dbf])", r"“\1", s)
    s = re.sub(r"([\u4e00-\u9fff\u3400-\u4dbf])'", r"\1‘", s)
    s = re.sub(r"'([\u4e00-\u9fff\u3400-\u4dbf])", r"‘\1", s)
    return s


def wrap(text: str) -> str:
    """普通正文文本 -> <span leaf> 包裹（已做标点修正）。"""
    return f'<span leaf="">{fix_punct(text)}</span>'


def wrap_raw(text: str) -> str:
    """代码/纯文本 -> <span leaf> 包裹（不做标点修正，保持原样）。"""
    return f'<span leaf="">{text}</span>'


# ---------------------------------------------------------------------------
# 组件模板（取自 theme-zen-whitespace.md + common-components.md）
# 约定：{x} 处若模板内已带 <span leaf>，则调用方传 fix_punct 后的纯文本；
#       否则调用方传 wrap()/render_inline() 后的 HTML。
# ---------------------------------------------------------------------------
CONTAINER_OPEN = ('<section style="max-width:677px;margin:0 auto;background:#FFFFFF;'
                  "font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB',"
                  "'Microsoft YaHei',sans-serif;color:#525252;line-height:1.9;"
                  'letter-spacing:0.3px;overflow-x:hidden;">')
CONTAINER_CLOSE = "</section>"

# 组件 2 开头引言卡片
INTRO_TPL = """<section style="margin:32px 16px 48px;padding:40px 24px;border-top:1px solid #E8E8E8;border-bottom:1px solid #E8E8E8;text-align:center;">
  <p style="font-family:'Noto Serif SC',Georgia,'Times New Roman',serif;font-size:19px;font-weight:600;color:#2B2B2B;margin:0 0 28px;line-height:1.85;letter-spacing:0.8px;">
    {quote}
  </p>
  <p style="font-size:12px;color:#A3A3A3;margin:0;letter-spacing:1.5px;">
    {author}
  </p>
</section>"""

# 组件 3 前言导读（极简目录，最多 3 项）
TOC_TPL = """<section style="padding:0 16px 48px;">
  <p style="font-size:11px;color:#A3A3A3;margin:0 0 20px;letter-spacing:2px;text-transform:uppercase;"><span leaf="">本文脉络</span></p>
  <section style="border-top:1px solid #E8E8E8;">
    <section style="display:flex;">
      {items}
    </section>
  </section>
</section>"""
TOC_ITEM = """<section style="flex:1;padding:18px 12px 18px 0;border-bottom:1px solid #E8E8E8;{border}">
  <p style="font-size:11px;color:#4A5D52;font-weight:600;margin:0 0 6px;letter-spacing:1px;"><span leaf="">{num}</span></p>
  <p style="font-size:13px;color:#2B2B2B;margin:0;font-weight:500;line-height:1.5;"><span leaf="">{title}</span></p>
</section>"""

# 组件 4 章节分割线（1px 极细线 + 超大留白）
DIVIDER = """<section style="padding:0 16px;">
  <section style="height:1px;background:#E8E8E8;margin:64px 0 0;">
    <span leaf=""><br></span>
  </section>
</section>"""

# 组件 5 章节标题（结语变体用 ∞ · POSTSCRIPT）
CHAPTER_TPL = """<section style="margin-top:64px;margin-bottom:32px;padding:0 16px;">
  <p style="font-size:10px;color:#4A5D52;font-weight:600;letter-spacing:4px;margin:0 0 10px;text-transform:uppercase;">
    {num_label}
  </p>
  <h3 style="font-family:'Noto Serif SC',Georgia,'Times New Roman',serif;font-size:22px;font-weight:700;color:#2B2B2B;margin:0 0 16px;letter-spacing:0.5px;line-height:1.4;">
    {title}
  </h3>
  <section style="width:40px;height:2px;background:#4A5D52;">
    <span leaf=""><br></span>
  </section>
</section>"""

# 组件 6 正文段落
PARA = ('<p style="margin-bottom:26px;font-size:15px;line-height:1.9;text-align:justify;'
        'color:#525252;padding:0 16px;">{content}</p>')

# 组件 7 高亮
BOLD_NORMAL = '<strong style="color:#2B2B2B;">{content}</strong>'
BOLD_ANCHOR = '<strong style="color:#4A5D52;">{content}</strong>'
LABEL_SPAN = ('<span style="background:#EEF3F0;color:#3D5046;padding:2px 6px;'
              'border-radius:2px;font-weight:600;font-size:14px;">{content}</span>')
UNDERLINE_SPAN = ('<span style="border-bottom:1.5px solid #B5C8BC;font-weight:500;">{content}</span>')
HIGHLIGHT_SPAN = ('<span style="background:linear-gradient(180deg,transparent 60%,#D6E4DC 60%);'
                  'font-weight:600;color:#2B2B2B;">{content}</span>')

# 组件 8 引用块（8a 居中衬线 / 8b 左竖条）
QUOTE_CENTER = """<section style="margin:40px 16px;padding:36px 20px;border-top:1px solid #E8E8E8;border-bottom:1px solid #E8E8E8;text-align:center;">
  <p style="font-family:'Noto Serif SC',Georgia,'Times New Roman',serif;font-size:17px;font-weight:600;color:#2B2B2B;margin:0;line-height:1.9;letter-spacing:0.8px;">
    {content}
  </p>
</section>"""
QUOTE_LEFT = """<section style="border-left:2px solid #4A5D52;padding:10px 20px 10px 20px;margin:0 16px 30px;background:#FFFFFF;">
  <p style="font-size:14px;color:#525252;margin:0;line-height:1.9;text-align:justify;">
    {content}
  </p>
</section>"""

# 组件 9 提示块（墨绿左竖条 + NOTE 小标签）
NOTE_TPL = """<section style="margin:0 16px 32px;padding:18px 20px;border-left:2px solid #4A5D52;">
  <p style="font-size:10px;color:#4A5D52;font-weight:600;letter-spacing:2px;margin:0 0 8px;text-transform:uppercase;">
    <span leaf="">{label}</span>
  </p>
  <p style="font-size:14px;color:#525252;margin:0;line-height:1.9;">
    {content}
  </p>
</section>"""

# 组件 10 图片容器（细线边框；有说明才加说明行）
IMAGE_TPL = """<section style="margin:0 16px {img_mb};border:1px solid #E8E8E8;">
  <section style="margin:0;overflow:hidden;">
    <span leaf=""><img src="{url}" style="max-width:100%;height:auto;display:block;margin:0 auto;"></span>
  </section>
</section>{caption}"""
IMAGE_CAPTION = """
<p style="font-size:12px;color:#A3A3A3;text-align:center;margin:8px 16px 32px;letter-spacing:0.5px;">
  <span leaf="">— {text}</span>
</p>"""
GIF_BADGE = ('<span style="display:inline-block;border:1px solid #B5C8BC;color:#4A5D52;'
             'font-size:11px;font-weight:500;padding:2px 10px;border-radius:2px;'
             'margin-right:6px;letter-spacing:0.5px;"><span leaf="">GIF 动图</span></span>')

# 组件 11 加粗结论段落
CONCLUSION_TPL = ('<p style="margin-bottom:26px;font-size:15px;line-height:1.9;text-align:justify;'
                  'font-weight:600;color:#2B2B2B;padding:0 16px;">{content}</p>')

# 组件 12 要点列表版（细线分隔；marker 原样保留原文编号）
POINT_LIST = """<section style="margin:0 16px 32px;border-top:1px solid #E8E8E8;">
{rows}
</section>"""
POINT_ROW = """<section style="display:flex;align-items:baseline;padding:16px 0;border-bottom:1px solid #E8E8E8;">
  <p style="font-size:11px;color:#4A5D52;font-weight:600;letter-spacing:1px;margin:0;min-width:28px;">{marker}</p>
  <p style="font-size:14px;color:#2B2B2B;margin:0;line-height:1.7;padding-left:12px;">{text}</p>
</section>"""

# 组件 14 END 结尾分割线
END_BLOCK = """<section style="padding:0 16px;">
  <section style="text-align:center;margin:48px 0 40px;">
    <section style="display:flex;align-items:center;justify-content:center;">
      <span style="height:1px;width:48px;background:#E8E8E8;margin-right:16px;"></span>
      <span style="font-size:10px;color:#A3A3A3;letter-spacing:4px;font-weight:400;"><span leaf="">END</span></span>
      <span style="height:1px;width:48px;background:#E8E8E8;margin-left:16px;"></span>
    </section>
  </section>
</section>"""

# 组件 15 尾部作者签名区
SIGNATURE_TPL = """<section style="padding:0 16px 40px;">
  <p style="margin-bottom:26px;font-size:15px;line-height:1.9;text-align:justify;color:#525252;">
    <span leaf="">我是 {author}，{bio}。</span>
  </p>
  <p style="margin-bottom:26px;font-size:15px;line-height:1.9;text-align:justify;color:#525252;">
    <span leaf="">如果你觉得今天这篇有收获，欢迎</span><strong style="color:#4A5D52;"><span leaf="">点赞、在看、转发</span></strong><span leaf="">三连，我们下篇见。</span>
  </p>
</section>"""

# 通用库 1a 深色代码块（各主题共用；每行一个 <p style="margin:0">，缩进用全角空格）
CODE_TPL = """<section style="margin:0 0 20px;border-radius:8px;overflow:hidden;background:#1E293B;box-shadow:0 4px 16px -8px rgba(15,23,42,0.4);">
  <section style="display:flex;align-items:center;padding:9px 14px;background:#0F172A;">
    <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#FF5F56;margin-right:7px;font-size:0;line-height:0;overflow:hidden;">.</span>
    <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#FFBD2E;margin-right:7px;font-size:0;line-height:0;overflow:hidden;">.</span>
    <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#27C93F;font-size:0;line-height:0;overflow:hidden;">.</span>
    <span style="margin-left:12px;font-size:12px;color:#64748B;font-family:Consolas,Monaco,monospace;letter-spacing:1px;"><span leaf="">{lang}</span></span>
  </section>
  <section style="padding:11px 14px;">
    {lines}
  </section>
</section>"""
CODE_LINE = ('<p style="margin:0;font-family:\'SF Mono\',Consolas,Monaco,monospace;font-size:13px;'
             'line-height:1.6;color:#E2E8F0;">{line}</p>')

# 通用库 1c 行内代码（文字色换主题主色 #4A5D52，底色中性浅灰）
CODE_INLINE = ('<span style="background:#F1F5F9;color:#4A5D52;padding:1px 6px;'
               'border-radius:4px;font-family:\'SF Mono\',Consolas,Monaco,monospace;'
               'font-size:14px;">{content}</span>')

# 通用库 3a 左竖条小标题（zen 版：2px 墨绿竖条，无色块）
SUBTITLE_TPL = ('<p style="margin:28px 0 14px;font-size:16px;font-weight:800;color:#2B2B2B;'
                'line-height:1.5;border-left:2px solid #4A5D52;padding-left:12px;">'
                '<span leaf="">{text}</span></p>')

# 通用库 2c 待补素材占位（唯一允许虚线框的场景，居中）
PLACEHOLDER_TPL = """<section style="margin:0 0 24px;padding:30px 20px;border:1.5px dashed #DAD7D2;border-radius:14px;background:#FAFAF8;text-align:center;">
  <p style="margin:0 0 10px;font-size:26px;line-height:1;"><span leaf="">🎬</span></p>
  <p style="margin:0;font-size:14px;font-weight:700;color:#9CA3AF;letter-spacing:1px;"><span leaf="">待补素材</span></p>
  <p style="margin:8px 0 0;font-size:13px;color:#B8B5B0;line-height:1.7;"><span leaf="">{text}</span></p>
</section>"""

# 表格（zen 版细线卡片式：header 浅墨绿底 + 细线分隔；不用 <table>）
TABLE_TPL = """<section style="margin:0 16px 32px;border:1px solid #E8E8E8;">
{rows}
</section>"""
TABLE_HEADER_ROW = """<section style="display:flex;background:#EEF3F0;border-bottom:1px solid #E8E8E8;">
{cells}
</section>"""
TABLE_BODY_ROW = """<section style="display:flex;border-bottom:1px solid #E8E8E8;">
{cells}
</section>"""
TABLE_CELL = ('<p style="flex:1;padding:10px 12px;font-size:13px;color:{color};margin:0;'
              'line-height:1.6;{bold}">{content}</p>')

# ---------------------------------------------------------------------------
# 填充工具
# ---------------------------------------------------------------------------
def fill(tpl: str, **kw) -> str:
    for k, v in kw.items():
        tpl = tpl.replace("{" + k + "}", v)
    return tpl


# ---------------------------------------------------------------------------
# 行内渲染：**加粗** / ==标签== / <u>下划线</u> / ~~荧光笔~~ / `行内代码`
# ---------------------------------------------------------------------------
_INLINE_RE = re.compile(r"\*\*(.+?)\*\*|==(.+?)==|<u>(.*?)</u>|~~(.+?)~~|`([^`]+)`")

# 关键词下划线：优先标「引号内术语」与「数字+量词」（lookaround 保证括号保留在正文）
_KEYWORD_RE = re.compile(
    r"(?<=「)[^」\n]{1,20}(?=」)|(?<=“)[^”\n]{1,20}(?=”)|(?<=‘)[^’\n]{1,20}(?=’)|"
    r"\d+(?:\.\d+)?\s*(?:亿|万|千|%|％|倍|步|个|年|月|天|篇|次|项|位|处)")
_MAX_UNDERLINE_PER_PARA = 3


def _mark_keywords(text: str, state: dict) -> str:
    out = ""
    last = 0
    count = 0
    for m in _KEYWORD_RE.finditer(text):
        if count >= _MAX_UNDERLINE_PER_PARA:
            break
        kw = m.group(0).strip()
        if not kw or len(kw) > 20:
            continue
        out += wrap(text[last:m.start()])
        out += fill(UNDERLINE_SPAN, content=wrap(kw))
        last = m.end()
        count += 1
    out += wrap(text[last:])
    return out


def _render_inline(text: str, state: dict) -> str:
    out = ""
    pos = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            out += _mark_keywords(text[pos:m.start()], state)
        if m.group(1) is not None:            # **bold**
            if state["anchors"] < 5:
                state["anchors"] += 1
                out += fill(BOLD_ANCHOR, content=wrap(m.group(1)))
            else:
                out += fill(BOLD_NORMAL, content=wrap(m.group(1)))
        elif m.group(2) is not None:          # ==label==
            out += fill(LABEL_SPAN, content=wrap(m.group(2)))
        elif m.group(3) is not None:          # <u>underline</u>
            out += fill(UNDERLINE_SPAN, content=wrap(m.group(3)))
        elif m.group(4) is not None:          # ~~highlight~~
            out += fill(HIGHLIGHT_SPAN, content=wrap(m.group(4)))
        elif m.group(5) is not None:          # `code`
            out += fill(CODE_INLINE, content=wrap_raw(m.group(5)))
        pos = m.end()
    if pos < len(text):
        out += _mark_keywords(text[pos:], state)
    return out


# 列表行识别：marker 原样保留（1. / 1.2. / a) / (1) / ① / 三、 / 步骤一： 等）
_LIST_RE = re.compile(
    r"^((?:[-*+]\s+)|(?:\d+\.(?:\d+\.)?\s+)|(?:\d+\)\s+)|(?:\(\d+\)\s+)|"
    r"(?:[A-Za-z][.)]\s+)|(?:[①-⑩]\s+)|(?:[一二三四五六七八九十]+[、.]\s+)|"
    r"(?:步骤[一二三四五六七八九十]+[：:]?))(.*)$")


# ---------------------------------------------------------------------------
# Markdown 块解析
# ---------------------------------------------------------------------------
def parse_blocks(lines):
    lines = list(lines)
    # 去掉 frontmatter
    if lines and lines[0].strip() == "---":
        idx = 1
        while idx < len(lines) and lines[idx].strip() != "---":
            idx += 1
        lines = lines[idx + 1:]

    blocks, i, n = [], 0, len(lines)
    while i < n:
        raw = lines[i].rstrip("\n")
        s = raw.strip()
        if not s:
            i += 1
            continue
        # 代码围栏
        if s.startswith("```"):
            lang = s[3:].strip()
            i += 1
            code = []
            while i < n and not lines[i].lstrip().startswith("```"):
                code.append(lines[i].rstrip("\n"))
                i += 1
            i += 1  # 跳过结束围栏
            blocks.append({"type": "code", "lang": lang, "lines": code})
            continue
        # 标题
        if s.startswith("### "):
            blocks.append({"type": "subtitle", "text": s[4:].strip()})
            i += 1
            continue
        if s.startswith("## "):
            blocks.append({"type": "chapter", "text": s[3:].strip()})
            i += 1
            continue
        if s.startswith("# "):
            blocks.append({"type": "h1", "text": s[2:].strip()})
            i += 1
            continue
        # 分割线
        if s in ("---", "***", "___"):
            blocks.append({"type": "divider"})
            i += 1
            continue
        # 图片
        m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", s)
        if m:
            url = m.group(2).strip()
            gif = url.lower().endswith(".gif")
            blocks.append({"type": "image", "url": url, "alt": m.group(1).strip(), "gif": gif})
            i += 1
            continue
        # 引用 / 提示 / 开头引言
        if s.startswith(">") or s.startswith("!>"):
            qlines = []
            while i < n and (lines[i].lstrip().startswith(">") or lines[i].lstrip().startswith("!>")):
                ql = lines[i].lstrip()
                if ql.startswith(">"):
                    ql = ql[1:]
                else:
                    ql = ql[2:]
                qlines.append(ql.strip())
                i += 1
            joined = "\n".join(qlines)
            first = qlines[0] if qlines else ""
            note_m = re.match(r"^\[!(\w+)\]", first)
            if note_m:
                body = "\n".join(qlines[1:]) if len(qlines) > 1 else joined
                blocks.append({"type": "note", "label": note_m.group(1).upper(), "text": body})
            elif s.startswith("!>"):
                blocks.append({"type": "note", "label": "NOTE", "text": joined})
            else:
                blocks.append({"type": "quote", "text": joined})
            continue
        # 待补素材占位
        if "【" in s and s.endswith("】"):
            blocks.append({"type": "placeholder", "text": s})
            i += 1
            continue
        # 列表（marker 原样保留，含 1.2. / ① / a) / 步骤三 等自定义编号）
        lm = _LIST_RE.match(s)
        if lm:
            items = []
            while i < n:
                sl = lines[i].rstrip("\n").strip()
                mm = _LIST_RE.match(sl)
                if not mm:
                    break
                items.append({"marker": mm.group(1).strip(), "text": mm.group(2).strip()})
                i += 1
            blocks.append({"type": "list", "items": items})
            continue
        # 表格
        if "|" in s and i + 1 < n and re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", lines[i + 1]) and "-" in lines[i + 1]:
            header = [c.strip() for c in s.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < n:
                tl = lines[i].rstrip("\n").strip()
                if not tl or "|" not in tl:
                    break
                rows.append([c.strip() for c in tl.strip().strip("|").split("|")])
                i += 1
            blocks.append({"type": "table", "headers": header, "rows": rows})
            continue
        # 普通段落（收集连续行，\n 渲染为 <br>）
        para = []
        while i < n:
            sl = lines[i].rstrip("\n")
            s2 = sl.strip()
            if (not s2 or s2.startswith("#") or s2.startswith(">") or s2.startswith("!>")
                    or s2.startswith("```") or s2.startswith("![") or s2 in ("---", "***", "___")
                    or _LIST_RE.match(s2)):
                break
            para.append(sl)
            i += 1
        blocks.append({"type": "paragraph", "text": "\n".join(para)})
    return blocks


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------
_EN_CHAPTER = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE", 6: "SIX",
               7: "SEVEN", 8: "EIGHT", 9: "NINE", 10: "TEN", 11: "ELEVEN", 12: "TWELVE"}
_POSTSCRIPT_KEYS = ("结语", "总结", "尾声", "终章", "收尾", "后记")


def _is_postscript(title: str) -> bool:
    return any(k in title for k in _POSTSCRIPT_KEYS)


def render_block(b: dict, state: dict) -> str:
    t = b["type"]
    if t == "h1":
        return ""
    if t == "divider":
        return DIVIDER
    if t == "subtitle":
        return fill(SUBTITLE_TPL, text=fix_punct(b["text"]))
    if t == "paragraph":
        html = _render_inline(b["text"], state).replace("\n", "<br>")
        return fill(PARA, content=html)
    if t == "quote":
        inner = _render_inline(b["text"], state).replace("\n", "<br>")
        if "\n" in b["text"] or len(b["text"]) > 40:
            return fill(QUOTE_LEFT, content=inner)
        return fill(QUOTE_CENTER, content=inner)
    if t == "note":
        return fill(NOTE_TPL, label=fix_punct(b["label"]),
                    content=_render_inline(b["text"], state).replace("\n", "<br>"))
    if t == "list":
        rows = []
        for item in b["items"]:
            mk = item["marker"]
            if re.match(r"^\d+[.)]$", mk):
                marker = f"{int(mk[:-1]):02d}"
            elif mk in ("-", "*", "+"):
                marker = "·"
            else:
                marker = mk  # 1.2. / ① / a) / 步骤三 等原样保留
            text = _render_inline(item["text"], state).replace("\n", "<br>")
            rows.append(fill(POINT_ROW, marker=wrap(marker), text=text))
        return fill(POINT_LIST, rows="\n".join(rows))
    if t == "code":
        lang = b["lang"] if b["lang"] else "code"
        lines_html = []
        for line in b["lines"]:
            # 只把行首缩进转成全角空格（避免大左缩进/空行），行内空格保持原样
            line_html = re.sub(r"^[ \t]+",
                               lambda m: "　" * (m.group(0).count(" ") + m.group(0).count("\t") * 4),
                               line)
            lines_html.append(fill(CODE_LINE, line=wrap_raw(line_html)))
        if not lines_html:
            lines_html.append(fill(CODE_LINE, line="<br>"))
        return fill(CODE_TPL, lang=lang, lines="\n".join(lines_html))
    if t == "image":
        img_mb = "8px" if b["alt"] else "10px"
        caption = ""
        if b["alt"]:
            caption = fill(IMAGE_CAPTION, text=fix_punct(b["alt"]))
            if b["gif"]:
                caption = "\n<p style=\"font-size:12px;color:#A3A3A3;text-align:center;margin:8px 16px 32px;letter-spacing:0.5px;\">" + GIF_BADGE + "<span leaf=\"\">" + fix_punct(b["alt"]) + "</span></p>"
        elif b["gif"]:
            caption = "\n<p style=\"font-size:12px;color:#A3A3A3;text-align:center;margin:8px 16px 32px;letter-spacing:0.5px;\">" + GIF_BADGE + "</p>"
        return fill(IMAGE_TPL, url=b["url"], img_mb=img_mb, caption=caption)
    if t == "placeholder":
        return fill(PLACEHOLDER_TPL, text=fix_punct(b["text"]))
    if t == "table":
        return _render_table(b, state)
    return ""


def _render_table(b: dict, state: dict) -> str:
    rows = []
    head_cells = "".join(fill(TABLE_CELL, content=wrap(c), color="#3D5046", bold="font-weight:600;")
                         for c in b["headers"])
    rows.append(fill(TABLE_HEADER_ROW, cells=head_cells))
    for r in b["rows"]:
        cells = "".join(fill(TABLE_CELL, content=_render_inline(c, state), color="#525252", bold="")
                        for c in r)
        rows.append(fill(TABLE_BODY_ROW, cells=cells))
    return fill(TABLE_TPL, rows="\n".join(rows))


def render_document(blocks: list, config: dict) -> str:
    state = {"anchors": 0}
    # 分离：开头引言 / 前言正文 / 章节组
    intro, pre, chapters, cur, seen_chapter = None, [], [], None, False
    for b in blocks:
        if b["type"] == "chapter":
            seen_chapter = True
            cur = {"title": b["text"], "blocks": []}
            chapters.append(cur)
        elif not seen_chapter:
            if b["type"] == "quote" and intro is None:
                intro = b
            else:
                pre.append(b)
        else:
            cur["blocks"].append(b)

    out = [CONTAINER_OPEN]
    if intro:
        lines = intro["text"].split("\n")
        author = ""
        if lines and (lines[-1].startswith("——") or lines[-1].startswith("--")):
            author = lines[-1].lstrip("-").strip()
            lines = lines[:-1]
        quote = _render_inline("\n".join(lines), state).replace("\n", "<br>")
        out.append(fill(INTRO_TPL, quote=quote,
                        author=wrap(author) if author else wrap("—— 作者名")))
    for b in pre:
        r = render_block(b, state)
        if r:
            out.append(r)
    # 目录（前 3 个章节）
    if chapters:
        items = []
        toc = chapters[:3]
        for idx, c in enumerate(toc):
            border = "" if idx == len(toc) - 1 else "border-right:1px solid #E8E8E8;margin-right:16px;"
            items.append(fill(TOC_ITEM, border=border,
                              num=fix_punct(f"{idx + 1:02d}"), title=fix_punct(c["title"])))
        out.append(fill(TOC_TPL, items="\n".join(items)))
    out.append(DIVIDER)
    total = len(chapters)
    for idx, c in enumerate(chapters):
        if idx == total - 1 and _is_postscript(c["title"]):
            num_label = "∞ · POSTSCRIPT"
        else:
            num = idx + 1
            en = _EN_CHAPTER.get(num, f"CHAPTER {num}")
            num_label = f"{num:02d} · CHAPTER {en}"
        out.append(fill(CHAPTER_TPL, num_label=wrap(num_label), title=wrap(c["title"])))
        for b in c["blocks"]:
            r = render_block(b, state)
            if r:
                out.append(r)
        if idx < total - 1:
            out.append(DIVIDER)
    out.append(END_BLOCK)
    out.append(fill(SIGNATURE_TPL, author=fix_punct(config["author"]),
                    bio=fix_punct(config["bio"])))
    out.append(CONTAINER_CLOSE)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def load_config():
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    return {
        "author": cfg.get("author") or os.environ.get("GZH_AUTHOR") or "{{作者名}}",
        "bio": cfg.get("bio") or os.environ.get("GZH_AUTHOR_BIO") or "{{简介}}",
    }


def load_manifest():
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"files": {}}


def run_validate(html_file: Path):
    res = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "validate_gzh_html.py"), str(html_file)],
        capture_output=True, text=True)
    print(res.stdout, end="")
    if res.returncode != 0:
        raise SystemExit(f"✗ 校验未通过（{html_file.name}），请检查。\n{res.stderr}")


def run_wrap_preview(html_file: Path):
    res = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "wrap_preview.py"), str(html_file)],
        capture_output=True, text=True)
    print(res.stdout, end="")
    if res.returncode != 0:
        print(f"⚠ 预览页生成失败: {res.stderr}")


def write_index():
    """在 gzh/排版/ 下写一份产物清单，便于云函数定位「最新排版文件」取 raw 直链。"""
    entries = []
    for html in sorted(OUT_DIR.glob("*_排版_留白禅意风(zen-whitespace).html")):
        entries.append({"file": html.name, "preview": html.stem + "_预览.html"})
    idx = {"count": len(entries), "branch": os.environ.get("GITHUB_REF_NAME", "main"),
           "entries": entries}
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo:
        idx["raw_url_prefix"] = f"https://raw.githubusercontent.com/{repo}/{idx['branch']}/gzh/排版/"
    OUT_DIR.joinpath("产物清单.json").write_text(
        json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(entries)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    config = load_config()

    md_files = []
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            fp = Path(p)
            if fp.is_file():
                md_files.append(fp)
    else:
        for f in sorted(GZH_DIR.glob("*.md")):
            md_files.append(f)

    done, skipped = 0, 0
    for f in md_files:
        rel = str(f.resolve().relative_to(REPO_ROOT.resolve()))
        try:
            content = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = f.read_text(encoding="utf-8", errors="replace")
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if manifest.get("files", {}).get(rel) == h:
            skipped += 1
            continue
        html = render_document(parse_blocks(content.split("\n")), config)
        stem = f.stem
        out = OUT_DIR / f"{stem}_排版_留白禅意风(zen-whitespace).html"
        out.write_text(html, encoding="utf-8")
        run_validate(out)
        run_wrap_preview(out)
        manifest.setdefault("files", {})[rel] = h
        done += 1
        print(f"✓ 已排版: {rel} -> {out.name}")

    write_index()
    if done:
        MANIFEST_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(f"没有需要处理的新文件（跳过 {skipped} 个未变化的 .md）")


if __name__ == "__main__":
    main()
