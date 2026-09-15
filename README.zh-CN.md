# repowiki-cli · 仓库 Wiki 查询工具

从终端查询任意公开 GitHub 仓库的 [DeepWiki](https://deepwiki.com) 文档。

> English docs: [README.md](README.md) · 英文文档见 [README.md](README.md)

## 这是什么

`repowiki-cli` 是一个基于 Python/Typer 的 CLI，能在终端里读取 AI 生成的仓库文档、
并就代码提问。它在**同一套命令界面**下对接了**两个后端**：

| 后端 | 传输 | 命令 | 信息量 |
|------|------|------|--------|
| **MCP**（官方） | Streamable HTTP | `structure`、`contents`、`ask` | 只有正文 |
| **逆向**（`api.devin.ai`） | REST + WebSocket | `ask`（带参数）+ `list`/`status`/`warm`/`get` | 正文、摘要、引用、源码、统计 |

MCP 后端是 DeepWiki 官方文档化的服务，公开仓库免费、无需鉴权。逆向后端是底层引擎
`api.devin.ai`（与 DeepWiki 网页版同源）——它**不是**公开文档 API，但提供了 MCP
没有的能力：引擎选择（`fast`/`deep`/`codemap`）、流式输出、对话线程、索引管理端点。

## 安装

```bash
uvx repowiki-cli --help
```

从源码：

```bash
git clone <this-repo> && cd <this-repo>
uv sync
uv run repowiki-cli --help
```

## 快速上手

```bash
repowiki-cli structure facebook/react          # 文档目录
repowiki-cli contents vercel/next.js           # 完整文档
repowiki-cli ask facebook/react "What is Fiber?"
```

## 命令总览

| 命令 | 用途 | 后端 |
|------|------|------|
| `structure REPO` | 打印文档目录 | MCP |
| `contents REPO` | 打印完整文档 | MCP |
| `ask REPO [QUESTION]` | 提问（单次或交互） | 默认 MCP；带参数走逆向 |
| `list SEARCH` | 搜索已索引的公开仓库 | 逆向 |
| `status REPO` | 查询仓库索引状态 | 逆向 |
| `warm REPO` | 预热文档缓存 | 逆向 |
| `get QUERY_ID` | 按 query id 重放历史回答 | 逆向 |

## 命令详解

### `structure`

```bash
repowiki-cli structure REPO [--json]
```

打印文档目录（MCP `read_wiki_structure`）。

### `contents`

```bash
repowiki-cli contents REPO [--page TITLE] [--rich] [--json]
```

打印完整文档（MCP `read_wiki_contents`），可能很大。

- `--page TITLE` — 只打印标题匹配（大小写不敏感的精确匹配）的那一页。会去掉
  `# Page:` 分隔符，选中的页面只显示一个标题。若无匹配，会在 stderr 列出可用标题，
  并以错误类型 `page_not_found` 退出。
- `--rich` — 用 `rich` 渲染 Markdown（带颜色和格式）。
- `--json` — 输出 JSON 信封而非 Markdown。

### `ask`

```bash
repowiki-cli ask REPO [QUESTION] \
  [--rich] [--json] [--save [PATH]] \
  [--mode fast|deep|codemap] [--id QUERY_ID] \
  [--sources] [--no-summary] [--context TEXT] [--repo REPO]... \
  [--mermaid] [--stream] [--timeout SECONDS]
```

带 `QUESTION` 则单次回答后退出；不带则进入交互式 REPL（输入 `/exit` 退出）。

**后端路由。** 除非出现任一逆向参数，`ask` 使用 MCP 后端。`--mode`、`--id`、
`--sources`、`--repo`、`--context`、`--no-summary`、`--stream` 中的任意一个都会
切换到逆向后端。单独的 `--mermaid` **不会**切换后端——请与 `--mode codemap` 搭配。

- `--mode fast|deep|codemap` — 引擎选择。底层映射：`fast` → `multihop_faster`、
  `deep` → `agent`、`codemap` → `codemap`。
- `--id QUERY_ID` — 复用之前的 query id 继续同一对话线程。
- `--sources` — 为每条引用追加带行号的源码切片。
- `--context TEXT` — 随问题附带额外上下文。
- `--no-summary` — 跳过摘要生成。
- `--repo REPO` — 可重复；一次对多个仓库提问（位置参数 `repo` + 每个 `--repo`）。
- `--mermaid` — 把 `codemap` 答案渲染成 Mermaid `flowchart TB`。若答案不是
  codemap，则告警并回退为纯文本。可粘贴到 mermaid.live、GitHub 或 VS Code 查看。
- `--stream` — 通过 WebSocket 逐字流式输出答案，然后追加摘要和源码。与 `--json`
  一起使用时无效。
- `--timeout SECONDS` — 逆向后端的回答超时（秒）。默认 `120`，`--mode deep` 为
  `300`。优先级高于 `DEEPWIKI_TIMEOUT`。
- `--save [PATH]` — 把每个答案保存为 Markdown 文件（见「保存」）。
- `--rich` — 用 `rich` 渲染答案。
- `--json` — 输出 JSON 信封；交互模式下忽略。

### `list`

```bash
repowiki-cli list SEARCH [--json]
```

搜索 DeepWiki 公开索引（逆向 `list_public_indexes`）。

### `status`

```bash
repowiki-cli status REPO [--json]
```

查询仓库索引状态（逆向 `public_repo_indexing_status`）。未索引仓库返回 `unknown`
属于正常结果，退出码 `0`。

### `warm`

```bash
repowiki-cli warm REPO [--json]
```

预热仓库文档缓存（逆向 `warm_public_repo`）。

### `get`

```bash
repowiki-cli get QUERY_ID [--rich] [--sources] [--json] [--mermaid]
```

按 query id 重放历史回答（逆向 `get_query`）。

## 设计

整个 CLI 共用同一个结果类型 `Answer`，让两个后端都接入同一套格式化层：

```python
@dataclass
class Answer:
    body: str                          # 主回答文本
    summary: str | None = None         # 仅逆向后端
    references: list[Reference] = []   # {file_path, range_start, range_end}
    sources: list[SourceFile] = []     # {repo, path, content}
    stats: dict[str, float] = {}       # 仅逆向后端
    query_id: str | None = None        # 仅逆向后端
    truncated: bool = False
```

MCP 后端只产生裸的 `Answer(body=...)`；逆向后端补齐 summary、references、sources、
stats、query_id——`--json` 会全部携带。

源码结构：

```
src/repowiki/
  cli.py      # Typer 命令、路由、REPL、重试/降级
  client.py   # MCP 后端（DeepWikiClient）+ 错误分类
  devin.py    # 逆向后端（DevinClient）：REST + WebSocket + 轮询
  model.py    # Answer / Reference / SourceFile
  output.py   # 格式化、页面过滤、引用填充、富文本渲染
  codemap.py  # codemap JSON -> Mermaid 流程图
  repo.py     # 仓库引用归一化
  save.py     # --save 文件命名与追加
```

## 后端详解

### MCP 后端（`client.py`）

- 端点：`DEEPWIKI_MCP_URL`，默认 `https://mcp.deepwiki.com/mcp`。
- 使用 **Streamable HTTP**（SSE 端点已废弃）。
- 工具：`read_wiki_structure`、`read_wiki_contents`、`ask_question`。
- 工具参数用 camelCase：`repoName`（`ask_question` 还有 `question`）。
- 连接生命周期：
  - 单次命令每次调用开关一次会话。
  - 交互式 REPL 只开**一条**会话，跨问题复用。
  - 首次连接失败重试一次；会话中途断开会重开一次恢复。

### 逆向后端（`devin.py`）

- 端点：`DEEPWIKI_API_URL`，默认 `https://api.devin.ai`。
- 回答流程（`ask`）：
  1. `POST /ada/query`（见下方 payload），然后流式或轮询。
  2. **流式** — 打开 `wss://…/ada/ws/query/{query_id}`，从事件组装答案。
  3. **轮询** — 按间隔 `GET /ada/query/{query_id}`，直到 `state` 为 `done` 或 `error`。

请求 payload（`POST /ada/query`）：

```json
{
  "engine_id": "agent",
  "user_query": "...",
  "keywords": [],
  "repo_names": ["owner/repo"],
  "additional_context": "",
  "query_id": "<uuid>",
  "use_notes": false,
  "attached_context": [],
  "generate_summary": true
}
```

引擎映射：`fast` → `multihop_faster`，`deep` → `agent`，`codemap` → `codemap`。

WebSocket 流上观测到的事件类型：`snapshot`、`file_contents`、`stats`、`chunk`、
`reference`、`summary_chunk`、`summary_done`、`done`。流携带完整答案，因此流式结束
后无需再 `GET` —— `parse_response` 直接从事件组装 `Answer`。

管理端点：

| 方法 | 路径 | 对应命令 |
|------|------|---------|
| `GET` | `/ada/list_public_indexes?search_repo=` | `list` |
| `GET` | `/ada/public_repo_indexing_status?repo_name=` | `status` |
| `POST` | `/ada/warm_public_repo?repo_name=` | `warm` |
| `GET` | `/ada/query/{query_id}` | `get` |

## 错误处理与退出码

异常被归入一个小型分类，并映射到退出码：

| 错误类型 | 含义 | 退出码 |
|---------|------|--------|
| 成功 | — | `0` |
| `not_indexed` | 仓库未在 DeepWiki 建立索引 | `2` |
| `connection` | 无法连接服务器 | `3` |
| `tool` / `error` / `invalid_repo` / `invalid_input` / `page_not_found` / `unexpected` | 其他 | `1` |

两个核心异常是 `ConnectionError`（传输层失败）和 `ToolError`（服务器返回的
`{"detail": …}` 或工具错误）。HTTP 错误体会通过 FastAPI 的 `detail` 字段透出，供
CLI 区分「未索引」和普通工具错误。

`--json` 模式下，错误以单行 JSON 写到 **stderr**：

```json
{"error": "Could not connect to DeepWiki server...", "kind": "connection"}
```

## 流式、重试与降级

仅适用于**逆向**后端。

**单次 `--stream`** 通过 WebSocket 把 chunk 流式写到 stdout，之后打印摘要/源码尾巴。

**重试。** 单次 `ask` 与交互式 REPL 都会对瞬时故障——`ConnectionError` 或含
`HTTP 5` 的 `ToolError`——用**带抖动的指数退避**重试：延迟 =
`1.0s × 2^attempt + random(0 … 0.5s)`。默认 **4 次**尝试，可用
`DEEPWIKI_REPL_RETRIES` 覆盖。只有在**尚未流式输出任何内容**时才重试——一旦部分
答案已上屏，连接中断就直接报错，避免重放乱码。

**交互式逆向 REPL** 在此基础上增加了线程接续与轮询降级：

1. 每个追问复用上一个 `query_id`，让服务端保持同一对话线程（`/new` 开启新线程）。
2. 在**最后一次**流式尝试失败时，客户端**降级为轮询**已提交的 query：
   `GET /ada/query/{query_id}`（`DevinClient.poll_answer`）。因为 `POST` 已经成功，
   query 在服务端已存在；轮询只是换一条传输通道等它完成。那一问会失去逐字流式，
   但仍能返回完整答案。

为什么需要这些：逆向端点是非官方的，偶尔会拒绝 WebSocket 握手（毫秒级的连接
重置，而非缓慢超时）。退避重试吸收偶发抖动；轮询降级则能从持续的 WS 拒绝中恢复。

## 仓库格式

`REPO` 接受以下任意形式：

- `owner/repo`
- `github.com/owner/repo`
- `www.github.com/owner/repo`
- `https://github.com/owner/repo`（可带 `/tree/main` 或 `.git`）

统一归一化为 `owner/repo`。

## JSON 输出

主命令输出带 `repo` 与 `command` 的信封：

```json
{
  "repo": "facebook/react",
  "command": "ask",
  "question": "What is Fiber?",
  "answer": "...",
  "truncated": false
}
```

`ask` 在逆向后端提供数据时，还会附带 `summary`、`references`、`sources`、`stats`、
`query_id`。管理命令（`list`/`status`/`warm`/`get`）省略 `repo`，仅含 `command` +
字段。错误以 `{"error": ..., "kind": ...}` 写到 stderr。

## 保存（`--save`）

- 裸 `--save` 自动命名为当前目录下的 `repowiki-<owner>-<repo>_<timestamp>.md`。
- `--save PATH` 写入（并追加到）指定路径，自动创建父目录。
- 交互模式下整个会话的所有回答追加到同一文件；单次回答在文件已存在时追加。
- 可与 `--json` 组合：stdout 保持 JSON，同时把 Markdown 写入文件。

## Mermaid

`--mode codemap` 返回 codemap（形如 `{"traces": [...]}` 的 JSON）。`--mermaid` 把
它渲染成 `flowchart TB`，每条 trace 一个子图并带配色。粘贴到 mermaid.live、GitHub
或 VS Code 即可查看。若答案不是 codemap，`--mermaid` 会告警并打印纯文本。

## 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `DEEPWIKI_MCP_URL` | MCP 端点 | `https://mcp.deepwiki.com/mcp` |
| `DEEPWIKI_API_URL` | 逆向后端端点 | `https://api.devin.ai` |
| `DEEPWIKI_REPL_RETRIES` | 逆向 REPL 重试次数 | `4` |
| `DEEPWIKI_TIMEOUT` | 逆向回答超时（秒） | `120`（`--mode deep` 为 `300`） |
| `REPOWIKI_MOCK_TEXT` | mock MCP 结果（测试用） | — |
| `REPOWIKI_DEVIN_MOCK` | mock 逆向回答（测试用） | — |

## 组合实践方案

以下组合按意图分组，仓库默认 `facebook/react`。

**读文档（MCP）**

```bash
repowiki-cli structure facebook/react
repowiki-cli contents vercel/next.js
repowiki-cli contents vercel/next.js --page "Getting Started"   # 只看一页
repowiki-cli contents vercel/next.js --rich                      # 富文本渲染
```

**提问（MCP）**

```bash
repowiki-cli ask facebook/react "What is Fiber?"
repowiki-cli ask facebook/react "What is Fiber?" --rich
repowiki-cli ask facebook/react                                  # 交互式
```

**机器可读输出**

```bash
repowiki-cli structure facebook/react --json
repowiki-cli contents vercel/next.js --json
repowiki-cli ask facebook/react "What is Fiber?" --json
repowiki-cli ask facebook/react "What is Fiber?" --json --save out.md   # JSON + Markdown 文件
```

**保存回答到文件**

```bash
repowiki-cli ask facebook/react "What is Fiber?" --save            # 自动命名
repowiki-cli ask facebook/react "What is Fiber?" --save notes/answers.md
```

**逆向后端 — 引擎与深度**

```bash
repowiki-cli ask facebook/react "What is Fiber?" --mode deep
repowiki-cli ask facebook/react "Quick facts?" --mode fast
repowiki-cli ask facebook/react "Show the data flow" --mode codemap --mermaid
```

**逆向后端 — 源码与摘要**

```bash
repowiki-cli ask facebook/react "What is Fiber?" --mode deep --sources
repowiki-cli ask facebook/react "What is Fiber?" --mode deep --no-summary
```

**逆向后端 — 流式与上下文**

```bash
repowiki-cli ask facebook/react "What is Fiber?" --mode deep --stream
repowiki-cli ask facebook/react "What is Fiber?" --mode deep --context "answer in Chinese"
```

**逆向后端 — 线程与多仓库**

```bash
repowiki-cli ask facebook/react "Follow-up?" --id <query-id>      # 继续线程
repowiki-cli ask facebook/react "diff?" --repo remix-run/react-router --repo TanStack/router
repowiki-cli ask facebook/react --mode deep                        # 交互式，自动接续线程
```

**管理命令**

```bash
repowiki-cli list react
repowiki-cli status facebook/react
repowiki-cli warm facebook/react
repowiki-cli get <query-id>
repowiki-cli get <query-id> --sources
repowiki-cli get <query-id> --mermaid
```

**脚本中利用退出码**

```bash
repowiki-cli ask some/repo "q?" --json > out.json
case $? in
  0) ;;                       # 成功
  2) echo "未索引" ;;
  3) echo "连接错误" ;;
  *) echo "其他错误" ;;
esac
```

## DeepWiki MCP 服务

官方 [DeepWiki MCP 服务](https://docs.devin.ai/work-with-devin/deepwiki-mcp) 免费、
公开仓库无需鉴权。它暴露两种传输协议：Streamable HTTP（`/mcp`，推荐）与 SSE
（`/sse`，已废弃）。`repowiki-cli` 使用 Streamable HTTP。

添加到 Claude Code：

```bash
claude mcp add -s user -t http deepwiki https://mcp.deepwiki.com/mcp
```

私有仓库不在 `repowiki-cli` 支持范围内；请使用带 Devin API key 的
[Devin MCP 服务](https://docs.devin.ai/work-with-devin/devin-mcp)。完整文档索引在
<https://docs.devin.ai/llms.txt>。

## 相关工具

以下是同一领域的参考/替代 CLI，重造轮子前值得先看看：

- [Zread CLI](https://github.com/ZreadAI/zread_cli) — 用 LLM 从你的仓库本地生成
  wiki 文档（配置 `~/.zread/config.yaml`）。
- [readmeX CLI](https://github.com/aibox22/readmeX) — 官方 CLI。
- [deepwiki-open](https://github.com/AsyncFuncAI/deepwiki-open) — 开源的 DeepWiki CLI。

如果目标是用自己的 API **生成** wiki，而非查询公开的 DeepWiki 索引，上述官方 CLI
已经解决了这个问题——不必自己造轮子。

## 开发

```bash
uv sync
uv run pytest
```
