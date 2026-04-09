import { useAppStore } from '../store/useAppStore';
import { Sparkles, Plus, ToggleLeft, ToggleRight, Trash2, Code, Bug, TestTube, FileText, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import styles from './PageLayout.module.css';

const SKILL_ICONS: Record<string, React.ReactNode> = {
  'code-review': <Code size={20} />,
  'debugging': <Bug size={20} />,
  'testing': <TestTube size={20} />,
  'documentation': <FileText size={20} />,
  'refactoring': <RefreshCw size={20} />,
};

export function SkillsPage() {
  const { skills, toggleSkill, addSkill, removeSkill } = useAppStore();
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSkill, setNewSkill] = useState({ name: '', description: '' });
  
  const enabledSkills = skills.filter(s => s.enabled);
  
  const handleAddSkill = () => {
    if (newSkill.name && newSkill.description) {
      addSkill({
        id: newSkill.name.toLowerCase().replace(/\s+/g, '-'),
        name: newSkill.name,
        description: newSkill.description,
        enabled: true
      });
      setNewSkill({ name: '', description: '' });
      setShowAddForm(false);
    }
  };
  
  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Sparkles size={24} /> Skills</h1>
        <p>Manage AI skills and capabilities</p>
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
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
          <button 
            className={styles.primaryButton}
            onClick={() => setShowAddForm(!showAddForm)}
          >
            <Plus size={18} />
            Add Skill
          </button>
        </div>
        
        {showAddForm && (
          <div className={styles.formCard}>
            <h3>Add New Skill</h3>
            <div className={styles.formGroup}>
              <label>Skill Name</label>
              <input
                type="text"
                value={newSkill.name}
                onChange={(e) => setNewSkill({ ...newSkill, name: e.target.value })}
                placeholder="My Custom Skill"
              />
            </div>
            <div className={styles.formGroup}>
              <label>Description</label>
              <textarea
                value={newSkill.description}
                onChange={(e) => setNewSkill({ ...newSkill, description: e.target.value })}
                placeholder="What does this skill do?"
                rows={3}
              />
            </div>
            <div className={styles.formActions}>
              <button className={styles.secondaryButton} onClick={() => setShowAddForm(false)}>
                Cancel
              </button>
              <button className={styles.primaryButton} onClick={handleAddSkill}>
                Add Skill
              </button>
            </div>
          </div>
        )}
        
        {skills.length === 0 ? (
          <div className={styles.emptyState}>
            <Sparkles size={48} />
            <h3>No skills configured</h3>
            <p>Add skills to enhance AI capabilities</p>
          </div>
        ) : (
          <div className={styles.gridLayout}>
            {skills.map((skill) => (
              <div key={skill.id} className={`${styles.skillCard} ${skill.enabled ? styles.enabled : ''}`}>
                <div className={styles.skillHeader}>
                  <div className={styles.skillIcon}>
                    {SKILL_ICONS[skill.id] || <Sparkles size={20} />}
                  </div>
                  <div className={styles.skillInfo}>
                    <span className={styles.skillName}>{skill.name}</span>
                    <span className={styles.skillStatus}>
                      {skill.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                </div>
                
                <p className={styles.skillDescription}>{skill.description}</p>
                
                <div className={styles.skillActions}>
                  <button 
                    className={styles.toggleButton}
                    onClick={() => toggleSkill(skill.id)}
                    title={skill.enabled ? 'Disable' : 'Enable'}
                  >
                    {skill.enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                  </button>
                  <button 
                    className={`${styles.iconButton} ${styles.danger}`}
                    onClick={() => removeSkill(skill.id)}
                    title="Remove"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}