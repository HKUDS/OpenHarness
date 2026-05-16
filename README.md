-----

# 🎨 OpenHarness Web UI

A modern, high-performance web-based GUI for OpenHarness, providing a rich, "glassmorphism" inspired interface for your AI coding assistant. This frontend transforms the core agent infrastructure into a professional development workspace.

-----

## ✨ Key Frontend Features

### 💬 Advanced Chat Experience

  * **Multi-Session Management**: Create, rename, and delete multiple chat sessions with persistent history and active chat highlighting.
  * **Adjustable Input Architecture**: Dynamically resize the input box (80px to 300px) to accommodate complex multi-line prompts.
  * **Model Selector**: Quick-switch between available models (Claude 3.5 series, GPT-4 Turbo, etc.) directly from the header.
  * **Streaming Markdown**: Real-time rendering of structured Markdown, including tables, code fences, and mathematical blocks.

### 🛠️ Developer Toolkit

  * **Drag & Drop File Upload**: Supports multiple file uploads with visual feedback, file type icons, and size displays.
  * **MCP Server Management**: Dedicated panel to view connected Model Context Protocol servers, their health, and available tools.
  * **Swarm Coordination**: Monitor multi-agent teams, track teammate status, and view active background tasks.
  * **TODO Integration**: A persistent, syncable TODO list to manage project goals across sessions.

### 🛡️ Governance & Settings

  * **Permission Mode Toggle**: Switch between **Default** (auto-approve safe commands) and **Plan Mode** (review-only) via visual cards.
  * **Secure API Configuration**: Dedicated settings panel for managing LLM provider keys with visibility toggles.

-----

## 🎨 Modern Design System

The UI follows a cohesive **v2.0 Design Philosophy** focused on clarity and efficiency:

  * **Visual Aesthetic**: Dark-themed "Glassmorphism" with backdrop blur effects and modern gradients (Purple-to-Green accents).
  * **Typography**: Optimized for readability using **Inter** for UI text and **JetBrains Mono** for code elements.
  * **Command Palette (Ctrl+K)**: A centralized "Raycast-style" interface for lightning-fast navigation between views and panels.

-----

## 🚀 Quick Start

### 1\. Launch

Launch the web server with one command:

```bash
uv run oh web --port 8080
```

Then navigate to `http://localhost:8080` in your browser.

-----

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Ctrl + K` | Open Command Palette |
| `Ctrl + B` | Toggle Sidebar |
| ` Ctrl + \`` | Switch to Terminal View | |  `Ctrl + 1-4`| Switch Panels (Tasks, MCP, Swarm, TODO) | |`Ctrl + ,\` | Open Settings Panel |

-----

## 🔧 Technical Stack

  * **Framework**: React 18 with TypeScript.
  * **State**: Zustand for lightweight global state management.
  * **Real-time**: Socket.io for bidirectional communication with the FastAPI backend.
  * **Terminal**: xterm.js integration for traditional terminal emulation within the web view.
  * **Icons**: Lucide React icon set.

-----

## 🤝 Contributing

OpenHarness UI is a community-driven project. We welcome contributions to the React component library, CSS modules, and theme extensions. Please see [CONTRIBUTING.md](https://github.com/Shun-Calvin/OpenHarness-UI/blob/main/CONTRIBUTING.md) for local setup and PR expectations.

**License**: [MIT](https://github.com/Shun-Calvin/OpenHarness-UI/blob/main/LICENSE).
