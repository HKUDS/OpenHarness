# OpenHarness Web Frontend

A modern web-based interface for OpenHarness, providing a rich GUI for interacting with your AI coding assistant.

## Features

- 🎨 **Modern UI** - Clean, dark-themed interface built with React
- 💬 **Chat Interface** - Conversational interface for interacting with OpenHarness
- 💻 **Terminal View** - Traditional terminal emulation for power users
- 📊 **Real-time Updates** - WebSocket-based live updates from the backend
- 🧩 **MCP Server Management** - View and manage connected MCP servers
- 🐝 **Swarm Coordination** - Monitor and manage multi-agent teams
- ✅ **Task Tracking** - View background tasks and their progress
- 📝 **TODO Integration** - Persistent TODO list management

## Quick Start

### 1. Install Dependencies

First, install the Python dependencies:

```bash
pip install -e .
```

Then install the frontend dependencies:

```bash
cd frontend/web
npm install
```

### 2. Build the Frontend (Optional for Development)

For production use, build the frontend:

```bash
cd frontend/web
npm run build
```

### 3. Launch the Web Server

```bash
oh web --port 8080
```

Or with options:

```bash
oh web --host 0.0.0.0 --port 8080 --model sonnet --permission-mode default
```

### 4. Open in Browser

Navigate to `http://localhost:8080` in your web browser.

## Development

### Run in Development Mode

Start the web server:

```bash
oh web --port 8080
```

In another terminal, start the Vite dev server:

```bash
cd frontend/web
npm run dev
```

The Vite dev server will run on `http://localhost:3000` and proxy API requests to the backend.

### Project Structure

```
frontend/web/
├── src/
│   ├── components/       # React components
│   │   ├── Header.tsx
│   │   ├── Sidebar.tsx
│   │   ├── ChatView.tsx
│   │   └── TerminalView.tsx
│   ├── hooks/            # Custom React hooks
│   │   └── useBackendConnection.ts
│   ├── store/            # State management
│   │   └── useAppStore.ts
│   ├── styles/           # CSS modules
│   └── types.ts          # TypeScript types
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## Configuration

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Host to bind the server to | `0.0.0.0` |
| `--port`, `-p` | Port to run on | `8080` |
| `--serve-frontend` | Serve static frontend files | `true` |
| `--cwd` | Working directory | Current dir |
| `--model`, `-m` | Model to use | Config default |
| `--max-turns` | Maximum agentic turns | Unlimited |
| `--permission-mode` | Permission mode | `default` |

### Environment Variables

- `OPENHARNESS_API_KEY` - API key for the LLM provider
- `OPENHARNESS_MODEL` - Default model to use
- `OPENHARNESS_BASE_URL` - Custom API base URL

## Architecture

The web frontend uses a client-server architecture:

### Frontend (React)
- **State Management**: Zustand for lightweight global state
- **WebSocket**: Socket.io for real-time bidirectional communication
- **UI Components**: Custom components with CSS modules
- **Terminal**: xterm.js for terminal emulation

### Backend (FastAPI)
- **WebSocket Server**: Handles real-time communication
- **Runtime Integration**: Connects to OpenHarness core runtime
- **Session Management**: Maintains conversation state
- **Event Broadcasting**: Pushes updates to connected clients

### Communication Protocol

Messages are prefixed with `OHJSON:` and contain JSON payloads:

```typescript
interface BackendEvent {
  type: 'ready' | 'state_snapshot' | 'transcript_item' | 
        'assistant_delta' | 'assistant_complete' | 'error';
  state?: Record<string, unknown>;
  item?: TranscriptItem;
  message?: string;
}
```

## API Endpoints

### WebSocket

- **URL**: `ws://localhost:8080/ws`
- **Purpose**: Real-time bidirectional communication

### REST

- `GET /api/health` - Health check
- `GET /api/state` - Get current session state
- `POST /api/submit` - Submit a prompt

## Troubleshooting

### Connection Issues

If the frontend can't connect to the backend:
1. Check that the web server is running
2. Verify the port isn't blocked by a firewall
3. Check browser console for error messages

### Build Errors

If the frontend build fails:
1. Clear `node_modules` and reinstall: `rm -rf node_modules && npm install`
2. Ensure Node.js >= 18 is installed
3. Check for TypeScript errors: `npm run build`

### API Errors

If you see API errors:
1. Verify your API key is configured: `oh auth list`
2. Check your provider configuration: `oh provider list`
3. Ensure you have internet connectivity

## Browser Support

- Chrome/Edge >= 90
- Firefox >= 88
- Safari >= 14

## Contributing

Contributions are welcome! Please see the main [CONTRIBUTING.md](../../CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](../../LICENSE) for details.
