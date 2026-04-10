import { useState, useEffect } from 'react';
import { 
  Globe, RefreshCw, Check, X, Eye, EyeOff, Key, Server, Search, 
  Zap, Shield, CheckCircle, Star, Settings
} from 'lucide-react';
import styles from '../styles/PageLayout.module.css';

interface ProviderSpec {
  name: string;
  display_name: string;
  backend_type: string;
  env_key: string;
  default_base_url: string;
  is_gateway: boolean;
  is_local: boolean;
  is_oauth: boolean;
  keywords: string[];
}

interface ProviderProfile {
  name: string;
  label: string;
  provider: string;
  api_format: string;
  auth_source: string;
  default_model: string;
  base_url: string | null;
  allowed_models: string[];
}

interface ProvidersResponse {
  providers: ProviderSpec[];
  profiles: ProviderProfile[];
  total_providers: number;
  total_profiles: number;
}

interface ProviderConfig {
  name: string;
  api_key: string;
  base_url: string;
  is_configured: boolean;
}

const PROVIDER_ICONS: Record<string, string> = {
  'anthropic': '🧠',
  'openai': '🤖',
  'openai_compat': '🔌',
  'copilot': '✈️',
  'google': '🔍',
  'deepseek': '🔬',
  'ollama': '🦙',
  'groq': '⚡',
  'mistral': '🌀',
};

const BACKEND_COLORS: Record<string, string> = {
  'anthropic': '#d97706',
  'openai': '#10b981',
  'openai_compat': '#6366f1',
  'copilot': '#3b82f6',
  'google': '#ef4444',
  'deepseek': '#8b5cf6',
  'ollama': '#14b8a6',
  'groq': '#f97316',
  'mistral': '#ec4899',
};

