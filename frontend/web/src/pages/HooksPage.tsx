import { useState, useEffect } from 'react';
import { Zap, RefreshCw, Terminal, MessageSquare, Globe, Bot, Clock, Shield, ChevronDown, ChevronUp, Copy, Check } from 'lucide-react';
import styles from '../styles/PageLayout.module.css';

interface Hook {
  event: string;
  type: 'command' | 'prompt' | 'http' | 'agent';
  matcher: string | null;
  timeout_seconds: number;
  block_on_failure: boolean;
  command?: string;
  prompt?: string;
  url?: string;
}

interface HooksResponse {
  hooks: Hook[];
  total: number;
  events: string[];
}

const HOOK_TYPE_ICONS: Record<string, React.ReactNode> = {
  'command': <Terminal size={16} />,
  'prompt': <MessageSquare size={16} />,
  'http': <Globe size={16} />,
  'agent': <Bot size={16} />,
};

const HOOK_TYPE_COLORS: Record<string, string> = {
  'command': '#10b981',
  'prompt': '#6366f1',
  'http': '#f59e0b',
  'agent': '#ec4899',
};

const HOOK_EVENTS_INFO: Record<string, { description: string; color: string }> = {
  'PreToolUse': { description: 'Triggered before a tool is executed', color: '#3b82f6' },
  'PostToolUse': { description: 'Triggered after a tool completes', color: '#10b981' },
  'Notification': { description: 'Triggered on notifications', color: '#f59e0b' },
  'Stop': { description: 'Triggered when session stops', color: '#ef4444' },
  'SubagentStop': { description: 'Triggered when a subagent stops', color: '#8b5cf6' },
};

