"""FastAPI web server for OpenHarness frontend."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import socketio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from openharness.ui.runtime import build_runtime, start_runtime, handle_line, close_runtime

if TYPE_CHECKING:
    from openharness.api.client import SupportsStreamingMessages

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROTOCOL_PREFIX = 'OHJSON:'


def _get_doctor_summary(runtime_bundle: Any, cwd: str) -> dict[str, Any]:
    """Generate doctor summary from runtime state."""
    from openharness.config import load_settings
    from openharness.auth.manager import AuthManager
    from openharness.memory.paths import get_project_memory_dir
    
    # Default values
    result = {
        'cwd': cwd,
        'active_profile': 'unknown',
        'model': 'unknown',
        'provider_workflow': 'unknown',
        'auth_source': 'unknown',
        'permission_mode': 'default',
        'theme': 'dark',
        'output_style': 'default',
        'vim_mode': False,
        'voice_mode': False,
        'effort': 'medium',
        'passes': 1,
        'memory_dir': cwd,
        'plugin_count': 0,
        'mcp_configured': False,
        'auth_configured': False,
    }
    
    try:
        settings = load_settings()
        manager = AuthManager(settings)
        active_profile_name, active_profile = settings.resolve_profile()
        
        result['active_profile'] = active_profile_name
        result['model'] = settings.model or 'unknown'
        result['provider_workflow'] = active_profile.label
        result['auth_source'] = active_profile.auth_source
        result['permission_mode'] = settings.permission.mode
        result['theme'] = settings.theme
        result['output_style'] = settings.output_style
        result['vim_mode'] = settings.vim_mode
        result['voice_mode'] = settings.voice_mode
        result['effort'] = settings.effort
        result['passes'] = settings.passes
        
        try:
            memory_dir = get_project_memory_dir(cwd)
            result['memory_dir'] = str(memory_dir)
        except Exception:
            pass
        
        try:
            statuses = manager.get_profile_statuses()
            if active_profile_name in statuses:
                result['auth_configured'] = statuses[active_profile_name].get('configured', False)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"Failed to load settings for doctor: {e}")
    
    # Get state from runtime bundle if available
    if runtime_bundle and hasattr(runtime_bundle, 'app_state') and runtime_bundle.app_state:
        try:
            state = runtime_bundle.app_state.get()
            if state:
                result['permission_mode'] = getattr(state, 'permission_mode', result['permission_mode'])
                result['theme'] = getattr(state, 'theme', result['theme'])
                result['output_style'] = getattr(state, 'output_style', result['output_style'])
                result['vim_mode'] = getattr(state, 'vim_enabled', result['vim_mode'])
                result['voice_mode'] = getattr(state, 'voice_enabled', result['voice_mode'])
                result['effort'] = getattr(state, 'effort', result['effort'])
                result['passes'] = getattr(state, 'passes', result['passes'])
        except Exception:
            pass
    
    # Get plugin and MCP info from runtime bundle
    if runtime_bundle:
        try:
            if hasattr(runtime_bundle, 'plugins') and runtime_bundle.plugins:
                result['plugin_count'] = len(runtime_bundle.plugins)
        except Exception:
            pass
        try:
            if hasattr(runtime_bundle, 'mcp_manager') and runtime_bundle.mcp_manager:
                result['mcp_configured'] = len(runtime_bundle.mcp_manager.list_servers()) > 0
        except Exception:
            pass
    
    return result


class WebBackendHost:
    """Manages the backend host session for web frontend."""
    
    def __init__(self):
        self.runtime_bundle = None
        self.clients: set[str] = set()
        self.running = False
        self._permission_requests: dict[str, asyncio.Future[bool]] = {}
        self._permission_lock = asyncio.Lock()
        self._sio: socketio.AsyncServer | None = None
        
    def set_sio(self, sio: socketio.AsyncServer) -> None:
        """Set the Socket.IO server instance."""
        self._sio = sio
        
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        if not self._sio:
            logger.warning("Socket.IO server not set")
            return
        data = f"{PROTOCOL_PREFIX}{json.dumps(message)}"
        for sid in self.clients:
            try:
                await self._sio.emit('backend_event', data, to=sid)
            except Exception as e:
                logger.warning(f"Failed to send to {sid}: {e}")
    
    async def broadcast_with_sio(self, sio: socketio.AsyncServer, message: dict):
        """Broadcast message to all connected clients using provided sio."""
        data = f"{PROTOCOL_PREFIX}{json.dumps(message)}"
        for sid in self.clients:
            try:
                await sio.emit('backend_event', data, to=sid)
            except Exception as e:
                logger.warning(f"Failed to send to {sid}: {e}")
    
    async def ask_permission(self, tool_name: str, reason: str) -> bool:
        """Ask for permission via modal request to frontend."""
        async with self._permission_lock:
            request_id = uuid4().hex
            future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
            self._permission_requests[request_id] = future
            await self.broadcast({
                'type': 'modal_request',
                'modal': {
                    'kind': 'permission',
                    'request_id': request_id,
                    'tool_name': tool_name,
                    'reason': reason,
                }
            })
            try:
                return await asyncio.wait_for(future, timeout=300)
            except asyncio.TimeoutError:
                logger.warning(f"Permission request {request_id} timed out")
                return False
            finally:
                self._permission_requests.pop(request_id, None)
    
    def handle_permission_response(self, request_id: str, allowed: bool) -> bool:
        """Handle permission response from frontend."""
        if request_id in self._permission_requests:
            future = self._permission_requests[request_id]
            if not future.done():
                future.set_result(allowed)
                return True
        return False
    
    async def handle_request(self, sio: socketio.AsyncServer, sid: str, payload: dict):
        """Handle incoming request from frontend."""
        if not self.runtime_bundle:
            await self.broadcast_with_sio(sio, {
                'type': 'error',
                'message': 'Runtime not initialized'
            })
            return
        
        request_type = payload.get('type')
        
        # Handle permission response first (doesn't require runtime_bundle)
        if request_type == 'permission_response':
            request_id = payload.get('request_id')
            allowed = payload.get('allowed', False)
            if request_id and self.handle_permission_response(request_id, allowed):
                logger.info(f"Permission response processed: {request_id} -> {allowed}")
                # Send acknowledgment to frontend
                await self.broadcast_with_sio(sio, {
                    'type': 'permission_response_ack',
                    'request_id': request_id,
                    'success': True
                })
            else:
                logger.warning(f"Permission response not found or already resolved: {request_id}")
                # Send error acknowledgment to frontend
                await self.broadcast_with_sio(sio, {
                    'type': 'permission_response_ack',
                    'request_id': request_id,
                    'success': False,
                    'error': 'Request not found or already resolved'
                })
            return
        
        if request_type == 'set_model':
            # Handle model change request from frontend
            model = payload.get('model')
            if model:
                try:
                    # Update the engine's model
                    self.runtime_bundle.engine.set_model(model)
                    # Update app state
                    self.runtime_bundle.app_state.set(model=model)
                    # Broadcast the updated state to all clients
                    state = self.runtime_bundle.app_state.get()
                    await self.broadcast_with_sio(sio, {
                        'type': 'state_snapshot',
                        'state': {
                            'model': model,
                            'permission_mode': state.permission_mode,
                            'working_directory': state.cwd,
                        }
                    })
                    logger.info(f"Model changed to: {model}")
                except Exception as e:
                    logger.exception("Error setting model")
                    await self.broadcast_with_sio(sio, {
                        'type': 'error',
                        'message': f'Failed to set model: {str(e)}'
                    })
            return
        
        if request_type == 'config_update':
            # Handle general config update
            config = payload.get('config', {})
            try:
                if 'permission_mode' in config:
                    # Normalize permission mode value (handle legacy 'auto' value)
                    permission_mode_value = config['permission_mode']
                    if permission_mode_value == 'auto':
                        permission_mode_value = 'full_auto'
                    
                    self.runtime_bundle.app_state.set(permission_mode=permission_mode_value)
                    # Update the permission checker with the new mode
                    from openharness.config.settings import PermissionSettings
                    from openharness.permissions.checker import PermissionChecker
                    from openharness.permissions.modes import PermissionMode
                    
                    # Get current settings and update permission mode
                    current_settings = self.runtime_bundle.current_settings()
                    new_permission_settings = PermissionSettings(
                        mode=PermissionMode(permission_mode_value),
                        allowed_tools=current_settings.permission.allowed_tools,
                        denied_tools=current_settings.permission.denied_tools,
                        path_rules=current_settings.permission.path_rules,
                        denied_commands=current_settings.permission.denied_commands,
                    )
                    new_checker = PermissionChecker(new_permission_settings)
                    self.runtime_bundle.engine.set_permission_checker(new_checker)
                    logger.info(f"Permission mode updated to: {permission_mode_value}")
                    
                if 'model' in config:
                    self.runtime_bundle.engine.set_model(config['model'])
                    self.runtime_bundle.app_state.set(model=config['model'])
                
                # Broadcast updated state
                state = self.runtime_bundle.app_state.get()
                await self.broadcast_with_sio(sio, {
                    'type': 'state_snapshot',
                    'state': {
                        'model': state.model,
                        'permission_mode': state.permission_mode,
                        'working_directory': state.cwd,
                    }
                })
                logger.info(f"Config updated: {config}")
            except Exception as e:
                logger.exception("Error updating config")
                await self.broadcast_with_sio(sio, {
                    'type': 'error',
                    'message': f'Failed to update config: {str(e)}'
                })
            return
        
        if request_type == 'submit_line':
            line = payload.get('line', '')
            
            async def print_system(message: str):
                await self.broadcast_with_sio(sio, {
                    'type': 'system',
                    'message': message
                })
            
            async def render_event(event):
                from openharness.engine.stream_events import (
                    AssistantTextDelta,
                    AssistantTurnComplete,
                    ErrorEvent,
                    StatusEvent,
                    ToolExecutionCompleted,
                    ToolExecutionStarted,
                )
                
                if isinstance(event, AssistantTextDelta):
                    await self.broadcast_with_sio(sio, {
                        'type': 'assistant_delta',
                        'message': event.text
                    })
                elif isinstance(event, AssistantTurnComplete):
                    await self.broadcast_with_sio(sio, {
                        'type': 'assistant_complete',
                        'message': event.message.text.strip()
                    })
                    await self.broadcast_with_sio(sio, {
                        'type': 'line_complete'
                    })
                elif isinstance(event, ToolExecutionStarted):
                    await self.broadcast_with_sio(sio, {
                        'type': 'transcript_item',
                        'item': {
                            'role': 'tool',
                            'tool_name': event.tool_name,
                            'tool_input': event.tool_input
                        }
                    })
                elif isinstance(event, ToolExecutionCompleted):
                    await self.broadcast_with_sio(sio, {
                        'type': 'transcript_item',
                        'item': {
                            'role': 'tool_result',
                            'tool_name': event.tool_name,
                            'output': event.output,
                            'is_error': event.is_error
                        }
                    })
                elif isinstance(event, ErrorEvent):
                    await self.broadcast_with_sio(sio, {
                        'type': 'error',
                        'message': event.message,
                        'recoverable': event.recoverable
                    })
                elif isinstance(event, StatusEvent):
                    await self.broadcast_with_sio(sio, {
                        'type': 'status',
                        'message': event.message
                    })
            
            async def clear_output():
                pass
            
            try:
                await handle_line(
                    self.runtime_bundle,
                    line,
                    print_system=print_system,
                    render_event=render_event,
                    clear_output=clear_output,
                )
            except Exception as e:
                logger.exception("Error handling line")
                await self.broadcast_with_sio(sio, {
                    'type': 'error',
                    'message': str(e)
                })
        
        if request_type == 'clear_conversation':
            # Clear the backend conversation history for new chat
            try:
                self.runtime_bundle.engine.clear()
                # Notify frontend that conversation was cleared
                await self.broadcast_with_sio(sio, {
                    'type': 'conversation_cleared'
                })
                logger.info("Conversation cleared for new chat")
            except Exception as e:
                logger.exception("Error clearing conversation")
                await self.broadcast_with_sio(sio, {
                    'type': 'error',
                    'message': f'Failed to clear conversation: {str(e)}'
                })
            return
        
        elif request_type == 'shutdown':
            self.running = False


# Global backend host instance
backend_host = WebBackendHost()

# Create Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', path='/socket.io')

# Set the sio on the backend_host
backend_host.set_sio(sio)


def create_app(
    *,
    cwd: str | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
    api_format: str | None = None,
    api_client: SupportsStreamingMessages | None = None,
    permission_mode: str | None = None,
    frontend_dir: Path | None = None,
) -> FastAPI:
    """Create FastAPI application for web frontend."""
    
    app = FastAPI(title="OpenHarness Web")
    
    # Define API routes first (before catch-all static route)
    @app.get("/api/health")
    async def health_check():
        return {"status": "healthy", "connected": len(backend_host.clients)}
    
    @app.get("/api/state")
    async def get_state():
        # Get actual state from runtime if available
        if backend_host.runtime_bundle:
            try:
                state_obj = backend_host.runtime_bundle.app_state.get()
                return {
                    'permission_mode': getattr(state_obj, 'permission_mode', permission_mode or 'default'),
                    'model': getattr(state_obj, 'model', model),
                    'working_directory': getattr(state_obj, 'cwd', cwd),
                }
            except Exception as e:
                logger.warning(f"Failed to get runtime state: {e}")
        
        # Fallback to initial parameters
        return {
            'permission_mode': permission_mode or 'default',
            'model': model,
            'working_directory': cwd,
        }
    
    @app.get("/api/plugins")
    async def get_plugins():
        """Get list of loaded plugins."""
        from openharness.config import load_settings
        from openharness.plugins import load_plugins
        
        settings = load_settings()
        plugins = load_plugins(settings, cwd or str(Path.cwd()))
        
        result = []
        for plugin in plugins:
            result.append({
                'name': plugin.name,
                'description': plugin.description,
                'version': plugin.manifest.version,
                'enabled': plugin.enabled,
                'path': str(plugin.path),
                'skills': [{'name': s.name, 'description': s.description} for s in plugin.skills],
                'commands': [{'name': c.name, 'description': c.description} for c in plugin.commands],
                'agents': [{'name': a.name, 'description': a.description} for a in plugin.agents],
                'hooks_count': sum(len(h) for h in plugin.hooks.values()),
                'mcp_servers': list(plugin.mcp_servers.keys()),
            })
        return {'plugins': result, 'total': len(result), 'enabled': sum(1 for p in plugins if p.enabled)}
    
    @app.get("/api/tools")
    async def get_tools():
        """Get list of registered tools."""
        from openharness.tools import create_default_tool_registry
        
        registry = create_default_tool_registry()
        if backend_host.runtime_bundle:
            try:
                registry = backend_host.runtime_bundle.tool_registry
            except Exception:
                pass
        
        result = []
        for tool in registry.list_tools():
            schema = tool.to_api_schema()
            result.append({
                'name': tool.name,
                'description': tool.description,
                'input_schema': schema.get('input_schema', {}),
                'is_read_only': hasattr(tool, 'is_read_only'),
            })
        return {'tools': result, 'total': len(result)}
    
    @app.get("/api/hooks")
    async def get_hooks():
        """Get list of configured hooks."""
        from openharness.config import load_settings
        from openharness.plugins import load_plugins
        from openharness.hooks.loader import load_hook_registry
        
        settings = load_settings()
        plugins = load_plugins(settings, cwd or str(Path.cwd()))
        registry = load_hook_registry(settings, plugins)
        
        result = []
        for event in registry._hooks.keys():
            hooks = registry.get(event)
            for hook in hooks:
                hook_info = {
                    'event': event.value,
                    'type': hook.type,
                    'matcher': getattr(hook, 'matcher', None),
                    'timeout_seconds': getattr(hook, 'timeout_seconds', 30),
                    'block_on_failure': getattr(hook, 'block_on_failure', False),
                }
                if hook.type == 'command':
                    hook_info['command'] = hook.command
                elif hook.type == 'prompt':
                    hook_info['prompt'] = hook.prompt
                elif hook.type == 'http':
                    hook_info['url'] = hook.url
                elif hook.type == 'agent':
                    hook_info['prompt'] = hook.prompt
                result.append(hook_info)
        return {'hooks': result, 'total': len(result), 'events': [e.value for e in registry._hooks.keys()]}
    
    @app.get("/api/prompts")
    async def get_prompts():
        """Get prompt configuration."""
        from openharness.config import load_settings
        from openharness.prompts import discover_claude_md_files, get_environment_info
        
        settings = load_settings()
        env_info = get_environment_info()
        
        # Discover CLAUDE.md files
        claude_md_files = []
        try:
            discovered = discover_claude_md_files(cwd or str(Path.cwd()))
            for path, rel in discovered:
                claude_md_files.append({
                    'path': str(path),
                    'relative': rel,
                    'exists': path.exists(),
                })
        except Exception:
            pass
        
        return {
            'system_prompt': settings.system_prompt,
            'claude_md_files': claude_md_files,
            'environment': env_info,
            'model': settings.model,
            'effort': settings.effort,
            'passes': settings.passes,
        }
    
    @app.get("/api/commands")
    async def get_commands():
        """Get list of registered slash commands."""
        from openharness.commands.registry import create_default_command_registry
        
        registry = create_default_command_registry()
        if backend_host.runtime_bundle:
            try:
                registry = backend_host.runtime_bundle.commands
            except Exception:
                pass
        
        result = []
        for cmd in registry.list_commands():
            result.append({
                'name': f"/{cmd.name}",
                'description': cmd.description,
                'template': getattr(cmd, 'template', None),
                'category': getattr(cmd, 'category', None),
            })
        return {'commands': result, 'total': len(result)}
    
    @app.get("/api/providers")
    async def get_providers():
        """Get list of available providers."""
        from openharness.api.registry import PROVIDERS
        from openharness.config.settings import default_provider_profiles
        
        profiles = default_provider_profiles()
        providers_list = []
        
        for spec in PROVIDERS:
            providers_list.append({
                'name': spec.name,
                'display_name': spec.display_name or spec.name.title(),
                'backend_type': spec.backend_type,
                'env_key': spec.env_key,
                'default_base_url': spec.default_base_url,
                'is_gateway': spec.is_gateway,
                'is_local': spec.is_local,
                'is_oauth': spec.is_oauth,
                'keywords': list(spec.keywords),
            })
        
        profiles_list = []
        for name, profile in profiles.items():
            profiles_list.append({
                'name': name,
                'label': profile.label,
                'provider': profile.provider,
                'api_format': profile.api_format,
                'auth_source': profile.auth_source,
                'default_model': profile.default_model,
                'base_url': profile.base_url,
                'allowed_models': profile.allowed_models,
            })
        
        return {
            'providers': providers_list,
            'profiles': profiles_list,
            'total_providers': len(providers_list),
            'total_profiles': len(profiles_list),
        }
    
    @app.get("/api/models")
    async def get_models():
        """Get list of available models."""
        from openharness.config import load_settings
        from openharness.api.registry import PROVIDERS
        
        settings = load_settings()
        
        # Build model list from providers
        models = []
        default_models = [
            'claude-sonnet-4-6',
            'claude-opus-4-6',
            'claude-haiku-4-5',
            'claude-3-5-sonnet-20241022',
            'claude-3-opus-20240229',
            'claude-3-haiku-20240307',
            'gpt-4-turbo-preview',
            'gpt-4-0125-preview',
            'gpt-3.5-turbo-0125',
            'gemini-1.5-pro',
            'gemini-1.5-flash',
            'deepseek-chat',
            'deepseek-coder',
        ]
        
        # Get current model and any custom models from settings
        custom_models = getattr(settings, 'custom_models', [])
        
        models = default_models + custom_models
        
        return {
            'models': models,
            'current_model': settings.model,
            'total': len(models),
        }
    
    @app.post("/api/models")
    async def add_model(payload: dict):
        """Add a custom model."""
        model = payload.get('model')
        if not model:
            return {"status": "error", "message": "Model name required"}
        
        # In a real implementation, this would save to settings/config
        # For now, broadcast the change to connected clients
        await backend_host.broadcast({
            'type': 'model_added',
            'model': model,
        })
        
        return {"status": "success", "model": model}
    
    @app.delete("/api/models/{model}")
    async def delete_model(model: str):
        """Delete a custom model."""
        # In a real implementation, this would remove from settings/config
        await backend_host.broadcast({
            'type': 'model_deleted',
            'model': model,
        })
        
        return {"status": "success", "model": model}
    
    @app.post("/api/providers/config")
    async def configure_provider(payload: dict):
        """Configure a provider with API key."""
        provider = payload.get('provider')
        api_key = payload.get('api_key')
        base_url = payload.get('base_url')
        
        if not provider:
            return {"status": "error", "message": "Provider name required"}
        
        # Update runtime if available
        if backend_host.runtime_bundle:
            try:
                # Store in settings
                await backend_host.broadcast({
                    'type': 'provider_configured',
                    'provider': provider,
                    'api_key_set': bool(api_key),
                    'base_url': base_url,
                })
            except Exception as e:
                logger.exception("Error configuring provider")
                return {"status": "error", "message": str(e)}
        
        return {"status": "success", "provider": provider}
    
    @app.get("/api/doctor")
    async def get_doctor():
        """Get doctor/health check summary."""
        try:
            return _get_doctor_summary(backend_host.runtime_bundle, cwd or str(Path.cwd()))
        except Exception as e:
            logger.exception("Error getting doctor summary")
            # Return a minimal summary on error
            return {
                'cwd': cwd or str(Path.cwd()),
                'active_profile': 'unknown',
                'model': 'unknown',
                'provider_workflow': 'unknown',
                'auth_source': 'unknown',
                'permission_mode': 'default',
                'theme': 'dark',
                'output_style': 'default',
                'vim_mode': False,
                'voice_mode': False,
                'effort': 'medium',
                'passes': 1,
                'memory_dir': cwd or str(Path.cwd()),
                'plugin_count': 0,
                'mcp_configured': False,
                'auth_configured': False,
                'error': str(e),
            }
    
    @app.get("/api/config")
    async def get_config():
        """Get full OpenHarness configuration."""
        from openharness.config import load_settings
        from openharness.mcp.config import load_mcp_server_configs
        from openharness.plugins import load_plugins
        
        settings = load_settings()
        plugins = load_plugins(settings, cwd or str(Path.cwd()))
        mcp_configs = load_mcp_server_configs(settings, plugins)
        
        return {
            'model': settings.model,
            'permission_mode': settings.permission.mode,
            'theme': settings.theme,
            'output_style': settings.output_style,
            'vim_mode': settings.vim_mode,
            'voice_mode': settings.voice_mode,
            'effort': settings.effort,
            'passes': settings.passes,
            'max_turns': settings.max_turns,
            'mcp_servers': list(mcp_configs.keys()),
            'plugins_enabled': settings.enabled_plugins,
            'hooks': dict(settings.hooks),
            'allowed_tools': settings.permission.allowed_tools,
            'denied_tools': settings.permission.denied_tools,
        }
    
    @app.post("/api/config")
    async def update_config(payload: dict):
        """Update and persist OpenHarness configuration."""
        from openharness.config import load_settings, save_settings
        from openharness.config.settings import PermissionMode
        
        try:
            settings = load_settings()
            
            # Update model if provided
            if 'model' in payload and payload['model']:
                settings.model = payload['model']
            
            # Update permission mode if provided
            if 'permission_mode' in payload:
                mode_value = payload['permission_mode']
                # Normalize permission mode value
                if mode_value == 'auto':
                    mode_value = 'full_auto'
                try:
                    settings.permission.mode = PermissionMode(mode_value)
                except ValueError:
                    pass
            
            # Update theme if provided
            if 'theme' in payload:
                settings.theme = payload['theme']
            
            # Update output_style if provided
            if 'output_style' in payload:
                settings.output_style = payload['output_style']
            
            # Update vim_mode if provided
            if 'vim_mode' in payload:
                settings.vim_mode = bool(payload['vim_mode'])
            
            # Update voice_mode if provided
            if 'voice_mode' in payload:
                settings.voice_mode = bool(payload['voice_mode'])
            
            # Update effort if provided
            if 'effort' in payload:
                settings.effort = payload['effort']
            
            # Update passes if provided
            if 'passes' in payload:
                settings.passes = int(payload['passes'])
            
            # Update max_turns if provided
            if 'max_turns' in payload:
                settings.max_turns = int(payload['max_turns'])
            
            # Save settings to disk
            save_settings(settings)
            logger.info(f"Settings saved: {payload}")
            
            # Update runtime bundle if available
            if backend_host.runtime_bundle:
                # Update engine model if changed
                if 'model' in payload and payload['model']:
                    try:
                        backend_host.runtime_bundle.engine.set_model(payload['model'])
                    except Exception as e:
                        logger.warning(f"Failed to update engine model: {e}")
                
                # Update permission mode in app state
                if 'permission_mode' in payload:
                    backend_host.runtime_bundle.app_state.set(permission_mode=payload['permission_mode'])
                    # Update permission checker
                    from openharness.permissions.checker import PermissionChecker
                    current_settings = backend_host.runtime_bundle.current_settings()
                    new_checker = PermissionChecker(current_settings.permission)
                    backend_host.runtime_bundle.engine.set_permission_checker(new_checker)
            
            # Broadcast updated state to all clients
            await backend_host.broadcast({
                'type': 'config_saved',
                'settings': {
                    'model': settings.model,
                    'permission_mode': settings.permission.mode,
                    'theme': settings.theme,
                    'output_style': settings.output_style,
                    'vim_mode': settings.vim_mode,
                    'voice_mode': settings.voice_mode,
                    'effort': settings.effort,
                    'passes': settings.passes,
                    'max_turns': settings.max_turns,
                }
            })
            
            return {"status": "success", "settings": payload}
        except Exception as e:
            logger.exception("Error saving settings")
            return {"status": "error", "message": str(e)}
    
    @app.post("/api/submit")
    async def submit_prompt(payload: dict):
        line = payload.get('line', '')
        if backend_host.runtime_bundle and line:
            asyncio.create_task(backend_host.handle_request(sio, None, {'type': 'submit_line', 'line': line}))
            return {"status": "accepted"}
        return {"status": "error", "message": "Runtime not ready"}
    
    # Mount static files if frontend directory exists
    if frontend_dir and (frontend_dir / "dist").exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dir / "dist" / "assets")), name="assets")
        
        @app.get("/")
        async def root():
            return FileResponse(frontend_dir / "dist" / "index.html")
        
        @app.get("/{path:path}")
        async def static_files(path: str):
            # Skip API routes - they're already defined above
            if path.startswith("api/"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="API route not found")
            file_path = frontend_dir / "dist" / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(frontend_dir / "dist" / "index.html")
    
    # Initialize runtime on startup
    @app.on_event("startup")
    async def startup_event():
        logger.info("Starting OpenHarness web backend...")
        backend_host.running = True
        
        try:
            backend_host.runtime_bundle = await build_runtime(
                prompt=None,
                cwd=cwd,
                model=model,
                max_turns=max_turns,
                base_url=base_url,
                system_prompt=system_prompt,
                api_key=api_key,
                api_format=api_format,
                enforce_max_turns=max_turns is not None if max_turns else False,
                api_client=api_client,
                permission_mode=permission_mode,
            )
            await start_runtime(backend_host.runtime_bundle)
            logger.info("Runtime initialized successfully")
        except Exception as e:
            logger.exception("Failed to initialize runtime")
            raise
    
    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("Shutting down OpenHarness web backend...")
        backend_host.running = False
        
        if backend_host.runtime_bundle:
            await close_runtime(backend_host.runtime_bundle)
        
        backend_host.clients.clear()
    
    return app


# Socket.IO event handlers
@sio.event
async def connect(sid, environ, auth):
    """Handle new Socket.IO connection."""
    logger.info(f"Client connected: {sid}")
    backend_host.clients.add(sid)
    
    # Get actual state from runtime if available
    app_state = None
    commands = [
        'provider', 'model', 'theme', 'output-style',
        'permissions', 'resume', 'effort', 'passes',
        'turns', 'fast', 'vim', 'voice'
    ]
    
    if backend_host.runtime_bundle:
        try:
            state_obj = backend_host.runtime_bundle.app_state.get()
            app_state = {
                'permission_mode': getattr(state_obj, 'permission_mode', 'default'),
                'model': getattr(state_obj, 'model', None),
                'working_directory': getattr(state_obj, 'cwd', None),
            }
            # Get available commands from runtime
            try:
                commands = [f"/{cmd.name}" for cmd in backend_host.runtime_bundle.commands.list_commands()]
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Failed to get runtime state: {e}")
            app_state = {
                'permission_mode': 'default',
                'model': None,
                'working_directory': None,
            }
    else:
        app_state = {
            'permission_mode': 'default',
            'model': None,
            'working_directory': None,
        }
    
    # Send ready event with actual state
    state = {
        'type': 'ready',
        'state': app_state,
        'commands': commands,
        'tasks': [],
        'mcp_servers': [],
        'bridge_sessions': [],
    }
    await sio.emit('backend_event', PROTOCOL_PREFIX + json.dumps(state), to=sid)


@sio.event
async def disconnect(sid):
    """Handle Socket.IO disconnection."""
    logger.info(f"Client disconnected: {sid}")
    backend_host.clients.discard(sid)


@sio.event
async def frontend_request(sid, data):
    """Handle frontend request."""
    try:
        payload = json.loads(data)
        await backend_host.handle_request(sio, sid, payload)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON received")
    except Exception as e:
        logger.exception("Error processing request")
        await sio.emit('backend_event', PROTOCOL_PREFIX + json.dumps({
            'type': 'error',
            'message': str(e)
        }), to=sid)


def _is_port_available(host: str, port: int) -> bool:
    """Check if a port is available for binding."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def _find_available_port(host: str, start_port: int, max_attempts: int = 10) -> int:
    """Find an available port starting from start_port."""
    for offset in range(max_attempts):
        candidate_port = start_port + offset
        if _is_port_available(host, candidate_port):
            return candidate_port
    raise OSError(f"Could not find an available port from {start_port} to {start_port + max_attempts - 1}")


