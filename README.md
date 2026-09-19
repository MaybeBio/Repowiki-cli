# repowiki-cli

Query [DeepWiki](https://deepwiki.com) and [Google Code Wiki](https://codewiki.google)
documentation for any public GitHub repository from your terminal.

> 中文文档见 [README.zh-CN.md](README.zh-CN.md) · Chinese docs:
> [README.zh-CN.md](README.zh-CN.md)

## What it is

`repowiki-cli` is a Python/Typer CLI that reads AI-generated repository
documentation and answers questions about code, from the terminal. It speaks to
**two backends** behind a single uniform command surface:

| Backend | Transport | Commands | Richness |
|---------|-----------|----------|----------|
| **MCP** (official) | Streamable HTTP | `structure`, `contents`, `ask` | body only |
| **Reverse** (`api.devin.ai`) | REST + WebSocket | `ask` (with flags) + `list` / `status` / `warm` / `get` | body, summary, references, sources, stats |

The MCP backend is the official, documented DeepWiki server and is free for
public repos with no auth. The reverse backend is the underlying engine
`api.devin.ai` (same as the DeepWiki web app) — it is *not* a documented public
API, but it exposes engine selection (`fast`/`deep`/`codemap`), streaming,
conversation threading, and index-management endpoints that MCP does not.

## Install

```bash
uvx repowiki-cli --help
```

From source:

```bash
git clone <this-repo> && cd <this-repo>
uv sync
uv run repowiki-cli --help
```

## Quick start

```bash
repowiki-cli deepwiki structure facebook/react          # table of contents
repowiki-cli deepwiki contents vercel/next.js           # full documentation
repowiki-cli deepwiki ask facebook/react "What is Fiber?"
```

## Command overview

| Command | Purpose | Backend |
|---------|---------|---------|
| `structure REPO` | Print the documentation table of contents | MCP |
| `contents REPO` | Print the full documentation | MCP |
| `ask REPO [QUESTION]` | Answer a question (single-shot or interactive) | MCP by default; reverse with flags |
| `list SEARCH` | Search indexed public repos | Reverse |
| `status REPO` | Report a repo's indexing status | Reverse |
| `warm REPO` | Pre-warm a repo's docs cache | Reverse |
| `get QUERY_ID` | Replay a past answer by query id | Reverse |

## Command reference

### `structure`

```bash
repowiki-cli deepwiki structure REPO [--json]
```

Prints the documentation table of contents (MCP `read_wiki_structure`).

### `contents`

```bash
repowiki-cli deepwiki contents REPO [--page TITLE] [--rich] [--json]
```

Prints the full documentation (MCP `read_wiki_contents`), which can be large.

- `--page TITLE` — print only the page whose title matches (case-insensitive
  exact match). The `# Page:` delimiter is dropped, so the selected page shows a
  single heading. If no page matches, the available titles are listed (to
  stderr) and the command exits with error kind `page_not_found`.
- `--rich` — render Markdown with color/formatting via `rich`.
- `--json` — emit a JSON envelope instead of Markdown.

### `ask`

```bash
repowiki-cli deepwiki ask REPO [QUESTION] \
  [--rich] [--json] [--save [PATH]] \
  [--mode fast|deep|codemap] [--id QUERY_ID] \
  [--sources] [--no-summary] [--context TEXT] [--repo REPO]... \
  [--mermaid] [--stream] [--timeout SECONDS]
```

With a `QUESTION`, it answers once and exits. Without one, it enters an
interactive REPL (type `/exit` to quit).

**Backend routing.** `ask` uses the MCP backend unless at least one reverse flag
is present. Any of `--mode`, `--id`, `--sources`, `--repo`, `--context`,
`--no-summary`, or `--stream` switches it to the reverse backend. `--mermaid`
alone does **not** switch backends — pair it with `--mode codemap`.

- `--mode fast|deep|codemap` — engine selection. Mapping to the underlying
  engine id: `fast` → `multihop_faster`, `deep` → `agent`, `codemap` → `codemap`.
- `--id QUERY_ID` — reuse a previous query id to continue the same conversation
  thread.
- `--sources` — append line-numbered source-code slices for each citation.
- `--context TEXT` — pass additional context alongside the question.
- `--no-summary` — skip summary generation.
- `--repo REPO` — repeatable; ask one question against multiple repos at once
  (the positional `repo` plus every `--repo`).
- `--mermaid` — render a `codemap` answer as a Mermaid `flowchart TB`. If the
  answer is not a codemap, it warns and falls back to plain text. Paste the
  output into mermaid.live, GitHub, or VS Code to view it.
- `--stream` — stream answer text chunk-by-chunk over a WebSocket instead of
  waiting for the full answer, then append the summary and sources. Output is
  plain text, so `--rich` has no effect. A mid-answer drop falls back to
  polling. No effect with `--json`.
- `--timeout SECONDS` — answer timeout for the reverse backend. Defaults to
  `120`, or `300` for `--mode deep`. Overrides `DEEPWIKI_TIMEOUT`.
- `--save [PATH]` — save each answer to a Markdown file (see *Saving*).
- `--rich` — render the answer's Markdown with `rich`. No effect with
  `--stream`.
- `--json` — emit a JSON envelope. Ignored in interactive mode.

### `list`

```bash
repowiki-cli deepwiki list SEARCH [--json]
```

Searches DeepWiki's public index (reverse `list_public_indexes`).

### `status`

```bash
repowiki-cli deepwiki status REPO [--json]
```

Reports a repo's indexing state (reverse `public_repo_indexing_status`).
`unknown` is a normal result for an unindexed repo and exits `0`.

### `warm`

```bash
repowiki-cli deepwiki warm REPO [--json]
```

Pre-warms a repo's docs cache (reverse `warm_public_repo`).

### `get`

```bash
repowiki-cli deepwiki get QUERY_ID [--rich] [--sources] [--json] [--mermaid]
```

Replays a past answer by query id (reverse `get_query`).

## Design

The whole CLI shares one result type, `Answer`, so both backends feed the same
formatting layer:

```python
@dataclass
class Answer:
    body: str                          # main answer text
    summary: str | None = None         # reverse backend only
    references: list[Reference] = []   # {file_path, range_start, range_end}
    sources: list[SourceFile] = []     # {repo, path, content}
    stats: dict[str, float] = {}       # reverse backend only
    query_id: str | None = None        # reverse backend only
```

The MCP backend produces a bare `Answer(body=...)`. The reverse backend fills in
summary, references, sources, stats, and query_id — all carried by `--json`.

Source layout:

```
src/repowiki/
  cli.py      # Typer commands, routing, REPL, retry
  client.py   # MCP backend (DeepWikiClient) + error taxonomy
  devin.py    # reverse backend (DevinClient): REST + WebSocket + polling
  model.py    # Answer / Reference / SourceFile
  output.py   # formatting, page filter, citation fill, Mermaid-adjacent render
  codemap.py  # codemap JSON -> Mermaid flowchart
  repo.py     # repo reference normalization
  save.py     # --save file naming and append
```

## Backends in detail

### MCP backend (`client.py`)

- Endpoint: `DEEPWIKI_MCP_URL`, default `https://mcp.deepwiki.com/mcp`.
- Speaks **Streamable HTTP** (the SSE endpoint is deprecated).
- Tools: `read_wiki_structure`, `read_wiki_contents`, `ask_question`.
- Tool arguments use camelCase: `repoName` (and `question` for `ask_question`).
- Connection lifecycle:
  - One-shot commands open/close a session per call.
  - The interactive REPL opens **one** session and reuses it across questions.
  - The initial connect is retried once on failure; a mid-session drop is
    recovered by reopening once.

### Reverse backend (`devin.py`)

- Endpoint: `DEEPWIKI_API_URL`, default `https://api.devin.ai`.
- Answer flow (`ask`):
  1. `POST /ada/query` with the payload below, then either stream or poll.
  2. **Streaming** — open `wss://…/ada/ws/query/{query_id}` and assemble the
     answer from events.
  3. **Polling** — `GET /ada/query/{query_id}` on an interval until `state` is
     `done` or `error`.

Request payload (`POST /ada/query`):

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

Engine mapping: `fast` → `multihop_faster`, `deep` → `agent`, `codemap` → `codemap`.

WebSocket event types observed on the stream: `snapshot`, `file_contents`,
`stats`, `chunk`, `reference`, `summary_chunk`, `summary_done`, `done`. The
stream carries the complete answer, so no follow-up `GET` is needed after
streaming — `parse_response` assembles the `Answer` directly from the events.

Management endpoints:

| Method | Path | Used by |
|--------|------|---------|
| `GET` | `/ada/list_public_indexes?search_repo=` | `list` |
| `GET` | `/ada/public_repo_indexing_status?repo_name=` | `status` |
| `POST` | `/ada/warm_public_repo?repo_name=` | `warm` |
| `GET` | `/ada/query/{query_id}` | `get` |

## Error handling and exit codes

Exceptions are classified into a small taxonomy and mapped to an exit code:

| Error kind | Meaning | Exit code |
|-----------|---------|-----------|
| success | — | `0` |
| `not_indexed` | repo is not indexed on DeepWiki | `2` |
| `connection` | could not connect to the server | `3` |
| `tool` / `error` / `invalid_repo` / `invalid_input` / `page_not_found` / `unexpected` | anything else | `1` |

`ConnectionError` (transport-level failure) and `ToolError` (a `{"detail": …}`
or tool error surfaced from the server) are the two core exception types. HTTP
error bodies are surfaced via FastAPI's `detail` field so the CLI can classify
"not indexed" vs. a generic tool error.

With `--json`, errors go to **stderr** as a single line:

```json
{"error": "Could not connect to DeepWiki server...", "kind": "connection"}
```

## Streaming, retry, and citations

This applies to the **reverse** backend only.

**Single-shot `--stream`** streams chunks over the WebSocket to stdout, then
prints the summary/sources tail. Inline `[i]` citation markers are emitted the
moment each `reference` event arrives, so the streamed body shows citations that
line up with the `## Sources` list printed at the end.

**Interactive reverse REPL** polls for each answer and renders the complete
result, so inline `[i]` citations, the summary, and sources all line up. Each
follow-up question reuses the previous `query_id`, keeping one conversation
thread (`/new` starts a fresh thread).

**Retry.** Both single-shot `ask` and the interactive REPL retry transient
failures — `ConnectionError` or a `ToolError` containing `HTTP 5` — with
**jittered exponential backoff**: delay = `1.0s × 2^attempt + random(0 … 0.5s)`.
The default is **4 attempts**, overridable with `DEEPWIKI_REPL_RETRIES`. Retries
happen only while **nothing has streamed yet**. If a single-shot `--stream`
drops **mid-answer**, the CLI falls back to polling the same `query_id` and
re-prints the complete answer (body, citations, summary, sources); the part
already streamed appears twice, but the answer is never lost.

Why retry matters: the reverse endpoint is unofficial and occasionally refuses
the WebSocket handshake (a millisecond-fast connection reset, not a slow
timeout). Retry with backoff absorbs one-off blips.

**Citation line numbers.** The `range_start`/`range_end` attached to each
citation are model-estimated, so treat them as approximate rather than exact:

1. **Precision** — the range points at the *region* the model associated with a
   claim, not necessarily the exact lines that back it; it can be off.
2. **Version drift** — the numbers reflect whatever snapshot DeepWiki indexed,
   which may not match your local checkout.

The CLI passes these numbers through unchanged; it does not offset or
re-interpret them.

## Repo formats

`REPO` accepts any of:

- `owner/repo`
- `github.com/owner/repo`
- `www.github.com/owner/repo`
- `https://github.com/owner/repo` (optionally with `/tree/main` or `.git`)

Everything is normalized to `owner/repo`.

## JSON output

Main commands emit an envelope with `repo` and `command`:

```json
{
  "repo": "facebook/react",
  "command": "ask",
  "question": "What is Fiber?",
  "answer": "..."
}
```

`ask` additionally includes `summary`, `references`, `sources`, `stats`, and
`query_id` when the reverse backend provides them. Management commands
(`list` / `status` / `warm` / `get`) omit `repo` and use `command` + fields
only. Errors go to stderr as `{"error": ..., "kind": ...}`.

## Saving (`--save`)

- Bare `--save` auto-names the file `repowiki-<owner>-<repo>_<timestamp>.md` in
  the current directory.
- `--save PATH` writes to (and appends to) the given path, creating parent
  directories.
- In interactive mode all answers in the session append to one file; single-shot
  answers append when the file already exists.
- Combine with `--json` to keep stdout as JSON while writing Markdown to the file.

## Mermaid

`--mode codemap` returns a codemap (a `{"traces": [...]}` JSON blob). `--mermaid`
renders it as a `flowchart TB` with per-trace subgraphs and color styling. Paste
the output into mermaid.live, GitHub, or VS Code to view it. If the answer is
not a codemap, `--mermaid` warns and prints the plain text.

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DEEPWIKI_MCP_URL` | MCP endpoint | `https://mcp.deepwiki.com/mcp` |
| `DEEPWIKI_API_URL` | reverse backend endpoint | `https://api.devin.ai` |
| `DEEPWIKI_REPL_RETRIES` | reverse REPL retry attempts | `4` |
| `DEEPWIKI_TIMEOUT` | reverse answer timeout in seconds | `120` (`300` for `--mode deep`) |
| `REPOWIKI_MOCK_TEXT` | mock MCP result (tests) | — |
| `REPOWIKI_DEVIN_MOCK` | mock reverse answer (tests) | — |

## Usage recipes

The combinations below are grouped by intent. All assume `facebook/react` as the
repo unless noted.

**Read documentation (MCP)**

```bash
repowiki-cli deepwiki structure facebook/react
repowiki-cli deepwiki contents vercel/next.js
repowiki-cli deepwiki contents vercel/next.js --page "Getting Started"   # one page only
repowiki-cli deepwiki contents vercel/next.js --rich                      # rendered
```

**Ask questions (MCP)**

```bash
repowiki-cli deepwiki ask facebook/react "What is Fiber?"
repowiki-cli deepwiki ask facebook/react "What is Fiber?" --rich
repowiki-cli deepwiki ask facebook/react                                  # interactive
```

**Machine-readable output**

```bash
repowiki-cli deepwiki structure facebook/react --json
repowiki-cli deepwiki contents vercel/next.js --json
repowiki-cli deepwiki ask facebook/react "What is Fiber?" --json
repowiki-cli deepwiki ask facebook/react "What is Fiber?" --json --save out.md   # JSON + Markdown file
```

**Save answers to files**

```bash
repowiki-cli deepwiki ask facebook/react "What is Fiber?" --save            # auto-named
repowiki-cli deepwiki ask facebook/react "What is Fiber?" --save notes/answers.md
```

**Reverse backend — engine and depth**

```bash
repowiki-cli deepwiki ask facebook/react "What is Fiber?" --mode deep
repowiki-cli deepwiki ask facebook/react "Quick facts?" --mode fast
repowiki-cli deepwiki ask facebook/react "Show the data flow" --mode codemap --mermaid
```

**Reverse backend — sources and summary**

```bash
repowiki-cli deepwiki ask facebook/react "What is Fiber?" --mode deep --sources
repowiki-cli deepwiki ask facebook/react "What is Fiber?" --mode deep --no-summary
```

**Reverse backend — streaming and context**

```bash
repowiki-cli deepwiki ask facebook/react "What is Fiber?" --mode deep --stream
repowiki-cli deepwiki ask facebook/react "What is Fiber?" --mode deep --context "answer in Chinese"
```

**Reverse backend — timeout**

```bash
repowiki-cli deepwiki ask facebook/react "Deep dive?" --mode deep --timeout 600   # allow 10 min for deep answers
repowiki-cli deepwiki ask facebook/react "Quick facts?" --mode fast --timeout 30
DEEPWIKI_TIMEOUT=600 repowiki-cli deepwiki ask facebook/react "Deep dive?" --mode deep   # or via env var
```

**Reverse backend — threads and multi-repo**

```bash
repowiki-cli deepwiki ask facebook/react "Follow-up?" --id <query-id>      # continue a thread
repowiki-cli deepwiki ask facebook/react "diff?" --repo remix-run/react-router --repo TanStack/router
repowiki-cli deepwiki ask facebook/react --mode deep                        # interactive, auto-threads
```

**Management**

```bash
repowiki-cli deepwiki list react
repowiki-cli deepwiki status facebook/react
repowiki-cli deepwiki warm facebook/react
repowiki-cli deepwiki get <query-id>
repowiki-cli deepwiki get <query-id> --sources
repowiki-cli deepwiki get <query-id> --mermaid
```

**CodeWiki — read documentation (Google Code Wiki)**

```bash
repowiki-cli codewiki structure facebook/react
repowiki-cli codewiki contents vercel/next.js
repowiki-cli codewiki contents vercel/next.js --page "Getting Started"   # one section only
repowiki-cli codewiki contents vercel/next.js --rich                      # rendered
```

**CodeWiki — ask**

```bash
repowiki-cli codewiki ask facebook/react "What is Fiber?"
repowiki-cli codewiki ask facebook/react "What is Fiber?" --rich
repowiki-cli codewiki ask facebook/react                                    # interactive (type /exit to quit)
```

**CodeWiki — machine-readable and save**

```bash
repowiki-cli codewiki structure facebook/react --json
repowiki-cli codewiki contents vercel/next.js --json
repowiki-cli codewiki ask facebook/react "What is Fiber?" --json
repowiki-cli codewiki ask facebook/react "What is Fiber?" --save notes/answers.md   # path required (no bare --save)
```

**Scripting with exit codes**

```bash
repowiki-cli deepwiki ask some/repo "q?" --json > out.json
case $? in
  0) ;;                       # success
  2) echo "not indexed" ;;
  3) echo "connection error" ;;
  *) echo "other error" ;;
esac
```

## DeepWiki MCP server

The official [DeepWiki MCP server](https://docs.devin.ai/work-with-devin/deepwiki-mcp)
is free and requires no auth for public repos. It exposes two wire protocols:
Streamable HTTP (`/mcp`, recommended) and SSE (`/sse`, deprecated). `repowiki-cli`
speaks Streamable HTTP.

To add it to Claude Code:

```bash
claude mcp add -s user -t http deepwiki https://mcp.deepwiki.com/mcp
```

Private repositories are out of scope for `repowiki-cli`; use the
[Devin MCP server](https://docs.devin.ai/work-with-devin/devin-mcp) with a Devin
API key. The full documentation index lives at
<https://docs.devin.ai/llms.txt>.

## Related tools

These are reference/alternative CLIs for the same space — worth consulting
before re-implementing anything:

- [Zread CLI](https://github.com/ZreadAI/zread_cli) — generates wiki docs
  locally from your repo via an LLM (config `~/.zread/config.yaml`).
- [readmeX CLI](https://github.com/aibox22/readmeX) — official CLI.
- [deepwiki-open](https://github.com/AsyncFuncAI/deepwiki-open) — open-source
  DeepWiki CLI.

If the goal is *generating* a wiki from your own API rather than querying the
public DeepWiki index, the official CLIs above already solve it — don't
reinvent the wheel.

## CodeWiki

[Google Code Wiki](https://codewiki.google) is a second wiki service, exposed
under the `codewiki` namespace. CodeWiki reads **public repositories only** and
requires **no auth** — it does not support private repos.

```bash
repowiki-cli codewiki structure REPO [--json]
repowiki-cli codewiki contents REPO [--page TITLE] [--rich] [--json]
repowiki-cli codewiki ask REPO [QUESTION] [--rich] [--json] [--save PATH]
```

Quick start:

```bash
repowiki-cli codewiki structure facebook/react          # table of contents
repowiki-cli codewiki contents vercel/next.js           # full documentation
repowiki-cli codewiki ask facebook/react "What is Fiber?"
```

### `codewiki structure`

Prints the CodeWiki table of contents for a repository.

- `--json` — emit a JSON envelope instead of text.

### `codewiki contents`

Prints the full CodeWiki documentation for a repository, which can be large.

- `--page TITLE` — print only the page whose title matches (case-insensitive
  exact match). If no page matches, the available titles are listed (to stderr)
  and the command exits with error kind `page_not_found`.
- `--rich` — render Markdown with color/formatting via `rich`.
- `--json` — emit a JSON envelope instead of Markdown.

### `codewiki ask`

```bash
repowiki-cli codewiki ask REPO [QUESTION] [--rich] [--json] [--save PATH]
```

With `QUESTION`, `ask` answers once and exits. Without it, `ask` starts an
interactive REPL — type one question per line and `/exit` (or `/quit`/`/q`) to
quit. CodeWiki's `ask` is stateless, so each question is independent (no thread
continuation).

- `--rich` — render the answer's Markdown with `rich`.
- `--json` — emit a JSON envelope. Ignored in interactive mode.
- `--save PATH` — save the answer to a Markdown file (see *Saving*). A path is
  required (CodeWiki's `ask` does not auto-name on a bare `--save`).

## Development

```bash
uv sync
uv run pytest
```
