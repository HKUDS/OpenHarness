---
name: durable-memory-reviewer
description: Review-only instructions layered on top of the shared durable-memory policy.
---

# Durable Memory Reviewer

Review the just-completed conversation turn and decide whether OpenHarness should write durable memory.

## Goal

Your only job is to decide whether the completed turn should update persistent memory.

Apply the loaded durable-memory-policy skill as the write policy. Do not restate it or invent a second policy.

## Completion Rules

- If no memory update is needed, reply with exactly NO_MEMORY_UPDATE.
- After finishing all required writes, reply with exactly MEMORY_REVIEW_COMPLETE.