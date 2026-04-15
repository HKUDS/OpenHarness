import { useAppStore } from '../store/useAppStore';
import { 
  Sparkles, Plus, Trash2, Code, Bug, TestTube, FileText, 
  RefreshCw, Upload, FolderOpen, Link, Github, Download, Edit3, Save, X, 
  ChevronDown, ChevronUp, Copy, Check, FileCode, ExternalLink, Search, 
  Info, AlertCircle, Clock, User, Tag, Globe, Package, Zap, Star
} from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import styles from '../styles/PageLayout.module.css';

const SKILL_ICONS: Record<string, React.ReactNode> = {
  'code-review': <Code size={20} />,
  'debugging': <Bug size={20} />,
  'testing': <TestTube size={20} />,
  'documentation': <FileText size={20} />,
  'refactoring': <RefreshCw size={20} />,
  'commit': <Save size={20} />,
  'plan': <FileText size={20} />,
  'simplify': <Zap size={20} />,
};

const SCRIPT_TYPE_COLORS: Record<string, string> = {
  'python': '#3776ab',
  'bash': '#4eaa25',
  'javascript': '#f7df1e',
  'other': '#6b7280',
};

const SOURCE_ICONS: Record<string, React.ReactNode> = {
  'local': <Package size={12} />,
  'github': <Github size={12} />,
  'clawhub': <Globe size={12} />,
  'upload': <Upload size={12} />,
};

interface SkillFormData {
  name: string;
  description: string;
  script: string;
  scriptType: 'python' | 'bash' | 'javascript' | 'other';
  author: string;
  version: string;
  tags: string;
}

