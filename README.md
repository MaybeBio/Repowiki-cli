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
repowiki-cli ask facebook/react "What is Fiber?"
repowiki-cli ask facebook/react          # interactive REPL
```

`structure` prints the documentation table of contents; `contents` prints the
full documentation (may be large); `ask` answers a question (single-shot when a
question is passed, interactive REPL otherwise — type `/exit` to quit).

Repos may be given as `owner/repo`, `github.com/owner/repo`, or a full GitHub
URL. The MCP endpoint defaults to `https://mcp.deepwiki.com/mcp` and can be
overridden with `DEEPWIKI_MCP_URL`.

## Development

```bash
uv sync
uv run pytest
```
