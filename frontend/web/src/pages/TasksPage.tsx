import { useState, useMemo } from 'react';
import { useAppStore } from '../store/useAppStore';
import { 
  ListTodo, Clock, CheckCircle2, XCircle, Loader2, Plus, Trash2, Play, Square, Edit2, Save, X, HelpCircle,
  Search, Calendar, Terminal, RefreshCw, PlayCircle, AlertCircle, Activity, Zap, LayoutGrid
} from 'lucide-react';
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

type TaskFilter = 'all' | 'running' | 'completed' | 'failed';

const STAT_COLORS = {
  running: { bg: 'rgba(59, 130, 246, 0.15)', color: '#3b82f6', icon: Activity },
  completed: { bg: 'rgba(34, 197, 94, 0.15)', color: '#22c55e', icon: CheckCircle2 },
  failed: { bg: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', icon: AlertCircle },
  total: { bg: 'rgba(168, 85, 247, 0.15)', color: '#a855f7', icon: LayoutGrid },
};

export function TasksPage() {
  const { 
    tasks, 
    cronJobs, 
    createCronJob, 
    deleteCronJob, 
    toggleCronJob, 
    updateCronJob,
    triggerCronJob 
  } = useAppStore();
  
  // Form states
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingJob, setEditingJob] = useState<string | null>(null);
  const [newJobName, setNewJobName] = useState('');
  const [newJobSchedule, setNewJobSchedule] = useState('*/5 * * * *');
  const [newJobCommand, setNewJobCommand] = useState('');
  const [newJobCwd, setNewJobCwd] = useState('');
  const [newJobRequirements, setNewJobRequirements] = useState('');
  const [showCronHelp, setShowCronHelp] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState('');
  
  // Filter and search states
  const [taskFilter, setTaskFilter] = useState<TaskFilter>('all');
  const [taskSearch, setTaskSearch] = useState('');
  const [cronSearch, setCronSearch] = useState('');
  
  const getStatusIcon = (status: string, size = 16) => {
    switch (status) {
      case 'running':
        return <Loader2 size={size} className={styles.spinning} />;
      case 'completed':
        return <CheckCircle2 size={size} />;
      case 'failed':
        return <XCircle size={size} />;
      default:
        return <Clock size={size} />;
    }
  };
  
  const getEnhancedStatusBadge = (status: string) => {
    const statusClasses: Record<string, string> = {
      running: styles.statusBadgeRunning,
      completed: styles.statusBadgeCompleted,
      failed: styles.statusBadgeFailed,
    };
    return `${styles.enhancedStatusBadge} ${statusClasses[status] || ''}`;
  };
  
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return '#3b82f6';
      case 'completed':
        return '#22c55e';
      case 'failed':
        return '#ef4444';
      default:
        return 'var(--primary-500)';
    }
  };
  
  const getStatusBg = (status: string) => {
    switch (status) {
      case 'running':
        return 'rgba(59, 130, 246, 0.15)';
      case 'completed':
        return 'rgba(34, 197, 94, 0.15)';
      case 'failed':
        return 'rgba(239, 68, 68, 0.15)';
      default:
        return 'var(--bg-tertiary)';
    }
  };
  
  // Derived task stats
  const runningTasks = tasks.filter(t => t.status === 'running');
  const completedTasks = tasks.filter(t => t.status === 'completed');
  const failedTasks = tasks.filter(t => t.status === 'failed');
  
  // Filtered background tasks
  const filteredTasks = useMemo(() => {
    let filtered = tasks;
    
    // Apply status filter
    if (taskFilter !== 'all') {
      filtered = filtered.filter(t => t.status === taskFilter);
    }
    
    // Apply search filter
    if (taskSearch.trim()) {
      const query = taskSearch.toLowerCase();
      filtered = filtered.filter(t => 
        t.description.toLowerCase().includes(query) ||
        t.id.toLowerCase().includes(query) ||
        (t.status_note && t.status_note.toLowerCase().includes(query))
      );
    }
    
    return filtered.sort((a, b) => {
      // Sort by status priority: running first, then failed, then completed
      const priority: Record<string, number> = { running: 0, failed: 1, completed: 2 };
      return (priority[a.status] ?? 3) - (priority[b.status] ?? 3);
    });
  }, [tasks, taskFilter, taskSearch]);
  
  // Filtered cron jobs
  const filteredCronJobs = useMemo(() => {
    if (!cronSearch.trim()) return cronJobs;
    const query = cronSearch.toLowerCase();
    return cronJobs.filter(job => 
      job.name.toLowerCase().includes(query) ||
      job.command.toLowerCase().includes(query) ||
      (job.requirements && job.requirements.toLowerCase().includes(query))
    );
  }, [cronJobs, cronSearch]);
  
  const handleRunNow = async (jobName: string) => {
    try {
      await triggerCronJob(jobName);
    } catch (err) {
      console.error('Failed to trigger job:', err);
    }
  };
  
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
        <p>Manage and monitor background tasks and scheduled jobs</p>
      </div>
      
      {/* Enhanced Stats Grid */}
      <div className={styles.statsGrid}>
        <div className={`${styles.statCard} ${styles.statCardRunning}`}>
          <div className={styles.statCardHeader}>
            <div className={styles.statIcon} style={{ background: STAT_COLORS.running.bg, color: STAT_COLORS.running.color }}>
              <Activity size={20} />
            </div>
            {runningTasks.length > 0 && <div className={styles.statPulse} />}
          </div>
          <div className={styles.statContent}>
            <span className={styles.statValue} style={{ color: STAT_COLORS.running.color }}>{runningTasks.length}</span>
            <span className={styles.statLabel}>Running</span>
          </div>
        </div>
        
        <div className={`${styles.statCard} ${styles.statCardCompleted}`}>
          <div className={styles.statCardHeader}>
            <div className={styles.statIcon} style={{ background: STAT_COLORS.completed.bg, color: STAT_COLORS.completed.color }}>
              <CheckCircle2 size={20} />
            </div>
          </div>
          <div className={styles.statContent}>
            <span className={styles.statValue} style={{ color: STAT_COLORS.completed.color }}>{completedTasks.length}</span>
            <span className={styles.statLabel}>Completed</span>
          </div>
        </div>
        
        <div className={`${styles.statCard} ${styles.statCardFailed}`}>
          <div className={styles.statCardHeader}>
            <div className={styles.statIcon} style={{ background: STAT_COLORS.failed.bg, color: STAT_COLORS.failed.color }}>
              <AlertCircle size={20} />
            </div>
            {failedTasks.length > 0 && (
              <div className={styles.statAlertBadge}>{failedTasks.length}</div>
            )}
          </div>
          <div className={styles.statContent}>
            <span className={styles.statValue} style={{ color: STAT_COLORS.failed.color }}>{failedTasks.length}</span>
            <span className={styles.statLabel}>Failed</span>
          </div>
        </div>
        
        <div className={`${styles.statCard} ${styles.statCardScheduled}`}>
          <div className={styles.statCardHeader}>
            <div className={styles.statIcon} style={{ background: STAT_COLORS.total.bg, color: STAT_COLORS.total.color }}>
              <Calendar size={20} />
            </div>
          </div>
          <div className={styles.statContent}>
            <span className={styles.statValue} style={{ color: STAT_COLORS.total.color }}>{cronJobs.length}</span>
            <span className={styles.statLabel}>Scheduled</span>
          </div>
        </div>
      </div>
      
      {/* Scheduled Tasks Section */}
      <div className={styles.pageContent}>
        <div className={styles.sectionHeaderEnhanced}>
          <h2><Clock size={20} /> Scheduled Tasks</h2>
          <div className={styles.sectionMeta}>
            <span className={styles.totalCount}>{filteredCronJobs.length} jobs</span>
            <button 
              className={styles.primaryButton}
              onClick={() => setShowCreateForm(!showCreateForm)}
            >
              {showCreateForm ? <><X size={16} /> Cancel</> : <><Plus size={16} /> Add Job</>}
            </button>
          </div>
        </div>
        
        {/* Search bar for cron jobs */}
        <div className={styles.pageToolbar}>
          <div style={{ position: 'relative', flex: 1, maxWidth: '400px' }}>
            <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)' }} />
            <input
              type="text"
              placeholder="Search scheduled tasks..."
              value={cronSearch}
              onChange={(e) => setCronSearch(e.target.value)}
              style={{
                width: '100%',
                padding: 'var(--space-2) var(--space-3) var(--space-2) var(--space-8)',
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-primary)',
                fontSize: '0.875rem',
              }}
            />
          </div>
        </div>
        
        {showCreateForm && (
          <div className={styles.formCard} style={{ marginBottom: 'var(--space-4)' }}>
            {renderCronJobForm()}
          </div>
        )}
        
        {filteredCronJobs.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyStateIcon}>
              <div className={styles.emptyStateIconInner}>
                <Clock size={32} />
              </div>
              <div className={styles.emptyStateRing} />
            </div>
            <h3>{cronSearch ? 'No matching tasks' : 'No scheduled tasks'}</h3>
            <p>{cronSearch ? 'Try adjusting your search' : 'Create a scheduled task to run commands automatically'}</p>
          </div>
        ) : (
          <div className={styles.taskListGrid}>
            {filteredCronJobs.map((job) => (
              <div key={job.name} className={`${styles.enhancedTaskCard} ${!job.enabled ? styles.taskStatusDisabled : ''}`}>
                {editingJob === job.name ? (
                  <div style={{ padding: 'var(--space-2)' }}>{renderCronJobForm(job, true)}</div>
                ) : (
                  <>
                    <div className={styles.enhancedTaskHeader}>
                      <div className={styles.enhancedTaskStatus}>
                        <div 
                          className={styles.enhancedStatusIcon}
                          style={{ 
                            background: job.enabled ? 'rgba(168, 85, 247, 0.15)' : 'var(--bg-tertiary)',
                            color: job.enabled ? '#a855f7' : 'var(--text-tertiary)'
                          }}
                        >
                          <Clock size={18} />
                        </div>
                        <div className={styles.enhancedStatusInfo}>
                          <span className={styles.enhancedTaskDescription}>{job.name}</span>
                          <span 
                            className={`${styles.enhancedStatusBadge} ${job.enabled ? styles.statusBadgeCompleted : styles.statusBadgeFailed}`}
                            style={{ 
                              background: job.enabled ? 'rgba(34, 197, 94, 0.15)' : 'rgba(156, 163, 175, 0.15)',
                              color: job.enabled ? '#22c55e' : 'var(--text-tertiary)'
                            }}
                          >
                            {job.enabled ? 'Enabled' : 'Disabled'}
                          </span>
                        </div>
                      </div>
                      <div className={styles.enhancedTaskActions}>
                        <button
                          className={styles.enhancedActionButton}
                          onClick={() => handleRunNow(job.name)}
                          title="Run now"
                        >
                          <PlayCircle size={14} />
                        </button>
                        <button
                          className={styles.enhancedActionButton}
                          onClick={() => toggleCronJob(job.name, !job.enabled)}
                          title={job.enabled ? 'Disable' : 'Enable'}
                        >
                          {job.enabled ? <Square size={14} /> : <Play size={14} />}
                        </button>
                        <button
                          className={styles.enhancedActionButton}
                          onClick={() => startEditing(job)}
                          title="Edit"
                        >
                          <Edit2 size={14} />
                        </button>
                        <button
                          className={`${styles.enhancedActionButton} ${styles.danger}`}
                          onClick={() => deleteCronJob(job.name)}
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                    
                    <div className={styles.enhancedTaskMeta} style={{ marginTop: 'var(--space-3)' }}>
                      <div className={styles.enhancedTaskMetaItem}>
                        <RefreshCw size={12} />
                        <code style={{ fontSize: '0.75rem', background: 'var(--bg-tertiary)', padding: '2px 6px', borderRadius: 'var(--radius-sm)' }}>
                          {job.schedule}
                        </code>
                      </div>
                      <div className={styles.enhancedTaskMetaItem}>
                        <Terminal size={12} />
                        <span style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {job.command}
                        </span>
                      </div>
                      {job.cwd && (
                        <div className={styles.enhancedTaskMetaItem}>
                          <LayoutGrid size={12} />
                          <span style={{ maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {job.cwd}
                          </span>
                        </div>
                      )}
                    </div>
                    
                    {job.requirements && (
                      <div style={{ marginTop: 'var(--space-3)', padding: 'var(--space-2) var(--space-3)', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', fontSize: '0.8125rem', color: 'var(--text-secondary)', borderLeft: '3px solid var(--primary-500)' }}>
                        <p style={{ margin: 0, whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{job.requirements}</p>
                      </div>
                    )}
                    
                    {job.next_run && (
                      <div className={styles.enhancedTaskMeta} style={{ marginTop: 'var(--space-3)', paddingTop: 'var(--space-3)', borderTop: '1px solid var(--border-subtle)' }}>
                        <div className={styles.enhancedTaskMetaItem}>
                          <Calendar size={12} />
                          <span>Next run: {job.next_run}</span>
                        </div>
                      </div>
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
        <div className={styles.sectionHeaderEnhanced}>
          <h2><ListTodo size={20} /> Background Tasks</h2>
          <div className={styles.sectionMeta}>
            <span className={styles.totalCount}>{filteredTasks.length} of {tasks.length}</span>
          </div>
        </div>
        
        {/* Filter Tabs & Search */}
        <div className={styles.pageToolbar} style={{ flexWrap: 'wrap', gap: 'var(--space-3)' }}>
          {/* Status Filter Tabs */}
          <div style={{ display: 'flex', gap: 'var(--space-1)', background: 'var(--bg-tertiary)', padding: '4px', borderRadius: 'var(--radius-md)' }}>
            {(['all', 'running', 'completed', 'failed'] as TaskFilter[]).map((filter) => (
              <button
                key={filter}
                onClick={() => setTaskFilter(filter)}
                style={{
                  padding: 'var(--space-1) var(--space-3)',
                  background: taskFilter === filter ? 'var(--bg-primary)' : 'transparent',
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  color: taskFilter === filter ? 'var(--text-primary)' : 'var(--text-secondary)',
                  fontSize: '0.8125rem',
                  fontWeight: taskFilter === filter ? 600 : 500,
                  cursor: 'pointer',
                  transition: 'var(--transition-fast)',
                  boxShadow: taskFilter === filter ? 'var(--shadow-sm)' : 'none',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-1)',
                }}
              >
                {filter === 'all' && <LayoutGrid size={14} />}
                {filter === 'running' && <Activity size={14} />}
                {filter === 'completed' && <CheckCircle2 size={14} />}
                {filter === 'failed' && <AlertCircle size={14} />}
                {filter.charAt(0).toUpperCase() + filter.slice(1)}
                <span style={{ 
                  marginLeft: 'var(--space-1)', 
                  padding: '0 6px', 
                  background: taskFilter === filter ? 'var(--bg-tertiary)' : 'var(--bg-secondary)',
                  borderRadius: 'var(--radius-full)',
                  fontSize: '0.6875rem',
                  fontWeight: 600,
                }}>
                  {filter === 'all' ? tasks.length : tasks.filter(t => t.status === filter).length}
                </span>
              </button>
            ))}
          </div>
          
          {/* Search */}
          <div style={{ position: 'relative', flex: 1, minWidth: '200px', maxWidth: '300px', marginLeft: 'auto' }}>
            <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)' }} />
            <input
              type="text"
              placeholder="Search tasks..."
              value={taskSearch}
              onChange={(e) => setTaskSearch(e.target.value)}
              style={{
                width: '100%',
                padding: 'var(--space-2) var(--space-3) var(--space-2) var(--space-8)',
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-primary)',
                fontSize: '0.875rem',
              }}
            />
          </div>
        </div>
        
        {filteredTasks.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyStateIcon}>
              <div className={styles.emptyStateIconInner}>
                <ListTodo size={32} />
              </div>
              <div className={styles.emptyStateRing} />
            </div>
            <h3>{taskSearch || taskFilter !== 'all' ? 'No matching tasks' : 'No tasks yet'}</h3>
            <p>{taskSearch || taskFilter !== 'all' ? 'Try adjusting your filters' : 'Tasks will appear here when you start background operations'}</p>
          </div>
        ) : (
          <div className={styles.taskList}>
            {filteredTasks.map((task) => (
              <div 
                key={task.id} 
                className={`${styles.enhancedTaskCard} ${
                  task.status === 'running' ? styles.taskStatusRunning : 
                  task.status === 'failed' ? styles.taskStatusFailed : 
                  task.status === 'completed' ? styles.taskStatusCompleted : ''
                }`}
              >
                <div className={styles.enhancedTaskHeader}>
                  <div className={styles.enhancedTaskStatus}>
                    <div 
                      className={styles.enhancedStatusIcon}
                      style={{ 
                        background: getStatusBg(task.status),
                        color: getStatusColor(task.status)
                      }}
                    >
                      {getStatusIcon(task.status, 18)}
                    </div>
                    <div className={styles.enhancedStatusInfo}>
                      <span className={styles.enhancedTaskDescription}>{task.description}</span>
                      <span className={getEnhancedStatusBadge(task.status)}>
                        {task.status}
                      </span>
                    </div>
                  </div>
                  <span className={styles.enhancedProgressText}>{task.progress !== undefined ? `${task.progress}%` : ''}</span>
                </div>
                
                {task.progress !== undefined && (
                  <div className={styles.enhancedProgressContainer}>
                    <div className={styles.enhancedProgressBar}>
                      <div 
                        className={styles.enhancedProgressFill}
                        style={{ 
                          width: `${task.progress}%`,
                          background: getStatusColor(task.status)
                        }}
                      />
                    </div>
                  </div>
                )}
                
                {task.status_note && (
                  <div style={{ marginTop: 'var(--space-3)', padding: 'var(--space-2) var(--space-3)', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                    <p style={{ margin: 0 }}>{task.status_note}</p>
                  </div>
                )}
                
                <div className={styles.enhancedTaskMeta} style={{ marginTop: 'var(--space-3)', paddingTop: 'var(--space-3)', borderTop: '1px solid var(--border-subtle)' }}>
                  <div className={styles.enhancedTaskMetaItem}>
                    <Terminal size={12} />
                    <code style={{ fontSize: '0.75rem', background: 'var(--bg-tertiary)', padding: '2px 6px', borderRadius: 'var(--radius-sm)' }}>
                      {task.id.slice(0, 8)}
                    </code>
                  </div>
                  <div className={styles.enhancedTaskMetaItem}>
                    <Zap size={12} />
                    <span>{task.type || 'local_bash'}</span>
                  </div>
                  {task.progress !== undefined && (
                    <div className={styles.enhancedTaskMetaItem}>
                      <Activity size={12} />
                      <span>{task.progress}% complete</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
