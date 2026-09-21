# repowiki-cli

Query [DeepWiki](https://deepwiki.com), [Google Code Wiki](https://codewiki.google),
and [zread.ai](https://zread.ai) documentation for any public GitHub repository
from your terminal.

> 中文文档见 [README.zh-CN.md](README.zh-CN.md) · Chinese docs:
> [README.zh-CN.md](README.zh-CN.md)

## What it is

`repowiki-cli` is a Python/Typer CLI that reads AI-generated repository
documentation and answers questions about code, from the terminal. It speaks to
**three wiki services** behind a single uniform command surface, one namespace
per service:

| Service | Namespace | Transport | Auth |
|---------|-----------|-----------|------|
| **DeepWiki** | `deepwiki` | MCP (Streamable HTTP) + reverse REST/WebSocket | none |
| **Google Code Wiki** | `codewiki` | Google `batchexecute` RPC | none |
| **Zread** | `zread` | JSON REST + SSE | `ask` / `submit` need a token |

DeepWiki is served by two interchangeable backends:

| Backend | Transport | Commands | Richness |
|---------|-----------|----------|----------|
| **MCP** (official) | Streamable HTTP | `structure`, `contents`, `ask`, `cp` | body only |
| **Reverse** (`api.devin.ai`) | REST + WebSocket | `ask` (with flags) + `list` / `status` / `warm` / `get` / `stat` | body, summary, references, sources, stats |

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
repowiki-cli codewiki ask facebook/react "What is Fiber?"
repowiki-cli zread contents vercel/next.js              # overview page
```

## Command overview

| Command | Purpose | Service |
|---------|---------|---------|
| `structure REPO` | Print the documentation table of contents | DeepWiki (MCP) |
| `contents REPO` | Print the full documentation | DeepWiki (MCP) |
| `ask REPO [QUESTION]` | Answer a question (single-shot or interactive) | DeepWiki (MCP / reverse) |
| `list SEARCH` | Search indexed public repos | DeepWiki (reverse) |
| `status REPO` | Report a repo's indexing status | DeepWiki (reverse) |
| `warm REPO` | Pre-warm a repo's docs cache | DeepWiki (reverse) |
| `get QUERY_ID` | Replay a past answer by query id | DeepWiki (reverse) |
| `stat REPO` | Report a repo's index metadata | DeepWiki (reverse) |
| `cp REPO [OUTPUT_DIR]` | Export the whole wiki as Markdown + `llms.txt`/`README.md` | DeepWiki (MCP) |
| `structure REPO` | Print the documentation table of contents | CodeWiki |
| `contents REPO` | Print the full documentation | CodeWiki |
| `ask REPO [QUESTION]` | Answer a question (single-shot or interactive) | CodeWiki |
| `stat REPO` | Show the commit the wiki was generated from | CodeWiki |
| `cp REPO [OUTPUT_DIR]` | Export the whole wiki as Markdown + `llms.txt`/`README.md` | CodeWiki |
| `structure REPO` | Print the documentation table of contents | Zread |
| `contents REPO [SLUG]` | Print a page of documentation (default: overview) | Zread |
| `ask REPO [QUESTION]` | Answer a question (single-shot or interactive, needs token) | Zread |
| `find QUERY` | Search repositories | Zread |
| `stat REPO` | Report a repo's info and index status | Zread |
| `top [WEEKS]` | Show the trending list | Zread |
| `rand [TOPIC]` | Get a random repository recommendation | Zread |
| `cp REPO [OUTPUT_DIR]` | Export the whole wiki as Markdown + `llms.txt`/`README.md` | Zread |
| `submit REPO` | Submit a repo for indexing (needs token) | Zread |

Each service is documented in its own section below: [DeepWiki](#deepwiki),
[CodeWiki](#codewiki), [Zread](#zread).

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

DeepWiki `ask` additionally includes `summary`, `references`, `sources`, `stats`,
and `query_id` when the reverse backend provides them. Management commands
(`list` / `status` / `warm` / `get` / `stat`) omit `repo` and use `command` +
fields only. Errors go to stderr as `{"error": ..., "kind": ...}`.

## Saving (`--save`)

`--save` writes answers to a Markdown file:

- `--save PATH` writes to (and appends to) the given path, creating parent
  directories.
- A bare `--save` (all three services) auto-names the file
  `repowiki-<owner>-<repo>_<timestamp>.md` in the current directory.
- In interactive mode all answers in the session append to one file; single-shot
  answers append when the file already exists.
- Combine with `--json` to keep stdout as JSON while writing Markdown to the file.

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DEEPWIKI_MCP_URL` | DeepWiki MCP endpoint | `https://mcp.deepwiki.com/mcp` |
| `DEEPWIKI_API_URL` | DeepWiki reverse backend endpoint | `https://api.devin.ai` |
| `DEEPWIKI_REPL_RETRIES` | DeepWiki reverse REPL retry attempts | `4` |
| `DEEPWIKI_TIMEOUT` | DeepWiki reverse answer timeout in seconds | `120` (`300` for `--mode deep`) |
| `CODEWIKI_CACHE_DIR` | CodeWiki bootstrap cache directory | `$XDG_CACHE_HOME` or `~/.cache` |
| `ZREAD_TOKEN` | Zread auth token for `ask` / `submit` | — |
| `ZREAD_LANG` | Zread default language | `en` |
| `ZREAD_MODEL` | Zread `ask` model | `glm-5.1` |
| `REPOWIKI_MOCK_TEXT` | mock MCP result (tests) | — |
| `REPOWIKI_DEVIN_MOCK` | mock reverse answer (tests) | — |
| `REPOWIKI_CODEWIKI_MOCK` | mock CodeWiki result (tests) | — |
| `REPOWIKI_ZREAD_MOCK` | mock Zread result (tests) | — |

## DeepWiki

[DeepWiki](https://deepwiki.com) is the primary service, exposed under the
`deepwiki` namespace. It reads **public repositories** with **no auth**.

### `deepwiki structure`

```bash
repowiki-cli deepwiki structure REPO [--json]
```

Prints the documentation table of contents (MCP `read_wiki_structure`).

### `deepwiki contents`

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

### `deepwiki ask`

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

### `deepwiki list`

```bash
repowiki-cli deepwiki list SEARCH [--json]
```

Searches DeepWiki's public index (reverse `list_public_indexes`).

### `deepwiki status`

```bash
repowiki-cli deepwiki status REPO [--json]
```

Reports a repo's indexing state (reverse `public_repo_indexing_status`).
`unknown` is a normal result for an unindexed repo and exits `0`.

### `deepwiki warm`

```bash
repowiki-cli deepwiki warm REPO [--json]
```

Pre-warms a repo's docs cache (reverse `warm_public_repo`).

### `deepwiki get`

```bash
repowiki-cli deepwiki get QUERY_ID [--rich] [--sources] [--json] [--mermaid]
```

Replays a past answer by query id (reverse `get_query`).

### `deepwiki stat`

```bash
repowiki-cli deepwiki stat REPO [--human] [--stale] [--json]
```

Shows a repo's index metadata from the reverse `list_public_indexes` — the
short commit sha (last segment of the index `id`) and `last_modified` (the
"Last indexed" timestamp shown on deepwiki.com).

- `--human` — render `last_modified` as a local, space-separated time.
- `--stale` — compare the indexed short sha against GitHub HEAD (via
  `api.github.com/.../commits/HEAD`) and print `最新`/`过期`. Note: a refresh
  (re-index) has no public endpoint — `index_public_repo` is reCAPTCHA-gated —
  so `stat` can only *detect* staleness, not fix it.
- `--json` — emit a JSON envelope (with `stale` when `--stale` is set).

### `deepwiki cp`

```bash
repowiki-cli deepwiki cp REPO [OUTPUT_DIR]
```

Exports the full wiki (MCP `read_wiki_contents`) as one Markdown file per
`# Page:` section, plus `llms.txt` / `README.md` (index) and `llms-full.txt`
(concatenated). `OUTPUT_DIR` defaults to `owner_repo`.

**Implementation:** the raw Markdown is split on `# Page:` delimiters by
`shared/output.py::split_pages` (a payload with no delimiters becomes a single
`Overview` page). Files are written by the shared `shared/export.py::export_pages`
helper, which names each page `NN-slug.md` and also emits `llms.txt` (index of
`- [title](NN-slug.md)` links), a `README.md` with the same index for GitHub
auto-rendering, and `llms-full.txt` (the whole concatenated text).

### DeepWiki design

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

### DeepWiki backends in detail

**MCP backend (`services/deepwiki/client.py`)**

- Endpoint: `DEEPWIKI_MCP_URL`, default `https://mcp.deepwiki.com/mcp`.
- Speaks **Streamable HTTP** (the SSE endpoint is deprecated).
- Tools: `read_wiki_structure`, `read_wiki_contents`, `ask_question`.
- Tool arguments use camelCase: `repoName` (and `question` for `ask_question`).
- Connection lifecycle:
  - One-shot commands open/close a session per call.
  - The interactive REPL opens **one** session and reuses it across questions.
  - The initial connect is retried once on failure; a mid-session drop is
    recovered by reopening once.

**Reverse backend (`services/deepwiki/devin.py`)**

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

### DeepWiki error handling and exit codes

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

### DeepWiki streaming, retry, and citations

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

### DeepWiki Mermaid

`--mode codemap` returns a codemap (a `{"traces": [...]}` JSON blob). `--mermaid`
renders it as a `flowchart TB` with per-trace subgraphs and color styling. Paste
the output into mermaid.live, GitHub, or VS Code to view it. If the answer is
not a codemap, `--mermaid` warns and prints the plain text.

### DeepWiki usage recipes

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
repowiki-cli deepwiki stat Junjie-Zhu/IDPFold2 --human --stale
repowiki-cli deepwiki stat facebook/react --stale
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

### DeepWiki MCP server

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

### DeepWiki related tools

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
repowiki-cli codewiki ask REPO [QUESTION] [--rich] [--json] [--save [PATH]]
repowiki-cli codewiki stat REPO [--stale] [--json]
repowiki-cli codewiki cp REPO [OUTPUT_DIR]
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
repowiki-cli codewiki ask REPO [QUESTION] [--rich] [--json] [--save [PATH]]
```

With `QUESTION`, `ask` answers once and exits. Without it, `ask` starts an
interactive REPL — type one question per line and `/exit` (or `/quit`/`/q`) to
quit. CodeWiki's `ask` is stateless, so each question is independent (no thread
continuation).

- `--rich` — render the answer's Markdown with `rich`.
- `--json` — emit a JSON envelope. Ignored in interactive mode.
- `--save [PATH]` — save the answer to a Markdown file (see *Saving*). A bare
  `--save` auto-names the file in the current directory.

### `codewiki stat`

```bash
repowiki-cli codewiki stat REPO [--stale] [--json]
```

Shows the commit sha the CodeWiki documentation was generated from (parsed from
the wiki payload header by `codewiki/wiki.py::parse`).

- `--stale` — compare the wiki commit against GitHub HEAD (via
  `api.github.com/.../commits/HEAD`) and print `最新`/`过期`. CodeWiki has no
  timestamp, so there is no `--human`; the wiki sha is a prefix of the full
  GitHub sha when the wiki is current.
- `--json` — emit a JSON envelope (with `stale` when `--stale` is set).

**Implementation:** staleness is checked by the shared
`shared/github.py::fetch_github_head` (called from `CodeWikiClient.github_head()`),
which does `GET https://api.github.com/repos/{owner}/{name}/commits/HEAD` (with
`follow_redirects=True` to survive renamed-repo 301s) and returns the full
40-char `sha` plus `commit.committer.date`; `shared/github.py::format_stale`
renders the verdict. A wiki is current when the GitHub sha `startswith` the
wiki's (possibly short) sha.

### `codewiki cp`

```bash
repowiki-cli codewiki cp REPO [OUTPUT_DIR]
```

Exports the full wiki as one Markdown file per section, plus `llms.txt` /
`README.md` (index) and `llms-full.txt` (concatenated). `OUTPUT_DIR` defaults to
`owner_repo`.

**Implementation:** each `Section` is rendered via
`codewiki/wiki.py::render_section` (heading + body + `dot` diagrams) and the full
text via `render_markdown`; both feed the shared `shared/export.py::export_pages`
helper (see `deepwiki cp`).

## Zread

[zread.ai](https://zread.ai) is a third wiki service, exposed under the `zread`
namespace. Zread serves pre-generated docs for **public repositories**, and all
read commands need **no auth**. The commands `ask` and `submit` require a token
(see below).

> **Implementation note:** `structure`/`contents` fetch the wiki outline and page
> Markdown from zread's JSON REST API (`GET /api/v1/wiki/{id}` and
> `/api/v1/wiki/{id}/page/{slug}`), not by scraping the Next.js RSC flight
> payload. REST is more stable and faster than parsing `self.__next_f.push`. If
> those endpoints ever change, the previous RSC-scraping implementation is
> preserved in git history (`git log`) rather than kept as a fragile in-code
> fallback.

```bash
repowiki-cli zread structure REPO [--lang zh|en] [--json]
repowiki-cli zread contents REPO [SLUG] [--file PATH] [--start N] [--end M] [--lang zh|en] [--rich] [--json]
repowiki-cli zread ask REPO [QUESTION] [--model MODEL] [--lang zh|en] [--rich] [--json] [--save [PATH]] [--stream] [--show-reasoning]
repowiki-cli zread find QUERY [--limit N] [--lang zh|en] [--json]
repowiki-cli zread stat REPO [--lang zh|en] [--human] [--stale] [--json]
repowiki-cli zread search REPO QUERY [--lang zh|en] [--json]
repowiki-cli zread top [WEEKS] [--lang zh|en] [--json]
repowiki-cli zread rand [TOPIC] [--lang zh|en] [--json]
repowiki-cli zread cp REPO [OUTPUT_DIR] [--concurrency N] [--lang zh|en]
repowiki-cli zread submit REPO [--json]
repowiki-cli zread refresh REPO [--json]
```

Quick start:

```bash
repowiki-cli zread structure facebook/react          # table of contents
repowiki-cli zread contents vercel/next.js           # overview page
repowiki-cli zread find react                        # search repositories
```

The `--lang zh|en` flag selects the documentation language (default `en`, or the
`ZREAD_LANG` environment variable).

### `zread structure`

Prints the zread.ai table of contents for a repository.

- `--lang zh|en` — language.
- `--json` — emit a JSON envelope instead of text.

### `zread contents`

Prints a single page of Markdown documentation. With no `SLUG`, it prints the
overview (first) page.

The `REPO` argument also accepts a GitHub blob URL with an optional line
fragment, which reads that source file instead of a wiki page:

```bash
repowiki-cli zread contents https://github.com/o/r/blob/main/src/a.py#L10-L20
```

- `--file PATH` — read a source file from the repository instead of a wiki page
  (mutually exclusive with `SLUG`).
- `--start N` / `--end M` — with `--file`, restrict to a line range.
- `--lang zh|en` — language.
- `--rich` — render Markdown with `rich`.
- `--json` — emit a JSON envelope instead of Markdown.

### `zread ask`

```bash
repowiki-cli zread ask REPO [QUESTION] [--model MODEL] [--rich] [--json] [--save [PATH]] [--stream] [--show-reasoning]
```

With `QUESTION`, `ask` answers once and exits. Without it, `ask` starts an
interactive REPL — type one question per line and `/exit` (or `/quit`/`/q`) to
quit. In the REPL each turn is **threaded**: the same `talk_id` is reused and the
previous answer's message id is sent as `parent_message_id`, so follow-up
questions carry conversational memory. Type `/new` (or `/reset`) to start a fresh
thread.

Unlike the other commands, `ask` requires an auth token (a JWT). Log in to
zread.ai, open the browser DevTools console, and run
`JSON.parse(localStorage.getItem("CGX_AUTH_STORAGE")).state.token` — this returns
the token. Set it as the `ZREAD_TOKEN` environment variable.

- `--model MODEL` — model (default `glm-5.1`, or the `ZREAD_MODEL` environment
  variable). This maps to the web UI's `CGX_CHAT_MODEL` (e.g. `glm-5.1`,
  `claude-sonnet-4.6`).
- `--lang zh|en` — language.
- `--rich` — render the answer's Markdown with `rich`. Has no effect with
  `--stream` (the answer streams as plain text).
- `--json` — emit a JSON envelope. Ignored in interactive mode. Has no effect
  with `--stream`.
- `--save [PATH]` — save the answer to a Markdown file (see *Saving*). A bare
  `--save` auto-names the file in the current directory.
- `--stream` — stream the answer's `answer` SSE chunks to stdout as they arrive
  (plain text), instead of buffering until the full answer is ready.
- `--show-reasoning` — also show the model's reasoning trace (the
  `reasoning_content` SSE field, streamed before the answer). In `--stream` mode
  it prints a `reasoning:` block before the `answer:` block; otherwise it prints
  the trace dimmed above the answer. Has no effect with `--json`.

