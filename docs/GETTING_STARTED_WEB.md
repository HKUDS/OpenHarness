# Getting Started with OpenHarness Web Frontend

Welcome! This guide will help you get the OpenHarness web frontend up and running in minutes.

## Prerequisites

Before you begin, ensure you have:

- ✅ **Python 3.10+** installed
- ✅ **Node.js 18+** installed
- ✅ **npm** (comes with Node.js)
- ✅ **OpenHarness** installed (`pip install -e .`)
- ✅ **API credentials** configured (`oh auth list`)

## Quick Start (5 Minutes)

### Step 1: Install Frontend Dependencies

**Unix/macOS:**
```bash
bash scripts/install-web.sh
```

**Windows:**
```bash
scripts\install-web.bat
```

**Manual installation:**
```bash
cd frontend/web
npm install
npm run build
```

### Step 2: Launch Web Server

```bash
oh web
```

You should see output like:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

### Step 3: Open in Browser

Navigate to: **http://localhost:8080**

You should see the OpenHarness web interface! 🎉

## Verification Checklist

- [ ] Server starts without errors
- [ ] Browser connects successfully
- [ ] Status shows "Connected" (green dot)
- [ ] Welcome message appears
- [ ] You can type and send messages
- [ ] Sidebar panels are accessible

## Common Configurations

### Use a Different Port

```bash
oh web --port 3000
# Then open http://localhost:3000
```

### Specify a Model

```bash
oh web --model sonnet
# or
oh web --model claude-sonnet-4-20250514
```

### Set Permission Mode

```bash
# Plan mode (requires approval for changes)
oh web --permission-mode plan

# Full auto mode (no approval needed)
oh web --permission-mode full_auto
```

### Set Working Directory

```bash
oh web --cwd /path/to/your/project
```

### Full Example

```bash
oh web \
  --host 0.0.0.0 \
  --port 8080 \
  --model sonnet \
  --max-turns 50 \
  --permission-mode default \
  --cwd ~/projects/my-app
```

## Using the Interface

### Chat View (Default)

The chat interface is perfect for:
- Conversational interactions
- Viewing tool outputs
- Multi-turn conversations
- Visual feedback

**How to use:**
1. Type your question in the input box
2. Press `Enter` to send (or click ➤)
3. Watch the response stream in real-time
4. Use `Shift+Enter` for multi-line input

### Terminal View

Switch to terminal view for:
- Command-line style work
- ANSI color output
- Traditional terminal experience
- Copy/paste friendly

**How to switch:**
- Click the terminal icon in the header (coming soon)
- Or use keyboard shortcut (Ctrl+T)

### Sidebar Panels

#### Tasks Panel
View background tasks and their progress:
- Running tasks with progress bars
- Completed/failed task history
- Task descriptions and status notes

#### MCP Servers Panel
Monitor connected MCP servers:
- Server connection status
- Available tools per server
- Tool count and health

#### Swarm Panel
Track multi-agent coordination:
- Active teammate agents
- Agent status and tasks
- Team notifications

#### TODO Panel
Manage your task list:
- Persistent TODO items
- Markdown formatting
- Auto-sync with MEMORY.md

## Development Mode

For active development with hot reload:

### Terminal 1: Backend
```bash
oh web --port 8080
```

### Terminal 2: Frontend Dev Server
```bash
cd frontend/web
npm run dev
```

### Browser
Open **http://localhost:3000**

Changes to frontend code will automatically reload!

## Troubleshooting

### "Connection refused" or "Can't connect"

**Solution:**
1. Verify server is running: `oh web`
2. Check port isn't blocked: `netstat -an | grep 8080`
3. Try different port: `oh web --port 3000`
4. Check firewall settings

### "Module not found" errors

**Solution:**
```bash
cd frontend/web
rm -rf node_modules package-lock.json
npm install
npm run build
```

### Blank page or loading forever

**Solution:**
1. Open browser DevTools (F12)
2. Check Console for errors
3. Check Network tab for failed requests
4. Verify backend is running
5. Try hard refresh (Ctrl+Shift+R)

### WebSocket connection failed

**Solution:**
1. Check browser console for WebSocket errors
2. Verify firewall allows WebSocket
3. Try different browser
4. Check proxy settings if behind corporate network

### API errors or authentication issues

**Solution:**
```bash
# Check credentials
oh auth list

# If no credentials, set them up
oh setup

# Or set environment variable
export ANTHROPIC_API_KEY=your_key_here
```

## Next Steps

### Explore Features

1. **Send a message** - Try "Hello, what can you help me with?"
2. **Check Tasks panel** - See background operations
3. **View MCP Servers** - Check connected tools
4. **Use TODO panel** - Create a task list
5. **Switch views** - Try terminal view

### Learn More

- **Quick Reference**: `docs/WEB_FRONTEND_QUICKSTART.md`
- **Full Documentation**: `docs/WEB_FRONTEND.md`
- **Implementation Details**: `docs/WEB_FRONTEND_IMPLEMENTATION.md`
- **Main README**: `README.md`

### Customize

- **Modify styles**: Edit files in `frontend/web/src/styles/`
- **Add components**: Create in `frontend/web/src/components/`
- **Extend backend**: Modify `src/openharness/web_server.py`
- **Update types**: Edit `frontend/web/src/types.ts`

## Tips & Best Practices

### Performance
- Use production build for best performance: `npm run build`
- Keep message history reasonable (auto-managed)
- Close unused sidebar panels

### Productivity
- Use Chat View for most interactions
- Use Terminal View for command-line work
- Monitor Tasks panel for background operations
- Keep TODO panel updated

### Security
- Use on localhost or trusted network
- Don't expose to public internet without auth
- Keep API keys secure (server-side only)
- Use environment variables for secrets

## Getting Help

### Resources
- Documentation: `docs/WEB_FRONTEND*.md`
- Browser Console: F12 → Console tab
- Backend Logs: Terminal output

### Support Channels
- GitHub Issues: https://github.com/HKUDS/OpenHarness/issues
- Documentation: See docs folder
- Community: Check README for links

## FAQ

**Q: Can I use this on mobile?**
A: The interface is responsive but optimized for desktop. Mobile support is planned.

**Q: Does it work offline?**
A: No, it requires connection to the backend server. Offline mode is planned.

**Q: Can I customize the theme?**
A: Yes! Edit CSS files in `frontend/web/src/styles/`. Theme editor is planned.

**Q: How do I save conversations?**
A: Conversations are saved in OpenHarness session storage automatically.

**Q: Can multiple users connect?**
A: Currently designed for single-user. Multi-user support would require auth.

**Q: Is it secure?**
A: For local use, yes. For public deployment, add authentication first.

## What's Next?

Now that you're set up, try:

1. Asking OpenHarness to help with a coding task
2. Exploring the different panels
3. Customizing the interface
4. Contributing improvements!

Happy coding! 🚀

---

**Need more help?** See the comprehensive documentation in the `docs/` folder or open an issue on GitHub.
