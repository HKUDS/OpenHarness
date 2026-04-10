import { useState, useEffect } from 'react';
import { Wrench, RefreshCw, Search, Code, FileText, Database, Globe, Terminal, ChevronDown, ChevronUp, Star, Copy, Check, Info, Shield, ShieldAlert, Zap } from 'lucide-react';
import styles from '../styles/PageLayout.module.css';

interface Tool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  is_read_only: boolean;
}

interface ToolsResponse {
  tools: Tool[];
  total: number;
}

const TOOL_ICONS: Record<string, React.ReactNode> = {
  'bash': <Terminal size={18} />,
  'read_file': <FileText size={18} />,
  'write_file': <FileText size={18} />,
  'edit_file': <FileText size={18} />,
  'glob': <Search size={18} />,
  'grep': <Search size={18} />,
  'lsp': <Code size={18} />,
  'web_fetch': <Globe size={18} />,
  'web_search': <Globe size={18} />,
  'task': <Terminal size={18} />,
  'mcp': <Database size={18} />,
  'notebook_edit': <FileText size={18} />,
};

const TOOL_CATEGORIES: Record<string, string[]> = {
  'File Operations': ['read_file', 'write_file', 'edit_file', 'glob', 'notebook_edit'],
  'Search & Analysis': ['grep', 'lsp', 'tool_search', 'web_search', 'web_fetch'],
  'System & Execution': ['bash', 'task_create', 'task_get', 'task_list', 'task_stop', 'task_output', 'task_update'],
  'MCP & Resources': ['mcp_', 'list_mcp_resources', 'read_mcp_resource', 'mcp_auth'],
  'Workflow': ['skill', 'config', 'enter_plan_mode', 'exit_plan_mode', 'enter_worktree', 'exit_worktree'],
  'Scheduling': ['cron_create', 'cron_list', 'cron_delete', 'cron_toggle', 'remote_trigger'],
  'Communication': ['ask_user_question', 'send_message', 'team_create', 'team_delete'],
  'Utilities': ['brief', 'sleep', 'todo_write', 'agent'],
};

const CATEGORY_COLORS: Record<string, string> = {
  'File Operations': '#10b981',
  'Search & Analysis': '#3b82f6',
  'System & Execution': '#f59e0b',
  'MCP & Resources': '#8b5cf6',
  'Workflow': '#ec4899',
  'Scheduling': '#06b6d4',
  'Communication': '#84cc16',
  'Utilities': '#6b7280',
};

function getToolCategory(toolName: string): string {
  for (const [category, patterns] of Object.entries(TOOL_CATEGORIES)) {
    for (const pattern of patterns) {
      if (toolName.includes(pattern) || toolName === pattern) {
        return category;
      }
    }
  }
  return 'Other';
}

