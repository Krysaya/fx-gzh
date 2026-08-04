# gzh-fx — 公众号「留白禅意风」自动排版流水线

把写好的 Markdown 文章放进 `gzh/`，触发 GitHub Action 后自动按 **gzh-design「留白禅意风」**（墨绿 `#4A5D52`、超大留白、细线分层）排版，产出可直接粘贴进公众号草稿箱的 HTML。

> 排版动作由**离线 Python 脚本**完成（组件 HTML 内嵌自 gzh-design 主题库），CI 里不需要 AI、不花 API 费用，结果完全确定。

## 一、目录结构

```
gzh-fx/
├── .github/workflows/gzh-format.yml   # GitHub Action（手动 / push 触发）
├── scripts/
│   ├── gzh_format.py                  # 核心排版器（md → 留白禅意风 HTML）
│   ├── validate_gzh_html.py           # 合规校验（0 ERROR / 0 WARNING 才算过）
│   └── wrap_preview.py                # 生成带「复制」按钮的预览页
├── assets/preview-template.html       # 预览页外壳
├── references/
│   ├── theme-zen-whitespace.md        # 留白禅意风组件库（样式参考文档）
│   └── common-components.md           # 通用组件库（代码块/图片/小标签）
├── gzh/                               # ← 你把 .md 源文章放这里
│   ├── .processed.json                # 已处理记录（自动维护，勿手改）
│   ├── config.json                    # 【可选】{"author":"你的名字","bio":"一句话简介"}
│   └── 排版/                           # ← 排版产物输出到这里
│       ├── {名}_排版_留白禅意风(zen-whitespace).html
│       ├── {名}_排版_留白禅意风(zen-whitespace)_预览.html
│       └── 产物清单.json               # 最新产物清单（云函数定位用）
```

## 二、使用流程（云函数取件）

1. **写文章**：把 `.md` 放进 `gzh/`（支持 frontmatter、引言 `>`、`##` 章节、`###` 子标题、`**加粗**`、`==标签==`、`<u>下划线</u>`、`~~荧光笔~~`、`` `行内代码` ``、列表、代码块、图片、表格、`> [!NOTE]` 提示、`【插入…】` 占位）。
2. **触发**：仓库 Actions 页点 **Run workflow**（或 push 到 `gzh/**` 自动触发）。
3. **排版落盘**：Action 跑完把 HTML 提交回 `gzh/排版/`，并更新 `产物清单.json`。
4. **云函数取件**：读 `gzh/排版/产物清单.json`，拿到文件名后拼 raw 直链抓取：
   ```
   https://raw.githubusercontent.com/Krysaya/fx-gzh/main/gzh/排版/<文件名>
   ```
   ⚠️ 中文路径需要 URL 编码，云函数里用 `urllib.parse.quote("gzh/排版/" + 文件名, safe="/")` 再请求。
5. **推草稿箱**：云函数拿 HTML 调公众号接口（需 `appid`/`secret` 换 `access_token`，`draft/add` 草稿接口）推入草稿箱。
6. **清理**：文件是一次性消耗品，推完即可弃。仓库里 `gzh/排版/` 会保留历史产物，可定期手动清理（删除后 push 一次即可）。

## 三、排版规则速记（对应 gzh-design skill）

- 章节 `##` 自动编号 `01 · CHAPTER ONE`，末章若为「结语/总结/尾声」用 `∞ · POSTSCRIPT`。
- 每段自动给 1~3 处关键词加**低饱和墨绿下划线**（优先 `「引号内术语」` 与「数字+量词」）。
- `**加粗**`：前 5 处墨绿锚点加粗，之后普通深色加粗。
- 列表**原文编号原样保留**：`1.2.`、`①`、`a)`、`步骤三：` 等不会被组件编号替换。
- 中文标点自动全角化（中文后紧跟的 `, . ; : ! ?` 与直引号会转全角；代码/URL 不动）。
- 引用 `>`：短文居中衬线金句，长文/多行转左竖条旁注；`> [!NOTE]` 或 `!>` 为墨绿竖条提示块。
- 代码块用深色紧凑风格；`【插入…】` 渲染为居中「待补素材」占位。
- 结尾自动附 END 细线与作者签名（默认 `{{作者名}}`/`{{简介}}` 占位，见下节）。

## 四、作者署名配置

三选一（优先级从高到低）：

1. 仓库根 `gzh/config.json`：
   ```json
   {"author": "老板", "bio": "热衷于分享 iOS 免越狱玩法与认知随笔"}
   ```
2. GitHub Secrets：`GZH_AUTHOR` / `GZH_AUTHOR_BIO`。
3. 都不配 → 保留 `{{作者名}}` / `{{简介}}` 占位，你自己在 HTML 里替换。

## 五、本地调试

```bash
# 处理 gzh/ 下所有新增/改动过的 .md
python3 scripts/gzh_format.py

# 只处理指定文件
python3 scripts/gzh_format.py "gzh/某篇.md"

# 单独校验某份产物
python3 scripts/validate_gzh_html.py "gzh/排版/xxx_排版_留白禅意风(zen-whitespace).html"
```

本地跑完会在 `gzh/排版/` 直接出 HTML，浏览器打开 `_预览.html` 点右上角「复制到公众号」即可手动粘贴。

## 六、改样式

组件模板内嵌在 `scripts/gzh_format.py` 的 `TEMPLATES` 区（逐字取自 `references/theme-zen-whitespace.md`）。改色板/组件请同步改两处，改完本地跑一遍 `validate_gzh_html.py` 确认 0 ERROR / 0 WARNING 再提交。

> 平台红线（校验器强制）：禁用 `<style>/<script>/<div>/class/id`、`position/fixed/float/@media/grid`、外部字体；样式全部内联；所有文字节点用 `<span leaf="">` 包裹。
