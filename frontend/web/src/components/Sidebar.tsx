import { 
  ListTodo, 
  Puzzle, 
  Users, 
  FileCheck, 
  X,
  ChevronRight,
  MessageSquare,
  Sparkles,
  Brain,
  Radio,
  Sliders,
  Plug,
  Wrench,
  Zap,
  FileText,
  Activity,
  Terminal,
  Globe
} from 'lucide-react';
import { useCallback, useEffect, useRef } from 'react';
import { NavLink } from 'react-router-dom';
import { useAppStore } from '../store/useAppStore';
import styles from '../styles/Sidebar.module.css';

export function Sidebar() {
  const { 
    sidebarOpen, 
    toggleSidebar,
    tasks,
    mcpServers,
    swarmTeammates,
    sidebarWidth,
    setSidebarWidth,
    isResizingSidebar,
    setIsResizingSidebar,
    channels
  } = useAppStore();
  
  const sidebarRef = useRef<HTMLDivElement>(null);

  // Drag to resize sidebar with requestAnimationFrame for smooth performance
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizingSidebar(true);
    // Disable transitions during drag for instant response
    if (sidebarRef.current) {
      sidebarRef.current.style.transition = 'none';
    }
  }, [setIsResizingSidebar]);

  useEffect(() => {
    let rafId: number | null = null;
    let lastWidth = sidebarWidth;
    
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingSidebar) return;
      
      // Cancel pending frame if exists
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      
      // Schedule update on next frame
      rafId = requestAnimationFrame(() => {
        const newWidth = e.clientX;
        const clampedWidth = Math.max(200, Math.min(500, newWidth));
        
        // Only update if width actually changed
        if (clampedWidth !== lastWidth) {
          lastWidth = clampedWidth;
          setSidebarWidth(clampedWidth);
        }
        rafId = null;
      });
    };

    const handleMouseUp = () => {
      setIsResizingSidebar(false);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = 'auto';
      // Re-enable transitions
      if (sidebarRef.current) {
        sidebarRef.current.style.transition = '';
      }
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
    };

    if (isResizingSidebar) {
      document.addEventListener('mousemove', handleMouseMove, { passive: true });
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [isResizingSidebar, setSidebarWidth, setIsResizingSidebar]);

  const panels = [
    { id: 'chats', label: 'Chats', icon: MessageSquare, path: '/chats' },
    { id: 'tasks', label: 'Tasks', icon: ListTodo, path: '/tasks', count: tasks.filter(t => t.status === 'running').length },
    { id: 'mcp', label: 'MCP Servers', icon: Puzzle, path: '/mcp', count: mcpServers.filter(s => s.status === 'connected').length },
    { id: 'swarm', label: 'Swarm', icon: Users, path: '/swarm', count: swarmTeammates.length },
    { id: 'skills', label: 'Skills', icon: Sparkles, path: '/skills' },
    { id: 'plugins', label: 'Plugins', icon: Plug, path: '/plugins' },
    { id: 'tools', label: 'Tools', icon: Wrench, path: '/tools' },
    { id: 'hooks', label: 'Hooks', icon: Zap, path: '/hooks' },
    { id: 'prompts', label: 'Prompts', icon: FileText, path: '/prompts' },
    { id: 'commands', label: 'Commands', icon: Terminal, path: '/commands' },
    { id: 'providers', label: 'Providers', icon: Globe, path: '/providers' },
    { id: 'memory', label: 'Memory', icon: Brain, path: '/memory' },
    { id: 'todo', label: 'TODO', icon: FileCheck, path: '/todo' },
    { id: 'channels', label: 'Channels', icon: Radio, path: '/channels', count: channels.filter(c => c.enabled).length },
    { id: 'doctor', label: 'Doctor', icon: Activity, path: '/doctor' },
    { id: 'config', label: 'OpenHarness Config', icon: Sliders, path: '/config' },
  ];

  if (!sidebarOpen) {
    return (
      <aside className={`${styles.sidebar} ${styles.collapsed}`}>
        <button className={styles.expandButton} onClick={toggleSidebar}>
          <ChevronRight size={20} />
        </button>
        <nav className={styles.collapsedNav}>
          {panels.map((panel) => {
            const Icon = panel.icon;
            return (
              <NavLink
                key={panel.id}
                to={panel.path}
                className={({ isActive }) => 
                  `${styles.collapsedNavItem} ${isActive ? styles.active : ''}`
                }
                title={panel.label}
              >
                <Icon size={20} />
                {panel.count !== undefined && panel.count > 0 && (
                  <span className={styles.collapsedBadge}>{panel.count}</span>
                )}
              </NavLink>
            );
          })}
        </nav>
      </aside>
    );
  }

  return (
    <>
      <aside 
        ref={sidebarRef}
        className={styles.sidebar}
        style={{ width: `${sidebarWidth}px` }}
      >
        <div className={styles.sidebarInner}>
          <div className={styles.header}>
            <h2>Navigation</h2>
            <button className={styles.closeButton} onClick={toggleSidebar}>
              <X size={20} />
            </button>
          </div>
          
          <nav className={styles.nav}>
            {panels.map((panel) => {
              const Icon = panel.icon;
              return (
                <NavLink
                  key={panel.id}
                  to={panel.path}
                  className={({ isActive }) => 
                    `${styles.navItem} ${isActive ? styles.active : ''}`
                  }
                >
                  <Icon size={20} />
                  <span>{panel.label}</span>
                  {panel.count !== undefined && panel.count > 0 && (
                    <span className={styles.badge}>{panel.count}</span>
                  )}
                </NavLink>
              );
            })}
          </nav>

          {/* Quick Info Section */}
          <div className={styles.infoSection}>
          <div className={styles.infoCard}>
            <div className={styles.infoHeader}>
              <span className={styles.infoTitle}>Quick Stats</span>
            </div>
            <div className={styles.infoContent}>
              <div className={styles.infoRow}>
                <span>Active Tasks</span>
                <span className={styles.infoValue}>{tasks.filter(t => t.status === 'running').length}</span>
              </div>
              <div className={styles.infoRow}>
                <span>MCP Connected</span>
                <span className={styles.infoValue}>{mcpServers.filter(s => s.status === 'connected').length}</span>
              </div>
              <div className={styles.infoRow}>
                <span>Teammates</span>
                <span className={styles.infoValue}>{swarmTeammates.length}</span>
              </div>
              <div className={styles.infoRow}>
                <span>Channels</span>
                <span className={styles.infoValue}>{channels.filter(c => c.enabled).length}</span>
              </div>
            </div>
          </div>
        </div>
        </div>

        {/* Resize Handle */}
        <div 
          className={`${styles.resizeHandle} ${isResizingSidebar ? styles.resizing : ''}`}
          onMouseDown={handleMouseDown}
        />
      </aside>
    </>
  );
}