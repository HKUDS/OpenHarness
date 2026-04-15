import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Terminal, RefreshCw, Search, ChevronDown, ChevronUp, Star, Info, Copy, Check, Command, Settings, Zap, HelpCircle, Code, GitBranch, FileText, Database, Activity, Download, Upload, FolderOpen, Link, X, AlertCircle, Globe } from 'lucide-react';
import styles from '../styles/PageLayout.module.css';

interface Command {
  name: string;
  description: string;
  template?: string;
  category?: string;
}

interface CommandsResponse {
  commands: Command[];
  total: number;
}

const COMMAND_CATEGORIES: Record<string, { icon: React.ReactNode; color: string }> = {
  'General': { icon: <HelpCircle size={14} />, color: '#6b7280' },
  'Configuration': { icon: <Settings size={14} />, color: '#3b82f6' },
  'Workflow': { icon: <Zap size={14} />, color: '#10b981' },
  'Tasks': { icon: <Activity size={14} />, color: '#f59e0b' },
  'Providers': { icon: <Database size={14} />, color: '#8b5cf6' },
  'Memory': { icon: <FileText size={14} />, color: '#ec4899' },
  'System': { icon: <Terminal size={14} />, color: '#06b6d4' },
  'Git': { icon: <GitBranch size={14} />, color: '#f97316' },
  'Development': { icon: <Code size={14} />, color: '#84cc16' },
};

function getCommandCategory(commandName: string): string {
  const name = commandName.replace('/', '').toLowerCase();
  
  if (['help', 'version', 'status', 'clear', 'exit'].some(n => name.includes(n))) return 'General';
  if (['model', 'theme', 'permissions', 'effort', 'passes', 'turns', 'vim', 'voice', 'fast'].some(n => name.includes(n))) return 'Configuration';
  if (['plan', 'commit', 'review', 'test', 'debug', 'simplify'].some(n => name.includes(n))) return 'Workflow';
  if (['resume', 'task', 'agent', 'swarm'].some(n => name.includes(n))) return 'Tasks';
  if (['provider', 'auth', 'mcp'].some(n => name.includes(n))) return 'Providers';
  if (['memory', 'todo'].some(n => name.includes(n))) return 'Memory';
  if (['doctor', 'config', 'setup', 'plugin'].some(n => name.includes(n))) return 'System';
  if (['git', 'branch', 'push', 'pull'].some(n => name.includes(n))) return 'Git';
  if (['code', 'build', 'run', 'lint'].some(n => name.includes(n))) return 'Development';
  
  return 'General';
}

