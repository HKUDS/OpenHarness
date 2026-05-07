---
name: skill-creator
description: >
  Create, improve, and verify OpenHarness skills. Use this whenever the user
  asks to create a new skill, convert a workflow into a skill, update an
  existing SKILL.md, add skills for oh/ohmo, design skill trigger behavior,
  or test whether a skill loads and works correctly.
---

# skill-creator

Create or improve OpenHarness skills in the directory-based `SKILL.md` format.

## When to use

Use this skill when the user wants to:

- create a new skill from a workflow, repeated task, domain guide, or tool process
- convert existing notes, prompts, or instructions into a reusable skill
- modify or harden an existing skill
- make a skill available to `oh`, `ohmo`, or a plugin
- debug why the `skill` tool cannot find or load a skill
- test trigger wording, skill metadata, or skill behavior

## OpenHarness skill locations

Choose the target deliberately:

- Built-in OpenHarness skills live in `src/openharness/skills/bundled/content/*.md`.
- User skills for `oh` live in `~/.openharness/skills/<skill-dir>/SKILL.md`.
- Private `ohmo` skills live in `~/.ohmo/skills/<skill-dir>/SKILL.md`.
- Plugin skills live in `<plugin-root>/skills/<skill-dir>/SKILL.md`.

OpenHarness user and plugin skills use a directory layout. Do not create flat
`*.md` user skills under `skills/`; they will not be loaded by the normal loader.

## Skill anatomy

Use this structure for user, ohmo, and plugin skills:

```text
my-skill/
├── SKILL.md
├── scripts/      # optional deterministic helpers
├── references/   # optional long docs loaded only when relevant
└── assets/       # optional templates or static files
```

Use this structure inside `SKILL.md`:

```markdown
---
name: my-skill
description: >
  What the skill does and exactly when to use it.
---

# my-skill

Short purpose statement.

## When to use

Trigger contexts in plain language.

## Workflow

Concrete steps the agent should follow.

## Rules

Important boundaries, verification, and failure handling.
```

## Workflow

1. Capture intent before writing.
   Ask or infer what the skill should help with, when it should trigger, what
   output it should produce, and what success looks like. If the conversation
   already contains the workflow, extract the sequence from history before
   asking more questions.

2. Inspect existing examples.
   Read nearby skills and loader behavior before choosing a layout. For
   OpenHarness, confirm whether the target is bundled, user, ohmo-private, or
   plugin-provided.

3. Write the metadata first.
   The `description` is the primary trigger hint shown in the available skills
   list. Make it specific and slightly assertive: include both what the skill
   does and the phrases or situations that should trigger it. Avoid vague
   descriptions like "Helpful notes for X".

4. Keep the body procedural.
   Use concise imperative steps. Explain why non-obvious constraints matter.
   Prefer general principles over overfitted examples. If a skill is getting
   long, move details into `references/` and point to the relevant file.

5. Add deterministic resources only when they pay for themselves.
   If the skill repeatedly needs the same script, template, schema, or checklist,
   place it under `scripts/`, `assets/`, or `references/` rather than making the
   model regenerate it every time.

6. Verify loading.
   Run a local loader check for the chosen target. For bundled skills, use:

   ```bash
   PYTHONPATH=src python - <<'PY'
   from openharness.skills import load_skill_registry
   for skill in load_skill_registry().list_skills():
       print(skill.name, skill.source, skill.path)
   PY
   ```

   For ohmo-private skills, include the extra skill directory:

   ```bash
   PYTHONPATH=src python - <<'PY'
   from openharness.skills import load_skill_registry
   from ohmo.workspace import get_skills_dir
   for skill in load_skill_registry(extra_skill_dirs=[get_skills_dir()]).list_skills():
       print(skill.name, skill.source, skill.path)
   PY
   ```

7. Test behavior.
   Create two or three realistic prompts that should use the skill. If the skill
   changes code or files, add regression tests around loading or command
   behavior. Run targeted tests first, then broader tests if the loader or
   runtime path changed.

8. Iterate from evidence.
   If a skill under-triggers, improve the frontmatter description. If it
   triggers but produces poor work, improve the body workflow. If agents repeat
   deterministic work, add a helper script or reference file.

## Writing rules

- Preserve the skill name when updating an existing skill unless the user
  explicitly asks to rename it.
- Do not overwrite user-created skills without reading the existing `SKILL.md`.
- Keep `SKILL.md` under roughly 500 lines; use `references/` for long material.
- Keep trigger guidance in frontmatter `description`, not buried only in the
  body.
- Make skills safe and unsurprising. Do not create skills that hide behavior,
  bypass permissions, exfiltrate data, or encourage unauthorized access.
- Prefer directory names that are lowercase kebab-case, even if the displayed
  skill `name` is more human-readable.
- Mention exact install or verification paths in the final response.

## Test prompts

After drafting a skill, propose a small eval set:

```json
{
  "skill_name": "my-skill",
  "evals": [
    {
      "id": "happy-path",
      "prompt": "A realistic user request that should trigger the skill.",
      "expected_output": "What good behavior looks like."
    },
    {
      "id": "near-miss",
      "prompt": "A similar request that should not trigger this skill.",
      "expected_output": "The agent should choose a different path."
    }
  ]
}
```

For objective skills, add assertions or tests. For subjective skills, collect
human feedback and revise the workflow from concrete complaints rather than
adding rigid rules.
