import { useState, useEffect } from 'react';
import { 
  Activity, RefreshCw, CheckCircle, XCircle, AlertTriangle, 
  Folder, Cpu, Brain, Shield, Zap, Key, Server, 
  Settings, Palette, Terminal, Mic, Gauge, Package, Globe
} from 'lucide-react';
import styles from '../styles/PageLayout.module.css';

interface DoctorSummary {
  cwd: string;
  active_profile: string;
  model: string;
  provider_workflow: string;
  auth_source: string;
  permission_mode: string;
  theme: string;
  output_style: string;
  vim_mode: boolean;
  voice_mode: boolean;
  effort: string;
  passes: number;
  memory_dir: string;
  plugin_count: number;
  mcp_configured: boolean;
  auth_configured: boolean;
}

interface HealthCheck {
  name: string;
  status: 'ok' | 'warning' | 'error';
  message: string;
  details?: string;
  icon?: React.ReactNode;
  category?: string;
}

function getHealthChecks(summary: DoctorSummary): HealthCheck[] {
  return [
    {
      name: 'Authentication',
      status: summary.auth_configured ? 'ok' : 'error',
      message: summary.auth_configured 
        ? `Configured (${summary.auth_source})` 
        : 'Not configured',
      details: summary.auth_configured 
        ? `Using ${summary.provider_workflow}` 
        : 'Run /login to configure authentication',
      icon: <Key size={18} />,
      category: 'Core',
    },
    {
      name: 'Model',
      status: summary.model ? 'ok' : 'warning',
      message: summary.model || 'No model set',
      details: summary.model ? `Active model: ${summary.model}` : 'Set a model in settings',
      icon: <Brain size={18} />,
      category: 'Core',
    },
    {
      name: 'Working Directory',
      status: 'ok',
      message: summary.cwd.length > 40 ? '...' + summary.cwd.slice(-37) : summary.cwd,
      details: 'Current working directory',
      icon: <Folder size={18} />,
      category: 'Environment',
    },
    {
      name: 'Memory',
      status: 'ok',
      message: summary.memory_dir.length > 40 ? '...' + summary.memory_dir.slice(-37) : summary.memory_dir,
      details: 'Memory directory location',
      icon: <Server size={18} />,
      category: 'Environment',
    },
    {
      name: 'Plugins',
      status: summary.plugin_count > 0 ? 'ok' : 'warning',
      message: `${summary.plugin_count} plugins loaded`,
      details: summary.plugin_count > 0 
        ? 'Plugins are active' 
        : 'No plugins installed',
      icon: <Package size={18} />,
      category: 'Extensions',
    },
    {
      name: 'MCP Servers',
      status: summary.mcp_configured ? 'ok' : 'warning',
      message: summary.mcp_configured ? 'Configured' : 'Not configured',
      details: summary.mcp_configured 
        ? 'MCP servers are available' 
        : 'Add MCP servers in settings',
      icon: <Globe size={18} />,
      category: 'Extensions',
    },
    {
      name: 'Permission Mode',
      status: summary.permission_mode === 'full_auto' ? 'warning' : 'ok',
      message: summary.permission_mode,
      details: summary.permission_mode === 'full_auto' 
        ? 'Auto mode - be careful with sensitive operations' 
        : 'Current permission mode',
      icon: <Shield size={18} />,
      category: 'Settings',
    },
    {
      name: 'Reasoning',
      status: 'ok',
      message: `${summary.effort} effort, ${summary.passes} passes`,
      details: `Reasoning effort: ${summary.effort}, passes: ${summary.passes}`,
      icon: <Gauge size={18} />,
      category: 'Settings',
    },
    {
      name: 'Theme',
      status: 'ok',
      message: summary.theme,
      details: `UI theme: ${summary.theme}`,
      icon: <Palette size={18} />,
      category: 'Settings',
    },
    {
      name: 'Output Style',
      status: 'ok',
      message: summary.output_style,
      details: `Output formatting: ${summary.output_style}`,
      icon: <Terminal size={18} />,
      category: 'Settings',
    },
    {
      name: 'Vim Mode',
      status: 'ok',
      message: summary.vim_mode ? 'Enabled' : 'Disabled',
      details: summary.vim_mode ? 'Vim keybindings active' : 'Standard keybindings',
      icon: <Settings size={18} />,
      category: 'Settings',
    },
    {
      name: 'Voice Mode',
      status: 'ok',
      message: summary.voice_mode ? 'Enabled' : 'Disabled',
      details: summary.voice_mode ? 'Voice input active' : 'Text input only',
      icon: <Mic size={18} />,
      category: 'Settings',
    },
  ];
}

