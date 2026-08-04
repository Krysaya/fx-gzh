# -*- coding: utf-8 -*-
"""
gzh 云函数：从 GitHub 拉取「留白禅意风」排版产物，推送至公众号草稿箱。

适配：腾讯云 SCF（Python 3.10+），零三方依赖（仅标准库 urllib）。
触发：定时触发器 或 API 网关 均可，入口统一为 main_handler，跑同一套流程。

流程：
  1. 拉取 gzh/排版/产物清单.json
  2. 逐篇：抓 HTML 片段 + 抓源 .md 取标题 + 取摘要
  3. 调微信 draft/add 推草稿箱
  4. （可选，默认开）推完清理 GitHub 上的产物文件并更新清单，实现「用完即弃」

环境变量（SCF 控制台配置）：
  WX_APPID            公众号 AppID                【必填】
  WX_APPSECRET       公众号 AppSecret            【必填】
  GH_OWNER           GitHub 用户名              默认 Krysaya
  GH_REPO            仓库名                    默认 fx-gzh
  GH_BRANCH          分支                      默认 main（以清单为准）
  GH_PAT             GitHub 个人令牌（repo 写权限） 清理产物时用，留空则跳过清理
  WX_AUTHOR          草稿作者名（文章署名）       可选
  WX_THUMB_MEDIA_ID  封面图片 media_id          可选；不填则草稿无封面
  CLEANUP_AFTER_PUSH 推完是否清理 GitHub 产物    默认 true
"""

import os
import re
import json
import base64
import urllib.request
import urllib.parse
import urllib.error

# ----------------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------------
def cfg(key, default=None):
    return os.environ.get(key, default)

WX_APPID = cfg("WX_APPID")
WX_APPSECRET = cfg("WX_APPSECRET")
GH_OWNER = cfg("GH_OWNER", "Krysaya")
GH_REPO = cfg("GH_REPO", "fx-gzh")
GH_BRANCH = cfg("GH_BRANCH", "main")
GH_PAT = cfg("GH_PAT", "")
WX_AUTHOR = cfg("WX_AUTHOR", "")
WX_THUMB_MEDIA_ID = cfg("WX_THUMB_MEDIA_ID", "")
CLEANUP = str(cfg("CLEANUP_AFTER_PUSH", "true")).lower() == "true"

PRODUCT_INDEX_PATH = "gzh/排版/产物清单.json"
ARTICLE_DIR = "gzh/排版"


# ----------------------------------------------------------------------------
# HTTP 工具（标准库，零依赖）
# ----------------------------------------------------------------------------
def _get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")

def _get_json(url, headers=None, timeout=20):
    return json.loads(_get(url, headers, timeout))

def _post_json(url, payload, timeout=20):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ----------------------------------------------------------------------------
# 微信公众号
# ----------------------------------------------------------------------------
def get_access_token():
    url = ("https://api.weixin.qq.com/cgi-bin/token"
           "?grant_type=client_credential"
           f"&appid={WX_APPID}&secret={WX_APPSECRET}")
    resp = _get_json(url)
    if "access_token" not in resp:
        raise RuntimeError(f"获取 access_token 失败: {resp}")
    return resp["access_token"]