export function CommandsPage() {
  const [commands, setCommands] = useState<Command[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedCommand, setExpandedCommand] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [copiedCommand, setCopiedCommand] = useState<string | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importUrl, setImportUrl] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  
  const fetchCommands = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/commands');
      if (!response.ok) {
        throw new Error('Failed to fetch commands');
      }
      const data: CommandsResponse = await response.json();
      setCommands(data.commands);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchCommands();
  }, []);
  
  useEffect(() => {
    if (copiedCommand) {
      const timer = setTimeout(() => setCopiedCommand(null), 2000);
      return () => clearTimeout(timer);
    }
  }, [copiedCommand]);
  
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    
    setImportLoading(true);
    setImportError(null);
    
    try {
      for (const file of Array.from(files)) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('type', 'command');
        
        const response = await fetch('/api/import', {
          method: 'POST',
          body: formData,
        });
        
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.error || `Failed to import ${file.name}`);
        }
      }
      
      setShowImportModal(false);
      fetchCommands();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Failed to import file');
    } finally {
      setImportLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
      if (folderInputRef.current) folderInputRef.current.value = '';
    }
  };
  
  const handleUrlImport = async () => {
    if (!importUrl) return;
    
    setImportLoading(true);
    setImportError(null);
    
    try {
      let fetchUrl = importUrl;
      if (importUrl.includes('github.com') && !importUrl.includes('raw')) {
        fetchUrl = importUrl
          .replace('github.com', 'raw.githubusercontent.com')
          .replace('/blob/', '/');
      }
      
      const response = await fetch('/api/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: fetchUrl, type: 'command' }),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to import from URL');
      }
      
      setShowImportModal(false);
      setImportUrl('');
      fetchCommands();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Failed to import from URL');
    } finally {
      setImportLoading(false);
    }
  };
  
  const handleCopyCommand = async (commandName: string) => {
    try {
      await navigator.clipboard.writeText(commandName);
      setCopiedCommand(commandName);
    } catch (err) {
      console.error('Failed to copy command:', err);
    }
  };
  
  const toggleFavorite = (commandName: string) => {
    setFavorites(prev => {
      const next = new Set(prev);
      if (next.has(commandName)) {
        next.delete(commandName);
      } else {
        next.add(commandName);
      }
      return next;
    });
  };
  
  const filteredCommands = commands.filter(command => {
    const matchesSearch = searchQuery === '' || 
      command.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      command.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = selectedCategory === null || getCommandCategory(command.name) === selectedCategory;
    return matchesSearch && matchesCategory;
  });
  
  const categories = Array.from(new Set(commands.map(c => getCommandCategory(c.name))));
  
  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Terminal size={24} /> Commands</h1>
        <p>Browse and execute slash commands</p>
      </div>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{total}</span>
          <span className={styles.statLabel}>Total Commands</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{categories.length}</span>
          <span className={styles.statLabel}>Categories</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{favorites.size}</span>
          <span className={styles.statLabel}>Favorites</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{commands.filter(c => c.template).length}</span>
          <span className={styles.statLabel}>With Templates</span>
        </div>
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
          <div className={styles.searchContainer}>
            <Search size={18} />
            <input
              type="text"
              placeholder="Search commands..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={styles.searchInput}
            />
          </div>
          
          <div className={styles.filterChips}>
            {categories.slice(0, 6).map(cat => {
              const catInfo = COMMAND_CATEGORIES[cat] || { icon: <Command size={14} />, color: '#6b7280' };
              return (
                <button
                  key={cat}
                  className={`${styles.filterChip} ${selectedCategory === cat ? styles.active : ''}`}
                  onClick={() => setSelectedCategory(selectedCategory === cat ? null : cat)}
                >
                  <span style={{ color: catInfo.color }}>{catInfo.icon}</span>
                  {cat}
                </button>
              );
            })}
            {categories.length > 6 && (
              <select
                className={styles.categorySelect}
                value={selectedCategory || ''}
                onChange={(e) => setSelectedCategory(e.target.value || null)}
                style={{ padding: 'var(--space-1) var(--space-2)', minWidth: 'auto' }}
              >
                <option value="">More...</option>
                {categories.slice(6).map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            )}
          </div>
          
          <div style={{ flex: 1 }} />
          
          <button 
            className={styles.secondaryButton}
            onClick={() => setShowImportModal(true)}
          >
            <Download size={18} />
            Import
          </button>
          
          <button 
            className={styles.primaryButton}
            onClick={fetchCommands}
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
            <h3>Loading commands...</h3>
          </div>
        ) : filteredCommands.length === 0 ? (
          <div className={styles.emptyState}>
            <Terminal size={48} />
            <h3>No commands found</h3>
            <p>Try adjusting your search or category filter</p>
          </div>
        ) : (
          <div className={styles.commandsGrid}>
            {filteredCommands.map((command, index) => {
              const category = getCommandCategory(command.name);
              const catInfo = COMMAND_CATEGORIES[category] || { icon: <Command size={14} />, color: '#6b7280' };
              
              return (
                <div 
                  key={command.name} 
                  className={`${styles.commandCardEnhanced} ${styles.animateIn}`}
                  style={{ animationDelay: `${index * 30}ms` }}
                >
                  <div className={styles.commandHeaderEnhanced}>
                    <div 
                      className={styles.commandIconEnhanced}
                      style={{ 
                        background: `linear-gradient(135deg, ${catInfo.color}15 0%, ${catInfo.color}05 100%)`,
                        color: catInfo.color
                      }}
                    >
                      {catInfo.icon}
                    </div>
                    <div className={styles.commandTitleEnhanced}>
                      <span className={styles.commandNameEnhanced}>
                        {command.name}
                        {favorites.has(command.name) && (
                          <Star size={12} fill="#f59e0b" style={{ color: '#f59e0b', marginLeft: 'var(--space-1)' }} />
                        )}
                      </span>
                      <span 
                        className={styles.commandCategoryEnhanced}
                        style={{ color: catInfo.color }}
                      >
                        {category}
                      </span>
                    </div>
                    <button 
                      className={`${styles.favoriteButton} ${favorites.has(command.name) ? styles.active : ''}`}
                      onClick={() => toggleFavorite(command.name)}
                      title="Add to favorites"
                    >
                      <Star size={16} fill={favorites.has(command.name) ? 'currentColor' : 'none'} />
                    </button>
                  </div>
                  
                  <p className={styles.commandDescriptionEnhanced}>{command.description}</p>
                  
                  {/* Actions */}
                  <div className={styles.commandActionsEnhanced}>
                    <button 
                      className={styles.executeButton}
                      onClick={() => handleCopyCommand(command.name)}
                    >
                      {copiedCommand === command.name ? <Check size={14} /> : <Copy size={14} />}
                      {copiedCommand === command.name ? 'Copied!' : 'Copy'}
                    </button>
                    <button 
                      className={styles.expandButton}
                      onClick={() => setExpandedCommand(expandedCommand === command.name ? null : command.name)}
                      style={{ width: 'auto', padding: 'var(--space-2) var(--space-3)' }}
                    >
                      {expandedCommand === command.name ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      Details
                    </button>
                  </div>
                  
                  {/* Expanded Details */}
                  {expandedCommand === command.name && (
                    <div className={styles.commandDetailsEnhanced}>
                      {command.template && (
                        <div className={styles.templateSectionEnhanced}>
                          <h4>Template</h4>
                          <pre className={styles.templatePreviewEnhanced}>{command.template}</pre>
                        </div>
                      )}
                      
                      <div className={styles.usageHintEnhanced}>
                        <Info size={12} />
                        <span>Type <code>{command.name}</code> in the chat to execute this command</span>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
      
      {/* Import Modal */}
      {showImportModal && createPortal(
        <div className={styles.modalOverlay}>
          <div className={styles.modal} data-import-modal>
            <div className={styles.modalHeader}>
              <h2><Download size={20} /> Import Commands</h2>
              <button 
                className={styles.modalClose}
                onClick={() => {
                  setShowImportModal(false);
                  setImportError(null);
                  setImportUrl('');
                }}
              >
                <X size={20} />
              </button>
            </div>
            
            <div className={styles.modalContent}>
              <div className={styles.importOptions}>
                <div className={styles.importOption}>
                  <div className={styles.importOptionHeader}>
                    <Upload size={20} />
                    <h3>Upload Files</h3>
                  </div>
                  <p className={styles.importOptionDesc}>
                    Upload command definition files (.json, .md)
                  </p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".json,.md"
                    onChange={handleFileUpload}
                    style={{ display: 'none' }}
                  />
                  <button 
                    className={styles.primaryButton}
                    onClick={() => fileInputRef.current?.click()}
                    disabled={importLoading}
                  >
                    <Upload size={16} />
                    Select Files
                  </button>
                </div>
                
                <div className={styles.importOption}>
                  <div className={styles.importOptionHeader}>
                    <FolderOpen size={20} />
                    <h3>Upload Folder</h3>
                  </div>
                  <p className={styles.importOptionDesc}>
                    Import multiple command files from a folder
                  </p>
                  <input
                    ref={folderInputRef}
                    type="file"
                    multiple
                    // @ts-expect-error webkitdirectory is not in the type definitions
                    webkitdirectory="true"
                    onChange={handleFileUpload}
                    style={{ display: 'none' }}
                  />
                  <button 
                    className={styles.primaryButton}
                    onClick={() => folderInputRef.current?.click()}
                    disabled={importLoading}
                  >
                    <FolderOpen size={16} />
                    Select Folder
                  </button>
                </div>
                
                <div className={styles.importOption}>
                  <div className={styles.importOptionHeader}>
                    <Link size={20} />
                    <h3>Import from URL</h3>
                  </div>
                  <p className={styles.importOptionDesc}>
                    Import from GitHub or any URL
                  </p>
                  <div className={styles.urlInputSection}>
                    <input
                      type="url"
                      value={importUrl}
                      onChange={(e) => setImportUrl(e.target.value)}
                      placeholder="https://github.com/user/repo/commands.json"
                      className={styles.urlInput}
                    />
                    <button 
                      className={styles.primaryButton}
                      onClick={handleUrlImport}
                      disabled={!importUrl || importLoading}
                    >
                      {importLoading ? <RefreshCw size={16} className={styles.spinning} /> : <Download size={16} />}
                      Import
                    </button>
                  </div>
                  <div className={styles.urlExamples}>
                    <p><Globe size={14} /> GitHub: github.com/user/repo/commands.json</p>
                  </div>
                </div>
              </div>
              
              {importError && (
                <div className={styles.errorAlert}>
                  <AlertCircle size={18} />
                  <span>{importError}</span>
                </div>
              )}
              
              {importLoading && (
                <div className={styles.loadingIndicator}>
                  <RefreshCw size={24} className={styles.spinning} />
                  <span>Importing...</span>
                </div>
              )}
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}