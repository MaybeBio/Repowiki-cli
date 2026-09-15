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

Repos may be given as `owner/repo`, `github.com/owner/repo`, or a full GitHub
URL. The MCP endpoint defaults to `https://mcp.deepwiki.com/mcp` and can be
overridden with `DEEPWIKI_MCP_URL`.

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