import { Brain, Plus, Trash2, Edit2, Save, X } from 'lucide-react';
import { useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import styles from '../styles/MemoryPanel.module.css';

export function MemoryPanel() {
  const { memories, addMemory, removeMemory, updateMemory } = useAppStore();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [newMemory, setNewMemory] = useState('');

  const handleAdd = () => {
    if (newMemory.trim()) {
      addMemory({
        id: `memory-${Date.now()}`,
        content: newMemory.trim(),
        createdAt: Date.now(),
        type: 'context'
      });
      setNewMemory('');
    }
  };

  const handleStartEdit = (memory: any) => {
    setEditingId(memory.id);
    setEditContent(memory.content);
  };

  const handleSaveEdit = () => {
    if (editingId && editContent.trim()) {
      updateMemory(editingId, editContent.trim());
      setEditingId(null);
    }
  };

  const formatDate = (timestamp: number) => {
    return new Date(timestamp).toLocaleDateString([], { 
      month: 'short', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className={styles.memoryPanel}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <Brain size={20} />
          <h3>Memory</h3>
        </div>
      </div>

      <div className={styles.addForm}>
        <input
          type="text"
          value={newMemory}
          onChange={(e) => setNewMemory(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          placeholder="Add something to remember..."
          className={styles.input}
        />
        <button className={styles.addButton} onClick={handleAdd}>
          <Plus size={18} />
        </button>
      </div>

      <div className={styles.memories}>
        {memories.length === 0 ? (
          <div className={styles.empty}>
            <Brain size={32} />
            <p>No memories yet</p>
            <p className={styles.hint}>Add context, facts, or preferences the AI should remember</p>
          </div>
        ) : (
          memories.map(memory => (
            <div key={memory.id} className={styles.memoryCard}>
              <div className={styles.memoryIcon}>
                <Brain size={18} />
              </div>
              <div className={styles.memoryContent}>
                {editingId === memory.id ? (
                  <div className={styles.editMode}>
                    <input
                      type="text"
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      className={styles.editInput}
                      autoFocus
                    />
                    <div className={styles.editActions}>
                      <button className={styles.saveEdit} onClick={handleSaveEdit}>
                        <Save size={14} />
                      </button>
                      <button className={styles.cancelEdit} onClick={() => setEditingId(null)}>
                        <X size={14} />
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className={styles.memoryText}>{memory.content}</p>
                    <span className={styles.memoryDate}>{formatDate(memory.createdAt)}</span>
                  </>
                )}
              </div>
              {editingId !== memory.id && (
                <div className={styles.memoryActions}>
                  <button
                    className={styles.actionButton}
                    onClick={() => handleStartEdit(memory)}
                  >
                    <Edit2 size={14} />
                  </button>
                  <button
                    className={styles.deleteButton}
                    onClick={() => removeMemory(memory.id)}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <div className={styles.infoCard}>
        <h4>🧠 About Memory</h4>
        <p>Memories help the AI remember important context about your projects, preferences, and workflow. Add facts that should persist across conversations.</p>
      </div>
    </div>
  );
}
