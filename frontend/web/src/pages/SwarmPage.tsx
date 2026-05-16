import { useAppStore } from '../store/useAppStore';
import { Users, Bot, Plus, Activity, MessageSquare } from 'lucide-react';
import { useState } from 'react';
import styles from './PageLayout.module.css';

export function SwarmPage() {
  const { swarmTeammates, swarmNotifications } = useAppStore();
  const [showCreateTeam, setShowCreateTeam] = useState(false);
  
  const activeTeammates = swarmTeammates.filter(t => t.status === 'running' || t.status === 'active');
  
  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Users size={24} /> Swarm</h1>
        <p>Manage agent teams and teammates</p>
      </div>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{activeTeammates.length}</span>
          <span className={styles.statLabel}>Active</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{swarmTeammates.length}</span>
          <span className={styles.statLabel}>Teammates</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{swarmNotifications.length}</span>
          <span className={styles.statLabel}>Notifications</span>
        </div>
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
          <button 
            className={styles.primaryButton}
            onClick={() => setShowCreateTeam(!showCreateTeam)}
          >
            <Plus size={18} />
            Create Team
          </button>
        </div>
        
        {showCreateTeam && (
          <div className={styles.formCard}>
            <h3>Create New Team</h3>
            <div className={styles.formGroup}>
              <label>Team Name</label>
              <input type="text" placeholder="My Team" />
            </div>
            <div className={styles.formGroup}>
              <label>Description</label>
              <textarea placeholder="Team purpose and goals..." rows={3} />
            </div>
            <div className={styles.formActions}>
              <button className={styles.secondaryButton} onClick={() => setShowCreateTeam(false)}>
                Cancel
              </button>
              <button className={styles.primaryButton}>
                Create Team
              </button>
            </div>
          </div>
        )}
        
        {swarmTeammates.length === 0 ? (
          <div className={styles.emptyState}>
            <Users size={48} />
            <h3>No teammates yet</h3>
            <p>Create a team to collaborate with AI agents</p>
          </div>
        ) : (
          <div className={styles.gridLayout}>
            {swarmTeammates.map((teammate) => (
              <div key={teammate.agent_id} className={styles.teammateCard}>
                <div className={styles.teammateHeader}>
                  <div className={styles.teammateAvatar}>
                    <Bot size={24} />
                  </div>
                  <div className={styles.teammateInfo}>
                    <span className={styles.teammateName}>{teammate.name}</span>
                    <span className={`${styles.status} ${styles[teammate.status]}`}>
                      <Activity size={12} />
                      {teammate.status}
                    </span>
                  </div>
                </div>
                
                {teammate.task && (
                  <div className={styles.teammateTask}>
                    <MessageSquare size={14} />
                    <span>{teammate.task}</span>
                  </div>
                )}
                
                <div className={styles.teammateMeta}>
                  <span>ID: {teammate.agent_id}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}