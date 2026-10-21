---
name: notify
description: 给用户发一条通知（飞书、企业微信、钉钉、Slack、Telegram、Bark，取决于用户配置的渠道）。当用户要求「发个通知」「推送到飞书/企微/钉钉/Slack/Telegram/手机」「告诉我一声」，或需要在长任务的关键节点（完成、失败、需要决策、需要授权）主动提醒用户时使用。也用于排查通知配置问题。
---

# 发送通知

把一条通知推送到用户配置的渠道。纯 Python 标准库实现，无需安装任何依赖。

**你不需要关心渠道。** 发到飞书、企业微信、钉钉、Slack、Telegram 还是 Bark，
由用户配置里的 `channel` 决定；命令和参数完全一样，格式差异由各渠道自己处理。
用户说「发到飞书」而配置的是别的渠道时，照常发送，并在回复里提一句实际渠道（`doctor` 能看到）。

## 脚本位置

脚本在本插件的 `scripts/notify.py`。按以下顺序确定路径：

1. 环境变量可用时：`"${CLAUDE_PLUGIN_ROOT}/scripts/notify.py"`
2. 否则用本 SKILL.md 所在目录向上两级：`<skill 目录>/../../scripts/notify.py`

下文用 `$NOTIFY` 指代该路径。

## 发送通知

```bash
python3 "$NOTIFY" send -t "标题" -s <状态> -m "正文" [-d "补充详情"]
```

参数：

| 参数 | 说明 |
|------|------|
| `-t, --title` | 标题 |
| `-s, --status` | `success` / `failed` / `running` / `decision` / `warning` / `error` / `info`，决定图标（各渠道再映射成自己的颜色） |
| `-m, --message` | 正文，用通用 markdown 写（`**粗体**`、`` `代码` ``、列表、代码块）；渠道不支持的语法会自动降级 |
| `-d, --detail` | 补充详情，显示在分隔线下方 |
| `-c, --color` | 强制指定卡片颜色，**仅飞书生效**，其余渠道忽略 |
| `--session-name` | 覆盖会话名，默认自动从 transcript 的 `ai-title` 记录读取 |
| `--session-id` | 覆盖会话 ID，默认取环境变量 `CLAUDE_CODE_SESSION_ID` |
| `--no-session` | 标题退回项目名，且不附带会话 ID |
| `--dry-run` | 只打印当前渠道的请求体 JSON，不真正发送 |

状态与图标：

| 状态 | 显示 |
|------|------|
| `success` | 🟢 成功 |
| `failed` | 🔴 失败 |
| `running` | 🔵 进行中 |
| `decision` | 🔴 待决策 |
| `warning` | 🟡 警告 |
| `error` | 🔴 异常 |
| `info` | ⚪ 信息 |

通知**标题**会用当前会话名（来自 transcript 的 `ai-title` 记录），会话还没生成标题时退回项目名；
正文下方自动附带项目名、Git 分支、主机名和 session ID 前 8 位（来自 `CLAUDE_CODE_SESSION_ID`）。
这些都不需要手动填。只有在用户明确要求换个称呼、或要求不要暴露会话信息时，
才用 `--session-name` / `--no-session` 覆盖。

## 示例

```bash
# 任务完成
python3 "$NOTIFY" send -t "数据迁移完成" -s success -m "已迁移 12 万条记录，耗时 8 分钟。"

# 构建失败
python3 "$NOTIFY" send -t "CI 构建失败" -s failed \
  -m "**分支** feat/login 编译不通过" \
  -d '```\nerror[E0308]: mismatched types\n  --> src/auth.rs:42\n```'

# 需要用户拍板
python3 "$NOTIFY" send -t "需要你确认" -s decision \
  -m "接口风格选 REST 还是 GraphQL？我倾向 REST，等你一句话。"
```

## 检查配置

```bash
python3 "$NOTIFY" doctor          # 打印当前渠道、配置来源、监听事件、静默时段等
python3 "$NOTIFY" doctor --test   # 顺便发一条测试消息
```

`doctor` 退出码 `2` 表示目的地没配好。引导用户在 `~/.config/claude-hook-notify/config.json`
里选一个渠道并填上该渠道的字段：

| `channel` | 必填字段 | 可选字段 |
|-----------|----------|----------|
| `lark`（默认） | `webhook_url` | `secret` |
| `wecom` | `webhook_url` | |
| `dingtalk` | `webhook_url` | `secret` |
| `slack` | `webhook_url` | |
| `telegram` | `bot_token`、`chat_id` | |
| `bark` | `device_key` | `server`（自建服务器，需同时配 `allowed_hosts`） |

例如 `{"channel": "telegram", "bot_token": "...", "chat_id": "..."}`。
飞书也可以直接用环境变量 `LARK_WEBHOOK_URL`（及 `LARK_WEBHOOK_SECRET`）。

**不要**建议把 URL、令牌或 `channel` 写进项目里的 `.claude/notify.json` —— 该文件会随仓库传播，
所以插件只允许它按名字引用用户配置里已登记的目的地，自带的目的地字段会被忽略并告警。
需要按项目分流时，先在用户配置的 `destinations` 里登记，再在项目配置里写 `{"destination": "名字"}`。

## 注意

- **不要**把真实 webhook URL、bot token、device key 写进仓库里的文件或提交记录。
- 发送失败时脚本返回非 0 并在 stderr 打印原因；hook 模式下则永远返回 0，不会打断会话。
- 目的地只允许 https 且必须是该渠道的官方域名。报错信息里不会出现完整 URL（里面的 token 等同密码），
  所以看到「主机 xxx 不在允许列表内」时不要试图打印 URL 排查，改用 `doctor`。
- 不要为了「显得勤快」而频繁发通知。只在用户明确要求，或任务确实到了值得打扰对方的节点时发。
