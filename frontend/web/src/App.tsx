import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { CommandPalette } from './components/CommandPalette';
import { PermissionModal } from './components/PermissionModal';
import { useBackendConnection } from './hooks/useBackendConnection';
import { useAppStore } from './store/useAppStore';
import { ChatsPage } from './pages/ChatsPage';
import { TasksPage } from './pages/TasksPage';
import { McpServersPage } from './pages/McpServersPage';
import { SwarmPage } from './pages/SwarmPage';
import { SkillsPage } from './pages/SkillsPage';
import { PluginsPage } from './pages/PluginsPage';
import { ToolsPage } from './pages/ToolsPage';
import { HooksPage } from './pages/HooksPage';
import { PromptsPage } from './pages/PromptsPage';
import { CommandsPage } from './pages/CommandsPage';
import { ProvidersPage } from './pages/ProvidersPage';
import { MemoryPage } from './pages/MemoryPage';
import { TodoPage } from './pages/TodoPage';
import { ChannelsPage } from './pages/ChannelsPage';
import { DoctorPage } from './pages/DoctorPage';
import { OpenHarnessConfigPage } from './pages/OpenHarnessConfigPage';
import styles from './styles/App.module.css';

export function App() {
  const { connect, connected, connecting, error } = useBackendConnection();
  const { settings, updateSettings } = useAppStore();

  // Apply theme based on settings
  React.useEffect(() => {
    // Load theme from localStorage on first mount - skip backend sync to prevent loops
    const savedTheme = localStorage.getItem('openharness-theme');
    if (savedTheme && savedTheme !== settings.theme) {
      updateSettings({ theme: savedTheme as 'dark' | 'light' });
    }
  }, []);

  // Apply theme to document root
  React.useEffect(() => {
    document.documentElement.setAttribute('data-theme', settings.theme);
    localStorage.setItem('openharness-theme', settings.theme);
  }, [settings.theme]);

  // Connection is managed by the hook's singleton pattern
  // No need to call connect() here - it auto-connects on first hook usage

  return (
    <BrowserRouter>
      <div className={styles.app}>
        <CommandPalette />
        <PermissionModal />
        <Header />
        <div className={styles.main}>
          <Sidebar />
          <main className={styles.content}>
            {!connected && !connecting && (
              <div className={styles.connectionError}>
                <h2>Connection Lost</h2>
                <p>{error || 'Unable to connect to OpenHarness backend'}</p>
                <button onClick={() => connect()} className={styles.reconnectButton}>
                  Reconnect
                </button>
              </div>
            )}
            {connecting && (
              <div className={styles.connecting}>
                <div className={styles.spinner} />
                <p>Connecting to OpenHarness...</p>
              </div>
            )}
            {connected && (
              <Routes>
                <Route path="/" element={<Navigate to="/chats" replace />} />
                <Route path="/chats" element={<ChatsPage />} />
                <Route path="/tasks" element={<TasksPage />} />
                <Route path="/mcp" element={<McpServersPage />} />
                <Route path="/swarm" element={<SwarmPage />} />
                <Route path="/skills" element={<SkillsPage />} />
                <Route path="/plugins" element={<PluginsPage />} />
                <Route path="/tools" element={<ToolsPage />} />
                <Route path="/hooks" element={<HooksPage />} />
                <Route path="/prompts" element={<PromptsPage />} />
                <Route path="/commands" element={<CommandsPage />} />
                <Route path="/providers" element={<ProvidersPage />} />
                <Route path="/memory" element={<MemoryPage />} />
                <Route path="/todo" element={<TodoPage />} />
                <Route path="/channels" element={<ChannelsPage />} />
                <Route path="/doctor" element={<DoctorPage />} />
                <Route path="/config" element={<OpenHarnessConfigPage />} />
              </Routes>
            )}
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}