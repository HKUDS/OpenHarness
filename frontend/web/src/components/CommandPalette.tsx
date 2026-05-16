import { useEffect, useState } from 'react';
import { Command, X, ChevronRight, Terminal, Settings, ListTodo, Puzzle, Users, MessageSquare, FileCheck } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import styles from '../styles/CommandPalette.module.css';

interface CommandItem {
  id: string;
  label: string;
  shortcut: string;
  icon: React.ReactNode;
  action: () => void;
  category: 'navigation' | 'view' | 'actions';
}

export function CommandPalette() {
  const { 
    toggleSidebar,
    setTerminalView,
    setActivePanel,
    createNewChat,
    commandPaletteOpen,
    setCommandPaletteOpen
  } = useAppStore();
  
  const [search, setSearch] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  const commands: CommandItem[] = [
    {
      id: 'new-chat',
      label: 'New Chat',
      shortcut: '',
      icon: <Terminal size={18} />,
      action: () => createNewChat(),
      category: 'actions'
    },
    {
      id: 'toggle-sidebar',
      label: 'Toggle Sidebar',
      shortcut: 'Ctrl+B',
      icon: <ListTodo size={18} />,
      action: () => toggleSidebar(),
      category: 'navigation'
    },
    {
      id: 'chat-view',
      label: 'Switch to Chat View',
      shortcut: '',
      icon: <Terminal size={18} />,
      action: () => setTerminalView('chat'),
      category: 'view'
    },
    {
      id: 'terminal-view',
      label: 'Switch to Terminal View',
      shortcut: 'Ctrl+`',
      icon: <Terminal size={18} />,
      action: () => setTerminalView('terminal'),
      category: 'view'
    },
    {
      id: 'chats-panel',
      label: 'Open Chats Panel',
      shortcut: '',
      icon: <MessageSquare size={18} />,
      action: () => setActivePanel('chats'),
      category: 'navigation'
    },
    {
      id: 'tasks-panel',
      label: 'Open Tasks Panel',
      shortcut: 'Ctrl+1',
      icon: <ListTodo size={18} />,
      action: () => setActivePanel('tasks'),
      category: 'navigation'
    },
    {
      id: 'mcp-panel',
      label: 'Open MCP Servers Panel',
      shortcut: 'Ctrl+2',
      icon: <Puzzle size={18} />,
      action: () => setActivePanel('mcp'),
      category: 'navigation'
    },
    {
      id: 'swarm-panel',
      label: 'Open Swarm Panel',
      shortcut: 'Ctrl+3',
      icon: <Users size={18} />,
      action: () => setActivePanel('swarm'),
      category: 'navigation'
    },
    {
      id: 'todo-panel',
      label: 'Open TODO Panel',
      shortcut: 'Ctrl+4',
      icon: <FileCheck size={18} />,
      action: () => setActivePanel('todo'),
      category: 'navigation'
    },
    {
      id: 'settings-panel',
      label: 'Open Settings',
      shortcut: 'Ctrl+,',
      icon: <Settings size={18} />,
      action: () => setActivePanel('settings'),
      category: 'navigation'
    },
  ];

  const filteredCommands = commands.filter(cmd =>
    cmd.label.toLowerCase().includes(search.toLowerCase())
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setCommandPaletteOpen(!commandPaletteOpen);
        setSearch('');
        setSelectedIndex(0);
      }
      
      if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        toggleSidebar();
      }
      
      if ((e.ctrlKey || e.metaKey) && e.key === '`') {
        e.preventDefault();
        setTerminalView('terminal');
      }
      
      if ((e.ctrlKey || e.metaKey) && e.key === '1') {
        e.preventDefault();
        setActivePanel('tasks');
      }
      
      if ((e.ctrlKey || e.metaKey) && e.key === '2') {
        e.preventDefault();
        setActivePanel('mcp');
      }
      
      if ((e.ctrlKey || e.metaKey) && e.key === '3') {
        e.preventDefault();
        setActivePanel('swarm');
      }
      
      if ((e.ctrlKey || e.metaKey) && e.key === '4') {
        e.preventDefault();
        setActivePanel('todo');
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [commandPaletteOpen, setCommandPaletteOpen, toggleSidebar, setTerminalView, setActivePanel]);

  useEffect(() => {
    if (!commandPaletteOpen) return;
    
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => (prev + 1) % filteredCommands.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => (prev - 1 + filteredCommands.length) % filteredCommands.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        filteredCommands[selectedIndex]?.action();
        setCommandPaletteOpen(false);
      } else if (e.key === 'Escape') {
        setCommandPaletteOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [commandPaletteOpen, filteredCommands, selectedIndex, setCommandPaletteOpen]);

  useEffect(() => {
    if (!commandPaletteOpen) {
      setSearch('');
      setSelectedIndex(0);
    }
  }, [commandPaletteOpen]);

  if (!commandPaletteOpen) return null;

  return (
    <div className={styles.overlay} onClick={() => setCommandPaletteOpen(false)}>
      <div className={styles.palette} onClick={e => e.stopPropagation()}>
        <div className={styles.header}>
          <Command size={20} className={styles.searchIcon} />
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Type a command or search..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            autoFocus
          />
          <button className={styles.closeButton} onClick={() => setCommandPaletteOpen(false)}>
            <X size={18} />
          </button>
        </div>
        
        <div className={styles.commands}>
          {filteredCommands.length === 0 ? (
            <div className={styles.empty}>No commands found</div>
          ) : (
            filteredCommands.map((cmd, index) => (
              <button
                key={cmd.id}
                className={`${styles.command} ${index === selectedIndex ? styles.selected : ''}`}
                onClick={() => {
                  cmd.action();
                  setCommandPaletteOpen(false);
                }}
                onMouseEnter={() => setSelectedIndex(index)}
              >
                <div className={styles.commandLeft}>
                  <div className={styles.commandIcon}>{cmd.icon}</div>
                  <span className={styles.commandLabel}>{cmd.label}</span>
                </div>
                <div className={styles.commandRight}>
                  <span className={styles.shortcut}>{cmd.shortcut}</span>
                  <ChevronRight size={16} className={styles.chevron} />
                </div>
              </button>
            ))
          )}
        </div>
        
        <div className={styles.footer}>
          <span className={styles.footerItem}>
            <kbd>↑↓</kbd> to navigate
          </span>
          <span className={styles.footerItem}>
            <kbd>Enter</kbd> to select
          </span>
          <span className={styles.footerItem}>
            <kbd>Esc</kbd> to close
          </span>
        </div>
      </div>
    </div>
  );
}
