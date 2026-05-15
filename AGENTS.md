# AGENTS.md — MDB Dev Agent Operating Manual

This is the operating manual for all agents (Codex, Kimi, Gemini).
Read this once at the start of any session.
Read the project's own `Project.md` for project-specific context.
Do not read both — use `task_start()` which loads both automatically.

---

## The Golden Rule

**Every token you burn costs money. Every redundant file read, every
re-derived conclusion, every unanswered question that memory already
holds — is waste. Work surgically.**

---

## Start of Every Task — No Exceptions

```
task_start("<project>", "<what you need to do>")
```

This single call returns:
- Project stack, rules, key files (from Project.md)
- All prior agent findings for this project (from memory)
- Token efficiency reminders

Do not read Project.md manually. Do not call memory_list() first.
Just call `task_start()`. Everything is in there.

---

## File Reading Rules

### Rule 1: Never read a file without knowing why

Before reading any file, answer: *what specific thing am I looking for?*
If you can answer that, use `search_files()` to find it directly.
If you cannot answer it, use `file_outline()` to understand the structure first.

### Rule 2: Always outline before reading

```
# Wrong — burns tokens on content you don't need
read_file("ZenMSP", "backend/app/main.py")

# Right — see structure for free, then read only what you need
file_outline("ZenMSP", "backend/app/main.py")
# Returns: L12: class BillingService, L47: def calculate_renewal, L89: async def process_payment ...
read_file("ZenMSP", "backend/app/main.py", start_line=47, end_line=88)
```

### Rule 3: Files over 200 lines require a line range

The server enforces this. If you try to read a large file without a range,
you will get an error explaining how to proceed. This is intentional.

### Rule 4: Use search before reading

```
# Find where billing is handled — don't guess or read random files
search_files("ZenMSP", "calculate_billing", file_glob="*.py")
# Returns: backend/app/services/billing.py:142: def calculate_billing_cycle

# Now read only that section
file_outline("ZenMSP", "backend/app/services/billing.py")
read_file("ZenMSP", "backend/app/services/billing.py", start_line=142, end_line=180)
```

### Rule 5: The cache is your friend

`read_file()` caches results by file mtime. Repeated reads of unchanged
files cost zero disk I/O. `write_file()` automatically invalidates the cache.
You do not need to manage the cache manually.

---

## Code Change Workflow — Always Follow This Order

```
1.  task_start(project, task)              — load all context
2.  search_files(project, pattern)         — locate the relevant code
3.  file_outline(project, path)            — understand the file structure
4.  read_file(project, path, start, end)   — read only the relevant section
5.  write_file(project, path, content)     — make the change on disk
6.  lint(project, path)                    — catch issues immediately
7.  deploy_local(project)                  — build + restart containers
8.  http_request(method, url)              — verify the endpoint works
9.  memory_set("project:X:result", ...)    — save findings
10. git_push_staging(project, message)     — push + Telegram PR notification
```

Never skip steps 6, 7, or 8. Never push to main directly.

---

## Memory Rules

Memory is the primary mechanism for avoiding redundant work.

### Before starting any task
`task_start()` loads all relevant memory automatically. If you need a
specific entry: `memory_get("project:ZenMSP:billing-issue")`

### After completing any task
Always save findings before finishing:
```
memory_set("project:ZenMSP:billing-fix", "Fixed Numeric cast issue in billing.py L142. 
Root cause: SQLAlchemy returns Decimal, frontend expected string. 
Fixed by adding str() cast in the serializer.")
```

### Key naming convention
```
project:<name>:summary     — high-level project state
project:<name>:issue       — current bug or problem
project:<name>:last-deploy — result of last deploy
task:<slug>:result         — output of a completed task
```

### What to save
- Root cause of bugs found
- Files and line numbers that were changed
- Any decisions made about architecture or approach
- Test results and what they revealed
- Anything a future agent would need to not start from scratch

---

## Git Rules

- **Never push to main** — always use `git_push_staging()`
- `git_push_staging()` commits, pushes to `staging`, and sends a Telegram
  PR notification automatically
- The developer merges staging → main manually
- Commit messages: present tense, specific. e.g. `fix billing renewal date calculation`
- Only push after: lint passes + deploy works + endpoint verified

---

## Docker Rules

- All projects use Docker Compose with named volumes
- Code is edited on disk — containers mount named volumes
- After any code change: `deploy_local(project)` to rebuild and apply
- Scope to one service when possible: `deploy_local(project, service="backend")`
- To check health: `docker_compose_ps(project)`
- To debug: `docker_compose_logs(project, service, lines=100)`

