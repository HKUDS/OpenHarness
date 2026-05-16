import { Sparkles, Plus, Trash2, ToggleLeft, ToggleRight } from 'lucide-react';
import { useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import styles from '../styles/SkillsPanel.module.css';

export function SkillsPanel() {
  const { skills, toggleSkill, removeSkill, addSkill } = useAppStore();
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSkill, setNewSkill] = useState({ name: '', description: '' });

  const handleAdd = () => {
    if (newSkill.name && newSkill.description) {
      addSkill({
        id: `skill-${Date.now()}`,
        name: newSkill.name,
        description: newSkill.description,
        enabled: true
      });
      setNewSkill({ name: '', description: '' });
      setShowAddForm(false);
    }
  };

  return (
    <div className={styles.skillsPanel}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <Sparkles size={20} />
          <h3>Skills</h3>
        </div>
        <button 
          className={styles.addButton}
          onClick={() => setShowAddForm(!showAddForm)}
        >
          <Plus size={18} />
        </button>
      </div>

      {showAddForm && (
        <div className={styles.addForm}>
          <input
            type="text"
            value={newSkill.name}
            onChange={(e) => setNewSkill({ ...newSkill, name: e.target.value })}
            placeholder="Skill name"
            className={styles.input}
          />
          <input
            type="text"
            value={newSkill.description}
            onChange={(e) => setNewSkill({ ...newSkill, description: e.target.value })}
            placeholder="Description"
            className={styles.input}
          />
          <div className={styles.formActions}>
            <button className={styles.cancelButton} onClick={() => setShowAddForm(false)}>
              Cancel
            </button>
            <button className={styles.saveButton} onClick={handleAdd}>
              Add Skill
            </button>
          </div>
        </div>
      )}

      <div className={styles.skills}>
        {skills.length === 0 ? (
          <div className={styles.empty}>
            <Sparkles size={32} />
            <p>No skills configured</p>
            <p className={styles.hint}>Add skills to customize AI behavior</p>
          </div>
        ) : (
          skills.map(skill => (
            <div 
              key={skill.id} 
              className={`${styles.skillCard} ${skill.enabled ? styles.enabled : styles.disabled}`}
            >
              <div className={styles.skillHeader}>
                <div className={`${styles.skillIcon} ${skill.enabled ? styles.enabled : ''}`}>
                  <Sparkles size={18} />
                </div>
                <div className={styles.skillInfo}>
                  <h4 className={styles.skillName}>{skill.name}</h4>
                  <p className={styles.skillDescription}>{skill.description}</p>
                </div>
                <button
                  className={styles.toggleButton}
                  onClick={() => toggleSkill(skill.id)}
                  title={skill.enabled ? 'Disable skill' : 'Enable skill'}
                >
                  {skill.enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                </button>
              </div>
              <div className={styles.skillStatus}>
                <span className={`${styles.statusBadge} ${skill.enabled ? styles.enabled : styles.disabled}`}>
                  {skill.enabled ? '✓ Active' : '○ Inactive'}
                </span>
                <button
                  className={styles.deleteButton}
                  onClick={() => removeSkill(skill.id)}
                  title="Remove skill"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      <div className={styles.infoCard}>
        <h4>💡 About Skills</h4>
        <p>Skills customize how the AI assists you. Enable relevant skills for your current task to get better results.</p>
      </div>
    </div>
  );
}
