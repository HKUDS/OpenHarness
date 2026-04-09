# 技能系统

技能（Skills）是 OpenHarness 的知识加载机制，支持按需从 Markdown 文件加载领域知识。与工具不同，技能在模型需要时动态加载，为 Agent 提供专业领域的指导。

## 架构总览

```mermaid
flowchart LR
    SkillRegistry --> SkillDefinition
    SkillRegistry --> load_skill_registry
    load_skill_registry --> Bundled[内置技能]
    load_skill_registry --> User[用户技能]
    load_skill_registry --> Plugin[插件技能]
    SkillDefinition --> name
    SkillDefinition --> description
    SkillDefinition --> content
```

## 核心类型

### SkillDefinition

```python
# src/openharness/skills/types.py
@dataclass(frozen=True)
class SkillDefinition:
    name: str              # 技能名称
    description: str      # 技能描述
    content: str          # Markdown 格式的技能内容
    source: str           # 来源: "bundled", "user", "plugin"
    path: str | None      # 文件路径
```

### SkillRegistry

```python
# src/openharness/skills/registry.py
class SkillRegistry:
    def register(self, skill: SkillDefinition) -> None: ...
    def get(self, name: str) -> SkillDefinition | None: ...
    def list_skills(self) -> list[SkillDefinition]: ...
```

## 技能加载流程

`load_skill_registry()` 按优先级加载技能：

```python
def load_skill_registry(cwd, extra_skill_dirs, extra_plugin_roots, settings):
    registry = SkillRegistry()

    # 1. 内置技能 (bundled)
    for skill in get_bundled_skills():
        registry.register(skill)

    # 2. 用户技能 (~/.openharness/skills/)
    for skill in load_user_skills():
        registry.register(skill)

    # 3. 额外目录
    for skill in load_skills_from_dirs(extra_skill_dirs):
        registry.register(skill)

    # 4. 插件技能
    for plugin in load_plugins(settings, cwd, extra_roots=extra_plugin_roots):
        if plugin.enabled:
            for skill in plugin.skills:
                registry.register(skill)

    return registry
```

## 技能文件格式

技能以 Markdown 文件形式存储，支持 YAML frontmatter：

```markdown
---
name: commit
description: Create clean, well-structured git commits
---

# Commit Skill

## When to use
Use this skill when the user asks you to create a git commit.

## Workflow
1. Review staged changes with `git status` and `git diff`
2. Write a concise commit message following conventional commits
3. Use `git commit -m "type(scope): description"`
```

### frontmatter 字段

| 字段 | 说明 | 必填 |
|-----|------|-----|
| `name` | 技能名称 | Yes |
| `description` | 简短描述 | No |

### 布局规范

技能文件支持两种布局：

```
# 布局 1: 直接技能
skills/
  SKILL.md              ← 技能内容

# 布局 2: 目录技能
skills/
  commit/
    SKILL.md            ← 技能内容
  review/
    SKILL.md            ← 技能内容
```

## 技能解析

`_parse_skill_markdown()` 负责解析技能文件：

```python
def _parse_skill_markdown(default_name: str, content: str) -> tuple[str, str]:
    name = default_name
    description = ""

    # 1. 尝试 YAML frontmatter
    if content starts with "---":
        frontmatter, body = parse_frontmatter(content)
        name = frontmatter.get("name", default_name)
        description = frontmatter.get("description", "")

    # 2. 回退: 从标题和首段提取
    if not description:
        for line in content.splitlines():
            if line.startswith("# "):
                name = line[2:].strip() or default_name
            elif line.strip() and not line.startswith("---"):
                description = line.strip()[:200]
                break

    return name, description
```

## 技能使用方式

### /skills 命令

用户可以通过 `/skills` 命令查看和加载技能：

```
/skills              ← 列出所有可用技能
/skills commit       ← 查看 commit 技能内容
```

### Skill 工具

模型可以通过 `Skill` 工具按需加载技能：

```python
# 加载指定的技能内容
skill_content = skill_registry.get("commit").content
```

## 内置技能

OpenHarness 预置了多个内置技能（位于 `src/openharness/skills/bundled/`）：

| 技能 | 说明 |
|-----|------|
| `commit` | Git 提交工作流 |
| `review` | 代码审查 |
| `debug` | 调试诊断 |
| `plan` | 实现计划设计 |
| `test` | 测试编写 |
| `simplify` | 代码简化重构 |

## 插件技能

插件可以贡献技能，格式与用户技能相同：

```
plugin/
  skills/
    SKILL.md           ← 插件技能
    custom-skill/
      SKILL.md         ← 另一个插件技能
```

## 兼容性

OpenHarness 技能系统与 [anthropics/skills](https://github.com/anthropics/skills) 格式完全兼容：

> 只需将 `.md` 文件复制到 `~/.openharness/skills/` 即可使用。

## 扩展点

### 1. 自定义技能加载源

扩展 `load_skills_from_dirs()` 支持新的技能来源：

```python
# 添加新的技能目录
skills = load_skills_from_dirs(["/custom/skills/path"])
```

### 2. 技能注册时机

技能在 `RuntimeBundle` 初始化时注册，可以动态添加：

```python
registry = load_skill_registry(cwd, extra_skill_dirs=["/path/to/skills"])
skill = registry.get("my-skill")
```

## 与其他模块的关系

- **Plugins** — 插件可以贡献技能
- **Prompts** — 技能内容可能注入到 System Prompt
- **Commands** — `/skills` 命令用于查看技能

## 关键文件

| 文件 | 职责 |
|-----|------|
| `skills/loader.py` | 技能加载逻辑 |
| `skills/registry.py` | SkillRegistry |
| `skills/types.py` | SkillDefinition 类型定义 |
| `skills/bundled.py` | 内置技能 |
| `plugins/loader.py` | 插件技能加载 |