### `zread find`

Searches zread.ai for repositories.

- `--limit N` — cap the number of results.
- `--lang zh|en` — language.
- `--json` — emit a JSON envelope.

### `zread stat`

Prints repository info and index status on zread.ai.

- `--lang zh|en` — language.
- `--human` — render the timestamps (`created_at`, `updated_at`,
  `last_commit.when`) as human-readable local times.
- `--stale` — fetch GitHub HEAD and compare its commit sha against
  `last_commit.hash`, printing an up-to-date / stale verdict.
- `--json` — emit a JSON envelope.

```bash
❯ repowiki-cli zread stat google-deepmind/alphafold3 --human
## Zread: google-deepmind/alphafold3 (stat)

- repo_id: 5fa748a6-6785-11f0-817c-3a18d81350c2
- owner: google-deepmind
- name: alphafold3
- url: https://github.com/google-deepmind/alphafold3
- description: AlphaFold 3 inference pipeline.
- description_zh: AlphaFold 3 推理管线实现
- star_count: 8570
- language: python
- topics: []
- wiki_id: 89e1aa24-7878-494b-95a1-7de0c860b94e
- status: success
- visibility: public
- created_at: 1753248298 (2025-07-23 13:24:58 CST)
- updated_at: 1789875263 (2026-09-20 11:34:23 CST)
- last_commit: {'hash': 'c0f97eda2f1f482fd94d3a38bece18c7069b4a5c', 'when': 1787154197 (2026-08-19 23:43:17 CST)}

❯ repowiki-cli zread stat google-deepmind/alphafold3 --stale
## Zread: google-deepmind/alphafold3 (stat)

- repo_id: 5fa748a6-6785-11f0-817c-3a18d81350c2
- owner: google-deepmind
- name: alphafold3
- url: https://github.com/google-deepmind/alphafold3
- description: AlphaFold 3 inference pipeline.
- description_zh: AlphaFold 3 推理管线实现
- star_count: 8570
- language: python
- topics: []
- wiki_id: 89e1aa24-7878-494b-95a1-7de0c860b94e
- status: success
- visibility: public
- created_at: 1753248298
- updated_at: 1789875263
- last_commit: {'hash': 'c0f97eda2f1f482fd94d3a38bece18c7069b4a5c', 'when': 1787154197}

最新 (up-to-date): c0f97eda2f1f482fd94d3a38bece18c7069b4a5c
```

