# repowiki-cli

Query [DeepWiki](https://deepwiki.com) documentation for any public GitHub
repository from your terminal.

## Install

```bash
uvx repowiki-cli --help
```

Or from source:

```bash
git clone <this-repo> && cd <this-repo>
uv sync
uv run repowiki-cli --help
```

## Usage

```bash
repowiki-cli structure facebook/react
repowiki-cli contents vercel/next.js
repowiki-cli contents vercel/next.js --page "Getting Started"   # one page only
repowiki-cli contents vercel/next.js --rich                     # render Markdown
repowiki-cli ask facebook/react "What is Fiber?"
repowiki-cli ask facebook/react "What is Fiber?" --rich
repowiki-cli ask facebook/react "What is Fiber?" --save            # auto-named file
repowiki-cli ask facebook/react "What is Fiber?" --save notes/answers.md
repowiki-cli ask facebook/react "What is Fiber?" --json             # JSON output
repowiki-cli ask facebook/react          # interactive REPL
```

`structure` prints the documentation table of contents; `contents` prints the
full documentation (may be large); `ask` answers a question (single-shot when a
question is passed, interactive REPL otherwise — type `/exit` to quit).

### Options

- `contents --page <title>` — print only the page with that title
  (case-insensitive exact match). Page titles are long and descriptive (e.g.
  "Fiber Work Loop and Scheduling"); if no page matches, the available titles
  are listed so you can copy the exact one. The `# Page:` delimiter is dropped,
  so the selected page shows a single heading.
- `--rich` (on `contents` and `ask`) — render the Markdown with color and
  formatting via [rich](https://github.com/Textualize/rich), so headings, lists
  and code blocks are easier to read. Default output is plain Markdown.
- `--json` (on `structure`, `contents`, and `ask`) — emit a machine-readable
  JSON envelope instead of Markdown, e.g.
  `{"repo": "facebook/react", "command": "ask", "question": "...", "answer": "...", "truncated": false}`.
  Errors go to stderr as `{"error": "...", "kind": "..."}`. `--json` is ignored
  in interactive (`ask` without a question) mode; combine with `--save` to
  write Markdown to a file while stdout stays JSON.
- `--save [PATH]` (on `ask`) — save each answer to a Markdown file. Bare
  `--save` auto-names the file as
  `repowiki-<owner>-<repo>_<timestamp>.md` in the current directory; `--save
  PATH` writes to (and appends to) the given path. In interactive mode all
  answers in the session append to one file; single-shot answers append when
  the file already exists.

Repos may be given as `owner/repo`, `github.com/owner/repo`, or a full GitHub
URL. The MCP endpoint defaults to `https://mcp.deepwiki.com/mcp` and can be
overridden with `DEEPWIKI_MCP_URL`.

Exit codes: `0` success; `2` the repository is not indexed on DeepWiki; `3`
could not connect to the DeepWiki server; `1` any other error (bad repo
reference, tool error, and so on).

Connection handling: the interactive REPL keeps one MCP connection open for the
whole session instead of reconnecting per question. A connection failure — the
REPL's initial handshake or a one-shot command's connect — is retried once
before giving up, and a drop mid-session is recovered by reopening. This keeps
a transient network blip from surfacing as a hard error.

## DeepWiki MCP server

This CLI talks to the official [DeepWiki MCP
server](https://docs.devin.ai/work-with-devin/deepwiki-mcp), which is free and
requires no authentication for public repositories.

The server exposes two wire protocols:

- **Streamable HTTP** — `https://mcp.deepwiki.com/mcp` (recommended)
- **SSE** — `https://mcp.deepwiki.com/sse` (legacy, being deprecated)

`repowiki-cli` speaks Streamable HTTP, so `DEEPWIKI_MCP_URL` should point at the
`/mcp` endpoint (the default).

### Use the same server from an AI app

The MCP server can also be added directly to MCP-capable clients. For Claude
Code:

```bash
claude mcp add -s user -t http deepwiki https://mcp.deepwiki.com/mcp
```

### Private repositories

`repowiki-cli` reaches public repositories only. For private repos, use the
[Devin MCP server](https://docs.devin.ai/work-with-devin/devin-mcp) with a Devin
API key. The complete documentation index lives at
<https://docs.devin.ai/llms.txt>.

## Development

```bash
uv sync
uv run pytest
```


# 以上只是复刻 wiki 查询、拉取、回复功能

如果是使用自己的api接入做wiki生成，不建议自己再做轮子，因为官方有cli工具用于生成

* 官方zread cli：https://github.com/ZreadAI/zread_cli
* 官方readmex cli：https://github.com/aibox22/readmeX
* 开源deepwiki cli：https://github.com/AsyncFuncAI/deepwiki-open

https://docs.devin.ai/work-with-devin/deepwiki-mcp