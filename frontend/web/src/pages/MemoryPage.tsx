import { useAppStore } from '../store/useAppStore';
import { Brain, Plus, Trash2, Edit2, Save, X, FileText, Lightbulb, Settings } from 'lucide-react';
import { useState } from 'react';
import styles from './PageLayout.module.css';

const MEMORY_TYPES = [
  { value: 'fact', label: 'Fact', icon: <FileText size={16} /> },
  { value: 'preference', label: 'Preference', icon: <Settings size={16} /> },
  { value: 'context', label: 'Context', icon: <Lightbulb size={16} /> },
];

export function MemoryPage() {
  const { memories, addMemory, removeMemory, updateMemory } = useAppStore();
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [newMemory, setNewMemory] = useState({ content: '', type: 'fact' as 'fact' | 'preference' | 'context' });
  
  const handleAddMemory = () => {
    if (newMemory.content.trim()) {
      addMemory({
        id: `mem-${Date.now()}`,
        content: newMemory.content,
        createdAt: Date.now(),
        type: newMemory.type
      });
      setNewMemory({ content: '', type: 'fact' });
      setShowAddForm(false);
    }
  };
  
  const startEdit = (id: string, content: string) => {
    setEditingId(id);
    setEditContent(content);
  };
  
  const saveEdit = () => {
    if (editingId && editContent.trim()) {
      updateMemory(editingId, editContent);
      setEditingId(null);
      setEditContent('');
    }
  };
  
  const cancelEdit = () => {
    setEditingId(null);
    setEditContent('');
  };
  
  const formatDate = (timestamp: number) => {
    return new Date(timestamp).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };
  
  const getTypeClass = (type: string) => {
    return `${styles.memoryType} ${styles[type]}`;
  };
  
  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Brain size={24} /> Memory</h1>
        <p>Persistent memory and context for AI sessions</p>
      </div>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{memories.length}</span>
          <span className={styles.statLabel}>Total Memories</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{memories.filter(m => m.type === 'fact').length}</span>
          <span className={styles.statLabel}>Facts</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{memories.filter(m => m.type === 'preference').length}</span>
          <span className={styles.statLabel}>Preferences</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{memories.filter(m => m.type === 'context').length}</span>
          <span className={styles.statLabel}>Context</span>
        </div>
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
          <button 
            className={styles.primaryButton}
            onClick={() => setShowAddForm(!showAddForm)}
          >
            <Plus size={18} />
            Add Memory
          </button>
        </div>
        
        {showAddForm && (
          <div className={styles.formCard}>
            <h3>Add New Memory</h3>
            <div className={styles.formGroup}>
              <label>Type</label>
              <div className={styles.typeSelector}>
                {MEMORY_TYPES.map(type => (
                  <button
                    key={type.value}
                    className={`${styles.typeButton} ${newMemory.type === type.value ? styles.active : ''}`}
                    onClick={() => setNewMemory({ ...newMemory, type: type.value as any })}
                  >
                    {type.icon}
                    {type.label}
                  </button>
                ))}
              </div>
            </div>
            <div className={styles.formGroup}>
              <label>Content</label>
              <textarea
                value={newMemory.content}
                onChange={(e) => setNewMemory({ ...newMemory, content: e.target.value })}
                placeholder="What should the AI remember?"
                rows={3}
              />
            </div>
            <div className={styles.formActions}>
              <button className={styles.secondaryButton} onClick={() => setShowAddForm(false)}>
                Cancel
              </button>
              <button className={styles.primaryButton} onClick={handleAddMemory}>
                Save Memory
              </button>
            </div>
          </div>
        )}
        
        {memories.length === 0 ? (
          <div className={styles.emptyState}>
            <Brain size={48} />
            <h3>No memories stored</h3>
            <p>Add facts, preferences, or context to help the AI remember</p>
            <div className={styles.emptyStateHint}>
              <p><strong>Tip:</strong> You can also create memories directly in chat:</p>
              <code>/remember I prefer TypeScript over JavaScript</code><br/>
              <code>remember: My project uses React and Tailwind</code><br/>
              <code>Note: The API endpoint is https://api.example.com</code>
            </div>
          </div>
        ) : (
          <div className={styles.memoryList}>
            {memories.map((memory) => (
              <div key={memory.id} className={styles.memoryCard}>
                <div className={styles.memoryHeader}>
                  <span className={getTypeClass(memory.type)}>
                    {MEMORY_TYPES.find(t => t.value === memory.type)?.icon}
                    {memory.type}
                  </span>
                  <span className={styles.memoryDate}>{formatDate(memory.createdAt)}</span>
                </div>
                
                {editingId === memory.id ? (
                  <div className={styles.editForm}>
                    <textarea
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      rows={3}
                    />
                    <div className={styles.editActions}>
                      <button className={styles.iconButton} onClick={cancelEdit}>
                        <X size={16} />
                      </button>
                      <button className={styles.iconButton} onClick={saveEdit}>
                        <Save size={16} />
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className={styles.memoryContent}>{memory.content}</p>
                    <div className={styles.memoryActions}>
                      <button 
                        className={styles.iconButton}
                        onClick={() => startEdit(memory.id, memory.content)}
                        title="Edit"
                      >
                        <Edit2 size={16} />
                      </button>
                      <button 
                        className={`${styles.iconButton} ${styles.danger}`}
                        onClick={() => removeMemory(memory.id)}
                        title="Delete"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}