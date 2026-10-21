# claude-hook-notify

**English** | [简体中文](README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](#requirements)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#requirements)

A [Claude Code](https://code.claude.com) plugin that sends a notification when Claude finishes a task, needs your permission, or is waiting for input. Notifications can go to **Feishu / Lark, WeCom, DingTalk, Slack, Telegram, or Bark**.

The notification content is generated once and is the same on every channel. Each channel only decides how to format and deliver it. Switching channels is a one-line config change.

> Formerly `claude-hook-lark`. Existing configurations keep working — see [Migrating from claude-hook-lark](#migrating-from-claude-hook-lark).

## Contents

- [Features](#features)
- [Supported channels](#supported-channels)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Migrating from claude-hook-lark](#migrating-from-claude-hook-lark)
- [Development](#development)
- [License](#license)

## Features

- **Six channels, one config key.** Change `channel` and the same notification is delivered elsewhere.
- **Automatic notifications** on task completion, permission requests, and idle prompts, via Claude Code hooks.
- **Manual notifications** through the bundled `notify` skill ("ping me when the migration is done") or the command line.
- **Useful content.** The title is the session name, so parallel tasks in one project are easy to tell apart. The body includes your prompt, Claude's reply, tool-call count, duration, project, Git branch, host, and session ID.
- **Not noisy.** Event allowlist, quiet hours, and a minimum task duration filter.
- **Zero dependencies.** Python standard library only — no `pip install`, no `jq`, no `curl`.
- **Safe by default.** A repository's config file can never choose where your notifications go. See [Security](#security).
- **Bounded execution.** Synchronous hooks have a 30-second budget and exit quietly on any error.

Example (Feishu card; other channels carry the same content in their own format):

```
┌────────────────────────────────────────────┐
│ ✅ Task complete · Refactor login module   │  ← title is the session name
├────────────────────────────────────────────┤
│ 📝 Original reply                          │
│ ## What changed                            │
│ - Issue JWTs on login                      │
│ - Added 12 tests                           │
│ 📋 Task                                    │
│ Switch the login API to JWT and add tests  │
│ 🔧 19 tool calls · ⏱️ 6 min 31 s          │
├────────────────────────────────────────────┤
│ Project my-project     Branch feat/jwt     │
│ Host dev-macbook       Session 3f2a9c10-…  │
├────────────────────────────────────────────┤
│ Claude Code · Stop · 2026-08-23 00:39      │
└────────────────────────────────────────────┘
```

> The notification text itself is currently in Chinese; the example above is translated.

## Supported channels

| `channel` | Service | Required fields | Optional fields | Format |
|-----------|---------|-----------------|-----------------|--------|
| `lark` (default) | Feishu / Lark custom bot | `webhook_url` | `secret` (signature verification) | Card (schema 2.0), header colored by status |
| `wecom` | WeCom group bot | `webhook_url` | | Markdown |
| `dingtalk` | DingTalk group bot | `webhook_url` | `secret` (signing) | Markdown |
| `slack` | Slack incoming webhook | `webhook_url` | | Block Kit |
| `telegram` | Telegram bot | `bot_token`, `chat_id` | | Plain text |
| `bark` | Bark (iOS push) | `device_key` | `server` (self-hosted), `icon` (image URL, iOS 15+), `badge` (`false` disables the unread badge) | Push notification (Markdown body) |

Each channel may only send to its official host. To use a self-hosted Bark server or a proxy, add the host to `allowed_hosts` in your user config.

## Requirements

- Claude Code with plugin support
- Python 3.9 or later (`python3` on `PATH`)
- macOS or Linux. Windows is not supported yet.

## Installation

### 1. Install the plugin

In Claude Code:

```
/plugin marketplace add mrgeneralgoo/claude-hook-notify
/plugin install claude-hook-notify
```

### 2. Choose a channel

Create the user config file:

```bash
mkdir -p ~/.config/claude-hook-notify && chmod 700 ~/.config/claude-hook-notify
$EDITOR ~/.config/claude-hook-notify/config.json
chmod 600 ~/.config/claude-hook-notify/config.json
```

Put **one** destination in it. Pick the line for your channel:

```jsonc
// Feishu / Lark (the default when "channel" is omitted)
{"channel": "lark", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx", "secret": ""}

// WeCom
{"channel": "wecom", "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx"}

// DingTalk
{"channel": "dingtalk", "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxxx", "secret": "SECxxxx"}

// Slack
{"channel": "slack", "webhook_url": "https://hooks.slack.com/services/T000/B000/xxxx"}

// Telegram (chat_id must be a string)
{"channel": "telegram", "bot_token": "123456:ABC-xxxx", "chat_id": "123456789"}

// Bark
{"channel": "bark", "device_key": "xxxxxxxxxxxxxxxx"}
```

For Feishu you can use environment variables instead:

```bash
export LARK_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
export LARK_WEBHOOK_SECRET="..."   # only if signature verification is enabled
```

> ⚠️ Webhook URLs, bot tokens, and device keys are credentials. Never commit them.

### 3. Verify

```bash
python3 scripts/notify.py doctor --test
```

`doctor` prints the active channel and where each setting came from; `--test` sends a test message. If it arrives, you are done.

## Configuration

The user config lives at `~/.config/claude-hook-notify/config.json`. A full example is in [config.example.json](config.example.json).

### Options

| Key | Default | Description |
|-----|---------|-------------|
| `channel` | `"lark"` | Notification channel. See [Supported channels](#supported-channels). |
| Channel fields | — | `webhook_url`, `secret`, `bot_token`, `chat_id`, `device_key`, `server`, depending on the channel. |
| `destinations` | `{}` | Named destinations. Each entry is an object with its own `channel` and fields. |
| `destination` | — | Which entry of `destinations` to use. |
| `events` | `["Stop", "Notification"]` | Hook events that trigger a notification. `[]` means none. |
| `include_summary` | `true` | Include your prompt and Claude's reply. Set to `false` to send metadata only. |
| `recap` | Disabled | Optional OpenAI-compatible summary of long replies. User config only; see below. |
| `min_duration_seconds` | `0` | Skip turns shorter than this. |
| `quiet_hours` | `null` | Do not notify during these hours, e.g. `[22, 8]` for 22:00–08:00. |
| `timeout` | `5` | Send timeout in seconds. |
| `allowed_hosts` | Channel's official hosts | Replaces the host allowlist. Only needed for self-hosted servers or proxies. |
| `debug` | `false` | Write a detailed log to `~/.config/claude-hook-notify/debug.log`. |

Settings are validated strictly. An invalid privacy or filter setting is treated in its most restrictive form (for example, a malformed `quiet_hours` means "always quiet"), and `doctor` prints a warning.

### Optional recaps

By default, long replies are truncated rather than summarized. To enable model-generated recaps, add this object to your **user config**, alongside the existing notification destination:

```json
{
  "recap": {
    "enabled": true,
    "base_url": "https://api.example.com/v1",
    "model": "your-model",
    "api_key_env": "NOTIFY_RECAP_API_KEY",
    "timeout": 15
  }
}
```

Replace the endpoint and model. Credentials support either of these fields inside `recap`:

- `"api_key_env": "NOTIFY_RECAP_API_KEY"`: read the key from that environment variable, set before starting Claude Code.
- `"api_key": "your-api-key"`: read the literal key directly from your user config. Do not commit real keys to a repository.

If `api_key` is present, it takes precedence. An invalid or empty explicit key disables recap for that request rather than falling back to the environment. `api_key_env` always means an environment variable name, never a literal key.

The key is sent as a Bearer token. The endpoint must support non-streaming `POST /chat/completions`, `messages`, and `max_tokens`; the plugin appends `/chat/completions` to `base_url`. Only HTTPS is accepted, without URL credentials, a query, or a fragment. Redirects are refused.

- Recaps apply only to eligible `Stop` / `SubagentStop` replies longer than 600 characters. The existing event filters and `include_summary` setting still apply. Short replies, permission prompts, manual sends, and `--dry-run` never call the model.
- The request contains the current prompt, capped at 2,000 characters, and the last assistant reply. Replies over 12,000 characters retain their beginning and end with an omitted-middle marker. No tool logs or full conversation history are uploaded.
- The model is asked for a same-language summary: a one-sentence conclusion plus at most 4 bullet points (changes, verification, risks, todos). Accepted output is capped at 500 characters. Notification status remains determined by the hook, not the model.
- The result section label shows its source: `🤖 AI 摘要` (model-generated), `📝 回复原文` (original, not truncated), or `📝 回复原文（节选）` (original, truncated at 600 characters).
- A failed recap leaves `recap FAIL: <reason>` in the debug log (for example `HTTP 401`, `超时`, `finish_reason=length`) with no key, URL, or remote text; a skip due to low budget logs `recap skip`.
- The recap request defaults to a 15-second wall-clock limit. The remaining hook budget may shorten it to reserve notification time and message-building time. No retries are made. Invalid settings, a missing key, malformed output, or request failure retain the original truncated reply.
- Wall-clock enforcement uses Unix signal timers. If these are unavailable, recap is skipped and ordinary notification delivery continues.

**Enabling recap sends conversation text to the selected model provider and may incur charges.** It is an additional destination, separate from your notification channel. Project configs cannot enable or override it. Summaries are lossy and do not provide full-text viewing.

### Bark unread badge

The red badge on the Bark app icon is an **unread count**: each successful push adds 1, and it resets when you send a new message in that session (`UserPromptSubmit`) or the session ends. The count lives in `~/.config/claude-hook-notify/badge.json` (sessions idle for 24 hours are dropped; concurrent hooks may occasionally miss one increment). To turn the badge off, set `"badge": false` on the Bark destination. `--dry-run`, `send` and `doctor` never increment it.

### Switching channels

Change `channel` and its fields; everything else stays the same. To switch often, register several destinations and select one:

```json
{
  "destination": "phone",
  "destinations": {
    "team": {"channel": "lark", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/aaaa"},
    "phone": {"channel": "bark", "device_key": "xxxxxxxx"}
  }
}
```

Preview what a channel will receive without sending anything:

```bash
python3 scripts/notify.py send -t "Preview" -s info -m "hello" --dry-run
```

### Per-project settings

A project can add `.claude/notify.json` to pick a registered destination by name and to make behavior stricter:

```json
{"destination": "team", "events": ["Stop"]}
```

This file is safe to commit. It **cannot** contain URLs, tokens, `channel`, `destinations`, `allowed_hosts`, `recap`, or `debug` — those keys are ignored with a warning. Behavior settings can only be tightened:

| Key | Merge rule |
|-----|------------|
| `events` | Intersection with the user setting |
| `include_summary` | Can only change `true` → `false` |
| `min_duration_seconds` | Larger value wins |
| `timeout` | Smaller value wins |
| `quiet_hours` | Applied only if the user has not set one |

### Where the destination comes from

From lowest to highest priority:

1. User config `~/.config/claude-hook-notify/config.json`
2. The file named by `CLAUDE_HOOK_NOTIFY_CONFIG` (fully replaces the user config's destination)
3. `destination` in the project's `.claude/notify.json` (name lookup only)
4. `LARK_WEBHOOK_URL` / `LARK_WEBHOOK_SECRET` environment variables
5. `--webhook` on the command line

If an explicitly configured source is broken (missing file, invalid JSON, unknown destination name, unknown channel), sending stops instead of falling back to another destination.

## Usage

### Automatic notifications

| Event | When | Notification | Enabled by default |
|-------|------|--------------|:------------------:|
| `Stop` | Claude finishes a turn | ✅ Task complete · ⏳ Background tasks still running (listed) | ✔ |
| `Notification` | Claude needs permission, an MCP server asks a question, or it has been idle for 60 s (idle prompts are skipped when `Stop` is enabled) | 🔐 Permission needed · 🙋 Needs your answer · ⏳ Waiting for input | ✔ |
| `SubagentStop` | A subagent finishes | 📦 Subtask complete | |
| `SessionEnd` | The session exits | 👋 Session ended | |

All four hooks are registered by the plugin; `events` decides which ones send. Changing it takes effect immediately, without reinstalling.

### Manual notifications

Ask Claude directly — for example "notify me when the build finishes" — and it uses the bundled `notify` skill.

From a terminal:

```bash
# Locate the installed script
NOTIFY=$(find ~/.claude/plugins -name notify.py -path '*claude-hook-notify*' | head -1)

python3 "$NOTIFY" send -t "Migration finished" -s success -m "Migrated 120k rows."
python3 "$NOTIFY" send -t "CI failed" -s failed -m "**Branch** feat/login does not compile" \
                       -d "error[E0308]: mismatched types"
python3 "$NOTIFY" send -t "Decision needed" -s decision -m "REST or GraphQL?"
```

| Option | Description |
|--------|-------------|
| `-t, --title` | Title |
| `-s, --status` | `success`, `failed`, `running`, `decision`, `warning`, `error`, or `info` (✅ ❌ ⏳ 🤔 ⚠️ ⚠️ 💬). Channels with color support also color by status. |
| `-m, --message` | Body, in Markdown. Unsupported syntax is simplified per channel. |
| `-d, --detail` | Extra details, shown below a divider |
| `-c, --color` | Override the card color (Feishu only) |
| `--session-name`, `--session-id` | Override the detected session name or ID |
| `--no-session` | Use the project name as the title and omit the session ID |
| `--dry-run` | Print the request body for the active channel instead of sending |

## Security

Two things to know before you start:

**Notifications include your prompt and Claude's reply by default.** Anything you pasted into the conversation — keys, tokens, customer data — can end up in a group chat or on a phone. Set `"include_summary": false` to send only metadata (project, branch, session name, duration).

**A repository cannot redirect your notifications.** `.claude/notify.json` arrives with `git clone`. If it could choose the destination, cloning any third-party repository could send your session content to its author. Destinations — the channel and all credential fields — are therefore read only from your user config and environment variables.

Additionally:

- Notification requests go only to HTTPS URLs on the channel's allowlisted hosts.
- Optional recap requests use the explicitly configured HTTPS model endpoint, refuse redirects, and may incur model-provider charges.
- Error messages and logs never include URLs, tokens, or text returned by the remote server.
- Telegram bot tokens and chat IDs, and Bark device keys, are format-checked before use, so a malformed value cannot redirect the request.

Design notes and the reasoning behind each rule are in [docs/DESIGN.md](docs/DESIGN.md) (Chinese).

## Troubleshooting

```bash
python3 scripts/notify.py doctor         # channel, config sources, events, quiet hours, warnings
python3 scripts/notify.py doctor --test  # also send a test message
```

If notifications do not arrive:

1. Run `doctor`. Check the channel, any required field shown as `(未配置)` (not configured), and any ⚠️ warnings.
2. Set `"debug": true`, trigger a turn, and read `~/.config/claude-hook-notify/debug.log`. Send failures are logged even when `debug` is off.
3. Check the destination directly. For Feishu:
   ```bash
   curl -X POST "$LARK_WEBHOOK_URL" -H "Content-Type: application/json" \
     -d '{"msg_type":"text","content":{"text":"test"}}'
   ```
   `{"code":0,...}` means it works. `code: 19021` means the signature is wrong or the timestamp is more than an hour off.
4. Run `/plugin` in Claude Code and make sure claude-hook-notify is enabled.

**Will hooks slow down my session?** Hooks run synchronously, so slow I/O can delay the session. Each hook has a 30-second internal budget and a watchdog, exits with status 0 on any problem, and the plugin manifest declares a 40-second timeout enforced by Claude Code. The send timeout remains 5 seconds by default.

## Migrating from claude-hook-lark

Version 0.3.0 renamed the project. Existing setups keep working without changes:

| Old | New | Old name still works |
|-----|-----|:--------------------:|
| `~/.config/claude-hook-lark/config.json` | `~/.config/claude-hook-notify/config.json` | ✔ (used if the new file does not exist; `doctor` suggests moving it) |
| `CLAUDE_HOOK_LARK_CONFIG` | `CLAUDE_HOOK_NOTIFY_CONFIG` | ✔ |
| `.claude/lark.json` | `.claude/notify.json` | ✔ (used if the new file does not exist) |
| `webhooks` / `webhook` | `destinations` / `destination` | ✔ |
| No `channel` key | `"channel": "lark"` | ✔ (Feishu is the default) |
| `LARK_WEBHOOK_URL` and related variables | unchanged | ✔ |
| `scripts/lark_notify.py`, skill `lark-notify` | `scripts/notify.py`, skill `notify` | ✘ |

The plugin itself must be reinstalled:

```
/plugin uninstall claude-hook-lark
/plugin marketplace add mrgeneralgoo/claude-hook-notify
/plugin install claude-hook-notify
```

## Development

Run the tests (no dependencies; about 40 seconds, including watchdog timeout tests):

```bash
python3 -m unittest discover -s tests -v
```

### Project layout

```
scripts/notify.py              # hook / send / doctor commands, config loading, shared HTTPS sender
scripts/notify_channels/       # one module per channel, plus the Message/Channel contract (base.py)
skills/notify/SKILL.md         # the skill Claude uses to send notifications
.claude-plugin/plugin.json     # plugin manifest and hook registration
docs/DESIGN.md                 # design notes (Chinese)
```

### Adding a channel

1. Create `scripts/notify_channels/<name>.py` with a `Channel` subclass that sets `name`, `label`, `default_hosts`, `required`, and `optional`, and implements:
   - `render(msg)` — turn a `Message` into the request body
   - `request(dest, body)` — return the final URL and body, adding any signature
   - `check(status, parsed, raw)` — decide success; never include remote text in the result
2. Export `CHANNEL = YourChannel()` and register it in `scripts/notify_channels/__init__.py`.
3. Add the channel name to the registry test in `tests/test_channels.py` and add tests for its `request()` and `check()`. The cross-channel rendering, length-limit, and secret-leak tests loop over every registered channel, so they cover it automatically.

The new channel's credential fields are automatically excluded from project configs. HTTP, timeouts, and error redaction are handled by `notify.post()`.

Issues and pull requests are welcome. Please include a regression test with each change. See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

[MIT](LICENSE)