---

## Linting Rules

Run after every `write_file()` call, before deploying:

```
lint(project, file_path)          # auto-detects language
```

For sensitive code (auth, billing, payments, API keys):
```
analyse_code(project, file_path)  # lint + semgrep security scan
```

Never push to staging with lint errors.

---

## API Verification

After every deploy, verify the relevant endpoint works:
```
http_request("GET",  "http://localhost:8000/api/clients")
http_request("POST", "http://localhost:8000/api/orders",
             body='{"client_id": 1, "product_id": 2}')
```

If the endpoint returns an error, fix it before pushing to staging.

---

## Agent Routing (Codex orchestration)

Codex is the orchestrator. Use `route_task()` to delegate:

| Agent | Best for |
|---|---|
| `kimi` | Large file analysis, frontend/UI work, visual tasks, wide codebase scans |
| `gemini` | Web research, docs lookup, tasks needing very large context windows |
| Codex (default) | Architecture, logic, code generation, debugging |

### How to delegate efficiently

Always pass a `context_key` so the sub-agent inherits prior work:
```
# Save context first
memory_set("project:ZenMSP:billing-issue", "Renewal dates off by one day. 
Bug in calculate_renewal() at billing.py L142.")

# Delegate with context — sub-agent starts informed, not cold
route_task(
    task="Analyse the billing service and propose a fix for the renewal date issue",
    agent="kimi",
    context_key="project:ZenMSP:billing-issue"
)

# Save the result
memory_set("project:ZenMSP:billing-analysis", result)
```

The sub-agent gets the context prepended to its prompt. It does not need
to re-read files to understand the problem.

---

## Notifications

Use `telegram_notify()` to keep the developer informed:

```
telegram_notify("✅ ZenMSP — billing fix deployed to staging. PR ready for review.")
telegram_notify("⚠️ ZenMSP — tests failing after migration. Need input on schema change.")
```

When to notify:
- Task completed — what changed and what was deployed
- Tests failing — summary of failures
- Waiting for a decision — what the options are
- PR ready — `git_push_staging()` does this automatically

Keep messages short. Include the project name. Use Markdown.

---

## Remote Server Rules

Remote deploys happen **after** the developer merges staging → main.
Never run `remote_deploy()` on unmerged code.

```
remote_list()                                      — see registered servers
remote_deploy(project, remote_path)                — full remote deploy (post-merge)
remote_logs(project, remote_path, service)         — check remote service logs
remote_exec(project, command)                      — run one-off command
```

---

## Dev Tools Available

All tools are pre-installed. Call them via MCP:

| Tool | Purpose | MCP call |
|---|---|---|
| ripgrep | Fast file search | `search_files()` |
| ast-grep | Structural code search | `ast_search()` |
| black | Python formatter | `format_file()` |
| prettier | JS/TS/CSS formatter | `format_file()` |
| ruff | Python linter | `lint()` |
| eslint | JS/TS linter | `lint()` |
| semgrep | Security scanning | `analyse_code()` |
| httpie | API testing | `http_request()` |
| jq | JSON queries | `jq_query()` |

Check availability: `tool_status()`
Install missing: `tool_install("tool-name")`

---

## What Not To Do

| Don't | Do instead |
|---|---|
| Read a whole file | `file_outline()` then `read_file(start, end)` |
| Read files to find code | `search_files(project, pattern)` |
| Start a task without context | `task_start(project, task)` |
| Push directly to main | `git_push_staging()` |
| Deploy without linting | `lint()` first |
| Deploy without verifying | `http_request()` after deploy |
| Finish without saving findings | `memory_set()` before done |
| Run `remote_deploy()` before merge | Wait for developer to merge |
| Ask for info already in Project.md | `task_start()` loads it |
| Dump >200 lines into context | Use line ranges always |

---

## Quick Reference

```
task_start(project, task)                    # always first
file_outline(project, path)                  # always before read_file
read_file(project, path, start, end)         # surgical reads only
write_file(project, path, content)           # all code changes
search_files(project, pattern, glob)         # find before reading
lint(project, path)                          # after every write
analyse_code(project, path)                  # sensitive code
deploy_local(project, service)               # apply changes
http_request(method, url)                    # verify after deploy
git_push_staging(project, message)           # when confirmed working
memory_set(key, value)                       # save findings
memory_get(key)                              # load prior findings
telegram_notify(message)                     # keep developer informed
route_task(task, agent, context_key)         # delegate to sub-agent
remote_deploy(project, path)                 # post-merge only
```