export function ToolsPage() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedTool, setExpandedTool] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [copiedSchema, setCopiedSchema] = useState<string | null>(null);
  
  const fetchTools = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/tools');
      if (!response.ok) {
        throw new Error('Failed to fetch tools');
      }
      const data: ToolsResponse = await response.json();
      setTools(data.tools);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchTools();
  }, []);
  
  useEffect(() => {
    if (copiedSchema) {
      const timer = setTimeout(() => setCopiedSchema(null), 2000);
      return () => clearTimeout(timer);
    }
  }, [copiedSchema]);
  
  const handleCopySchema = async (schema: Record<string, unknown>, toolName: string) => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(schema, null, 2));
      setCopiedSchema(toolName);
    } catch (err) {
      console.error('Failed to copy schema:', err);
    }
  };
  
  const toggleFavorite = (toolName: string) => {
    setFavorites(prev => {
      const next = new Set(prev);
      if (next.has(toolName)) {
        next.delete(toolName);
      } else {
        next.add(toolName);
      }
      return next;
    });
  };
  
  const filteredTools = tools.filter(tool => {
    const matchesSearch = searchQuery === '' || 
      tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tool.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = selectedCategory === null || getToolCategory(tool.name) === selectedCategory;
    return matchesSearch && matchesCategory;
  });
  
  const categories = Array.from(new Set(tools.map(t => getToolCategory(t.name))));
  const readOnlyCount = tools.filter(t => t.is_read_only).length;
  const writeCount = tools.length - readOnlyCount;

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Wrench size={24} /> Tools</h1>
        <p>Browse and manage available tools</p>
      </div>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{total}</span>
          <span className={styles.statLabel}>Total Tools</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{readOnlyCount}</span>
          <span className={styles.statLabel}>Read-Only</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{writeCount}</span>
          <span className={styles.statLabel}>Write Access</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{categories.length}</span>
          <span className={styles.statLabel}>Categories</span>
        </div>
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
          <div className={styles.searchContainer}>
            <Search size={18} />
            <input
              type="text"
              placeholder="Search tools..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={styles.searchInput}
            />
          </div>
          
          <div className={styles.filterChips}>
            <button
              className={`${styles.filterChip} ${selectedCategory === null ? styles.active : ''}`}
              onClick={() => setSelectedCategory(null)}
            >
              All
            </button>
            {categories.map(cat => (
              <button
                key={cat}
                className={`${styles.filterChip} ${selectedCategory === cat ? styles.active : ''}`}
                onClick={() => setSelectedCategory(selectedCategory === cat ? null : cat)}
              >
                <span 
                  className={styles.statusDot} 
                  style={{ background: CATEGORY_COLORS[cat] || '#6b7280', width: '6px', height: '6px' }}
                />
                {cat}
              </button>
            ))}
          </div>
          
          <div style={{ flex: 1 }} />
          
          <button 
            className={styles.primaryButton}
            onClick={fetchTools}
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
            <h3>Loading tools...</h3>
          </div>
        ) : filteredTools.length === 0 ? (
          <div className={styles.emptyState}>
            <Wrench size={48} />
            <h3>No tools found</h3>
            <p>Try adjusting your search or category filter</p>
          </div>
        ) : (
          <div className={styles.toolsGrid}>
            {filteredTools.map((tool, index) => (
              <div 
                key={tool.name} 
                className={`${styles.toolCardEnhanced} ${tool.is_read_only ? styles.readOnly : ''} ${styles.animateIn}`}
                style={{ animationDelay: `${index * 30}ms` }}
              >
                <div className={styles.toolHeaderEnhanced}>
                  <div className={styles.toolIconEnhanced}>
                    {TOOL_ICONS[tool.name.split('_')[0]] || <Wrench size={18} />}
                  </div>
                  <div className={styles.toolTitleEnhanced}>
                    <span className={styles.toolNameEnhanced}>{tool.name}</span>
                    <span 
                      className={styles.toolCategoryEnhanced}
                      style={{ 
                        background: `${CATEGORY_COLORS[getToolCategory(tool.name)]}15`,
                        color: CATEGORY_COLORS[getToolCategory(tool.name)] || 'var(--text-tertiary)'
                      }}
                    >
                      {getToolCategory(tool.name)}
                    </span>
                  </div>
                  <button 
                    className={`${styles.favoriteButton} ${favorites.has(tool.name) ? styles.active : ''}`}
                    onClick={() => toggleFavorite(tool.name)}
                    title="Add to favorites"
                  >
                    <Star size={16} fill={favorites.has(tool.name) ? 'currentColor' : 'none'} />
                  </button>
                </div>
                
                <p className={styles.toolDescriptionEnhanced}>{tool.description}</p>
                
                {/* Tool Tags */}
                <div className={styles.toolTagsEnhanced}>
                  {tool.is_read_only ? (
                    <span className={`${styles.toolTagEnhanced} ${styles.readOnly}`}>
                      <Shield size={10} />
                      Read-Only
                    </span>
                  ) : (
                    <span className={`${styles.toolTagEnhanced} ${styles.write}`}>
                      <ShieldAlert size={10} />
                      Write Access
                    </span>
                  )}
                  {tool.input_schema && (
                    <span className={styles.toolTagEnhanced} style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>
                      <Zap size={10} />
                      Has Schema
                    </span>
                  )}
                </div>
                
                {/* Schema View */}
                {tool.input_schema && Object.keys(tool.input_schema).length > 0 && (
                  <div className={styles.schemaViewEnhanced}>
                    <div className={styles.schemaViewHeader}>
                      <span className={styles.schemaViewTitle}>
                        <Code size={14} />
                        Input Schema
                      </span>
                      <div style={{ display: 'flex', gap: 'var(--space-1)' }}>
                        <button 
                          className={styles.copyButton}
                          onClick={() => handleCopySchema(tool.input_schema, tool.name)}
                          title="Copy schema"
                        >
                          {copiedSchema === tool.name ? <Check size={14} /> : <Copy size={14} />}
                        </button>
                        <button 
                          className={styles.expandButton}
                          onClick={() => setExpandedTool(expandedTool === tool.name ? null : tool.name)}
                          style={{ padding: '4px 8px', width: 'auto' }}
                        >
                          {expandedTool === tool.name ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </button>
                      </div>
                    </div>
                    <pre className={styles.schemaViewContent} style={{ 
                      maxHeight: expandedTool === tool.name ? '400px' : '80px',
                      overflow: 'hidden'
                    }}>
                      {JSON.stringify(tool.input_schema, null, 2)}
                    </pre>
                  </div>
                )}
                
                {/* Usage Hint */}
                <div className={styles.usageHintEnhanced} style={{ marginTop: 'var(--space-3)' }}>
                  <Info size={12} />
                  <span>Tool is automatically available to the AI assistant</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}