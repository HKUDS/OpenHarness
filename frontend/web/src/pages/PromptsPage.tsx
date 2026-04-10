import { useState, useEffect } from 'react';
import { FileText, RefreshCw, Brain, Folder, Cpu, Zap, Info, CheckCircle, XCircle, Copy, Check, Settings, Sliders } from 'lucide-react';
import styles from '../styles/PageLayout.module.css';

interface ClaudeMdFile {
  path: string;
  relative: string;
  exists: boolean;
}

interface EnvironmentInfo {
  os: string;
  python_version: string;
  shell: string;
  working_directory: string;
  [key: string]: string | number | boolean;
}

interface PromptsResponse {
  system_prompt: string | null;
  claude_md_files: ClaudeMdFile[];
  environment: EnvironmentInfo;
  model: string;
  effort: string;
  passes: number;
}

const EFFORT_LEVELS = [
  { value: 'low', label: 'Low', description: 'Quick responses, minimal analysis' },
  { value: 'medium', label: 'Medium', description: 'Balanced depth and speed' },
  { value: 'high', label: 'High', description: 'Thorough analysis, detailed responses' },
];

export function PromptsPage() {
  const [data, setData] = useState<PromptsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'files' | 'environment' | 'settings'>('files');
  const [copiedPrompt, setCopiedPrompt] = useState(false);
  
  const fetchPrompts = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/prompts');
      if (!response.ok) {
        throw new Error('Failed to fetch prompts');
      }
      const promptsData: PromptsResponse = await response.json();
      setData(promptsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchPrompts();
  }, []);
  
  useEffect(() => {
    if (copiedPrompt) {
      const timer = setTimeout(() => setCopiedPrompt(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [copiedPrompt]);
  
  const handleCopyPrompt = async () => {
    if (data?.system_prompt) {
      try {
        await navigator.clipboard.writeText(data.system_prompt);
        setCopiedPrompt(true);
      } catch (err) {
        console.error('Failed to copy prompt:', err);
      }
    }
  };
  
  const existingFiles = data?.claude_md_files.filter(f => f.exists) || [];
  const missingFiles = data?.claude_md_files.filter(f => !f.exists) || [];

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><FileText size={24} /> Prompts & Context</h1>
        <p>Manage system prompts and context files</p>
      </div>
      
      {data && (
        <div className={styles.statsGrid}>
          <div className={styles.statCard}>
            <span className={styles.statValue}>{existingFiles.length}</span>
            <span className={styles.statLabel}>Available Files</span>
          </div>
          <div className={styles.statCard}>
            <span className={styles.statValue} style={{ color: data.effort === 'high' ? '#10b981' : data.effort === 'low' ? '#f59e0b' : 'var(--primary-500)' }}>
              {data.effort}
            </span>
            <span className={styles.statLabel}>Effort Level</span>
          </div>
          <div className={styles.statCard}>
            <span className={styles.statValue}>{data.passes}</span>
            <span className={styles.statLabel}>Passes</span>
          </div>
          <div className={styles.statCard}>
            <span className={styles.statValue}>{data.model.split('-').pop()?.substring(0, 8) || 'N/A'}</span>
            <span className={styles.statLabel}>Model</span>
          </div>
        </div>
      )}
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
          <div className={styles.tabButtons}>
            <button 
              className={`${styles.tabButton} ${activeTab === 'files' ? styles.activeTab : ''}`}
              onClick={() => setActiveTab('files')}
            >
              <FileText size={16} />
              CLAUDE.md Files
              {existingFiles.length > 0 && (
                <span className={styles.eventCountEnhanced} style={{ marginLeft: 'var(--space-2)' }}>
                  {existingFiles.length}
                </span>
              )}
            </button>
            <button 
              className={`${styles.tabButton} ${activeTab === 'environment' ? styles.activeTab : ''}`}
              onClick={() => setActiveTab('environment')}
            >
              <Cpu size={16} />
              Environment
            </button>
            <button 
              className={`${styles.tabButton} ${activeTab === 'settings' ? styles.activeTab : ''}`}
              onClick={() => setActiveTab('settings')}
            >
              <Sliders size={16} />
              Reasoning
            </button>
          </div>
          
          <div style={{ flex: 1 }} />
          
          <button 
            className={styles.primaryButton}
            onClick={fetchPrompts}
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
            <h3>Loading prompts configuration...</h3>
          </div>
        ) : !data ? (
          <div className={styles.emptyState}>
            <FileText size={48} />
            <h3>No prompt data available</h3>
          </div>
        ) : (
          <>
            {activeTab === 'files' && (
              <div className={styles.filesSection}>
                {/* System Prompt */}
                {data.system_prompt && (
                  <div className={styles.formCard}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-3)' }}>
                      <h3 style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', margin: 0 }}>
                        <Brain size={18} />
                        System Prompt
                      </h3>
                      <button 
                        className={styles.copyButton}
                        onClick={handleCopyPrompt}
                        title="Copy prompt"
                      >
                        {copiedPrompt ? <Check size={14} /> : <Copy size={14} />}
                      </button>
                    </div>
                    <pre className={styles.promptPreview} style={{ 
                      maxHeight: '200px', 
                      overflow: 'auto',
                      background: 'var(--bg-tertiary)',
                      padding: 'var(--space-3)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '0.8125rem',
                      margin: 0
                    }}>
                      {data.system_prompt}
                    </pre>
                  </div>
                )}
                
                {/* CLAUDE.md Files */}
                {data.claude_md_files.length === 0 ? (
                  <div className={styles.emptyState}>
                    <FileText size={48} />
                    <h3>No CLAUDE.md files found</h3>
                    <p>Create CLAUDE.md files to provide project-specific context</p>
                  </div>
                ) : (
                  <div className={styles.filesGrid}>
                    {data.claude_md_files.map((file, index) => (
                      <div 
                        key={index} 
                        className={`${styles.fileCardEnhanced} ${file.exists ? styles.fileExists : styles.fileMissing} ${styles.animateIn}`}
                        style={{ animationDelay: `${index * 50}ms` }}
                      >
                        <div className={styles.fileHeaderEnhanced}>
                          <div className={styles.fileIconEnhanced}>
                            {file.exists ? <CheckCircle size={18} /> : <XCircle size={18} />}
                          </div>
                          <div style={{ flex: 1 }}>
                            <span className={styles.fileNameEnhanced}>
                              {file.relative || file.path.split('/').pop()}
                            </span>
                            <span className={`${styles.fileStatusEnhanced} ${file.exists ? styles.exists : styles.missing}`}>
                              {file.exists ? 'Available' : 'Not found'}
                            </span>
                          </div>
                        </div>
                        <div className={styles.filePathEnhanced}>
                          <Folder size={12} />
                          <code>{file.path}</code>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Summary */}
                {missingFiles.length > 0 && (
                  <div className={styles.formCard} style={{ marginTop: 'var(--space-4)', background: 'rgba(245, 158, 11, 0.1)', borderColor: 'rgba(245, 158, 11, 0.3)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', color: '#f59e0b' }}>
                      <Info size={18} />
                      <span style={{ fontWeight: 500 }}>Missing Files</span>
                    </div>
                    <p style={{ color: 'var(--text-secondary)', margin: 'var(--space-2) 0 0 0', fontSize: '0.875rem' }}>
                      {missingFiles.length} CLAUDE.md file{missingFiles.length !== 1 ? 's' : ''} referenced but not found. 
                      Consider creating {missingFiles.length === 1 ? 'it' : 'them'} to provide additional context.
                    </p>
                  </div>
                )}
              </div>
            )}
            
            {activeTab === 'environment' && (
              <div className={styles.environmentSection}>
                <div className={styles.formCard}>
                  <h3 style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-4)' }}>
                    <Cpu size={18} />
                    Environment Information
                  </h3>
                  <div className={styles.envGridEnhanced}>
                    {Object.entries(data.environment).map(([key, value]) => (
                      <div key={key} className={styles.envItemEnhanced}>
                        <span className={styles.envKeyEnhanced}>
                          {key.replace(/_/g, ' ')}
                        </span>
                        <span className={styles.envValueEnhanced}>
                          {typeof value === 'boolean' 
                            ? (value ? 'Yes' : 'No')
                            : String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div className={styles.formCard}>
                  <h3 style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-4)' }}>
                    <Settings size={18} />
                    Model Configuration
                  </h3>
                  <div className={styles.envGridEnhanced}>
                    <div className={styles.envItemEnhanced}>
                      <span className={styles.envKeyEnhanced}>Model</span>
                      <span className={styles.envValueEnhanced}>{data.model}</span>
                    </div>
                    <div className={styles.envItemEnhanced}>
                      <span className={styles.envKeyEnhanced}>Effort</span>
                      <span className={styles.envValueEnhanced} style={{ 
                        color: data.effort === 'high' ? '#10b981' : data.effort === 'low' ? '#f59e0b' : 'var(--primary-500)'
                      }}>
                        {data.effort}
                      </span>
                    </div>
                    <div className={styles.envItemEnhanced}>
                      <span className={styles.envKeyEnhanced}>Passes</span>
                      <span className={styles.envValueEnhanced}>{data.passes}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
            
            {activeTab === 'settings' && (
              <div className={styles.settingsSection}>
                <div className={styles.reasoningSection}>
                  <div className={styles.reasoningHeader}>
                    <Zap size={18} />
                    Reasoning Settings
                  </div>
                  
                  <div style={{ marginBottom: 'var(--space-4)' }}>
                    <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 'var(--space-2)' }}>
                      Effort Level
                    </label>
                    <div className={styles.effortSelectorEnhanced}>
                      {EFFORT_LEVELS.map(level => (
                        <button
                          key={level.value}
                          className={`${styles.effortButtonEnhanced} ${data.effort === level.value ? styles.active : ''}`}
                        >
                          <span className={styles.effortLabel}>{level.label}</span>
                          <span className={styles.effortDesc}>{level.description}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                  
                  <div>
                    <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 'var(--space-2)' }}>
                      Number of Passes
                    </label>
                    <div className={styles.passesSelector}>
                      <input
                        type="number"
                        value={data.passes}
                        readOnly
                        className={styles.passesInput}
                      />
                      <span className={styles.passesHint}>
                        Higher values provide more thorough analysis
                      </span>
                    </div>
                  </div>
                </div>
                
                <div className={styles.formCard} style={{ marginTop: 'var(--space-4)' }}>
                  <h3 style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
                    <Info size={18} />
                    About Reasoning Settings
                  </h3>
                  <ul className={styles.settingsInfo}>
                    <li>
                      <strong>Effort Level</strong> controls how much computational effort the model puts into each response
                    </li>
                    <li>
                      <strong>Passes</strong> determines how many times the model refines its response
                    </li>
                    <li>
                      Higher effort and passes lead to more detailed, accurate responses but take longer
                    </li>
                    <li>
                      These settings can be configured in your OpenHarness configuration file
                    </li>
                  </ul>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}