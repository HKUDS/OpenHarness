import { useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import { ListTodo, Clock, CheckCircle2, XCircle, Loader2, Plus, Trash2, Play, Square, Edit2, Save, X, HelpCircle } from 'lucide-react';
import styles from './PageLayout.module.css';

const CRON_PRESETS = [
  { label: 'Every minute', value: '* * * * *' },
  { label: 'Every 5 minutes', value: '*/5 * * * *' },
  { label: 'Every 10 minutes', value: '*/10 * * * *' },
  { label: 'Every 30 minutes', value: '*/30 * * * *' },
  { label: 'Hourly', value: '0 * * * *' },
  { label: 'Daily at midnight', value: '0 0 * * *' },
  { label: 'Daily at 9am', value: '0 9 * * *' },
  { label: 'Weekly on Monday 9am', value: '0 9 * * 1' },
  { label: 'Weekdays at 9am', value: '0 9 * * 1-5' },
  { label: 'Weekends at 10am', value: '0 10 * * 0,6' },
  { label: 'Monthly on 1st at midnight', value: '0 0 1 * *' },
];

const CRON_HELP = {
  minute: '0-59',
  hour: '0-23',
  dayOfMonth: '1-31',
  month: '1-12 (or Jan-Dec)',
  dayOfWeek: '0-6 (or Sun-Sat, 0=Sunday)',
};

export function TasksPage() {
  const { tasks, cronJobs, createCronJob, deleteCronJob, toggleCronJob, updateCronJob } = useAppStore();
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingJob, setEditingJob] = useState<string | null>(null);
  const [newJobName, setNewJobName] = useState('');
  const [newJobSchedule, setNewJobSchedule] = useState('*/5 * * * *');
  const [newJobCommand, setNewJobCommand] = useState('');
  const [newJobCwd, setNewJobCwd] = useState('');
  const [newJobRequirements, setNewJobRequirements] = useState('');
  const [showCronHelp, setShowCronHelp] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState('');
  
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
  
  const handleCreateCronJob = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newJobName || !newJobCommand) return;
    
    createCronJob(newJobName, newJobSchedule, newJobCommand, newJobCwd || undefined, true, newJobRequirements || undefined);
    setNewJobName('');
    setNewJobSchedule('*/5 * * * *');
    setNewJobCommand('');
    setNewJobCwd('');
    setNewJobRequirements('');
    setSelectedPreset('');
    setShowCreateForm(false);
  };
  
  const handleUpdateCronJob = (e: React.FormEvent, jobName: string) => {
    e.preventDefault();
    if (!newJobName || !newJobCommand) return;
    
    updateCronJob(jobName, {
      name: newJobName,
      schedule: newJobSchedule,
      command: newJobCommand,
      cwd: newJobCwd || undefined,
      requirements: newJobRequirements || undefined,
    });
    setEditingJob(null);
    setNewJobName('');
    setNewJobSchedule('*/5 * * * *');
    setNewJobCommand('');
    setNewJobCwd('');
    setNewJobRequirements('');
    setSelectedPreset('');
  };
  
  const startEditing = (job: typeof cronJobs[0]) => {
    setEditingJob(job.name);
    setNewJobName(job.name);
    setNewJobSchedule(job.schedule);
    setNewJobCommand(job.command);
    setNewJobCwd(job.cwd || '');
    setNewJobRequirements(job.requirements || '');
    setSelectedPreset('');
  };
  
  const cancelEditing = () => {
    setEditingJob(null);
    setNewJobName('');
    setNewJobSchedule('*/5 * * * *');
    setNewJobCommand('');
    setNewJobCwd('');
    setNewJobRequirements('');
    setSelectedPreset('');
  };
  
  const handlePresetChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const preset = e.target.value;
    setSelectedPreset(preset);
    if (preset) {
      const selected = CRON_PRESETS.find(p => p.value === preset);
      if (selected) {
        setNewJobSchedule(selected.value);
      }
    }
  };
  
  const renderCronJobForm = (job?: typeof cronJobs[0], isEdit = false) => (
    <form onSubmit={isEdit ? (e) => handleUpdateCronJob(e, job!.name) : handleCreateCronJob} className={styles.createForm}>
      <div className={styles.formGroup}>
        <label>Name</label>
        <input
          type="text"
          value={newJobName}
          onChange={(e) => setNewJobName(e.target.value)}
          placeholder="my-task"
          required
        />
      </div>
      
      <div className={styles.formGroup}>
        <label>Schedule (cron expression)</label>
        <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'flex-start' }}>
          <select
            value={selectedPreset}
            onChange={handlePresetChange}
            style={{ flex: 1, padding: 'var(--space-2)', background: 'var(--bg-tertiary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', color: 'var(--text-secondary)', fontSize: '0.875rem' }}
          >
            <option value="">-- Select a preset --</option>
            {CRON_PRESETS.map(preset => (
              <option key={preset.value} value={preset.value}>{preset.label}</option>
            ))}
          </select>
          <button
            type="button"
            className={styles.iconButton}
            onClick={() => setShowCronHelp(!showCronHelp)}
            title="Cron format help"
          >
            <HelpCircle size={16} />
          </button>
        </div>
        <input
          type="text"
          value={newJobSchedule}
          onChange={(e) => setNewJobSchedule(e.target.value)}
          placeholder="*/5 * * * *"
          required
          style={{ marginTop: 'var(--space-2)' }}
        />
        <small>Examples: */5 * * * * (every 5 min), 0 9 * * 1-5 (weekdays at 9am)</small>
        
        {showCronHelp && (
          <div style={{ marginTop: 'var(--space-2)', padding: 'var(--space-3)', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', fontSize: '0.8125rem' }}>
            <strong>Cron Expression Format:</strong>
            <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
              <span>Minute:</span><code>{CRON_HELP.minute}</code>
              <span>Hour:</span><code>{CRON_HELP.hour}</code>
              <span>Day of Month:</span><code>{CRON_HELP.dayOfMonth}</code>
              <span>Month:</span><code>{CRON_HELP.month}</code>
              <span>Day of Week:</span><code>{CRON_HELP.dayOfWeek}</code>
            </div>
            <div style={{ marginTop: 'var(--space-2)', fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>
              Use * for any value, */n for every n units, n-m for ranges, n,m for lists
            </div>
          </div>
        )}
      </div>
      
      <div className={styles.formGroup}>
        <label>Command</label>
        <input
          type="text"
          value={newJobCommand}
          onChange={(e) => setNewJobCommand(e.target.value)}
          placeholder="oh cron list"
          required
        />
      </div>
      
      <div className={styles.formGroup}>
        <label>Working Directory (optional)</label>
        <input
          type="text"
          value={newJobCwd}
          onChange={(e) => setNewJobCwd(e.target.value)}
          placeholder="~/workspace"
        />
      </div>
      
      <div className={styles.formGroup}>
        <label>Requirements / Notes (optional)</label>
        <textarea
          value={newJobRequirements}
          onChange={(e) => setNewJobRequirements(e.target.value)}
          placeholder="Describe any requirements, dependencies, or notes for this scheduled task..."
          rows={3}
          style={{ resize: 'vertical', fontFamily: 'inherit' }}
        />
        <small>Specify any prerequisites, expected outcomes, or important notes for this task</small>
      </div>
      
      <div className={styles.formActions}>
        {isEdit && (
          <button type="button" className={styles.secondaryButton} onClick={cancelEditing}>
            <X size={16} /> Cancel
          </button>
        )}
        <button type="submit" className={styles.primaryButton}>
          {isEdit ? <><Save size={16} /> Save Changes</> : <><Plus size={16} /> Create Scheduled Task</>}
        </button>
      </div>
    </form>
  );
  
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
      
      {/* Scheduled Tasks Section */}
      <div className={styles.pageContent}>
        <div className={styles.sectionHeader}>
          <h2><Clock size={20} /> Scheduled Tasks</h2>
          <button 
            className={styles.primaryButton}
            onClick={() => setShowCreateForm(!showCreateForm)}
          >
            <Plus size={16} /> {showCreateForm ? 'Cancel' : 'Add Scheduled Task'}
          </button>
        </div>
        
        {showCreateForm && renderCronJobForm()}
        
        {cronJobs.length === 0 ? (
          <div className={styles.emptyState}>
            <Clock size={48} />
            <h3>No scheduled tasks</h3>
            <p>Create a scheduled task to run commands automatically</p>
          </div>
        ) : (
          <div className={styles.taskList}>
            {cronJobs.map((job) => (
              <div key={job.name} className={styles.taskCard}>
                {editingJob === job.name ? (
                  renderCronJobForm(job, true)
                ) : (
                  <>
                    <div className={styles.taskHeader}>
                      <div className={styles.taskTitle}>
                        <Clock size={16} />
                        <span>{job.name}</span>
                      </div>
                      <div className={styles.taskActions}>
                        <button
                          className={styles.iconButton}
                          onClick={() => toggleCronJob(job.name, !job.enabled)}
                          title={job.enabled ? 'Disable' : 'Enable'}
                        >
                          {job.enabled ? <Square size={16} /> : <Play size={16} />}
                        </button>
                        <button
                          className={styles.iconButton}
                          onClick={() => startEditing(job)}
                          title="Edit"
                        >
                          <Edit2 size={16} />
                        </button>
                        <button
                          className={styles.iconButton}
                          onClick={() => deleteCronJob(job.name)}
                          title="Delete"
                        >
                          <Trash2 size={16} className={styles.danger} />
                        </button>
                      </div>
                    </div>
                    
                    <div className={styles.taskMeta}>
                      <span>Schedule: {job.schedule}</span>
                      <span>Command: {job.command}</span>
                      {job.cwd && <span>CWD: {job.cwd}</span>}
                      <span>Status: {job.enabled ? 'Enabled' : 'Disabled'}</span>
                    </div>
                    
                    {job.requirements && (
                      <div style={{ marginTop: 'var(--space-2)', padding: 'var(--space-2)', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                        <strong>Requirements:</strong>
                        <p style={{ margin: 'var(--space-1) 0 0 0', whiteSpace: 'pre-wrap' }}>{job.requirements}</p>
                      </div>
                    )}
                    
                    {job.next_run && (
                      <div className={styles.taskNote}>Next run: {job.next_run}</div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      
      {/* Background Tasks Section */}
      <div className={styles.pageContent}>
        <div className={styles.sectionHeader}>
          <h2><ListTodo size={20} /> Background Tasks</h2>
        </div>
        
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
