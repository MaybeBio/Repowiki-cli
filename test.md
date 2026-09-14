# repowiki-cli 使用示例

从终端查询任意 GitHub 公开仓库的 [DeepWiki](https://deepwiki.com) AI 文档。

## 安装

安装后即可直接在终端使用 `repowiki-cli` 命令（无需 `uv run` 前缀）：

```bash
# 方式一：从源码安装（当前目录）
pip install .            # 或 pip install -e .（开发模式，改代码即时生效）

# 方式二：uv 安装为命令行工具（当前目录）
uv tool install .

# 方式三：从 PyPI（包发布后）
pip install repowiki-cli
```

验证安装：

```bash
$ repowiki-cli --version
```

```
repowiki-cli 0.1.0
```

## 查看帮助

```bash
$ repowiki-cli --help
```

```
 Usage: repowiki-cli [OPTIONS] COMMAND [ARGS]...

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --version          Show the version and exit.                                │
│ --help             Show this message and exit.                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ structure  Show the documentation table of contents for a repository.        │
│ contents   Show the full documentation for a repository.                     │
│ ask        Ask a question about a repository (single-shot or interactive).   │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## structure — 目录结构

```bash
$ repowiki-cli structure facebook/react
```

```
## DeepWiki: facebook/react (structure)

Available pages for facebook/react:

- 1 React Repository Overview
  - 1.1 Repository Structure and Packages
  - 1.2 Feature Flags System
- 2 Core Reconciler Architecture
  - 2.1 Fiber Work Loop and Scheduling
  - 2.2 Hooks Implementation
  - 2.3 Host Configurations and Renderer Interface
  - 2.4 Suspense, Error Boundaries, and Concurrent Features
  - 2.5 Scheduler Package
- 3 Rendering Targets
  - 3.1 React DOM: Client Rendering
  - 3.2 React DOM: Event System
  - 3.3 Server-Side Rendering: Fizz
  - 3.4 React Server Components: Flight Protocol
  - 3.5 React Native Renderer (Fabric)
  - 3.6 View Transitions and Gesture Scheduling
- 4 React Compiler
  - 4.1 Compiler Pipeline and HIR
  - 4.2 Compiler Validation Passes
  - 4.3 Compiler Tooling: ESLint Plugin, Playground, LSP, and MCP Server
  - 4.4 Compiler Rust Port
- 5 React DevTools
  - 5.1 DevTools Backend: Hook, Agent, and Renderer Interface
  - 5.2 DevTools Frontend: Store, Components Panel, and Profiler
  - 5.3 DevTools Distribution: Extensions, Standalone, Inline, Facade, and CDT-MCP
- 6 Build System and Tooling
  - 6.1 Rollup Build Pipeline
  - 6.2 Jest Test Infrastructure
  - 6.3 ESLint, Flow, and Code Quality
  - 6.4 Release Process and CI/CD
- 7 Additional Packages and Utilities
  - 7.1 React Refresh (Fast Refresh)
  - 7.2 Test Renderer, react-is, and Utility Packages
  - 7.3 Fixtures and Integration Examples
- 8 Glossary
```

## contents — 完整文档

输出可能很长（完整 dump，不分页）。

```bash
$ repowiki-cli contents facebook/react
```

```
## DeepWiki: facebook/react (contents)

# Page: React Repository Overview

# React Repository Overview

<details>
<summary>Relevant source files</summary>

The following files were used as context for generating this wiki page:

- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- [README.md](README.md)
- [package.json](package.json)
...
[... truncated ...]
```

## ask — 单次问答

```bash
$ repowiki-cli ask facebook/react "What is Fiber?"
```

```
## DeepWiki: facebook/react (ask)

A Fiber is the fundamental unit of work within the React reconciler, representing a component and its state.  It acts as a node in a linked-tree structure, which React uses to track updates and rendering progress.

## Fiber Structure and Creation
A Fiber node is defined by the `Fiber` type, which includes properties like `tag` (identifying the type of fiber), `key`, `elementType`, `type`, and `stateNode` (the local state associated with the fiber).  It also contains pointers for building the tree structure: `return` (parent), `child`, and `sibling`.

Fibers are created using the `createFiber` function, which can either instantiate a `FiberNode` class or create a plain JavaScript object, depending on the `enableObjectFiber` feature flag.   The `FiberNode` constructor initializes various properties, including `tag`, `pendingProps`, `key`, `mode`, and `lanes`.

Different types of components, such as function components, class components, host components (like DOM elements), and special React elements (e.g., `Fragment`, `Suspense`), each correspond to a specific `WorkTag` within the Fiber architecture.   For example, `createFiberFromElement` is used to create a Fiber from a React element, determining its `fiberTag` and `type` based on the element's properties.

## Work-in-Progress (WIP)
During the reconciliation process, React uses a double-buffering technique where a "work-in-progress" Fiber tree is built.  The `createWorkInProgress` function is responsible for creating or cloning a Fiber node to represent the current work being processed.   This allows React to prepare updates without directly mutating the currently rendered Fiber tree.

## Fiber in the Reconciliation Process
Fibers are processed in two main phases: the "render phase" and the "commit phase".
*   **Render Phase**: This phase is asynchronous and interruptible.  During this phase, `beginWork` starts processing a Fiber node, calculating changes and determining work for its children.  After all children are processed, `completeWork` finalizes changes and bubbles up properties.
*   **Commit Phase**: This phase is synchronous and applies the changes to the host environment (e.g., the DOM).   This involves functions like `commitMutationEffects` for applying mutations and `commitLayoutEffects` for running layout effects.

Fibers also play a role in managing concurrent updates through `lanes`, a bitmask-based priority system.  The `markUpdateLaneFromFiberToRoot` function updates the `lanes` and `childLanes` properties of a Fiber and its ancestors to propagate update priorities up to the root.

## Debugging and DevTools
In development environments, Fibers include debug-specific fields like `_debugInfo`, `_debugOwner`, and `_debugStack`.  React DevTools uses Fiber instances to track components, creating `FiberInstance` objects that contain a reference to the actual Fiber data.  It also uses a `WeakMap` to assign unique IDs to Fibers for tracking purposes.

## Notes
The term "Fiber" is central to React's internal reconciliation algorithm, often referred to as "Fiber Reconciler". It represents a significant re-architecture of React's core to enable features like incremental rendering, concurrent mode, and improved error handling.

Wiki pages you might want to explore:
- [Glossary (facebook/react)](/wiki/facebook/react#8)

View this search on DeepWiki: https://deepwiki.com/search/what-is-fiber_eb93395d-7ca0-4e48-89d0-7a11597caf33
```

## ask — 交互式 REPL

省略 `question` 参数即进入交互模式；输入 `/exit`（或 `/quit`、`/q`、Ctrl-C、Ctrl-D）退出。

```bash
$ repowiki-cli ask facebook/react
```

```
## DeepWiki: facebook/react (ask)

Ask a question, or /exit to quit.

> What is the scheduler package?
The `scheduler` package is a standalone library within the React codebase responsible for managing task scheduling with multiple priority levels.  It orchestrates the execution of asynchronous work on the JavaScript main thread, ensuring that higher priority tasks run sooner, long-running work yields cooperatively to the browser to keep the UI responsive, and profiling hooks enable fine-grained performance tracing.

## Key Concepts

### Priority Levels
The `scheduler` package defines six discrete priority levels, which guide task execution urgency and timeout characteristics.  These are defined in `packages/scheduler/src/SchedulerPriorities.js`  and include `NoPriority`, `ImmediatePriority`, `UserBlockingPriority`, `NormalPriority`, `LowPriority`, and `IdlePriority`.  Each priority level has an associated timeout that controls when a task expires.

...
> /exit
```

## 仓库格式

三种写法均接受，会归一化为 `owner/repo`：

- `facebook/react`
- `github.com/facebook/react`
- `https://github.com/facebook/react`

## 错误处理

仓库名非法（不足两段）：

```bash
$ repowiki-cli structure facebook
```

```
Error: invalid repository reference: 'facebook'. Expected owner/repo, github.com/owner/repo, or a GitHub URL.
```
（exit 1）

仓库未索引（不存在）：

```bash
$ repowiki-cli structure facebook/this-repo-definitely-does-not-exist-xyz123
```

```
Error: Error fetching wiki for facebook/this-repo-definitely-does-not-exist-xyz123: Repository not found. Visit https://deepwiki.com/facebook/this-repo-definitely-does-not-exist-xyz123 to index it.
```
（exit 1）

## 开发

```bash
uv sync
uv run pytest        # 37 个测试全部离线可跑
```

> 注：`uv tool install .` 装的是当前源码快照；改代码后需 `uv tool upgrade repowiki-cli`（或 `uv tool install --force .`）重新安装。若用 `pip install -e .` 开发模式则无需重装。
