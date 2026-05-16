# Web Frontend Integration Guide

This document describes how to integrate and use the OpenHarness web frontend.

## Overview

OpenHarness now provides two frontend options:

1. **Terminal UI (TUI)** - React-based terminal interface using Ink (default)
2. **Web UI** - Modern browser-based interface using React + Vite

Both frontends communicate with the same backend runtime, providing flexibility in how you interact with OpenHarness.

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Web Browser   │◄───────►│  FastAPI Server  │◄───────►│  OpenHarness    │
│   (React UI)    │  WS/HTTP │  (Python)        │  Runtime│  Core           │
└─────────────────┘         └──────────────────┘         └─────────────────┘
```

## Installation

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm or yarn

### Step 1: Install Python Dependencies

```bash
# From the project root
pip install -e .
```

This installs FastAPI, uvicorn, and other web dependencies.

### Step 2: Install Frontend Dependencies

```bash
cd frontend/web
npm install
```

### Step 3: Build Frontend (Production)

```bash
cd frontend/web
npm run build
```

This creates an optimized build in `frontend/web/dist/`.

## Usage

### Launch Web Server

```bash
# Basic usage
oh web

# With custom port
oh web --port 3000

# With model selection
oh web --model sonnet

# With permission mode
oh web --permission-mode plan

# Full example
oh web --host 0.0.0.0 --port 8080 --model sonnet --max-turns 50 --permission-mode default
```

### Access the Interface

Open your browser and navigate to:
- `http://localhost:8080` (default port)
- Or the port you specified with `--port`

## Features

### Chat Interface

The main chat interface provides:
- **Message History**: View all conversation messages
- **Streaming Responses**: See responses as they're generated
- **Tool Visualization**: View tool inputs and outputs
- **Status Indicators**: See when the assistant is busy
- **Error Handling**: Clear error messages and recovery

### Terminal View

For users who prefer a terminal experience:
- **xterm.js Integration**: Full terminal emulation
- **ANSI Color Support**: Proper color rendering
- **Scrollback**: 10,000 lines of history
- **Web Links**: Clickable URLs in output

### Sidebar Panels

#### Tasks Panel
View and monitor background tasks:
- Task status (pending, running, completed, failed)
- Progress indicators
- Status notes and descriptions

#### MCP Servers Panel
Monitor connected MCP servers:
- Connection status
- Available tools
- Server health

#### Swarm Panel
Track multi-agent coordination:
- Active teammates
- Agent status
- Task assignments

#### TODO Panel
Persistent TODO list:
- Markdown-formatted tasks
- Auto-sync with MEMORY.md
- Checkbox support

## Development

### Hot Reload Development

For active development with hot reload:

1. Start the backend:
```bash
oh web --port 8080
```

2. In another terminal, start Vite dev server:
```bash
cd frontend/web
npm run dev
```

3. Open `http://localhost:3000` in your browser

The Vite server proxies API requests to the backend on port 8080.

### Debugging

**Browser DevTools:**
- Open Chrome/Firefox DevTools (F12)
- Check Console for errors
- Monitor Network tab for WebSocket traffic

**Backend Logging:**
```bash
# Enable debug logging
export LOG_LEVEL=debug
oh web
```

**WebSocket Messages:**
Messages are prefixed with `OHJSON:` for easy filtering in browser console.

## Customization

### Theming

Modify CSS files in `frontend/web/src/styles/`:
- `App.module.css` - Main app styles
- `ChatView.module.css` - Chat interface
- `TerminalView.module.css` - Terminal view
- `Sidebar.module.css` - Sidebar panels
- `Header.module.css` - Top header

### Adding Features

1. **New Components**: Add to `frontend/web/src/components/`
2. **State Management**: Extend `useAppStore.ts`
3. **Backend Integration**: Update `web_server.py`
4. **Type Definitions**: Update `types.ts`

### API Extensions

Add new endpoints in `web_server.py`:

```python
@app.get("/api/custom")
async def custom_endpoint():
    return {"data": "value"}
```

Add WebSocket message handlers:

```python
async def handle_request(self, payload: dict):
    if payload.get('type') == 'custom_action':
        # Handle custom action
        pass
```

## Deployment

### Production Build

1. Build the frontend:
```bash
cd frontend/web
npm run build
```

2. Start the server:
```bash
oh web --host 0.0.0.0 --port 8080
```

### Docker Deployment

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml .
RUN pip install -e .

# Install Node.js
RUN apt-get update && apt-get install -y nodejs npm

# Build frontend
COPY frontend/web ./frontend/web
WORKDIR /app/frontend/web
RUN npm install && npm run build

# Expose port
EXPOSE 8080

# Run server
CMD ["oh", "web", "--host", "0.0.0.0", "--port", "8080"]
```

### Reverse Proxy (nginx)

Example nginx configuration:

```nginx
server {
    listen 80;
    server_name openharness.example.com;

    location / {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Security Considerations

### Authentication

The web interface currently has no authentication. For production use:

1. **Add Basic Auth** in FastAPI
2. **Use OAuth** integration
3. **Place behind reverse proxy** with auth
4. **Use VPN** or internal network only

### API Keys

- Never expose API keys in frontend code
- Use environment variables or secure config files
- Consider using a proxy for API calls

### CORS

For cross-origin requests, configure CORS in `web_server.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Troubleshooting

### Common Issues

**"Connection refused"**
- Ensure the web server is running
- Check firewall settings
- Verify port isn't in use

**"Module not found"**
- Run `npm install` in frontend/web
- Check Node.js version (>= 18)

**"Runtime not initialized"**
- Verify API credentials are configured
- Check `oh auth list` for active credentials
- Ensure network connectivity

**WebSocket disconnects**
- Check network stability
- Verify proxy/firewall allows WebSocket
- Increase timeout settings if needed

### Logs

**Frontend logs**: Browser console (F12)
**Backend logs**: Terminal output or configured log file

## Performance Optimization

### Frontend

- Enable production build (`npm run build`)
- Use code splitting for large components
- Optimize images and assets
- Enable gzip/brotli compression

### Backend

- Use uvicorn workers for concurrency
- Enable HTTP/2 support
- Configure appropriate timeouts
- Use connection pooling

## Contributing

Contributions to the web frontend are welcome! Please:

1. Follow existing code style
2. Add tests for new features
3. Update documentation
4. Test in multiple browsers

See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.

## Future Enhancements

Planned features:
- [ ] User authentication
- [ ] Session management
- [ ] Plugin marketplace
- [ ] Advanced settings UI
- [ ] Mobile responsive design
- [ ] PWA support
- [ ] Offline mode
- [ ] Custom theme editor

## Support

For issues or questions:
- GitHub Issues: https://github.com/HKUDS/OpenHarness/issues
- Documentation: https://github.com/HKUDS/OpenHarness/docs