async def run_web_server(
    *,
    host: str = "0.0.0.0",
    port: int = 8080,
    cwd: str | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
    api_format: str | None = None,
    permission_mode: str | None = None,
    serve_frontend: bool = True,
) -> None:
    """Run the web server for OpenHarness frontend."""
    import uvicorn
    
    frontend_dir = None
    if serve_frontend:
        # Try to find the frontend directory
        possible_paths = [
            Path(__file__).parent.parent.parent / "frontend" / "web",
            Path.cwd() / "frontend" / "web",
        ]
        for path in possible_paths:
            if path.exists():
                frontend_dir = path
                break
    
    # Check if port is available, find alternative if needed
    original_port = port
    if not _is_port_available(host, port):
        logger.warning(f"Port {port} is already in use, finding alternative...")
        try:
            port = _find_available_port(host, port)
            logger.info(f"Using alternative port {port}")
        except OSError as e:
            logger.error(str(e))
            raise
    
    app = create_app(
        cwd=cwd,
        model=model,
        max_turns=max_turns,
        base_url=base_url,
        system_prompt=system_prompt,
        api_key=api_key,
        api_format=api_format,
        permission_mode=permission_mode,
        frontend_dir=frontend_dir,
    )
    
    # Combine FastAPI and Socket.IO
    combined_app = socketio.ASGIApp(sio, app)
    
    config = uvicorn.Config(
        combined_app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


__all__ = ["create_app", "run_web_server"]