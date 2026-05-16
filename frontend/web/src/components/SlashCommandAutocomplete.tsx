import React, { useState, useEffect, useRef } from 'react';
import { 
  Terminal, Settings, Shield, Brain, Zap, FileText, Layers, 
  HelpCircle, Trash2, RefreshCw, Database, BarChart3, 
  Users, Globe, Palette, Activity, Plug, MessageSquare, 
  FileDown, Copy, Tag, Rewind, FolderOpen, GitBranch, GitCommit, 
  Stethoscope, Target, Play
} from 'lucide-react';
import styles from '../styles/SlashCommandAutocomplete.module.css';

interface SlashCommand {
  id: string;
  command: string;
  label: string;
  description: string;
  category: string;
  icon: React.ReactNode;
  example?: string;
}

// Commands matching the backend registry in src/openharness/commands/registry.py
const SLASH_COMMANDS: SlashCommand[] = [
  // Help & Info
  {
    id: 'help',
    command: '/help',
    label: 'Help',
    description: 'Show available commands and usage',
    category: 'Help',
    icon: <HelpCircle size={16} />,
    example: '/help'
  },
  {
    id: 'version',
    command: '/version',
    label: 'Version',
    description: 'Show the installed OpenHarness version',
    category: 'Help',
    icon: <Terminal size={16} />,
    example: '/version'
  },
  {
    id: 'status',
    command: '/status',
    label: 'Session Status',
    description: 'Show session status (messages, usage, profile, effort)',
    category: 'Help',
    icon: <Activity size={16} />,
    example: '/status'
  },
  {
    id: 'doctor',
    command: '/doctor',
    label: 'Doctor',
    description: 'Show environment diagnostics',
    category: 'Help',
    icon: <Stethoscope size={16} />,
    example: '/doctor'
  },
  
  // Session Management
  {
    id: 'clear',
    command: '/clear',
    label: 'Clear Conversation',
    description: 'Clear the conversation history',
    category: 'Session',
    icon: <Trash2 size={16} />,
    example: '/clear'
  },
  {
    id: 'exit',
    command: '/exit',
    label: 'Exit',
    description: 'Exit OpenHarness',
    category: 'Session',
    icon: <Terminal size={16} />,
    example: '/exit'
  },
  {
    id: 'resume',
    command: '/resume',
    label: 'Resume Session',
    description: 'Restore the latest saved session',
    category: 'Session',
    icon: <RefreshCw size={16} />,
    example: '/resume [session_id]'
  },
  {
    id: 'session',
    command: '/session',
    label: 'Session Info',
    description: 'Inspect the current session storage',
    category: 'Session',
    icon: <Database size={16} />,
    example: '/session show'
  },
  {
    id: 'export',
    command: '/export',
    label: 'Export Transcript',
    description: 'Export the current transcript',
    category: 'Session',
    icon: <FileDown size={16} />,
    example: '/export'
  },
  {
    id: 'share',
    command: '/share',
    label: 'Share Transcript',
    description: 'Create a shareable transcript snapshot',
    category: 'Session',
    icon: <Globe size={16} />,
    example: '/share'
  },
  {
    id: 'tag',
    command: '/tag',
    label: 'Tag Session',
    description: 'Create a named snapshot of the current session',
    category: 'Session',
    icon: <Tag size={16} />,
    example: '/tag my-tag'
  },
  {
    id: 'rewind',
    command: '/rewind',
    label: 'Rewind',
    description: 'Remove the latest conversation turn(s)',
    category: 'Session',
    icon: <Rewind size={16} />,
    example: '/rewind 2'
  },
  {
    id: 'continue',
    command: '/continue',
    label: 'Continue',
    description: 'Continue the previous tool loop if interrupted',
    category: 'Session',
    icon: <Play size={16} />,
    example: '/continue'
  },
  
  // Model & Provider
  {
    id: 'model',
    command: '/model',
    label: 'Set Model',
    description: 'Show or update the default model',
    category: 'Model',
    icon: <Brain size={16} />,
    example: '/model claude-sonnet-4-20250514'
  },
  {
    id: 'provider',
    command: '/provider',
    label: 'Provider Profiles',
    description: 'Show or switch provider profiles',
    category: 'Model',
    icon: <Globe size={16} />,
    example: '/provider anthropic'
  },
  {
    id: 'effort',
    command: '/effort',
    label: 'Set Effort',
    description: 'Show or update reasoning effort (low/medium/high)',
    category: 'Model',
    icon: <Zap size={16} />,
    example: '/effort high'
  },
  {
    id: 'passes',
    command: '/passes',
    label: 'Set Passes',
    description: 'Show or update reasoning pass count',
    category: 'Model',
    icon: <Layers size={16} />,
    example: '/passes 2'
  },
  {
    id: 'turns',
    command: '/turns',
    label: 'Max Turns',
    description: 'Show or update maximum agentic turn count',
    category: 'Model',
    icon: <Target size={16} />,
    example: '/turns 100'
  },
  
  // Permissions
  {
    id: 'permissions',
    command: '/permissions',
    label: 'Permission Mode',
    description: 'Show or update permission mode (default/plan/full_auto)',
    category: 'Permissions',
    icon: <Shield size={16} />,
    example: '/permissions plan'
  },
  {
    id: 'plan',
    command: '/plan',
    label: 'Plan Mode',
    description: 'Toggle plan permission mode (on/off)',
    category: 'Permissions',
    icon: <FileText size={16} />,
    example: '/plan on'
  },
  
  // Usage & Stats
  {
    id: 'cost',
    command: '/cost',
    label: 'Cost',
    description: 'Show token usage and estimated cost',
    category: 'Stats',
    icon: <BarChart3 size={16} />,
    example: '/cost'
  },
  {
    id: 'usage',
    command: '/usage',
    label: 'Usage',
    description: 'Show usage and token estimates',
    category: 'Stats',
    icon: <Activity size={16} />,
    example: '/usage'
  },
  {
    id: 'stats',
    command: '/stats',
    label: 'Session Stats',
    description: 'Show session statistics',
    category: 'Stats',
    icon: <BarChart3 size={16} />,
    example: '/stats'
  },
  
  // Context & Memory
  {
    id: 'context',
    command: '/context',
    label: 'System Context',
    description: 'Show the active runtime system prompt',
    category: 'Context',
    icon: <FileText size={16} />,
    example: '/context'
  },
  {
    id: 'summary',
    command: '/summary',
    label: 'Summarize',
    description: 'Summarize conversation history',
    category: 'Context',
    icon: <FileText size={16} />,
    example: '/summary 8'
  },
  {
    id: 'compact',
    command: '/compact',
    label: 'Compact',
    description: 'Compact older conversation history',
    category: 'Context',
    icon: <Trash2 size={16} />,
    example: '/compact 6'
  },
  {
    id: 'memory',
    command: '/memory',
    label: 'Memory',
    description: 'Inspect and manage project memory',
    category: 'Context',
    icon: <Database size={16} />,
    example: '/memory list'
  },
  {
    id: 'remember',
    command: '/remember',
    label: 'Remember',
    description: 'Save a fact, preference, or context to memory',
    category: 'Context',
    icon: <Brain size={16} />,
    example: '/remember I prefer TypeScript over JavaScript'
  },
  {
    id: 'add-memory',
    command: '/add-memory',
    label: 'Add Memory',
    description: 'Add information to long-term memory',
    category: 'Context',
    icon: <Brain size={16} />,
    example: '/add-memory This project uses React and Tailwind CSS'
  },
  {
    id: 'mem',
    command: '/mem',
    label: 'Mem (shortcut)',
    description: 'Quick shortcut to save a memory',
    category: 'Context',
    icon: <Brain size={16} />,
    example: '/mem Working directory is ~/projects/my-app'
  },
  {
    id: 'files',
    command: '/files',
    label: 'Files',
    description: 'List files in the current workspace',
    category: 'Context',
    icon: <FolderOpen size={16} />,
    example: '/files'
  },
  
  // Configuration
  {
    id: 'config',
    command: '/config',
    label: 'Configuration',
    description: 'Show or update configuration',
    category: 'Config',
    icon: <Settings size={16} />,
    example: '/config model claude-sonnet'
  },
  {
    id: 'theme',
    command: '/theme',
    label: 'Theme',
    description: 'List, set, show or preview TUI themes',
    category: 'Config',
    icon: <Palette size={16} />,
    example: '/theme dark'
  },
  {
    id: 'fast',
    command: '/fast',
    label: 'Fast Mode',
    description: 'Show or update fast mode',
    category: 'Config',
    icon: <Zap size={16} />,
    example: '/fast on'
  },
  
  // Auth
  {
    id: 'login',
    command: '/login',
    label: 'Login',
    description: 'Show auth status or store an API key',
    category: 'Auth',
    icon: <Users size={16} />,
    example: '/login'
  },
  {
    id: 'logout',
    command: '/logout',
    label: 'Logout',
    description: 'Clear the stored API key',
    category: 'Auth',
    icon: <Users size={16} />,
    example: '/logout'
  },
  
  // Plugins & MCP
  {
    id: 'mcp',
    command: '/mcp',
    label: 'MCP Status',
    description: 'Show MCP status',
    category: 'Plugins',
    icon: <Plug size={16} />,
    example: '/mcp'
  },
  {
    id: 'plugin',
    command: '/plugin',
    label: 'Plugin Management',
    description: 'Manage plugins (list/enable/disable/install/uninstall)',
    category: 'Plugins',
    icon: <Plug size={16} />,
    example: '/plugin list'
  },
  {
    id: 'reload-plugins',
    command: '/reload-plugins',
    label: 'Reload Plugins',
    description: 'Reload plugin discovery for this workspace',
    category: 'Plugins',
    icon: <RefreshCw size={16} />,
    example: '/reload-plugins'
  },
  {
    id: 'skills',
    command: '/skills',
    label: 'Skills',
    description: 'List or show available skills',
    category: 'Plugins',
    icon: <FileText size={16} />,
    example: '/skills'
  },
  
  // Git
  {
    id: 'diff',
    command: '/diff',
    label: 'Git Diff',
    description: 'Show git diff output',
    category: 'Git',
    icon: <FileText size={16} />,
    example: '/diff'
  },
  {
    id: 'branch',
    command: '/branch',
    label: 'Git Branch',
    description: 'Show git branch information',
    category: 'Git',
    icon: <GitBranch size={16} />,
    example: '/branch'
  },
  {
    id: 'commit',
    command: '/commit',
    label: 'Git Commit',
    description: 'Show status or create a git commit',
    category: 'Git',
    icon: <GitCommit size={16} />,
    example: '/commit'
  },
  
  // Tasks & Agents
  {
    id: 'agents',
    command: '/agents',
    label: 'Agents',
    description: 'List or inspect agent and teammate tasks',
    category: 'Tasks',
    icon: <Users size={16} />,
    example: '/agents'
  },
  {
    id: 'tasks',
    command: '/tasks',
    label: 'Tasks',
    description: 'Manage background tasks',
    category: 'Tasks',
    icon: <Layers size={16} />,
    example: '/tasks'
  },
  
  // Utilities
  {
    id: 'copy',
    command: '/copy',
    label: 'Copy',
    description: 'Copy the latest response or provided text',
    category: 'Utils',
    icon: <Copy size={16} />,
    example: '/copy'
  },
  {
    id: 'init',
    command: '/init',
    label: 'Init Project',
    description: 'Initialize project OpenHarness files',
    category: 'Utils',
    icon: <FolderOpen size={16} />,
    example: '/init'
  },
  {
    id: 'hooks',
    command: '/hooks',
    label: 'Hooks',
    description: 'Show configured hooks',
    category: 'Utils',
    icon: <Plug size={16} />,
    example: '/hooks'
  },
  {
    id: 'bridge',
    command: '/bridge',
    label: 'Bridge',
    description: 'Inspect bridge helpers and spawn bridge sessions',
    category: 'Utils',
    icon: <Globe size={16} />,
    example: '/bridge'
  },
  {
    id: 'feedback',
    command: '/feedback',
    label: 'Feedback',
    description: 'Save CLI feedback to the local feedback log',
    category: 'Utils',
    icon: <MessageSquare size={16} />,
    example: '/feedback Great feature!'
  },
  {
    id: 'onboarding',
    command: '/onboarding',
    label: 'Onboarding',
    description: 'Show the quickstart guide',
    category: 'Utils',
    icon: <HelpCircle size={16} />,
    example: '/onboarding'
  },
];

