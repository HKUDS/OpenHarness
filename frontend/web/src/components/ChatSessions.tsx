import { Plus, MessageSquare, Trash2, Edit2, Check, X } from 'lucide-react';
import { useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import styles from '../styles/ChatSessions.module.css';

export function ChatSessions() {
  const { chatSessions, currentChatId, createNewChat, switchChat, deleteChat, updateChatSession } = useAppStore();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (days === 1) {
      return 'Yesterday';
    } else if (days < 7) {
      return date.toLocaleDateString([], { weekday: 'short' });
    } else {
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
  };

  const handleStartEdit = (chat: any, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(chat.id);
    setEditName(chat.name);
  };

  const handleDelete = (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this chat?')) {
      deleteChat(chatId);
    }
  };

  const handleSaveEdit = (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (editName.trim()) {
      updateChatSession(chatId, { name: editName.trim() });
    }
    setEditingId(null);
    setEditName('');
  };

  const handleCancelEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(null);
    setEditName('');
  };

  return (
    <div className={styles.chatSessions}>
      <div className={styles.header}>
        <h3>Chat Sessions</h3>
        <button 
          className={styles.newChatButton}
          onClick={() => createNewChat()}
          title="New Chat"
        >
          <Plus size={18} />
        </button>
      </div>

      <div className={styles.sessions}>
        {chatSessions.length === 0 ? (
          <div className={styles.empty}>
            <MessageSquare size={32} className={styles.emptyIcon} />
            <p>No chat sessions yet</p>
            <button className={styles.createButton} onClick={() => createNewChat()}>
              Start Your First Chat
            </button>
          </div>
        ) : (
          chatSessions.map(chat => (
            <div
              key={chat.id}
              className={`${styles.session} ${chat.id === currentChatId ? styles.active : ''}`}
              onClick={() => switchChat(chat.id)}
            >
              <div className={styles.sessionIcon}>
                <MessageSquare size={18} />
              </div>
              <div className={styles.sessionContent}>
                {editingId === chat.id ? (
                  <div className={styles.editMode}>
                    <input
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      className={styles.editInput}
                      autoFocus
                      onClick={(e) => e.stopPropagation()}
                    />
                    <div className={styles.editActions}>
                      <button
                        className={styles.editSave}
                        onClick={(e) => handleSaveEdit(chat.id, e)}
                      >
                        <Check size={14} />
                      </button>
                      <button
                        className={styles.editCancel}
                        onClick={(e) => handleCancelEdit(e)}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <span className={styles.sessionName}>{chat.name}</span>
                    <span className={styles.sessionTime}>{formatTime(chat.updatedAt)}</span>
                  </>
                )}
              </div>
              {editingId !== chat.id && (
                <div className={styles.sessionActions}>
                  <button
                    className={styles.actionButton}
                    onClick={(e) => handleStartEdit(chat, e)}
                    title="Rename"
                  >
                    <Edit2 size={14} />
                  </button>
                  <button
                    className={styles.deleteButton}
                    onClick={(e) => handleDelete(chat.id, e)}
                    title="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