const STATUS_CONFIG: Record<string, { color: string; bg: string; icon: React.ReactNode }> = {
  'ok': { 
    color: '#10b981', 
    bg: 'rgba(16, 185, 129, 0.15)',
    icon: <CheckCircle size={18} />
  },
  'warning': { 
    color: '#f59e0b', 
    bg: 'rgba(245, 158, 11, 0.15)',
    icon: <AlertTriangle size={18} />
  },
  'error': { 
    color: '#ef4444', 
    bg: 'rgba(239, 68, 68, 0.15)',
    icon: <XCircle size={18} />
  },
};

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  'Core': <Zap size={16} />,
  'Environment': <Folder size={16} />,
  'Extensions': <Package size={16} />,
  'Settings': <Settings size={16} />,
};

export function DoctorPage() {
  const [summary, setSummary] = useState<DoctorSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  
  const fetchDoctor = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/doctor');
      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        console.error('Doctor API error:', response.status, errorText);
        throw new Error(`Server error (${response.status}): ${errorText.substring(0, 100)}`);
      }
      const data: DoctorSummary = await response.json();
      setSummary(data);
    } catch (err) {
      console.error('Failed to fetch doctor data:', err);
      setError(err instanceof Error ? err.message : 'Failed to connect to server. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchDoctor();
  }, []);
  
  const healthChecks = summary ? getHealthChecks(summary) : [];
  const okCount = healthChecks.filter(h => h.status === 'ok').length;
  const warningCount = healthChecks.filter(h => h.status === 'warning').length;
  const errorCount = healthChecks.filter(h => h.status === 'error').length;
  
  const categories = Array.from(new Set(healthChecks.map(h => h.category))).filter(Boolean) as string[];
  const filteredChecks = selectedCategory 
    ? healthChecks.filter(h => h.category === selectedCategory)
    : healthChecks;
  
  const overallHealth = errorCount > 0 ? 'error' : warningCount > 0 ? 'warning' : 'ok';

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Activity size={24} /> Doctor</h1>
        <p>Health check and diagnostics for OpenHarness</p>
      </div>
      
      {summary && (
        <div className={styles.statsGrid}>
          <div className={styles.statCard}>
            <span className={styles.statValue} style={{ color: '#10b981' }}>{okCount}</span>
            <span className={styles.statLabel}>Healthy</span>
          </div>
          <div className={styles.statCard}>
            <span className={styles.statValue} style={{ color: '#f59e0b' }}>{warningCount}</span>
            <span className={styles.statLabel}>Warnings</span>
          </div>
          <div className={styles.statCard}>
            <span className={styles.statValue} style={{ color: '#ef4444' }}>{errorCount}</span>
            <span className={styles.statLabel}>Errors</span>
          </div>
          <div className={styles.statCard}>
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 'var(--space-2)',
              color: STATUS_CONFIG[overallHealth].color 
            }}>
              {STATUS_CONFIG[overallHealth].icon}
              <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>
                {overallHealth === 'ok' ? 'All Good' : overallHealth === 'warning' ? 'Needs Attention' : 'Issues Found'}
              </span>
            </div>
            <span className={styles.statLabel}>Overall Status</span>
          </div>
        </div>
      )}
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
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
                {cat in CATEGORY_ICONS && CATEGORY_ICONS[cat]}
                {cat}
              </button>
            ))}
          </div>
          
          <div style={{ flex: 1 }} />
          
          <button 
            className={styles.primaryButton}
            onClick={fetchDoctor}
            disabled={loading}
          >
            <RefreshCw size={18} className={loading ? styles.spinning : ''} />
            {loading ? 'Running...' : 'Run Diagnostics'}
          </button>
        </div>
        
        {error && (
          <div className={styles.formCard} style={{ 
            background: 'rgba(239, 68, 68, 0.1)', 
            borderColor: 'rgba(239, 68, 68, 0.3)' 
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', color: '#ef4444' }}>
              <XCircle size={20} />
              <span style={{ fontWeight: 600 }}>Error</span>
            </div>
            <p style={{ color: 'var(--text-secondary)', margin: 'var(--space-2) 0 0 0', fontSize: '0.875rem' }}>
              {error}
            </p>
          </div>
        )}
        
        {loading ? (
          <div className={styles.emptyState}>
            <RefreshCw size={48} className={styles.spinning} />
            <h3>Running diagnostics...</h3>
            <p>Checking system health and configuration</p>
          </div>
        ) : !summary ? (
          <div className={styles.emptyState}>
            <Activity size={48} />
            <h3>No diagnostic data available</h3>
            <p>Click "Run Diagnostics" to check system health</p>
          </div>
        ) : (
          <>
            {/* Summary Panel */}
            <div className={styles.formCard} style={{ marginBottom: 'var(--space-4)' }}>
              <h3 style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-4)' }}>
                <Cpu size={18} />
                System Overview
              </h3>
              <div className={styles.envGridEnhanced}>
                <div className={styles.envItemEnhanced}>
                  <span className={styles.envKeyEnhanced}>Profile</span>
                  <span className={styles.envValueEnhanced}>{summary.active_profile}</span>
                </div>
                <div className={styles.envItemEnhanced}>
                  <span className={styles.envKeyEnhanced}>Model</span>
                  <span className={styles.envValueEnhanced}>{summary.model || 'Not set'}</span>
                </div>
                <div className={styles.envItemEnhanced}>
                  <span className={styles.envKeyEnhanced}>Provider</span>
                  <span className={styles.envValueEnhanced}>{summary.provider_workflow}</span>
                </div>
                <div className={styles.envItemEnhanced}>
                  <span className={styles.envKeyEnhanced}>Effort</span>
                  <span className={styles.envValueEnhanced}>{summary.effort}</span>
                </div>
              </div>
            </div>
            
            {/* Health Checks Grid */}
            <div className={styles.checksGrid}>
              {filteredChecks.map((check, index) => {
                const config = STATUS_CONFIG[check.status];
                return (
                  <div 
                    key={check.name}
                    className={`${styles.checkCard} ${styles[check.status]} ${styles.animateIn}`}
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                    <div className={styles.checkHeader}>
                      <div style={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        gap: 'var(--space-2)',
                        color: config.color
                      }}>
                        {check.icon}
                        <span className={styles.checkName}>{check.name}</span>
                      </div>
                      <div style={{ color: config.color }}>
                        {config.icon}
                      </div>
                    </div>
                    
                    <p className={styles.checkMessage}>{check.message}</p>
                    
                    {check.details && (
                      <p className={styles.checkDetails}>{check.details}</p>
                    )}
                    
                    {check.category && check.category in CATEGORY_ICONS && (
                      <div style={{ 
                        marginTop: 'var(--space-2)', 
                        display: 'flex', 
                        alignItems: 'center', 
                        gap: 'var(--space-1)',
                        fontSize: '0.6875rem',
                        color: 'var(--text-tertiary)'
                      }}>
                        {CATEGORY_ICONS[check.category]}
                        {check.category}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}