### `zread search`

Searches within a repository's wiki documentation for matching text, returning
the page title and highlighted matches.

```bash
repowiki-cli zread search REPO QUERY [--lang zh|en] [--json]
```

- `--lang zh|en` — language.
- `--json` — emit a JSON envelope.

### `zread top`

Prints the zread.ai trending list. `WEEKS` limits the number of week-groups shown.

- `--lang zh|en` — language.
- `--json` — emit a JSON envelope.

### `zread rand`

Prints a random repository recommendation, optionally filtered by `TOPIC`.

- `--lang zh|en` — language.
- `--json` — emit a JSON envelope.

### `zread cp`

Exports the whole wiki as Markdown (`NN-slug.md` files) plus `llms.txt`,
`README.md`, and `llms-full.txt` into `OUTPUT_DIR` (defaults to the repository
name).

- `--concurrency N` — parallel page fetches (default `5`).
- `--lang zh|en` — language.

### `zread submit`

Submits a repository for indexing on zread.ai. Requires a token (a JWT): log in
to zread.ai, run
`JSON.parse(localStorage.getItem("CGX_AUTH_STORAGE")).state.token` in the DevTools
console, and set the result as `ZREAD_TOKEN`. Without it, `submit` prints a
warning and skips. On success it also reports the indexing queue wait
(`backlog` repos ahead, `estimate_minutes` ETA).

- `--json` — emit a JSON envelope (includes an `eta` field).

### `zread refresh`

Requests a re-index (refresh) of a repository's wiki. No auth required.

```bash
repowiki-cli zread refresh REPO [--json]
```

- `--json` — emit a JSON envelope.

## Development

```bash
uv sync
uv run pytest
```
