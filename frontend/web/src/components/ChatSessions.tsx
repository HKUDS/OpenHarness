import { Plus, MessageSquare, Trash2, Edit2, Check, X, Search, XCircle } from 'lucide-react';
import { useState, useCallback, useEffect, useRef } from 'react';
import { useAppStore } from '../store/useAppStore';
import styles from '../styles/ChatSessions.module.css';

export function ChatSessions() {
  const { 
    chatSessions, 
    currentChatId, 
    createNewChat, 
    switchChat, 
    deleteChat, 
    updateChatSession,
    searchQuery,
    searchResults,
    setSearchQuery,
    searchMessages,
    clearSearch,
    setScrollToMessageId,
    chatSidebarWidth,
    setChatSidebarWidth,
    isResizingChatSidebar,
    setIsResizingChatSidebar
  } = useAppStore();
  
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Drag to resize chat sidebar with requestAnimationFrame for smooth performance
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizingChatSidebar(true);
    // Disable transitions during drag
    if (sidebarRef.current) {
      sidebarRef.current.style.transition = 'none';
    }
  }, [setIsResizingChatSidebar]);

  useEffect(() => {
    let rafId: number | null = null;
    let lastWidth = chatSidebarWidth;
    
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingChatSidebar) return;
      
      // Cancel pending frame if exists
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      
      // Schedule update on next frame
      rafId = requestAnimationFrame(() => {
        const newWidth = e.clientX;
        const clampedWidth = Math.max(200, Math.min(450, newWidth));
        
        // Only update if width actually changed
        if (clampedWidth !== lastWidth) {
          lastWidth = clampedWidth;
          setChatSidebarWidth(clampedWidth);
        }
        rafId = null;
      });
    };

    const handleMouseUp = () => {
      setIsResizingChatSidebar(false);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = 'auto';
      // Re-enable transitions
      if (sidebarRef.current) {
        sidebarRef.current.style.transition = '';
      }
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
    };

    if (isResizingChatSidebar) {
      document.addEventListener('mousemove', handleMouseMove, { passive: true });
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [isResizingChatSidebar, setChatSidebarWidth, setIsResizingChatSidebar]);

  // Focus search input when shown
  useEffect(() => {
    if (showSearch && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [showSearch]);

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

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value;
    setSearchQuery(query);
    searchMessages(query);
  };

  const handleSearchResultClick = (chatId: string, messageId: string) => {
    switchChat(chatId);
    setScrollToMessageId(messageId);
    clearSearch();
    setShowSearch(false);
  };

  const handleClearSearch = () => {
    clearSearch();
    setShowSearch(false);
  };

  return (
    <div className={styles.chatSessions} ref={sidebarRef} style={{ width: `${chatSidebarWidth}px` }}>
      {/* Resize Handle */}
      <div 
        className={`${styles.resizeHandle} ${isResizingChatSidebar ? styles.resizing : ''}`}
        onMouseDown={handleMouseDown}
      />
      
      <div className={styles.header}>
        <h3>Chat Sessions</h3>
        <div className={styles.headerActions}>
          <button 
            className={`${styles.searchButton} ${showSearch ? styles.active : ''}`}
            onClick={() => setShowSearch(!showSearch)}
            title="Search messages"
          >
            <Search size={18} />
          </button>
          <button 
            className={styles.newChatButton}
            onClick={() => createNewChat()}
            title="New Chat"
          >
            <Plus size={18} />
          </button>
        </div>
      </div>

      {/* Search Input */}
      {showSearch && (
        <div className={styles.searchContainer}>
          <div className={styles.searchInputWrapper}>
            <Search size={16} className={styles.searchIcon} />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={handleSearchChange}
              placeholder="Search across all chats..."
              className={styles.searchInput}
            />
            {searchQuery && (
              <button 
                className={styles.clearSearchButton}
                onClick={handleClearSearch}
                title="Clear search"
              >
                <XCircle size={16} />
              </button>
            )}
          </div>
          
          {/* Search Results */}
          {searchResults.length > 0 && (
            <div className={styles.searchResults}>
              <div className={styles.searchResultsHeader}>
                Found {searchResults.length} messages
              </div>
              {searchResults.map((result) => (
                <div 
                  key={`${result.chatId}-${result.messageId}`}
                  className={styles.searchResultItem}
                  onClick={() => handleSearchResultClick(result.chatId, result.messageId)}
                >
                  <div className={styles.searchResultChat}>{result.chatName}</div>
                  <div className={styles.searchResultContent}>{result.content}</div>
                  <div className={styles.searchResultTime}>{formatTime(result.timestamp)}</div>
                </div>
              ))}
            </div>
          )}
          
          {searchQuery && searchResults.length === 0 && (
            <div className={styles.noResults}>
              No messages found matching "{searchQuery}"
            </div>
          )}
        </div>
      )}

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
