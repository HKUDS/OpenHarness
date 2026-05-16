import { useAppStore } from '../store/useAppStore';
import { FileCheck, Plus, Trash2, Check, Circle } from 'lucide-react';
import { useState } from 'react';
import styles from './PageLayout.module.css';

export function TodoPage() {
  const { todoItems, addTodoItem, toggleTodoItem, removeTodoItem } = useAppStore();
  const [newTodoText, setNewTodoText] = useState('');
  
  const completedCount = todoItems.filter(t => t.checked).length;
  const pendingCount = todoItems.length - completedCount;
  
  const handleAddTodo = () => {
    if (newTodoText.trim()) {
      addTodoItem(newTodoText.trim());
      setNewTodoText('');
    }
  };
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleAddTodo();
    }
  };
  
  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><FileCheck size={24} /> TODO</h1>
        <p>Task tracking and todo list management</p>
      </div>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{pendingCount}</span>
          <span className={styles.statLabel}>Pending</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{completedCount}</span>
          <span className={styles.statLabel}>Completed</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{todoItems.length}</span>
          <span className={styles.statLabel}>Total</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>
            {todoItems.length > 0 ? Math.round((completedCount / todoItems.length) * 100) : 0}%
          </span>
          <span className={styles.statLabel}>Progress</span>
        </div>
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.addTodoForm}>
          <input
            type="text"
            value={newTodoText}
            onChange={(e) => setNewTodoText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Add a new todo item..."
            className={styles.todoInput}
          />
          <button 
            className={styles.primaryButton}
            onClick={handleAddTodo}
            disabled={!newTodoText.trim()}
          >
            <Plus size={18} />
            Add
          </button>
        </div>
        
        {todoItems.length === 0 ? (
          <div className={styles.emptyState}>
            <FileCheck size={48} />
            <h3>No todos yet</h3>
            <p>Add items to track your tasks</p>
          </div>
        ) : (
          <div className={styles.todoList}>
            {todoItems.map((todo, index) => (
              <div 
                key={index} 
                className={`${styles.todoItem} ${todo.checked ? styles.checked : ''}`}
              >
                <button 
                  className={styles.todoCheck}
                  onClick={() => toggleTodoItem(index)}
                >
                  {todo.checked ? <Check size={18} /> : <Circle size={18} />}
                </button>
                <span className={styles.todoText}>{todo.text}</span>
                <button 
                  className={`${styles.iconButton} ${styles.danger}`}
                  onClick={() => removeTodoItem(index)}
                  title="Delete"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
        
        {completedCount > 0 && (
          <div className={styles.progressSection}>
            <h4>Completion Progress</h4>
            <div className={styles.progressBar}>
              <div 
                className={styles.progressFill}
                style={{ width: `${(completedCount / todoItems.length) * 100}%` }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}