def add_draft(access_token, title, content, digest, author=""):
    """调用草稿箱接口 draft/add，返回 media_id。"""
    url = ("https://api.weixin.qq.com/cgi-bin/draft/add"
           f"?access_token={access_token}")
    article = {
        "title": title,
        "author": author or "",
        "digest": digest or "",
        "content": content,            # 直接传留白禅意风 <section> 片段
        "content_source_url": "",
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    if WX_THUMB_MEDIA_ID:
        article["thumb_media_id"] = WX_THUMB_MEDIA_ID
    resp = _post_json(url, {"articles": [article]})
    if resp.get("errcode", 0) != 0:
        raise RuntimeError(f"draft/add 失败: {resp}")
    return resp.get("media_id")


# ----------------------------------------------------------------------------
# GitHub raw 直链（中文/括号/空格必须 URL 编码）
# ----------------------------------------------------------------------------
def raw_url(path, branch=None):
    b = branch or GH_BRANCH
    enc = "/".join(urllib.parse.quote(p, safe="") for p in path.split("/"))
    return (f"https://raw.githubusercontent.com/{GH_OWNER}/{GH_REPO}/"
            f"{b}/{enc}")


def stem_of(file_name):
    """样例-留白禅意风_排版_留白禅意风(zen-whitespace).html -> 样例-留白禅意风"""
    return re.sub(r"_排版_留白禅意风\(zen-whitespace\)\.html$", "", file_name)


def extract_title(md_text, fallback):
    m = re.search(r"^#\s+(.+)$", md_text, re.MULTILINE)
    return m.group(1).strip() if m else fallback


def html_to_text(html):
    t = re.sub(r"<style[\s\S]*?</style>", "", html)
    t = re.sub(r"<[^>]+>", "", t)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip()


def make_digest(html, n=54):
    """摘要取纯文本前 54 字（微信摘要上限 120 字）。"""
    return html_to_text(html)[:n]


# ----------------------------------------------------------------------------
# GitHub 清理（可选，需 GH_PAT 具备 repo 写权限）
# ----------------------------------------------------------------------------
def _gh_headers():
    return {"Authorization": f"Bearer {GH_PAT}",
            "Accept": "application/vnd.github+json"}

def gh_get_meta(path, branch):
    url = (f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/"
           f"{urllib.parse.quote(path, safe='')}?ref={branch}")
    return _get_json(url, _gh_headers())

def gh_delete(path, sha, branch, msg="chore: 云函数推送后清理排版产物"):
    url = (f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/"
           f"{urllib.parse.quote(path, safe='')}")
    payload = {"message": msg, "sha": sha, "branch": branch}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers=_gh_headers(), method="DELETE")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def gh_update_index(index_obj, branch):
    path = PRODUCT_INDEX_PATH
    meta = gh_get_meta(path, branch)
    sha = meta["sha"]
    content = base64.b64encode(
        json.dumps(index_obj, ensure_ascii=False, indent=2).encode()).decode()
    url = (f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/"
           f"{urllib.parse.quote(path, safe='')}")
    payload = {"message": "chore: 清理已推送产物清单",
               "sha": sha, "branch": branch, "content": content}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers=_gh_headers(), method="PUT")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
def run():
    if not WX_APPID or not WX_APPSECRET:
        raise RuntimeError("缺少 WX_APPID / WX_APPSECRET 环境变量")

    # 1. 拉产物清单
    index = _get_json(raw_url(PRODUCT_INDEX_PATH))
    entries = index.get("entries", []) or []
    if not entries:
        return {"ok": True, "pushed": 0, "msg": "无新产物"}
    branch = index.get("branch", GH_BRANCH)

    # 2. 逐篇推送
    token = get_access_token()
    pushed, pushed_files = [], set()
    for e in entries:
        fname = e["file"]
        stem = stem_of(fname)
        html = _get(raw_url(f"{ARTICLE_DIR}/{fname}", branch))

        # 标题：优先源 .md 首行 # 标题
        title = stem
        try:
            md = _get(raw_url(f"gzh/{stem}.md", branch))
            title = extract_title(md, stem)
        except Exception as ex:
            print(f"[warn] 取源 md 标题失败，用文件名兜底: {ex}")

        digest = make_digest(html)
        media_id = add_draft(token, title, html, digest, author=WX_AUTHOR)
        pushed.append({"title": title, "media_id": media_id, "file": fname})
        pushed_files.add(fname)
        print(f"[ok] 已推送草稿: {title} -> {media_id}")

        # 3. 清理 GitHub 上的产物（用完即弃）
        if CLEANUP and GH_PAT:
            for p in (f"{ARTICLE_DIR}/{fname}",
                      f"{ARTICLE_DIR}/{e.get('preview', '')}"):
                if not p or p.endswith("/"):
                    continue
                try:
                    meta = gh_get_meta(p, branch)
                    gh_delete(p, meta["sha"], branch)
                    print(f"[ok] 已清理: {p}")
                except Exception as ex:
                    print(f"[warn] 清理失败 {p}: {ex}")

    # 4. 更新产物清单，移除已推送项
    if CLEANUP and GH_PAT and pushed:
        remaining = [e for e in entries if e["file"] not in pushed_files]
        new_index = {"count": len(remaining),
                     "branch": branch, "entries": remaining}
        try:
            gh_update_index(new_index, branch)
            print(f"[ok] 清单已更新，剩余 {len(remaining)} 篇")
        except Exception as ex:
            print(f"[warn] 更新清单失败: {ex}")

    return {"ok": True, "pushed": len(pushed), "items": pushed}


def main_handler(event, context):
    """SCF 入口：定时触发与 API 网关触发共用。"""
    try:
        result = run()
        return {"statusCode": 200,
                "body": json.dumps(result, ensure_ascii=False)}
    except Exception as ex:
        return {"statusCode": 500,
                "body": json.dumps({"ok": False, "error": str(ex)},
                                   ensure_ascii=False)}


# 本地调试：python3 index.py（需先 export 环境变量）
if __name__ == "__main__":
    import sys
    out = main_handler({}, None)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0 if out["statusCode"] == 200 else 1)
