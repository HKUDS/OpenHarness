# Feature Test Matrix — Detailed Test Cases

## Engine & Tools

| Test | What to Verify | Key Assertion |
|------|---------------|---------------|
| Multi-turn memory | Set fact turn 1, recall turn 3 | Fact appears in turn 3 response |
| Tool chaining | glob → grep → read in one task | All 3 tools in tool list |
| Write→Edit→Read | Create, modify, verify file | File content matches expected |
| Parallel tools | 3+ tool calls in one response | 3+ tools in single turn |
| Error recovery | Tool fails, model adapts | Alternative tool used after error |
| Auto-compaction | 5+ tasks on shared engine | No context overflow crash |

## Swarm & Coordinator

| Test | What to Verify | Key Assertion |
|------|---------------|---------------|
| InProcessBackend | spawn → active → status → shutdown | All states transition correctly |
| Concurrent teammates | 2+ agents running simultaneously | Both complete, total time < 2x single |
| Coordinator + notifications | Multi-turn delegation with XML | Coordinator synthesizes worker results |
| Permission sync | request → pending → resolve | Pending count goes to 0 after resolve |

## Hooks, Skills, Plugins

| Test | What to Verify | Key Assertion |
|------|---------------|---------------|
| Hook blocks → adapt | pre_tool_use blocks bash | "bash" in errors, "glob" in tools |
| Skill invocation | Model calls skill tool | "skill" in tools, content drives next action |
| Plugin skill | Plugin provides skill | Loaded via skill tool, model follows it |
| Hook + skill combined | Hook gates writes, skill guides | Protected file untouched, new file created |

## Memory, Session, Config

| Test | What to Verify | Key Assertion |
|------|---------------|---------------|
| Memory frontmatter | YAML parsed, not "---" | description != "---", body searchable |
| Session resume | Save → load → continue | Model remembers prior context |
| Cost tracking | Tokens accumulate | in_tokens strictly increasing |
| Cron CRUD | Create, toggle, mark_run, delete | Job count correct at each step |

## Provider Compatibility

| Test | What to Verify | Key Assertion |
|------|---------------|---------------|
| Anthropic client | Standard tool calling | Tools execute, response coherent |
| OpenAI client | Tool calling + reasoning_content | No 400 error on tool call round-trip |
| OpenAI multi-turn | reasoning_content persists | 3+ turns without API error |