export function SkillsPage() {
  const { skills, toggleSkill, addSkill, updateSkill, removeSkill } = useAppStore();
  const [showAddForm, setShowAddForm] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState<string | null>(null);
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [importUrl, setImportUrl] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [copiedScript, setCopiedScript] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [skillForm, setSkillForm] = useState<SkillFormData>({
    name: '',
    description: '',
    script: '',
    scriptType: 'python',
    author: '',
    version: '1.0.0',
    tags: '',
  });
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  
  const enabledSkills = skills.filter(s => s.enabled);
  const skillsWithScripts = skills.filter(s => s.script);
  
  const filteredSkills = skills.filter(skill => {
    const matchesSearch = searchQuery === '' || 
      skill.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      skill.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (skill.tags && skill.tags.some(t => t.toLowerCase().includes(searchQuery.toLowerCase())));
    const matchesSource = selectedSource === null || skill.source === selectedSource;
    return matchesSearch && matchesSource;
  });
  
  const sources = Array.from(new Set(skills.map(s => s.source || 'local')));
  
  // Clear copied state after 2 seconds
  useEffect(() => {
    if (copiedScript) {
      const timer = setTimeout(() => setCopiedScript(null), 2000);
      return () => clearTimeout(timer);
    }
  }, [copiedScript]);
  
  const handleCopyScript = async (script: string, skillId: string) => {
    try {
      await navigator.clipboard.writeText(script);
      setCopiedScript(skillId);
    } catch (err) {
      console.error('Failed to copy script:', err);
    }
  };
  
  const toggleFavorite = (skillId: string) => {
    setFavorites(prev => {
      const next = new Set(prev);
      if (next.has(skillId)) {
        next.delete(skillId);
      } else {
        next.add(skillId);
      }
      return next;
    });
  };
  
  const handleAddSkill = () => {
    if (skillForm.name && skillForm.description) {
      addSkill({
        id: skillForm.name.toLowerCase().replace(/\s+/g, '-'),
        name: skillForm.name,
        description: skillForm.description,
        enabled: true,
        script: skillForm.script || undefined,
        scriptType: skillForm.script ? skillForm.scriptType : undefined,
        author: skillForm.author || undefined,
        version: skillForm.version || undefined,
        source: 'local',
        tags: skillForm.tags ? skillForm.tags.split(',').map(t => t.trim()).filter(t => t) : undefined,
      });
      setSkillForm({
        name: '',
        description: '',
        script: '',
        scriptType: 'python',
        author: '',
        version: '1.0.0',
        tags: '',
      });
      setShowAddForm(false);
    }
  };
  
  const handleEditSkill = (skillId: string) => {
    const skill = skills.find(s => s.id === skillId);
    if (skill) {
      setSkillForm({
        name: skill.name,
        description: skill.description,
        script: skill.script || '',
        scriptType: skill.scriptType || 'python',
        author: skill.author || '',
        version: skill.version || '1.0.0',
        tags: skill.tags ? skill.tags.join(', ') : '',
      });
      setShowEditModal(skillId);
    }
  };
  
  const handleSaveEdit = () => {
    if (showEditModal && skillForm.name && skillForm.description) {
      updateSkill(showEditModal, {
        name: skillForm.name,
        description: skillForm.description,
        script: skillForm.script || undefined,
        scriptType: skillForm.script ? skillForm.scriptType : undefined,
        author: skillForm.author || undefined,
        version: skillForm.version || undefined,
        tags: skillForm.tags ? skillForm.tags.split(',').map(t => t.trim()).filter(t => t) : undefined,
      });
      setShowEditModal(null);
      setSkillForm({
        name: '',
        description: '',
        script: '',
        scriptType: 'python',
        author: '',
        version: '1.0.0',
        tags: '',
      });
    }
  };
  
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    
    setImportLoading(true);
    setImportError(null);
    
    try {
      for (const file of Array.from(files)) {
        const content = await file.text();
        let skillData;
        
        if (file.name.endsWith('.json')) {
          skillData = JSON.parse(content);
        } else if (file.name.endsWith('.md') || file.name.endsWith('.txt')) {
          const lines = content.split('\n');
          skillData = {
            name: file.name.replace(/\.(md|txt)$/, ''),
            description: lines.find(l => l.startsWith('description:'))?.replace('description:', '').trim() || 'Imported skill',
            script: content,
            scriptType: file.name.endsWith('.py') ? 'python' : file.name.endsWith('.sh') ? 'bash' : file.name.endsWith('.js') ? 'javascript' : 'other',
          };
        } else if (file.name.endsWith('.py')) {
          skillData = {
            name: file.name.replace('.py', ''),
            description: 'Python skill script',
            script: content,
            scriptType: 'python',
          };
        } else if (file.name.endsWith('.sh')) {
          skillData = {
            name: file.name.replace('.sh', ''),
            description: 'Bash skill script',
            script: content,
            scriptType: 'bash',
          };
        } else if (file.name.endsWith('.js')) {
          skillData = {
            name: file.name.replace('.js', ''),
            description: 'JavaScript skill script',
            script: content,
            scriptType: 'javascript',
          };
        } else {
          try {
            skillData = JSON.parse(content);
          } catch {
            skillData = {
              name: file.name,
              description: 'Imported skill',
              script: content,
              scriptType: 'other',
            };
          }
        }
        
        addSkill({
          id: skillData.name?.toLowerCase().replace(/\s+/g, '-') || `skill-${Date.now()}`,
          name: skillData.name || file.name,
          description: skillData.description || 'Imported skill',
          enabled: true,
          script: skillData.script,
          scriptType: skillData.scriptType || 'other',
          author: skillData.author,
          version: skillData.version || '1.0.0',
          source: 'upload',
          tags: skillData.tags,
        });
      }
      
      setShowImportModal(false);
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
      const isGitHub = importUrl.includes('github.com');
      const isClawHub = importUrl.includes('clawhub');
      const source = isGitHub ? 'github' : isClawHub ? 'clawhub' : 'upload';
      
      let fetchUrl = importUrl;
      if (isGitHub && !importUrl.includes('raw')) {
        fetchUrl = importUrl
          .replace('github.com', 'raw.githubusercontent.com')
          .replace('/blob/', '/');
      }
      
      const response = await fetch(fetchUrl);
      if (!response.ok) {
        throw new Error(`Failed to fetch: ${response.status}`);
      }
      
      const content = await response.text();
      let skillData;
      
      try {
        skillData = JSON.parse(content);
      } catch {
        const fileName = fetchUrl.split('/').pop() || 'skill';
        skillData = {
          name: fileName.replace(/\.[^.]+$/, ''),
          description: `Imported from ${source}`,
          script: content,
          scriptType: fileName.endsWith('.py') ? 'python' : fileName.endsWith('.sh') ? 'bash' : fileName.endsWith('.js') ? 'javascript' : 'other',
        };
      }
      
      addSkill({
        id: skillData.name?.toLowerCase().replace(/\s+/g, '-') || `skill-${Date.now()}`,
        name: skillData.name || 'Imported Skill',
        description: skillData.description || `Imported from ${importUrl}`,
        enabled: true,
        script: skillData.script,
        scriptType: skillData.scriptType || 'other',
        author: skillData.author,
        version: skillData.version || '1.0.0',
        source: source as 'github' | 'clawhub' | 'upload',
        sourceUrl: importUrl,
        tags: skillData.tags,
      });
      
      setShowImportModal(false);
      setImportUrl('');
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Failed to import from URL');
    } finally {
      setImportLoading(false);
    }
  };
  
  const toggleExpand = (skillId: string) => {
    setExpandedSkill(expandedSkill === skillId ? null : skillId);
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Sparkles size={24} /> Skills</h1>
        <p>Manage AI skills and capabilities with scripts</p>
      </div>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{enabledSkills.length}</span>
          <span className={styles.statLabel}>Enabled</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{skills.length}</span>
          <span className={styles.statLabel}>Total Skills</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{skillsWithScripts.length}</span>
          <span className={styles.statLabel}>With Scripts</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{sources.length}</span>
          <span className={styles.statLabel}>Sources</span>
        </div>
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
          <div className={styles.searchContainer}>
            <Search size={18} />
            <input
              type="text"
              placeholder="Search skills..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={styles.searchInput}
            />
          </div>
          
          <div className={styles.filterChips}>
            {sources.map(src => (
              <button
                key={src}
                className={`${styles.filterChip} ${selectedSource === src ? styles.active : ''}`}
                onClick={() => setSelectedSource(selectedSource === src ? null : src)}
              >
                {SOURCE_ICONS[src]}
                {src}
              </button>
            ))}
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
            onClick={() => setShowAddForm(!showAddForm)}
          >
            <Plus size={18} />
            Add Skill
          </button>
        </div>
        
        {/* Add Skill Form */}
        {showAddForm && (
          <div className={styles.formCard}>
            <h3><Plus size={18} /> Add New Skill</h3>
            <div className={styles.formGroup}>
              <label>Skill Name *</label>
              <input
                type="text"
                value={skillForm.name}
                onChange={(e) => setSkillForm({ ...skillForm, name: e.target.value })}
                placeholder="My Custom Skill"
              />
            </div>
            <div className={styles.formGroup}>
              <label>Description *</label>
              <textarea
                value={skillForm.description}
                onChange={(e) => setSkillForm({ ...skillForm, description: e.target.value })}
                placeholder="What does this skill do?"
                rows={3}
              />
            </div>
            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label>Author</label>
                <input
                  type="text"
                  value={skillForm.author}
                  onChange={(e) => setSkillForm({ ...skillForm, author: e.target.value })}
                  placeholder="Your name"
                />
              </div>
              <div className={styles.formGroup}>
                <label>Version</label>
                <input
                  type="text"
                  value={skillForm.version}
                  onChange={(e) => setSkillForm({ ...skillForm, version: e.target.value })}
                  placeholder="1.0.0"
                />
              </div>
            </div>
            <div className={styles.formGroup}>
              <label>Tags (comma-separated)</label>
              <input
                type="text"
                value={skillForm.tags}
                onChange={(e) => setSkillForm({ ...skillForm, tags: e.target.value })}
                placeholder="code, automation, review"
              />
            </div>
            <div className={styles.formGroup}>
              <label>Script Type</label>
              <select
                value={skillForm.scriptType}
                onChange={(e) => setSkillForm({ ...skillForm, scriptType: e.target.value as 'python' | 'bash' | 'javascript' | 'other' })}
                className={styles.categorySelect}
              >
                <option value="python">Python</option>
                <option value="bash">Bash</option>
                <option value="javascript">JavaScript</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div className={styles.formGroup}>
              <label>Script Content</label>
              <textarea
                value={skillForm.script}
                onChange={(e) => setSkillForm({ ...skillForm, script: e.target.value })}
                placeholder="# Enter your script here..."
                rows={8}
                className={styles.codeTextarea}
              />
              <p className={styles.formHint}>
                <Info size={14} />
                Add a script to execute when this skill is invoked
              </p>
            </div>
            <div className={styles.formActions}>
              <button className={styles.secondaryButton} onClick={() => setShowAddForm(false)}>
                <X size={16} />
                Cancel
              </button>
              <button className={styles.primaryButton} onClick={handleAddSkill} disabled={!skillForm.name || !skillForm.description}>
                <Save size={16} />
                Add Skill
              </button>
            </div>
          </div>
        )}
        
        {filteredSkills.length === 0 ? (
          <div className={styles.emptyState}>
            <Sparkles size={48} />
            <h3>No skills found</h3>
            <p>Add or import skills to enhance AI capabilities</p>
          </div>
        ) : (
          <div className={styles.skillsGrid}>
            {filteredSkills.map((skill, index) => (
              <div 
                key={skill.id} 
                className={`${styles.skillCardEnhanced} ${skill.enabled ? styles.enabled : styles.disabled} ${styles.animateIn}`}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <div className={styles.skillHeaderEnhanced}>
                  <div className={styles.skillHeaderLeft}>
                    <div className={styles.skillIconEnhanced}>
                      {SKILL_ICONS[skill.id] || <Sparkles size={20} />}
                    </div>
                    <div className={styles.skillTitleEnhanced}>
                      <span className={styles.skillNameEnhanced}>
                        {skill.name}
                        {skill.scriptType && (
                          <span 
                            className={styles.scriptTypeBadge}
                            style={{ backgroundColor: SCRIPT_TYPE_COLORS[skill.scriptType] || '#6b7280' }}
                          >
                            {skill.scriptType}
                          </span>
                        )}
                      </span>
                      <div className={styles.skillMeta}>
                        {skill.source && (
                          <span className={styles.sourceBadge}>
                            {SOURCE_ICONS[skill.source]}
                            {skill.source}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  <div className={styles.toggleSwitch} onClick={() => toggleSkill(skill.id)}>
                    <div className={`${styles.toggleSwitchKnob} ${skill.enabled ? styles.enabled : ''}`} />
                  </div>
                </div>
                
                <p className={styles.skillDescriptionEnhanced}>{skill.description}</p>
                
                {/* Tags */}
                {skill.tags && skill.tags.length > 0 && (
                  <div className={styles.skillTagsEnhanced}>
                    {skill.tags.map(tag => (
                      <span key={tag} className={styles.skillTagEnhanced}>
                        <Tag size={10} />
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
                
                {/* Metadata Grid */}
                <div className={styles.skillMetadataGrid}>
                  {skill.author && (
                    <div className={styles.skillMetadataItem}>
                      <User size={12} />
                      <span className={styles.skillMetadataValue}>{skill.author}</span>
                    </div>
                  )}
                  {skill.version && (
                    <div className={styles.skillMetadataItem}>
                      <Package size={12} />
                      <span className={styles.skillMetadataValue}>v{skill.version}</span>
                    </div>
                  )}
                  {skill.createdAt && (
                    <div className={styles.skillMetadataItem}>
                      <Clock size={12} />
                      <span className={styles.skillMetadataValue}>{new Date(skill.createdAt).toLocaleDateString()}</span>
                    </div>
                  )}
                  {skill.script && (
                    <div className={styles.skillMetadataItem}>
                      <FileCode size={12} />
                      <span className={styles.skillMetadataValue}>{skill.script.split('\n').length} lines</span>
                    </div>
                  )}
                </div>
                
                {/* Script Preview */}
                {skill.script && (
                  <div className={styles.scriptPreviewEnhanced}>
                    <div className={styles.scriptPreviewHeader}>
                      <span className={styles.scriptPreviewTitle}>
                        <FileCode size={14} />
                        Script Preview
                      </span>
                      <div className={styles.scriptPreviewActions}>
                        <button 
                          className={styles.copyButton}
                          onClick={() => handleCopyScript(skill.script!, skill.id)}
                          title="Copy script"
                        >
                          {copiedScript === skill.id ? <Check size={14} /> : <Copy size={14} />}
                        </button>
                        <button 
                          className={styles.expandButton}
                          onClick={() => toggleExpand(skill.id)}
                          style={{ padding: '4px 8px', width: 'auto' }}
                        >
                          {expandedSkill === skill.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </button>
                      </div>
                    </div>
                    <pre className={styles.scriptPreviewContent} style={{ 
                      maxHeight: expandedSkill === skill.id ? '400px' : '100px',
                      overflow: 'hidden'
                    }}>
                      {skill.script}
                    </pre>
                  </div>
                )}
                
                {/* Source URL */}
                {skill.sourceUrl && (
                  <div className={styles.sourceUrl}>
                    <ExternalLink size={12} />
                    <a href={skill.sourceUrl} target="_blank" rel="noopener noreferrer">
                      {skill.sourceUrl.length > 40 ? skill.sourceUrl.substring(0, 40) + '...' : skill.sourceUrl}
                    </a>
                  </div>
                )}
                
                {/* Actions */}
                <div className={styles.skillActions}>
                  <div className={styles.actionToolbar}>
                    <button 
                      className={styles.actionButton}
                      onClick={() => handleEditSkill(skill.id)}
                      title="Edit"
                    >
                      <Edit3 size={14} />
                    </button>
                    <button 
                      className={`${styles.actionButton} ${favorites.has(skill.id) ? styles.active : ''}`}
                      onClick={() => toggleFavorite(skill.id)}
                      title="Favorite"
                    >
                      <Star size={14} fill={favorites.has(skill.id) ? 'currentColor' : 'none'} />
                    </button>
                    <button 
                      className={`${styles.actionButton} ${styles.danger}`}
                      onClick={() => removeSkill(skill.id)}
                      title="Remove"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                  
                  <div className={styles.statusIndicator}>
                    <span className={`${styles.statusDot} ${skill.enabled ? styles.active : styles.inactive}`} />
                    <span>{skill.enabled ? 'Active' : 'Inactive'}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      
      {/* Import Modal */}
      {showImportModal && createPortal(
        <div className={styles.modalOverlay}>
          <div className={styles.modal} data-import-modal>
            <div className={styles.modalHeader}>
              <h2><Download size={20} /> Import Skills</h2>
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
                    Upload skill files (.json, .py, .sh, .js, .md)
                  </p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".json,.py,.sh,.js,.md,.txt"
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
                    Import multiple skill files from a folder
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
                    Import from GitHub, ClawHub, or any URL
                  </p>
                  <div className={styles.urlInputSection}>
                    <input
                      type="url"
                      value={importUrl}
                      onChange={(e) => setImportUrl(e.target.value)}
                      placeholder="https://github.com/user/skill.json"
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
                    <p><Github size={14} /> GitHub: github.com/user/repo/skill.json</p>
                    <p><Globe size={14} /> ClawHub: clawhub.io/skills/example</p>
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
      
      {/* Edit Modal */}
      {showEditModal && createPortal(
        <div className={styles.modalOverlay}>
          <div className={styles.modal} data-edit-modal>
            <div className={styles.modalHeader}>
              <h2><Edit3 size={20} /> Edit Skill</h2>
              <button 
                className={styles.modalClose}
                onClick={() => setShowEditModal(null)}
              >
                <X size={20} />
              </button>
            </div>
            
            <div className={styles.modalContent}>
              <div className={styles.formGroup}>
                <label>Skill Name *</label>
                <input
                  type="text"
                  value={skillForm.name}
                  onChange={(e) => setSkillForm({ ...skillForm, name: e.target.value })}
                />
              </div>
              <div className={styles.formGroup}>
                <label>Description *</label>
                <textarea
                  value={skillForm.description}
                  onChange={(e) => setSkillForm({ ...skillForm, description: e.target.value })}
                  rows={3}
                />
              </div>
              <div className={styles.formRow}>
                <div className={styles.formGroup}>
                  <label>Author</label>
                  <input
                    type="text"
                    value={skillForm.author}
                    onChange={(e) => setSkillForm({ ...skillForm, author: e.target.value })}
                  />
                </div>
                <div className={styles.formGroup}>
                  <label>Version</label>
                  <input
                    type="text"
                    value={skillForm.version}
                    onChange={(e) => setSkillForm({ ...skillForm, version: e.target.value })}
                  />
                </div>
              </div>
              <div className={styles.formGroup}>
                <label>Tags (comma-separated)</label>
                <input
                  type="text"
                  value={skillForm.tags}
                  onChange={(e) => setSkillForm({ ...skillForm, tags: e.target.value })}
                />
              </div>
              <div className={styles.formGroup}>
                <label>Script Type</label>
                <select
                  value={skillForm.scriptType}
                  onChange={(e) => setSkillForm({ ...skillForm, scriptType: e.target.value as 'python' | 'bash' | 'javascript' | 'other' })}
                  className={styles.categorySelect}
                >
                  <option value="python">Python</option>
                  <option value="bash">Bash</option>
                  <option value="javascript">JavaScript</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div className={styles.formGroup}>
                <label>Script Content</label>
                <textarea
                  value={skillForm.script}
                  onChange={(e) => setSkillForm({ ...skillForm, script: e.target.value })}
                  rows={8}
                  className={styles.codeTextarea}
                />
              </div>
              
              <div className={styles.formActions}>
                <button className={styles.secondaryButton} onClick={() => setShowEditModal(null)}>
                  <X size={16} />
                  Cancel
                </button>
                <button 
                  className={styles.primaryButton} 
                  onClick={handleSaveEdit}
                  disabled={!skillForm.name || !skillForm.description}
                >
                  <Save size={16} />
                  Save Changes
                </button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}