export function HooksPage() {
  const [hooks, setHooks] = useState<Hook[]>([]);
  const [events, setEvents] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const [expandedHook, setExpandedHook] = useState<number | null>(null);
  const [copiedContent, setCopiedContent] = useState<number | null>(null);
  
  const fetchHooks = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/hooks');
      if (!response.ok) {
        throw new Error('Failed to fetch hooks');
      }
      const data: HooksResponse = await response.json();
      setHooks(data.hooks);
      setEvents(data.events);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchHooks();
  }, []);
  
  useEffect(() => {
    if (copiedContent !== null) {
      const timer = setTimeout(() => setCopiedContent(null), 2000);
      return () => clearTimeout(timer);
    }
  }, [copiedContent]);
  
  const handleCopyContent = async (content: string, index: number) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedContent(index);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };
  
  const filteredHooks = selectedEvent === null 
    ? hooks 
    : hooks.filter(h => h.event === selectedEvent);
  
  const hooksByEvent = filteredHooks.reduce((acc, hook) => {
    if (!acc[hook.event]) {
      acc[hook.event] = [];
    }
    acc[hook.event].push(hook);
    return acc;
  }, {} as Record<string, Hook[]>);
  
  const blockingCount = hooks.filter(h => h.block_on_failure).length;
  const hooksByType = hooks.reduce((acc, h) => {
    acc[h.type] = (acc[h.type] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Zap size={24} /> Hooks</h1>
        <p>Configure lifecycle hooks for OpenHarness</p>
      </div>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{total}</span>
          <span className={styles.statLabel}>Total Hooks</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{events.length}</span>
          <span className={styles.statLabel}>Active Events</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{blockingCount}</span>
          <span className={styles.statLabel}>Blocking</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{Object.keys(hooksByType).length}</span>
          <span className={styles.statLabel}>Hook Types</span>
        </div>
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
          <div className={styles.filterChips}>
            <button
              className={`${styles.filterChip} ${selectedEvent === null ? styles.active : ''}`}
              onClick={() => setSelectedEvent(null)}
            >
              All Events
            </button>
            {events.map(event => (
              <button
                key={event}
                className={`${styles.filterChip} ${selectedEvent === event ? styles.active : ''}`}
                onClick={() => setSelectedEvent(selectedEvent === event ? null : event)}
              >
                <span 
                  className={styles.statusDot}
                  style={{ 
                    background: HOOK_EVENTS_INFO[event]?.color || '#6b7280',
                    width: '6px',
                    height: '6px'
                  }}
                />
                {event}
              </button>
            ))}
          </div>
          
          <div style={{ flex: 1 }} />
          
          <button 
            className={styles.primaryButton}
            onClick={fetchHooks}
            disabled={loading}
          >
            <RefreshCw size={18} className={loading ? styles.spinning : ''} />
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
        
        {error && (
          <div className={styles.formCard}>
            <p style={{ color: '#ef4444' }}>Error: {error}</p>
          </div>
        )}
        
        {loading ? (
          <div className={styles.emptyState}>
            <RefreshCw size={48} className={styles.spinning} />
            <h3>Loading hooks...</h3>
          </div>
        ) : hooks.length === 0 ? (
          <div className={styles.emptyState}>
            <Zap size={48} />
            <h3>No hooks configured</h3>
            <p>Add hooks in your OpenHarness settings to automate workflows</p>
          </div>
        ) : (
          <div className={styles.hooksContainer}>
            {Object.entries(hooksByEvent).map(([event, eventHooks]) => (
              <div key={event} className={styles.eventSectionEnhanced}>
                <div className={styles.eventHeaderEnhanced}>
                  <span 
                    className={styles.eventNameEnhanced}
                    style={{ color: HOOK_EVENTS_INFO[event]?.color || 'var(--text-primary)' }}
                  >
                    <Zap size={18} />
                    {event}
                  </span>
                  <span className={styles.eventDescriptionEnhanced}>
                    {HOOK_EVENTS_INFO[event]?.description || 'Custom event'}
                  </span>
                  <span className={styles.eventCountEnhanced}>
                    {eventHooks.length} hook{eventHooks.length !== 1 ? 's' : ''}
                  </span>
                </div>
                
                <div className={styles.hooksGridEnhanced}>
                  {eventHooks.map((hook, index) => {
                    const globalIndex = hooks.indexOf(hook);
                    return (
                      <div 
                        key={`${hook.event}-${index}`} 
                        className={`${styles.hookCardEnhanced} ${styles.animateIn}`}
                        style={{ animationDelay: `${index * 50}ms` }}
                      >
                        <div className={styles.hookHeaderEnhanced}>
                          <div 
                            className={styles.hookTypeIconEnhanced}
                            style={{ backgroundColor: HOOK_TYPE_COLORS[hook.type] }}
                          >
                            {HOOK_TYPE_ICONS[hook.type]}
                          </div>
                          <div style={{ flex: 1 }}>
                            <span className={styles.hookTypeEnhanced}>{hook.type}</span>
                            {hook.matcher && (
                              <span className={styles.hookMatcherEnhanced}>
                                matcher: {hook.matcher}
                              </span>
                            )}
                          </div>
                          {(hook.command || hook.url || hook.prompt) && (
                            <button 
                              className={styles.copyButton}
                              onClick={() => handleCopyContent(hook.command || hook.url || hook.prompt || '', globalIndex)}
                              title="Copy content"
                            >
                              {copiedContent === globalIndex ? <Check size={12} /> : <Copy size={12} />}
                            </button>
                          )}
                        </div>
                        
                        <div className={styles.hookContentEnhanced}>
                          {hook.type === 'command' && hook.command && (
                            <code className={styles.hookCommandEnhanced}>{hook.command}</code>
                          )}
                          {hook.type === 'prompt' && hook.prompt && (
                            <p className={styles.hookPromptEnhanced}>{hook.prompt}</p>
                          )}
                          {hook.type === 'http' && hook.url && (
                            <code className={styles.hookUrlEnhanced}>{hook.url}</code>
                          )}
                          {hook.type === 'agent' && hook.prompt && (
                            <p className={styles.hookPromptEnhanced}>{hook.prompt}</p>
                          )}
                        </div>
                        
                        <div className={styles.hookMetaEnhanced}>
                          <div className={styles.hookMetaItemEnhanced}>
                            <Clock size={10} />
                            <span>{hook.timeout_seconds}s timeout</span>
                          </div>
                          {hook.block_on_failure && (
                            <div className={`${styles.hookMetaItemEnhanced} ${styles.blocking}`}>
                              <Shield size={10} />
                              <span>Blocks on failure</span>
                            </div>
                          )}
                        </div>
                        
                        {/* Test Button */}
                        <button 
                          className={styles.expandButton}
                          onClick={() => setExpandedHook(expandedHook === globalIndex ? null : globalIndex)}
                          style={{ marginTop: 'var(--space-2)' }}
                        >
                          {expandedHook === globalIndex ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                          {expandedHook === globalIndex ? 'Hide Details' : 'View Details'}
                        </button>
                        
                        {expandedHook === globalIndex && (
                          <div style={{ 
                            marginTop: 'var(--space-2)', 
                            padding: 'var(--space-2)', 
                            background: 'var(--bg-primary)', 
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.75rem'
                          }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-tertiary)' }}>Event:</span>
                                <span style={{ color: 'var(--text-primary)' }}>{hook.event}</span>
                              </div>
                              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-tertiary)' }}>Type:</span>
                                <span style={{ color: 'var(--text-primary)' }}>{hook.type}</span>
                              </div>
                              {hook.matcher && (
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                  <span style={{ color: 'var(--text-tertiary)' }}>Matcher:</span>
                                  <code style={{ color: 'var(--primary-400)' }}>{hook.matcher}</code>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}