export function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderSpec[]>([]);
  const [profiles, setProfiles] = useState<ProviderProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [showApiKey, setShowApiKey] = useState<Record<string, boolean>>({});
  const [providerConfigs, setProviderConfigs] = useState<Record<string, ProviderConfig>>({});
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  
  const fetchProviders = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/providers');
      if (!response.ok) {
        throw new Error('Failed to fetch providers');
      }
      const data: ProvidersResponse = await response.json();
      setProviders(data.providers);
      setProfiles(data.profiles);
      
      const configs: Record<string, ProviderConfig> = {};
      data.providers.forEach(p => {
        configs[p.name] = {
          name: p.name,
          api_key: '',
          base_url: p.default_base_url,
          is_configured: false,
        };
      });
      setProviderConfigs(configs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchProviders();
  }, []);
  
  const filteredProviders = providers.filter(provider => {
    const matchesSearch = searchQuery === '' || 
      provider.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      provider.display_name.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSearch;
  });
  
  const toggleApiKeyVisibility = (name: string) => {
    setShowApiKey(prev => ({ ...prev, [name]: !prev[name] }));
  };
  
  const handleEditProvider = (name: string) => {
    setEditingProvider(editingProvider === name ? null : name);
  };
  
  const toggleFavorite = (name: string) => {
    setFavorites(prev => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };
  
  const handleSaveProvider = async (name: string) => {
    const config = providerConfigs[name];
    if (!config) return;
    
    setSaveStatus('saving');
    try {
      const response = await fetch('/api/providers/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: name,
          api_key: config.api_key,
          base_url: config.base_url,
        }),
      });
      
      if (!response.ok) {
        throw new Error('Failed to save provider config');
      }
      
      setProviderConfigs(prev => ({
        ...prev,
        [name]: { ...config, is_configured: Boolean(config.api_key) },
      }));
      
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 2000);
      setEditingProvider(null);
    } catch (err) {
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 2000);
    }
  };
  
  const handleUpdateConfig = (name: string, field: 'api_key' | 'base_url', value: string) => {
    setProviderConfigs(prev => ({
      ...prev,
      [name]: { ...prev[name], [field]: value },
    }));
  };
  
  const configuredCount = Object.values(providerConfigs).filter(c => c.is_configured).length;

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Globe size={24} /> Providers</h1>
        <p>Configure LLM providers and API keys</p>
      </div>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{providers.length}</span>
          <span className={styles.statLabel}>Providers</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{profiles.length}</span>
          <span className={styles.statLabel}>Profiles</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue} style={{ color: '#10b981' }}>{configuredCount}</span>
          <span className={styles.statLabel}>Configured</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue} style={{ color: '#f59e0b' }}>{providers.length - configuredCount}</span>
          <span className={styles.statLabel}>Pending</span>
        </div>
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
          <div className={styles.searchContainer}>
            <Search size={18} />
            <input
              type="text"
              placeholder="Search providers..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={styles.searchInput}
            />
          </div>
          
          <div style={{ flex: 1 }} />
          
          <button 
            className={styles.primaryButton}
            onClick={fetchProviders}
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
            <h3>Loading providers...</h3>
          </div>
        ) : filteredProviders.length === 0 ? (
          <div className={styles.emptyState}>
            <Globe size={48} />
            <h3>No providers found</h3>
            <p>Try adjusting your search</p>
          </div>
        ) : (
          <div className={styles.providersGrid}>
            {filteredProviders.map((provider, index) => {
              const config = providerConfigs[provider.name] || {
                api_key: '',
                base_url: provider.default_base_url,
                is_configured: false,
              };
              const isEditing = editingProvider === provider.name;
              const showKey = showApiKey[provider.name];
              const backendColor = BACKEND_COLORS[provider.backend_type] || '#6b7280';
              
              return (
                <div 
                  key={provider.name} 
                  className={`${styles.providerCard} ${config.is_configured ? styles.configured : ''} ${styles.animateIn}`}
                  style={{ animationDelay: `${index * 50}ms` }}
                >
                  <div className={styles.providerHeader}>
                    <div 
                      className={styles.providerIcon}
                      style={{ 
                        background: `linear-gradient(135deg, ${backendColor}20 0%, ${backendColor}10 100%)`,
                        color: backendColor,
                        fontSize: '1.5rem'
                      }}
                    >
                      {PROVIDER_ICONS[provider.backend_type] || '🌐'}
                    </div>
                    <div className={styles.providerInfo}>
                      <span className={styles.providerName}>
                        {provider.display_name}
                        {favorites.has(provider.name) && (
                          <Star size={12} fill="#f59e0b" style={{ color: '#f59e0b', marginLeft: 'var(--space-1)' }} />
                        )}
                      </span>
                      <span className={styles.providerBackend}>{provider.backend_type}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 'var(--space-1)' }}>
                      <button 
                        className={`${styles.favoriteButton} ${favorites.has(provider.name) ? styles.active : ''}`}
                        onClick={() => toggleFavorite(provider.name)}
                        title="Favorite"
                      >
                        <Star size={14} fill={favorites.has(provider.name) ? 'currentColor' : 'none'} />
                      </button>
                      <button 
                        className={styles.editButton}
                        onClick={() => handleEditProvider(provider.name)}
                        title={isEditing ? 'Cancel' : 'Configure'}
                      >
                        {isEditing ? <X size={16} /> : <Settings size={16} />}
                      </button>
                    </div>
                  </div>
                  
                  {/* Status & Tags */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
                    {config.is_configured ? (
                      <span className={styles.configuredBadge}>
                        <CheckCircle size={12} />
                        Configured
                      </span>
                    ) : (
                      <span style={{ 
                        display: 'inline-flex', 
                        alignItems: 'center', 
                        gap: 'var(--space-1)', 
                        padding: '2px 8px',
                        background: 'rgba(245, 158, 11, 0.15)',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.75rem',
                        color: '#f59e0b'
                      }}>
                        <Shield size={12} />
                        Not Configured
                      </span>
                    )}
                    
                    <div style={{ display: 'flex', gap: 'var(--space-1)' }}>
                      {provider.is_gateway && (
                        <span className={styles.providerTag} style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#6366f1' }}>
                          gateway
                        </span>
                      )}
                      {provider.is_local && (
                        <span className={styles.providerTag} style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#10b981' }}>
                          local
                        </span>
                      )}
                      {provider.is_oauth && (
                        <span className={styles.providerTag} style={{ background: 'rgba(236, 72, 153, 0.15)', color: '#ec4899' }}>
                          oauth
                        </span>
                      )}
                    </div>
                  </div>
                  
                  {/* Config Form */}
                  {isEditing && (
                    <div className={styles.configForm}>
                      <div className={styles.formGroup}>
                        <label>
                          <Key size={14} />
                          API Key
                        </label>
                        <div className={styles.apiKeyInput}>
                          <input
                            type={showKey ? 'text' : 'password'}
                            value={config.api_key}
                            onChange={(e) => handleUpdateConfig(provider.name, 'api_key', e.target.value)}
                            placeholder={`Enter ${provider.env_key || 'API key'}`}
                            className={styles.input}
                          />
                          <button 
                            className={styles.toggleVisibility}
                            onClick={() => toggleApiKeyVisibility(provider.name)}
                            type="button"
                          >
                            {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                          </button>
                        </div>
                      </div>
                      
                      {provider.default_base_url && (
                        <div className={styles.formGroup}>
                          <label>
                            <Server size={14} />
                            Base URL
                          </label>
                          <input
                            type="text"
                            value={config.base_url}
                            onChange={(e) => handleUpdateConfig(provider.name, 'base_url', e.target.value)}
                            placeholder={provider.default_base_url}
                            className={styles.input}
                          />
                        </div>
                      )}
                      
                      <button 
                        className={`${styles.saveButton} ${saveStatus === 'saved' ? styles.saved : ''}`}
                        onClick={() => handleSaveProvider(provider.name)}
                        disabled={saveStatus === 'saving'}
                      >
                        {saveStatus === 'saving' ? (
                          <RefreshCw size={16} className={styles.spinning} />
                        ) : saveStatus === 'saved' ? (
                          <Check size={16} />
                        ) : (
                          <Check size={16} />
                        )}
                        {saveStatus === 'saving' ? 'Saving...' : 
                         saveStatus === 'saved' ? 'Saved!' : 'Save Configuration'}
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
        
        {/* Profiles Section */}
        {profiles.length > 0 && (
          <div className={styles.profilesSection}>
            <h2><Zap size={18} /> Provider Profiles</h2>
            <div className={styles.profilesGrid}>
              {profiles.map((profile, index) => (
                <div 
                  key={profile.name} 
                  className={`${styles.profileCard} ${styles.animateIn}`}
                  style={{ animationDelay: `${index * 50}ms` }}
                >
                  <div className={styles.profileHeader}>
                    <span className={styles.profileName}>{profile.label}</span>
                    <span 
                      className={styles.profileProvider}
                      style={{ 
                        background: `${BACKEND_COLORS[profile.provider] || '#6b7280'}20`,
                        color: BACKEND_COLORS[profile.provider] || '#6b7280'
                      }}
                    >
                      {profile.provider}
                    </span>
                  </div>
                  <div className={styles.profileDetails}>
                    <div className={styles.profileDetail}>
                      <span className={styles.detailLabel}>Auth Source</span>
                      <span className={styles.detailValue}>{profile.auth_source}</span>
                    </div>
                    <div className={styles.profileDetail}>
                      <span className={styles.detailLabel}>Default Model</span>
                      <span className={styles.detailValue}>{profile.default_model}</span>
                    </div>
                    {profile.base_url && (
                      <div className={styles.profileDetail}>
                        <span className={styles.detailLabel}>Base URL</span>
                        <span className={styles.detailValue}>{profile.base_url}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}