interface SlashCommandAutocompleteProps {
  input: string;
  setInput: (value: string) => void;
  inputRef: React.RefObject<HTMLTextAreaElement>;
  onSubmit?: (prompt: string) => void;
}

export function SlashCommandAutocomplete({
  input,
  setInput,
  inputRef,
  onSubmit: _onSubmit // eslint-disable-line @typescript-eslint/no-unused-vars
}: SlashCommandAutocompleteProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [filteredCommands, setFilteredCommands] = useState<SlashCommand[]>([]);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Parse input to detect slash command
  const currentWord = input.split(' ').pop() || '';
  const isSlashCommand = currentWord.startsWith('/');
  const query = currentWord.slice(1).toLowerCase();

  // Filter commands based on query
  useEffect(() => {
    if (isSlashCommand) {
      const filtered = SLASH_COMMANDS.filter(cmd => 
        cmd.command.toLowerCase().includes(query) ||
        cmd.label.toLowerCase().includes(query) ||
        cmd.description.toLowerCase().includes(query) ||
        cmd.category.toLowerCase().includes(query)
      );
      setFilteredCommands(filtered);
      setIsOpen(filtered.length > 0);
      setSelectedIndex(0);
    } else {
      setIsOpen(false);
    }
  }, [input, isSlashCommand, query]);

  // Handle keyboard navigation
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => 
          prev < filteredCommands.length - 1 ? prev + 1 : prev
        );
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => 
          prev > 0 ? prev - 1 : prev
        );
      } else if (e.key === 'Tab' || e.key === 'Enter') {
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          selectCommand(filteredCommands[selectedIndex]);
        }
      } else if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };

    const textarea = inputRef.current;
    if (textarea) {
      textarea.addEventListener('keydown', handleKeyDown);
      return () => textarea.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, selectedIndex, filteredCommands]);

  // Scroll selected item into view
  useEffect(() => {
    if (isOpen && dropdownRef.current) {
      const selectedElement = dropdownRef.current.querySelector(`[data-index="${selectedIndex}"]`);
      if (selectedElement) {
        selectedElement.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [selectedIndex, isOpen]);

  const selectCommand = (cmd: SlashCommand) => {
    // Replace the current word with the full command
    const words = input.split(' ');
    words[words.length - 1] = cmd.command + ' ';
    setInput(words.join(' '));
    setIsOpen(false);
    
    // Focus back on input
    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  const handleCommandClick = (cmd: SlashCommand) => {
    selectCommand(cmd);
  };

  // Group commands by category
  const groupedCommands = filteredCommands.reduce((acc, cmd) => {
    if (!acc[cmd.category]) {
      acc[cmd.category] = [];
    }
    acc[cmd.category].push(cmd);
    return acc;
  }, {} as Record<string, SlashCommand[]>);

  if (!isOpen) return null;

  return (
    <div className={styles.dropdown} ref={dropdownRef}>
      <div className={styles.header}>
        <span className={styles.headerIcon}>⚡</span>
        <span>Slash Commands</span>
        <span className={styles.headerHint}>
          <kbd>Tab</kbd> or <kbd>Enter</kbd> to select
        </span>
      </div>
      <div className={styles.list}>
        {Object.entries(groupedCommands).map(([category, commands]) => (
          <div key={category} className={styles.category}>
            <div className={styles.categoryLabel}>{category}</div>
            {commands.map((cmd) => {
              const globalIndex = filteredCommands.indexOf(cmd);
              return (
                <button
                  key={cmd.id}
                  className={`${styles.item} ${globalIndex === selectedIndex ? styles.selected : ''}`}
                  onClick={() => handleCommandClick(cmd)}
                  data-index={globalIndex}
                >
                  <div className={styles.itemIcon}>{cmd.icon}</div>
                  <div className={styles.itemContent}>
                    <div className={styles.itemLabel}>
                      <span className={styles.commandName}>{cmd.command}</span>
                      <span className={styles.itemTitle}>{cmd.label}</span>
                    </div>
                    <div className={styles.itemDescription}>{cmd.description}</div>
                    {cmd.example && (
                      <div className={styles.itemExample}>
                        Example: <code>{cmd.example}</code>
                      </div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        ))}
      </div>
      <div className={styles.footer}>
        <span><kbd>↑↓</kbd> Navigate</span>
        <span><kbd>Tab</kbd> Complete</span>
        <span><kbd>Esc</kbd> Close</span>
      </div>
    </div>
  );
}