# claude-hook-notify

把 **Claude Code** 的任务完成事件推送到你选择的渠道 ——
**飞书 / Lark、企业微信、钉钉、Slack、Telegram、Bark** ——
并把「发通知」封装成一个可以手动调用的 skill。

> 本项目原名 `claude-hook-lark`。旧的配置路径、环境变量和 `.claude/lark.json` 仍然可以用，见[从 claude-hook-lark 升级](#从-claude-hook-lark-升级)。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](#开发)
[![deps](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#开发)

- 🧩 标准 Claude Code plugin，`/plugin` 一键安装
- 🔀 **换渠道只改一行配置**，通知内容不变 —— 格式差异由各渠道自己处理
- 🔔 任务完成 / 需要授权 / 等待输入时自动推送
- 🛠️ 附带 `notify` skill，也可以随时让 Claude 主动给你发一条
- 🪶 **零第三方依赖**，只用 Python 标准库，不需要 `pip install`，也不需要 `jq`
- 🏷️ 标题用**会话名**而不是项目名 —— 一个项目并行跑多个任务时，一眼就知道是哪件事
- 🔕 支持静默时段、最短耗时过滤、事件白名单，不吵人
- 🔒 仓库里的配置文件**不能**指定通知目的地（见[安全设计](#安全设计)）

```
┌────────────────────────────────────────────┐
│ ✅ 任务完成 · 重构登录模块                    │  ← 标题用会话名
├────────────────────────────────────────────┤
│ Claude Code 已完成本轮任务                   │
│ 📋 本轮任务                                 │
│ 把登录接口改成 JWT，顺便补一下测试             │
│ 📝 完成情况                                 │
│ ## 改了什么          ← 标题、列表、代码块      │
│ - 换成 JWT 签发         按渠道能力渲染         │
│ - 补了 12 个测试                             │
│ 🔧 19 次工具调用 · ⏱️ 用时 6 分 31 秒         │
├────────────────────────────────────────────┤
│ 项目 my-project        分支 feat/jwt        │
│ 主机 dev-macbook       会话 ID 3f2a9c10-…   │
├────────────────────────────────────────────┤
│ Claude Code · Stop · 2026-08-23 00:39       │
└────────────────────────────────────────────┘
          （图为飞书卡片；其他渠道内容相同，排版随平台）
```

---

## 支持的渠道

| `channel` | 平台 | 必填字段 | 可选字段 | 呈现方式 |
|-----------|------|----------|----------|----------|
| `lark`（默认） | 飞书 / Lark 自定义机器人 | `webhook_url` | `secret`（签名校验） | 卡片 schema 2.0，标题栏按状态上色 |
| `wecom` | 企业微信群机器人 | `webhook_url` | | markdown 消息 |
| `dingtalk` | 钉钉群机器人 | `webhook_url` | `secret`（加签） | markdown 消息 |
| `slack` | Slack Incoming Webhook | `webhook_url` | | Block Kit |
| `telegram` | Telegram Bot | `bot_token`、`chat_id` | | 纯文本（避免 MarkdownV2 转义失败被拒） |
| `bark` | Bark（iOS 推送） | `device_key` | `server`（自建服务器） | 系统推送 |

每个渠道只允许发往它的官方域名（自建 Bark 或代理需在用户配置里加 `allowed_hosts`）。

**新增渠道**：在 `scripts/notify_channels/` 下写一个模块，实现 `render` / `request` / `check`
三个方法，再登记到 `notify_channels/__init__.py`。契约见
[`notify_channels/base.py`](scripts/notify_channels/base.py)，HTTP 发送、超时、错误脱敏都由框架统一处理。

---

## 快速开始

### 1. 安装插件

在 Claude Code 里执行：

```
/plugin marketplace add mrgeneralgoo/claude-hook-notify
/plugin install claude-hook-notify
```

### 2. 选一个渠道并配置

```bash
mkdir -p ~/.config/claude-hook-notify && chmod 700 ~/.config/claude-hook-notify
$EDITOR ~/.config/claude-hook-notify/config.json
chmod 600 ~/.config/claude-hook-notify/config.json
```

写入**一个**目的地，例如：

```jsonc
// 飞书（不写 channel 时默认就是飞书）
{"channel": "lark", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx", "secret": ""}

// 企业微信
{"channel": "wecom", "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx"}

// 钉钉
{"channel": "dingtalk", "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxxx", "secret": "SECxxxx"}

// Slack
{"channel": "slack", "webhook_url": "https://hooks.slack.com/services/T000/B000/xxxx"}

// Telegram
{"channel": "telegram", "bot_token": "123456:ABC-xxxx", "chat_id": "123456789"}   // chat_id 要写成字符串

// Bark
{"channel": "bark", "device_key": "xxxxxxxxxxxxxxxx"}
```

完整示例见 [config.example.json](config.example.json)。飞书也可以只用环境变量：

```bash
export LARK_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
export LARK_WEBHOOK_SECRET="..."   # 开启签名校验时才需要
```

> ⚠️ Webhook URL、bot token、device key 都等同于密码，**不要提交到仓库**。

### 3. 验证

```bash
python3 scripts/notify.py doctor --test
```

收到测试消息就说明配好了。

---

## 切换渠道

通知内容由插件统一生成，渠道只负责「怎么呈现、怎么发」。所以换渠道只需要改 `channel`
和该渠道的字段，其余配置（事件、静默时段、摘要开关……）原样保留。

想在几个渠道之间来回切，可以把它们都登记成**具名目的地**，再用 `destination` 选一个：

```json
{
  "destination": "手机",
  "destinations": {
    "值班群": {"channel": "lark", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/aaaa"},
    "手机":   {"channel": "bark", "device_key": "xxxxxxxx"}
  }
}
```

用 `--dry-run` 可以看到同一条通知在当前渠道下的实际请求体：

```bash
python3 scripts/notify.py send -t "预览" -s info -m "hello" --dry-run
```

---

## 手动发通知

安装后直接跟 Claude 说「跑完了发个通知给我」，它会调用 `notify` skill。
也可以在终端直接用：

```bash
# 安装后脚本在 ~/.claude/plugins/cache/ 下，用这条命令定位：
NOTIFY=$(find ~/.claude/plugins -name notify.py -path '*claude-hook-notify*' | head -1)

python3 "$NOTIFY" send -t "数据迁移完成" -s success -m "已迁移 12 万条记录。"
python3 "$NOTIFY" send -t "CI 构建失败" -s failed -m "**分支** feat/login 编译不通过" \
                       -d "error[E0308]: mismatched types"
python3 "$NOTIFY" send -t "需要确认" -s decision -m "REST 还是 GraphQL？"
python3 "$NOTIFY" send -t "预览" -s info -m "hello" --dry-run   # 只打印，不发送
```

状态 `-s`：`success` `failed` `running` `decision` `warning` `error` `info`，
分别对应 ✅ ❌ ⏳ 🤔 ⚠️ ⚠️ 💬；有颜色能力的渠道（飞书卡片、企业微信字体色）会再按状态上色。
`-c` 可强制指定飞书卡片颜色（blue、wathet、turquoise、green、yellow、orange、red、carmine、violet、purple、indigo、grey），其余渠道忽略。

通知标题用**会话名**（取自 Claude Code 自动生成、你也能手动改的那个会话标题），
会话还没生成标题时退回项目名。正文下方自动带上项目、Git 分支、主机名和完整 session ID。
用 `--session-name` / `--session-id` 覆盖，`--no-session` 完全不带会话信息。

---

## 支持的事件

| 事件 | 触发时机 | 通知 | 默认开启 |
|------|----------|------|:--------:|
| `Stop` | Claude 完成一轮任务 | ✅ 任务完成 | ✔ |
| `Notification` | 需要授权 / 等待输入超时 | 🔐 需要授权 · ⏳ 等待输入 | ✔ |
| `SubagentStop` | 子任务（subagent）结束 | 📦 子任务完成 | ✘ |
| `SessionEnd` | 会话退出 | 👋 会话结束 | ✘ |

四种 hook 都已在 `plugin.json` 里注册，实际发不发由配置里的 `events` 决定，改配置不用重装。
只要「任务完成」就写 `{"events": ["Stop"]}`。

> `"events": []` 表示**一个都不发**，而不是「用默认值」。只有这个键完全缺失时才套用默认值。

---

## 配置项

| 键 | 默认值 | 说明 |
|----|--------|------|
| `channel` | `"lark"` | 通知渠道，见[支持的渠道](#支持的渠道) |
| 渠道字段 | — | `webhook_url`、`secret`、`bot_token`、`chat_id`、`device_key`、`server`，按渠道填 |
| `destinations` | `{}` | 具名目的地表，每项是一个带 `channel` 的目的地（旧名 `webhooks`） |
| `destination` | — | 选用 `destinations` 里的哪一项（旧名 `webhook`） |
| `events` | `["Stop", "Notification"]` | 哪些事件触发推送 |
| `include_summary` | `true` | 是否把任务内容和完成情况写进通知 |
| `min_duration_seconds` | `0` | 本轮耗时低于该值就不推送，过滤掉几秒钟的琐碎问答 |
| `quiet_hours` | `null` | 静默时段，如 `[22, 8]` 表示 22:00–08:00 不打扰（跨零点自动处理） |
| `timeout` | `5` | 发送超时（秒） |
| `allowed_hosts` | 当前渠道的官方域名 | 允许发往的主机白名单（整体替换），自建 Bark / 代理时才需要改 |
| `debug` | `false` | 写详细日志到 `~/.config/claude-hook-notify/debug.log` |

配置来源优先级从高到低：命令行 `--webhook` > 环境变量 `LARK_WEBHOOK_URL` >
项目级 `.claude/notify.json`（只能收窄）> `CLAUDE_HOOK_NOTIFY_CONFIG` 指向的文件 > 用户级配置。

### 按项目分流

先在**用户配置**里登记目的地：

```json
{
  "channel": "lark",
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/默认",
  "destinations": {
    "值班群": {"channel": "wecom", "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=aaaa"}
  }
}
```

再在项目的 `.claude/notify.json` 里**按名字引用**（这个文件可以安全地提交）：

```json
{ "destination": "值班群", "events": ["Stop"] }
```

项目配置只能引用已登记的名字、并把行为收窄，**不能自带 URL、令牌或渠道**。原因见下。

---

## 从 claude-hook-lark 升级

0.3.0 起项目改名为 claude-hook-notify。现有配置**不用改也能继续工作**：

| 旧 | 新 | 旧的还认吗 |
|----|----|:---:|
| `~/.config/claude-hook-lark/config.json` | `~/.config/claude-hook-notify/config.json` | ✔ 新路径不存在时读取，`doctor` 会提示迁移 |
| `CLAUDE_HOOK_LARK_CONFIG` | `CLAUDE_HOOK_NOTIFY_CONFIG` | ✔ |
| `.claude/lark.json` | `.claude/notify.json` | ✔ 新文件不存在时读取 |
| `webhooks` / `webhook` | `destinations` / `destination` | ✔ |
| 没有 `channel` 键 | `"channel": "lark"` | ✔ 缺省即飞书 |
| `LARK_WEBHOOK_URL` 等环境变量 | 不变 | ✔ |
| `scripts/lark_notify.py`、skill `lark-notify` | `scripts/notify.py`、skill `notify` | ✘ |

插件本身需要重新安装：`/plugin uninstall claude-hook-lark` 后按[快速开始](#1-安装插件)装新名字。

---

## 安全设计

两点是使用前该知道的：

**通知默认会把你的原始提问和 Claude 的回复发出去。** 如果你在对话里粘贴过密钥、令牌、客户数据，
它们会随通知进入群聊或手机并留在消息记录里。需要时用 `{"include_summary": false}` 关掉，
通知就只剩项目、分支、会话名和耗时这些元信息。

**仓库里的 `.claude/notify.json` 不能指定通知目的地。** 它会随 `git clone` 进入你的机器 ——
如果它能决定「发到哪」，克隆任意第三方仓库都可能让插件把你的会话内容发往仓库作者控制的地址。
所以目的地（渠道和全部凭据字段）只认环境变量和用户级配置；项目配置只能按名字引用已登记的目的地，并且只能把行为改得更严。

其余设计取舍——渠道契约、单调合并、配置类型校验、hook 时间预算与看门狗、凭据不入日志、
轮次边界与 transcript 解析——都记在 **[docs/DESIGN.md](docs/DESIGN.md)**。

---

## 故障排查

```bash
python3 scripts/notify.py doctor        # 当前渠道、配置从哪来、监听哪些事件、是否在静默时段
python3 scripts/notify.py doctor --test # 发一条测试消息
```

收不到通知时按顺序排查：

1. `doctor` 输出里「通知渠道」对不对、必填字段是不是 `(未配置)`，以及有没有 ⚠️ 告警行。
2. 把 `debug` 设为 `true`，触发一次任务完成，再 `tail -f ~/.config/claude-hook-notify/debug.log`。
   发送失败的记录**无论 debug 开关都会写**。
3. 单独验证目的地本身，例如飞书：
   ```bash
   curl -X POST "$LARK_WEBHOOK_URL" -H "Content-Type: application/json" \
     -d '{"msg_type":"text","content":{"text":"test"}}'
   ```
   返回 `{"code":0,...}` 才算通。`code: 19021` 是签名校验失败或时间戳超出 1 小时。
4. `/plugin` 看 claude-hook-notify 是否为 enabled。

**hook 会拖慢会话吗？** 不会。内部有 9 秒总预算和一个墙钟看门狗，超时安静退出 0；
`plugin.json` 另有 15 秒硬超时兜底。

---

## 开发

```bash
python3 -m unittest discover -s tests -v
```

不需要任何依赖。其中两个端到端用例会真的等待数秒来验证看门狗，整轮约 15 秒。

Python 3.9+，只用标准库。支持 macOS 与 Linux，暂不支持 Windows。

欢迎提 Issue 和 PR。改动请附带对应的回归用例 —— 这个项目的绝大多数分支都是某个具体失败场景的产物，
`docs/DESIGN.md` 记录了它们各自的来由。

版本变更见 [CHANGELOG.md](CHANGELOG.md)。

## License

MIT
