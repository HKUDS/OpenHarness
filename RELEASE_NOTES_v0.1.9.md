# v0.1.9 — Skill Workflows and Provider Key Updates

OpenHarness v0.1.9 is a small follow-up release after v0.1.8 focused on making skills easier to create and invoke, plus fixing provider API key updates.

## Highlights

- **Bundled skill creator**
  - Added a bundled `skill-creator` skill for creating, improving, and verifying OpenHarness/ohmo skills.
  - This makes repeatable workflows easier to capture as first-class skills.

- **User-invocable skill slash commands**
  - Skills marked as user-invocable can now be triggered directly with slash commands.
  - Slash-invoked skills support user arguments and can request a model override through skill metadata.

- **Provider API key update fix**
  - `oh setup` now lets users update the API key for an already-configured API-key provider profile.
  - `oh provider edit <profile> --api-key <key>` can replace a saved profile key directly.
  - `oh provider add ... --api-key <key>` can store a key while creating a provider profile.

## Fixes

- Fixed issue #238, where users could change a configured provider model but had no supported path to update the saved API key.

## Install

```bash
pip install --upgrade openharness-ai==0.1.9
```

## Contributors

This release is primarily a maintainer follow-up release. Thanks to the users and contributors who reported and validated the provider key update workflow, especially the reporter of #238.
