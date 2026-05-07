# v0.1.8 — Providers, ohmo Feishu Groups, and Safer Remotes

OpenHarness v0.1.8 is a stabilization and provider-expansion release. It adds more first-class provider workflows, improves ohmo's Feishu group experience, hardens remote-channel security, and fixes several Windows/MCP reliability issues.

## Highlights

- **New provider workflows**
  - Added NVIDIA NIM as a built-in OpenAI-compatible provider using `NVIDIA_API_KEY`.
  - Added ModelScope Inference API support.
  - Added Qwen (DashScope), MiniMax, and Gemini provider profiles.
  - Improved OpenAI-compatible API behavior, including explicit bearer authorization headers and `<think>` block filtering for compatible streaming responses.

- **ohmo Feishu group support**
  - Added Feishu managed group creation flow for ohmo.
  - Added gateway-scoped provider/model commands for chat-based operation.
  - Improved group routing and mention policy so ohmo responds in shared Feishu groups only when explicitly addressed.
  - Hardened Feishu attachment filename handling.

- **Security and remote-channel hardening**
  - Kept sensitive config/auth/provider/model/ship commands local-only by default in remote channels.
  - Kept bridge commands local-only by default.
  - Added coverage for bridge spawn blocking and remote gateway security behavior.
  - Rejected path traversal names during plugin uninstall.

- **Windows and shell reliability**
  - Fixed Windows agent/subagent spawning by direct-executing teammate argv instead of shell-wrapping Python paths.
  - Windows shell resolution now skips discovered `bash.exe` binaries that cannot actually run commands, falling back to PowerShell/cmd.
  - Improved Windows gateway process lifecycle handling.
  - Avoided shell execution when opening browsers on Windows.

- **MCP, tools, and stability**
  - MCP startup now isolates failed servers instead of aborting the whole OpenHarness startup.
  - Fixed subprocess stderr pipe deadlocks in grep/glob/bash/session runner paths.
  - Bounded large tool results in conversation history and improved compaction under large/vision contexts.
  - Improved skill frontmatter parsing with YAML `safe_load` for bundled and user skills.

- **TUI and UX fixes**
  - Restored raw `DEL` backspace handling for macOS Terminal-style environments.
  - Added better slash-command completion, markdown table rendering, spinner behavior, and escape interruption.
  - Added image-to-text fallback support for text-only models and `--vision-model` override.

## External contributors

Thanks to the external contributors whose PRs are included in this release:

- @Litianhui888 — MCP startup isolation (#237)
- @Hinotoi-agent — remote command security hardening (#232, #209, #208, #198, #197)
- @nsxdavid — Windows agent spawn fix (#231)
- @voidborne-d — bundled skill frontmatter parsing (#229)
- @Mcy0618 — image-to-text fallback and ModelScope support (#227, #224)
- @WANG-Guangxin — invalid regex fallback fix (#219)
- @glitch-ux — Windows browser auth safety, async coordinator draining, autopilot shell safety, hook events (#217, #200, #188, #170)
- @Escapingbug — Windows gateway lifecycle and Telegram proxy config fixes (#193, #192)
- @ZevGit — Qwen provider profile (#207)
- @yl-jiang — subprocess stderr deadlock fixes and OpenAI-compatible think-block filtering (#205, #174)
- @he-yufeng — TUI slash-command completion polish (#185)
- @powAu3 — raw DEL backspace fix (#182)
- @flobo3 — shell subprocess stdin default fix (#179)

## Install

```bash
pip install --upgrade openharness-ai==0.1.8
```

Or run the installer from the repository docs.
