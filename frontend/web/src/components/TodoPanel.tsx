import { useState } from 'react';
import { Plus, Trash2, Check, Square } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import styles from '../styles/TodoPanel.module.css';

export function TodoPanel() {
  const { todoItems, addTodoItem, toggleTodoItem, removeTodoItem, todoMarkdown } = useAppStore();
  const [newItem, setNewItem] = useState('');

  const handleAdd = () => {
    if (newItem.trim()) {
      addTodoItem(newItem.trim());
      setNewItem('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleAdd();
    }
  };

  return (
    <div className={styles.todoPanel}>
      <div className={styles.header}>
        <h3>TODO List</h3>
      </div>

      <div className={styles.addForm}>
        <input
          type="text"
          value={newItem}
          onChange={(e) => setNewItem(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Add a new task..."
          className={styles.input}
        />
        <button className={styles.addButton} onClick={handleAdd}>
          <Plus size={18} />
        </button>
      </div>

      <div className={styles.items}>
        {todoItems.length === 0 ? (
          <div className={styles.empty}>
            <p>No TODO items yet</p>
            <p className={styles.hint}>Add tasks above to track your progress</p>
          </div>
        ) : (
          todoItems.map((item, index) => (
            <div 
              key={index} 
              className={`${styles.item} ${item.checked ? styles.checked : ''}`}
            >
              <button 
                className={styles.checkbox}
                onClick={() => toggleTodoItem(index)}
              >
                {item.checked ? <Check size={16} /> : <Square size={16} />}
              </button>
              <span className={styles.itemText}>{item.text}</span>
              <button 
                className={styles.deleteButton}
                onClick={() => removeTodoItem(index)}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))
        )}
      </div>

      {todoMarkdown && (
        <div className={styles.markdownSection}>
          <h4>TODO.md</h4>
          <div className={styles.markdownContent}>
            <pre>{todoMarkdown}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
