import { ChatView } from '../components/ChatView';
import styles from './PageLayout.module.css';

export function ChatsPage() {
  return (
    <div className={styles.page}>
      <ChatView />
    </div>
  );
}