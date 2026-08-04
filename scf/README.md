# 云函数：排版产物 → 公众号草稿箱

把 GitHub 上 `gzh/排版/` 里的「留白禅意风」HTML 自动推送至微信公众号**草稿箱**。
代码：`index.py`（Python 3，零三方依赖，纯标准库）。

## 部署（腾讯云 SCF）

1. 新建函数 → 运行环境选 **Python 3.10+** → 上传方式「本地上传文件夹」，选本目录 `scf/`。
2. 执行方法填 `index.main_handler`。
3. 函数配置 → 环境变量，按下表填：

| 变量 | 必填 | 说明 | 默认 |
|------|------|------|------|
| `WX_APPID` | ✅ | 公众号 AppID | — |
| `WX_APPSECRET` | ✅ | 公众号 AppSecret | — |
| `GH_OWNER` | | GitHub 用户名 | `Krysaya` |
| `GH_REPO` | | 仓库名 | `fx-gzh` |
| `GH_BRANCH` | | 分支（以清单为准，可不改） | `main` |
| `GH_PAT` | 清理用 | GitHub 令牌，需 `repo` 写权限；**留空则跳过清理** | 空 |
| `WX_AUTHOR` | | 草稿作者署名 | 空 |
| `WX_THUMB_MEDIA_ID` | | 封面 media_id；不填则草稿无封面 | 空 |
| `CLEANUP_AFTER_PUSH` | | 推完是否删 GitHub 产物 | `true` |

4. 触发器：
   - **定时**：建「定时触发器」，如 `0 */30 * * * *`（每 30 分钟）。
   - **手动**：建「API 网关」触发器，给一个 URL，想推时访问一下即可。
   两种入口都走同一个 `main_handler`，逻辑一致。

## 流程

1. 拉 `gzh/排版/产物清单.json`
2. 逐篇：抓 HTML 片段 + 抓 `gzh/{名}.md` 取 `# 标题` + 取前 54 字作摘要
3. 调微信 `draft/add` 推草稿箱
4. （默认开）推完删 GitHub 上的 HTML + 预览页，并更新清单 → **用完即弃，不重复推**

## 注意事项

- **封面**：草稿箱允许无封面。要封面需先调 `material/add_material` 上传图拿到
  `media_id`，再配 `WX_THUMB_MEDIA_ID`。
- **不清理也行**：若想保留 GitHub 上的排版产物（比如还要人工复核），
  设 `CLEANUP_AFTER_PUSH=false`，并自己保证云函数不会重复推送
  （此时需另建去重机制，如把已推记录存 COS）。
- **首次联调**：本地 `export` 上述变量后 `python3 index.py` 即可跑（需联网）。

## 迁移到其他云

核心逻辑在 `run()`，是纯标准库、与平台无关。换平台只需改入口函数名：
- 阿里云 FC：把 `main_handler(event, context)` 改为 `handler(event, context)`。
- Cloudflare Workers：需改写为 JS（Workers 非 Python），HTTP 调用逻辑等价迁移。
