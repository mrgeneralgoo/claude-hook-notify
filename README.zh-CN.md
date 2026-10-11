# claude-hook-notify

[English](README.md) | **简体中文**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](#运行要求)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#运行要求)

一个 [Claude Code](https://code.claude.com) 插件：Claude 完成任务、需要你授权、或在等你输入时，给你发一条通知。
支持 **飞书 / Lark、企业微信、钉钉、Slack、Telegram、Bark**。

通知内容只生成一次，在每个渠道上都一样；渠道只负责怎么排版、怎么发送。换渠道只需改一行配置。

> 本项目原名 `claude-hook-lark`，现有配置无需修改即可继续使用，见[从 claude-hook-lark 升级](#从-claude-hook-lark-升级)。

## 目录

- [特性](#特性)
- [支持的渠道](#支持的渠道)
- [运行要求](#运行要求)
- [安装](#安装)
- [配置](#配置)
- [使用](#使用)
- [安全](#安全)
- [故障排查](#故障排查)
- [从 claude-hook-lark 升级](#从-claude-hook-lark-升级)
- [开发](#开发)
- [许可证](#许可证)

## 特性

- **六个渠道，一个配置项**：改 `channel`，同一条通知就发到别处。
- **自动通知**：任务完成、需要授权、等待输入时，通过 Claude Code hook 自动推送。
- **手动通知**：内置 `notify` skill（「迁移跑完了告诉我一声」），也可以在命令行调用。
- **内容有用**：标题是会话名，一个项目并行跑多个任务也能一眼分清；正文含你的提问、Claude 的回复、工具调用次数、耗时、项目、Git 分支、主机和会话 ID。
- **不吵人**：事件白名单、静默时段、最短耗时过滤。
- **零依赖**：只用 Python 标准库，不需要 `pip install`、`jq` 或 `curl`。
- **默认安全**：仓库里的配置文件无法决定通知发往哪里，见[安全](#安全)。
- **不拖慢会话**：hook 有 9 秒时间预算，出任何问题都安静退出。

示例（飞书卡片；其他渠道内容相同，排版随平台）：

```
┌────────────────────────────────────────────┐
│ ✅ 任务完成 · 重构登录模块                    │  ← 标题用会话名
├────────────────────────────────────────────┤
│ Claude Code 已完成本轮任务                   │
│ 📋 本轮任务                                 │
│ 把登录接口改成 JWT，顺便补一下测试             │
│ 📝 完成情况                                 │
│ ## 改了什么                                 │
│ - 换成 JWT 签发                              │
│ - 补了 12 个测试                             │
│ 🔧 19 次工具调用 · ⏱️ 用时 6 分 31 秒         │
├────────────────────────────────────────────┤
│ 项目 my-project        分支 feat/jwt        │
│ 主机 dev-macbook       会话 ID 3f2a9c10-…   │
├────────────────────────────────────────────┤
│ Claude Code · Stop · 2026-08-23 00:39       │
└────────────────────────────────────────────┘
```

## 支持的渠道

| `channel` | 平台 | 必填字段 | 可选字段 | 呈现方式 |
|-----------|------|----------|----------|----------|
| `lark`（默认） | 飞书 / Lark 自定义机器人 | `webhook_url` | `secret`（签名校验） | 卡片（schema 2.0），标题栏按状态上色 |
| `wecom` | 企业微信群机器人 | `webhook_url` | | Markdown |
| `dingtalk` | 钉钉群机器人 | `webhook_url` | `secret`（加签） | Markdown |
| `slack` | Slack Incoming Webhook | `webhook_url` | | Block Kit |
| `telegram` | Telegram Bot | `bot_token`、`chat_id` | | 纯文本 |
| `bark` | Bark（iOS 推送） | `device_key` | `server`（自建服务器） | 系统推送 |

每个渠道只允许发往其官方域名。使用自建 Bark 服务器或代理时，在用户配置的 `allowed_hosts` 里加上对应主机。

## 运行要求

- 支持插件的 Claude Code
- Python 3.9 及以上（`PATH` 中有 `python3`）
- macOS 或 Linux，暂不支持 Windows

## 安装

### 1. 安装插件

在 Claude Code 里执行：

```
/plugin marketplace add mrgeneralgoo/claude-hook-notify
/plugin install claude-hook-notify
```

### 2. 选择渠道

创建用户配置文件：

```bash
mkdir -p ~/.config/claude-hook-notify && chmod 700 ~/.config/claude-hook-notify
$EDITOR ~/.config/claude-hook-notify/config.json
chmod 600 ~/.config/claude-hook-notify/config.json
```

写入**一个**目的地，按你的渠道选一行：

```jsonc
// 飞书 / Lark（不写 channel 时默认就是飞书）
{"channel": "lark", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx", "secret": ""}

// 企业微信
{"channel": "wecom", "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx"}

// 钉钉
{"channel": "dingtalk", "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxxx", "secret": "SECxxxx"}

// Slack
{"channel": "slack", "webhook_url": "https://hooks.slack.com/services/T000/B000/xxxx"}

// Telegram（chat_id 要写成字符串）
{"channel": "telegram", "bot_token": "123456:ABC-xxxx", "chat_id": "123456789"}

// Bark
{"channel": "bark", "device_key": "xxxxxxxxxxxxxxxx"}
```

飞书也可以只用环境变量：

```bash
export LARK_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
export LARK_WEBHOOK_SECRET="..."   # 开启签名校验时才需要
```

> ⚠️ Webhook URL、bot token、device key 都是凭据，**不要提交到仓库**。

### 3. 验证

```bash
python3 scripts/notify.py doctor --test
```

`doctor` 会打印当前渠道和各项配置的来源，`--test` 会发一条测试消息。收到就说明配好了。

## 配置

用户配置位于 `~/.config/claude-hook-notify/config.json`，完整示例见 [config.example.json](config.example.json)。

### 配置项

| 键 | 默认值 | 说明 |
|----|--------|------|
| `channel` | `"lark"` | 通知渠道，见[支持的渠道](#支持的渠道) |
| 渠道字段 | — | 按渠道填写 `webhook_url`、`secret`、`bot_token`、`chat_id`、`device_key`、`server` |
| `destinations` | `{}` | 具名目的地表，每项是一个带 `channel` 和字段的对象 |
| `destination` | — | 选用 `destinations` 里的哪一项 |
| `events` | `["Stop", "Notification"]` | 哪些 hook 事件触发通知；`[]` 表示一个都不发 |
| `include_summary` | `true` | 是否包含你的提问和 Claude 的回复；设为 `false` 只发元信息 |
| `min_duration_seconds` | `0` | 本轮耗时低于该值就不推送 |
| `quiet_hours` | `null` | 静默时段，如 `[22, 8]` 表示 22:00–08:00 不打扰 |
| `timeout` | `5` | 发送超时（秒） |
| `allowed_hosts` | 当前渠道的官方域名 | 整体替换主机白名单，只有自建服务器或代理时才需要 |
| `debug` | `false` | 把详细日志写到 `~/.config/claude-hook-notify/debug.log` |

配置会被严格校验。隐私或过滤类配置写错时按最严格的方式处理（例如 `quiet_hours` 格式不对就当作「一直静默」），并由 `doctor` 打印告警。

### 切换渠道

改 `channel` 和对应字段即可，其他配置不用动。经常切换的话，可以登记多个目的地，再选一个：

```json
{
  "destination": "手机",
  "destinations": {
    "值班群": {"channel": "lark", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/aaaa"},
    "手机": {"channel": "bark", "device_key": "xxxxxxxx"}
  }
}
```

不发送、只预览当前渠道会收到的内容：

```bash
python3 scripts/notify.py send -t "预览" -s info -m "hello" --dry-run
```

### 项目级配置

项目可以添加 `.claude/notify.json`，按名字选用已登记的目的地，并把行为收得更严：

```json
{"destination": "值班群", "events": ["Stop"]}
```

这个文件可以放心提交。它**不能**包含 URL、令牌、`channel`、`destinations`、`allowed_hosts` 或 `debug` —— 写了会被忽略并告警。行为类配置只能收窄：

| 键 | 合并方式 |
|----|----------|
| `events` | 与用户配置取交集 |
| `include_summary` | 只能由 `true` 改为 `false` |
| `min_duration_seconds` | 取较大值 |
| `timeout` | 取较小值 |
| `quiet_hours` | 仅在用户未设置时生效 |

### 目的地从哪里来

优先级从低到高：

1. 用户配置 `~/.config/claude-hook-notify/config.json`
2. `CLAUDE_HOOK_NOTIFY_CONFIG` 指向的文件（完全取代用户配置里的目的地）
3. 项目 `.claude/notify.json` 里的 `destination`（只能按名字引用）
4. 环境变量 `LARK_WEBHOOK_URL` / `LARK_WEBHOOK_SECRET`
5. 命令行 `--webhook`

显式指定的来源出问题（文件不存在、JSON 非法、引用了未登记的名字、未知渠道）时会停止发送，而不是退回别的目的地。

## 使用

### 自动通知

| 事件 | 触发时机 | 通知 | 默认开启 |
|------|----------|------|:--------:|
| `Stop` | Claude 完成一轮任务 | ✅ 任务完成 | ✔ |
| `Notification` | 需要授权，或等待输入超时 | 🔐 需要授权 · ⏳ 等待输入 | ✔ |
| `SubagentStop` | 子任务（subagent）结束 | 📦 子任务完成 | |
| `SessionEnd` | 会话退出 | 👋 会话结束 | |

四个 hook 都由插件注册，实际发不发由 `events` 决定；修改后立即生效，无需重装。

### 手动通知

直接跟 Claude 说，比如「构建跑完了通知我」，它会调用内置的 `notify` skill。

在终端里：

```bash
# 定位安装后的脚本
NOTIFY=$(find ~/.claude/plugins -name notify.py -path '*claude-hook-notify*' | head -1)

python3 "$NOTIFY" send -t "数据迁移完成" -s success -m "已迁移 12 万条记录。"
python3 "$NOTIFY" send -t "CI 构建失败" -s failed -m "**分支** feat/login 编译不通过" \
                       -d "error[E0308]: mismatched types"
python3 "$NOTIFY" send -t "需要确认" -s decision -m "REST 还是 GraphQL？"
```

| 参数 | 说明 |
|------|------|
| `-t, --title` | 标题 |
| `-s, --status` | `success`、`failed`、`running`、`decision`、`warning`、`error`、`info`（✅ ❌ ⏳ 🤔 ⚠️ ⚠️ 💬）；支持颜色的渠道还会按状态上色 |
| `-m, --message` | 正文，用 Markdown 书写；渠道不支持的语法会自动简化 |
| `-d, --detail` | 补充详情，显示在分隔线下方 |
| `-c, --color` | 强制指定卡片颜色（仅飞书） |
| `--session-name`、`--session-id` | 覆盖自动识别的会话名或会话 ID |
| `--no-session` | 标题改用项目名，且不附带会话 ID |
| `--dry-run` | 打印当前渠道的请求体，不实际发送 |

## 安全

使用前有两点需要知道：

**通知默认包含你的提问和 Claude 的回复。** 你在对话里粘贴过的密钥、令牌、客户数据都可能随通知进入群聊或手机。设置 `"include_summary": false` 后只发元信息（项目、分支、会话名、耗时）。

**仓库无法改变通知的去向。** `.claude/notify.json` 会随 `git clone` 进入你的机器。如果它能决定发到哪里，克隆任何第三方仓库都可能把你的会话内容发给仓库作者。因此目的地（渠道和全部凭据字段）只从用户配置和环境变量读取。

此外：

- 请求只发往该渠道白名单内主机的 HTTPS 地址。
- 错误信息和日志中永远不出现 URL、令牌或远端返回的文本。
- Telegram 的 bot token、chat ID 和 Bark 的 device key 使用前会校验格式，畸形值无法把请求导向别处。

每条规则的来由见 [docs/DESIGN.md](docs/DESIGN.md)。

## 故障排查

```bash
python3 scripts/notify.py doctor         # 渠道、配置来源、监听事件、静默时段、告警
python3 scripts/notify.py doctor --test  # 并发送一条测试消息
```

收不到通知时按顺序排查：

1. 运行 `doctor`，检查渠道是否正确、必填字段是否显示为 `(未配置)`、有没有 ⚠️ 告警。
2. 设置 `"debug": true`，触发一轮任务，查看 `~/.config/claude-hook-notify/debug.log`。发送失败的记录无论 `debug` 开关都会写入。
3. 单独验证目的地。以飞书为例：
   ```bash
   curl -X POST "$LARK_WEBHOOK_URL" -H "Content-Type: application/json" \
     -d '{"msg_type":"text","content":{"text":"test"}}'
   ```
   返回 `{"code":0,...}` 才算通。`code: 19021` 表示签名错误或时间戳偏差超过 1 小时。
4. 在 Claude Code 里运行 `/plugin`，确认 claude-hook-notify 已启用。

**hook 会拖慢会话吗？** 不会。每个 hook 有 9 秒内部预算和看门狗，出任何问题都以 0 退出；插件清单另有 15 秒硬超时兜底。

## 从 claude-hook-lark 升级

0.3.0 起项目改名。现有配置无需修改即可继续使用：

| 旧 | 新 | 旧名是否仍可用 |
|----|----|:-------------:|
| `~/.config/claude-hook-lark/config.json` | `~/.config/claude-hook-notify/config.json` | ✔（新文件不存在时读取，`doctor` 会提示迁移） |
| `CLAUDE_HOOK_LARK_CONFIG` | `CLAUDE_HOOK_NOTIFY_CONFIG` | ✔ |
| `.claude/lark.json` | `.claude/notify.json` | ✔（新文件不存在时读取） |
| `webhooks` / `webhook` | `destinations` / `destination` | ✔ |
| 没有 `channel` 键 | `"channel": "lark"` | ✔（缺省即飞书） |
| `LARK_WEBHOOK_URL` 等环境变量 | 不变 | ✔ |
| `scripts/lark_notify.py`、skill `lark-notify` | `scripts/notify.py`、skill `notify` | ✘ |

插件本身需要重新安装：

```
/plugin uninstall claude-hook-lark
/plugin marketplace add mrgeneralgoo/claude-hook-notify
/plugin install claude-hook-notify
```

## 开发

运行测试（无需依赖；约 15 秒，其中两个用例会等待看门狗触发）：

```bash
python3 -m unittest discover -s tests -v
```

### 目录结构

```
scripts/notify.py              # hook / send / doctor 命令、配置加载、统一的 HTTPS 发送
scripts/notify_channels/       # 每个渠道一个模块，以及 Message/Channel 契约（base.py）
skills/notify/SKILL.md         # Claude 用来发通知的 skill
.claude-plugin/plugin.json     # 插件清单与 hook 注册
docs/DESIGN.md                 # 设计说明
```

### 新增渠道

1. 新建 `scripts/notify_channels/<name>.py`，写一个 `Channel` 子类，设置 `name`、`label`、`default_hosts`、`required`、`optional`，并实现：
   - `render(msg)` —— 把 `Message` 渲染成请求体
   - `request(dest, body)` —— 返回最终 URL 和请求体，需要签名的在这里加
   - `check(status, parsed, raw)` —— 判定成败；返回值里不得包含任何远端文本
2. 导出 `CHANNEL = YourChannel()`，并在 `scripts/notify_channels/__init__.py` 中登记。
3. 在 `tests/test_channels.py` 的注册表用例里加上渠道名，并为它的 `request()` 和 `check()` 补测试。跨渠道的渲染、长度上限、凭据泄漏用例会遍历所有已注册渠道，自动覆盖新渠道。

新渠道的凭据字段会自动被排除在项目配置之外；HTTP 发送、超时和错误脱敏由 `notify.post()` 统一处理。

欢迎提 Issue 和 PR，改动请附带回归用例。版本变更见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

[MIT](LICENSE)
