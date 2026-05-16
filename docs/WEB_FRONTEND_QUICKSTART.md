# OpenHarness Web Frontend - Quick Reference

## 🚀 Quick Start

```bash
# Install dependencies
bash scripts/install-web.sh    # Unix/Mac
scripts\install-web.bat        # Windows

# Start web server
oh web

# Open browser
# → http://localhost:8080
```

## 📋 Common Commands

```bash
# Basic usage
oh web

# Custom port
oh web --port 3000

# With model selection
oh web --model sonnet

# With working directory
oh web --cwd /path/to/project

# With permission mode
oh web --permission-mode plan

# Full example
oh web --host 0.0.0.0 --port 8080 --model sonnet --max-turns 50
```

## 🎨 Interface Overview

```
┌─────────────────────────────────────────────────────────┐
│  ☰  OpenHarness          ● Connected  sonnet  [mode]   │ ← Header
├────┬────────────────────────────────────────────────────┤
│    │                                                    │
│ T  │  Welcome to OpenHarness                            │
│ a  │  Your AI-powered coding assistant                  │
│ s  │                                                    │
│ k  │  ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│ s  │  │    🤖    │ │    ⚙️    │ │    ⚠️    │          │ ← Chat
│    │  │   AI     │ │  Tools   │ │  Safe    │          │   View
│ M  │  │ Powered  │ │  43+     │ │  Guard   │          │
│ C  │  └──────────┘ └──────────┘ └──────────┘          │
│    │                                                    │
│ S  │  Ask OpenHarness to help with coding tasks...      │
│ w  │  ┌──────────────────────────────────────────┐ ➤   │ ← Input
│ a  │  └──────────────────────────────────────────┘     │
│ r  │                                                    │
│ m  └────────────────────────────────────────────────────┘
│    │
│ T  │  Navigation
│ O  │  ┌────────────────────────────┐
│ D  │  │ 📋 Tasks          (2)      │ ← Active Panel
│ O  │  │ 🧩 MCP Servers    (3)      │
│    │  │ 🐝 Swarm          (1)      │
│ S  │  │ ✅ TODO                    │
│    │  │ ⚙️  Settings               │
│    │  └────────────────────────────┘
└────┴────────────────────────────────────────────────────┘
   Sidebar              Main Content Area
```

## 🔧 Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line |
| `Ctrl+C` | Copy selected text |
| `☰` (Menu) | Toggle sidebar |

## 📊 Status Indicators

| Status | Meaning |
|--------|---------|
| 🟢 Connected | Backend is running |
| 🟡 Connecting | Establishing connection |
| 🔴 Disconnected | Connection lost |
| ⏳ Loading | Processing request |

## 🎯 Panel Guide

### Tasks Panel
- View background tasks
- Monitor progress
- See task status

### MCP Servers Panel
- Connected servers
- Available tools
- Server health

### Swarm Panel
- Active agents
- Team status
- Task assignments

### TODO Panel
- Persistent tasks
- Markdown support
- Auto-sync

## 🐛 Troubleshooting

### Can't connect?
```bash
# Check if server is running
oh web --port 8080

# Try different port
oh web --port 3000
```

### Build errors?
```bash
# Reinstall dependencies
cd frontend/web
rm -rf node_modules
npm install
npm run build
```

### WebSocket issues?
- Check browser console (F12)
- Verify firewall settings
- Try different browser

## 📝 Configuration

### Environment Variables
```bash
export OPENHARNESS_API_KEY="your-key"
export OPENHARNESS_MODEL="sonnet"
export OPENHARNESS_BASE_URL="https://api.example.com"
```

### Config Files
- `~/.openharness/settings.json` - User settings
- `CLAUDE.md` - Project instructions
- `MEMORY.md` - Persistent memory

## 🔗 Quick Links

- Documentation: `docs/WEB_FRONTEND.md`
- Implementation: `docs/WEB_FRONTEND_IMPLEMENTATION.md`
- Source: `frontend/web/`
- Issues: https://github.com/HKUDS/OpenHarness/issues

## 💡 Tips

1. **Use Chat View** for conversational interactions
2. **Use Terminal View** for command-line style work
3. **Check Tasks Panel** for background operations
4. **Monitor MCP Servers** for tool availability
5. **Use TODO Panel** for task tracking

## 🆘 Getting Help

1. Check documentation: `docs/WEB_FRONTEND.md`
2. View logs in browser console (F12)
3. Check backend terminal output
4. Search issues on GitHub
5. Create new issue with details

---

**Need more help?** See full documentation in `docs/WEB_FRONTEND.md`
