import { ChatView } from '../components/ChatView';
import { ChatSessions } from '../components/ChatSessions';
import { useAppStore } from '../store/useAppStore';
import { Menu, X } from 'lucide-react';
import styles from '../styles/PageLayout.module.css';

export function ChatsPage() {
  const { sidebarOpen, toggleSidebar } = useAppStore();
  
  return (
    <div className={styles.page}>
      <div className={styles.chatPageLayout}>
        {/* Chat sessions sidebar - Left side */}
        <aside className={`${styles.chatSidebar} ${sidebarOpen ? styles.open : styles.closed}`}>
          <ChatSessions />
        </aside>
        
        {/* Sidebar toggle button - Fixed position */}
        <button 
          className={styles.sidebarToggle}
          onClick={toggleSidebar}
          title={sidebarOpen ? 'Hide sessions' : 'Show sessions'}
        >
          {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
        
        {/* Main chat view */}
        <main className={styles.chatMain}>
          <ChatView />
        </main>
      </div>
    </div>
  );
}