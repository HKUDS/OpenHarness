import { useAppStore } from '../store/useAppStore';
import { ListTodo, Clock, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import styles from './PageLayout.module.css';

export function TasksPage() {
  const { tasks } = useAppStore();
  
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <Loader2 size={16} className={styles.spinning} />;
      case 'completed':
        return <CheckCircle2 size={16} />;
      case 'failed':
        return <XCircle size={16} />;
      default:
        return <Clock size={16} />;
    }
  };
  
  const getStatusClass = (status: string) => {
    return `${styles.status} ${styles[status] || ''}`;
  };
  
  const runningTasks = tasks.filter(t => t.status === 'running');
  const completedTasks = tasks.filter(t => t.status === 'completed');
  const failedTasks = tasks.filter(t => t.status === 'failed');
  
  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><ListTodo size={24} /> Tasks</h1>
        <p>Manage and monitor background tasks</p>
      </div>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{runningTasks.length}</span>
          <span className={styles.statLabel}>Running</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{completedTasks.length}</span>
          <span className={styles.statLabel}>Completed</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{failedTasks.length}</span>
          <span className={styles.statLabel}>Failed</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{tasks.length}</span>
          <span className={styles.statLabel}>Total</span>
        </div>
      </div>
      
      <div className={styles.pageContent}>
        {tasks.length === 0 ? (
          <div className={styles.emptyState}>
            <ListTodo size={48} />
            <h3>No tasks yet</h3>
            <p>Tasks will appear here when you start background operations</p>
          </div>
        ) : (
          <div className={styles.taskList}>
            {tasks.map((task) => (
              <div key={task.id} className={styles.taskCard}>
                <div className={styles.taskHeader}>
                  <div className={styles.taskTitle}>
                    {getStatusIcon(task.status)}
                    <span>{task.description}</span>
                  </div>
                  <span className={getStatusClass(task.status)}>
                    {task.status}
                  </span>
                </div>
                
                {task.progress !== undefined && (
                  <div className={styles.progressContainer}>
                    <div className={styles.progressBar}>
                      <div 
                        className={styles.progressFill}
                        style={{ width: `${task.progress}%` }}
                      />
                    </div>
                    <span className={styles.progressText}>{task.progress}%</span>
                  </div>
                )}
                
                {task.status_note && (
                  <p className={styles.taskNote}>{task.status_note}</p>
                )}
                
                <div className={styles.taskMeta}>
                  <span>ID: {task.id}</span>
                  <span>Type: {task.type || 'local_bash'}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}