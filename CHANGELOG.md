# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.3.2]

### 修复

- **后台任务还在跑时不再报「任务完成」**。Stop 读取 Claude Code 提供的 `background_tasks`，
  有在途任务时推送「⏳ 后台运行中」并列出任务描述（不外发 `command`）；任务结束、Claude 被唤醒
  收尾后，会再推一条「✅ 任务完成」。旧版 Claude Code 没有该字段时行为不变。
- **Notification 按 `notification_type` 区分**：`permission_prompt` →「🔐 需要授权」；
  `elicitation_dialog` / `elicitation_url_dialog` →「🙋 需要你回答」。字段缺失时才退回按文本判断。

### 行为变更

- 订阅了 Stop 时，不再推送 `idle_prompt`（「回复完 60 秒没人输入」的计时提醒）。它在后台任务运行期间
  也会触发，和 Stop 通知重复且容易误导。只订阅 Notification 时照常推送。
- `auth_success`、`elicitation_complete`、`elicitation_response` 不需要用户操作，不再推送。

## [0.3.1]

### 变更

- **Bark 正文改用 `markdown` 参数**：粗体、标题、列表、代码块、链接由 App 渲染，不再降级成纯文本。
  项目、分支、主机、会话 ID 和脚注收进正文末尾的引用块（显示为浅灰色）。
  正文按字符数和 UTF-8 字节数双重截断，整条推送不超过 APNs 的 4KB 上限。

### 修复

- 请求带上 `User-Agent: claude-hook-notify`。自建 Bark 等服务挂在 Cloudflare 后面时，
  Python 默认的 UA 会被 error 1010 拦截（HTTP 403）。

## [0.3.0]

项目从「飞书通知插件」升级为通用的多渠道通知插件，并改名为 **claude-hook-notify**。

### 新增

- **渠道契约**（`scripts/notify_channels/`）。通知内容统一成与渠道无关的 `Message`，
  各渠道只负责 `render`（排版）、`request`（拼 URL、签名）、`check`（判成败），
  HTTP 发送、超时和错误脱敏由框架统一处理。新增渠道只需写一个模块并登记。
- **五个新渠道**：企业微信、钉钉（含加签）、Slack、Telegram、Bark。配置里写
  `"channel": "<名字>"` 加该渠道的字段即可切换，通知内容不变。
- 具名目的地 `destinations` / 选择器 `destination`，每项可以是不同渠道。
- `doctor` 显示当前渠道及其字段状态（凭据不回显）。

### 变更（改名）

- 插件 / marketplace 名 `claude-hook-lark` → `claude-hook-notify`，需要重新安装。
- 脚本 `scripts/lark_notify.py` → `scripts/notify.py`；skill `lark-notify` → `notify`。
- 用户配置 `~/.config/claude-hook-notify/config.json`、环境变量 `CLAUDE_HOOK_NOTIFY_CONFIG`、
  项目配置 `.claude/notify.json`。**旧路径、旧环境变量、旧键名（`webhooks` / `webhook`）都继续生效**，
  没有 `channel` 键的配置按飞书处理。
- 事件样式改为返回状态而非飞书颜色，颜色映射移入飞书渠道；飞书卡片外观不变。
- `send -c` 仅对飞书生效。

### 安全

- 信任边界随渠道扩展：所有渠道的凭据字段与 `channel` 都只能来自用户配置或环境变量，
  项目配置写了会被忽略并告警。字段名单由已注册渠道自动求并集。
- 未知渠道名直接停发，不退回飞书。
- 会拼进 URL 的凭据（Telegram `bot_token` / `chat_id`、Bark `device_key`）按格式校验，防止路径注入。

### 测试

236 → 301。新增用例覆盖：同一条 `Message` 经每个渠道渲染后内容完整、超长正文不超出各平台上限、
各渠道签名与 URL 拼装、响应判定不回显远端文本、项目配置不能指定渠道或令牌、未知渠道停发。

## [0.2.0]

卡片排版的三处修复，均来自实际使用中的反馈。

### 修复

- **Claude 回复里的 markdown 渲染不出来**。根因是卡片用的是 v1 schema，正文走
  `div` + `lark_md`，而 `lark_md` 只支持粗体、行内代码、链接这一小撮语法 ——
  标题（`##`）、列表、代码块、引用统统会以原文形式露在卡片上。
  改用 **schema 2.0** 的 `markdown` 元素。

  附带的结构调整：`note` 元素在 2.0 里会被飞书拒绝（`code 11246`），脚注改用
  `markdown` 元素加灰字代替；元素挂到 `body.elements` 下。`hr`、`div`（含 `fields`
  两列写法）、`column_set` 在 2.0 里仍然可用。详见 [docs/DESIGN.md](docs/DESIGN.md)。

- **正文每两个元素之间多出一个空行**。元素自带前导 `\n`，`"\n".join()` 又加一个，
  叠成了空行，信息密度很低。只压缩卡片自身的排版骨架，用户提问和 Claude 回复里的
  段落换行属于内容，原样保留。

### 变更

- **卡片标题改用会话名**，不再用项目名。一个项目下会并行跑很多任务，标题全是项目名
  就看不出通知的是哪件事；会话名按任务归属，天然有区分度。会话还没生成标题时退回项目名。
  相应地，正文里的「🏷️ 会话」行和字段区里的会话名都去掉了。
- **会话 ID 改为半宽字段**，与项目 / 分支 / 主机排成两列，不再独占一行。

### 测试

217 → 233。新增用例锁住 schema 2.0 结构、绝不产出 `note` 元素、底部字段全为半宽、
排版骨架不含空行、内容里的换行不被吞、以及两个清单文件的版本号保持一致。

## [0.1.0]

首个版本。

- hook Claude Code 的 `Stop` / `SubagentStop` / `Notification` / `SessionEnd`
  事件，推送飞书卡片
- 把通知能力包装成可手动调用的 `lark-notify` skill
- 零第三方依赖，只用 Python 标准库
- 支持签名校验、静默时段、最短耗时过滤、事件白名单
- 仓库内配置文件不能指定通知目的地，只能按名字引用已登记的地址并单调收窄行为
