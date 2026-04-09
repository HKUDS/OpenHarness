import React, { useRef, useEffect } from 'react';
import { Send, Bot, User, AlertCircle, Wrench, Paperclip, Maximize2, Minimize2, ChevronDown, ChevronUp, Sparkles, Brain, Plus } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { FileUpload } from './FileUpload';
import { ModelSelector } from './ModelSelector';
import styles from '../styles/ChatView.module.css';

export function ChatView() {
  const { 
    messages, 
    isBusy, 
    submitPrompt, 
    inputHeight, 
    setInputHeight, 
    showFileUpload, 
    uploadedFiles,
    expandedMessages,
    toggleMessageExpand,
    isResizingInput,
    setIsResizingInput,
    setShowFileUpload,
    createNewChat,
    currentChatId,
    chatSessions,
    clearMessages
  } = useAppStore();
  
  const [input, setInput] = React.useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const inputContainerRef = useRef<HTMLDivElement>(null);
  const resizeHandleRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Drag to resize input area
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingInput || !inputContainerRef.current) return;
      
      const containerRect = inputContainerRef.current.getBoundingClientRect();
      const newHeight = containerRect.bottom - e.clientY;
      const clampedHeight = Math.max(100, Math.min(400, newHeight));
      setInputHeight(clampedHeight);
    };

    const handleMouseUp = () => {
      setIsResizingInput(false);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = 'auto';
    };

    if (isResizingInput) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'ns-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizingInput, setInputHeight, setIsResizingInput]);

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizingInput(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Don't submit if resizing, busy, or no input
    if (isResizingInput || !input.trim() || isBusy || !submitPrompt) return;
    
    submitPrompt(input.trim());
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const formatTime = (timestamp: number) => {
    return new Date(timestamp).toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  const formatResponseTime = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const getRoleIcon = (role: string) => {
    switch (role) {
      case 'user':
        return <User size={20} />;
      case 'assistant':
        return <Bot size={20} />;
      case 'tool':
      case 'tool_result':
        return <Wrench size={20} />;
      case 'system':
        return <AlertCircle size={20} />;
      default:
        return null;
    }
  };

  const handleResize = (delta: number) => {
    const newHeight = Math.max(100, Math.min(400, inputHeight + delta));
    setInputHeight(newHeight);
  };

  return (
    <div className={styles.chatView}>
      {/* Chat Header with New Chat Button */}
      <div className={styles.chatHeader}>
        <div className={styles.chatHeaderInfo}>
          <span className={styles.chatTitle}>
            {currentChatId 
              ? chatSessions.find(c => c.id === currentChatId)?.name || 'Chat'
              : 'New Chat'
            }
          </span>
          <span className={styles.chatMessageCount}>
            {messages.length} messages
          </span>
        </div>
        <button
          className={styles.newChatButton}
          onClick={() => {
            clearMessages();
            createNewChat();
          }}
          title="Start a new chat"
        >
          <Plus size={18} />
          <span>New Chat</span>
        </button>
      </div>
      
      <div className={styles.messagesContainer}>
        {messages.length === 0 ? (
          <div className={styles.welcome}>
            <div className={styles.welcomeIcon}>
              <Sparkles size={64} />
            </div>
            <h1>OpenHarness</h1>
            <p className={styles.welcomeSubtitle}>Your AI-powered coding assistant</p>
            <div className={styles.suggestionCards}>
              <div className={styles.suggestionCard}>
                <Brain size={20} />
                <div>
                  <h3>Code Review</h3>
                  <p>Ask me to review your code for bugs and improvements</p>
                </div>
              </div>
              <div className={styles.suggestionCard}>
                <Wrench size={20} />
                <div>
                  <h3>Debug Help</h3>
                  <p>Stuck on a bug? I can help you find and fix it</p>
                </div>
              </div>
              <div className={styles.suggestionCard}>
                <Brain size={20} />
                <div>
                  <h3>File Analysis</h3>
                  <p>Upload files for me to analyze and explain</p>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <>
            {messages.map((message) => {
              const isExpanded = expandedMessages.has(message.id);
              const isLongContent = message.content.length > 500;
              
              return (
                <div 
                  key={message.id} 
                  className={`${styles.message} ${styles[message.role]}`}
                >
                  <div className={styles.messageHeader}>
                    <div className={`${styles.roleIcon} ${styles[message.role]}`}>
                      {getRoleIcon(message.role)}
                    </div>
                    <div className={styles.messageInfo}>
                      <span className={styles.roleName}>
                        {message.role === 'assistant' ? 'OpenHarness' : 
                         message.role === 'user' ? 'You' :
                         message.tool_name ? message.tool_name :
                         message.role}
                      </span>
                      <span className={styles.timestamp}>
                        {formatTime(message.timestamp)}
                      </span>
                    </div>
                    {/* Response time and token usage for assistant messages */}
                    {message.role === 'assistant' && (message.responseTime || message.tokenUsage) && (
                      <div className={styles.messageStats}>
                        {message.responseTime && (
                          <span className={styles.statItem} title="Response time">
                            ⏱ {formatResponseTime(message.responseTime)}
                          </span>
                        )}
                        {message.tokenUsage && (
                          <span className={styles.statItem} title="Token usage">
                            📊 {message.tokenUsage.total} tokens
                          </span>
                        )}
                      </div>
                    )}
                    {isLongContent && (
                      <button 
                        className={styles.expandButton}
                        onClick={() => toggleMessageExpand(message.id)}
                      >
                        {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        {isExpanded ? 'Collapse' : 'Expand'}
                      </button>
                    )}
                  </div>
                  <div 
                    className={`${styles.messageContent} ${isExpanded ? styles.expanded : ''} ${isLongContent && !isExpanded ? styles.truncated : ''}`}
                    style={isLongContent && !isExpanded ? { maxHeight: '300px' } : {}}
                  >
                    {message.tool_input && (
                      <pre className={styles.toolInput}>
                        {JSON.stringify(message.tool_input, null, 2)}
                      </pre>
                    )}
                    <div className={styles.text}>{message.content}</div>
                    {message.is_error && (
                      <div className={styles.error}>
                        <AlertCircle size={16} />
                        <span>Error occurred</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            {isBusy && (
              <div className={`${styles.message} ${styles.assistant} ${styles.busy}`}>
                <div className={styles.messageHeader}>
                  <div className={`${styles.roleIcon} ${styles.assistant}`}>
                    <Bot size={20} />
                  </div>
                  <span className={styles.roleName}>OpenHarness</span>
                </div>
                <div className={styles.thinkingIndicator}>
                  <div className={styles.thinkingDot} />
                  <div className={styles.thinkingDot} />
                  <div className={styles.thinkingDot} />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      <div className={styles.inputSection} ref={inputContainerRef}>
        {/* File Upload Area */}
        {showFileUpload && (
          <div className={styles.fileUploadWrapper}>
            <FileUpload />
          </div>
        )}

        {/* Attached Files Indicator */}
        {uploadedFiles.length > 0 && !showFileUpload && (
          <div className={styles.attachedFiles}>
            <span className={styles.attachedCount}>
              📎 {uploadedFiles.length} file(s) attached
            </span>
            <button 
              className={styles.showUploadButton}
              onClick={() => {}}
            >
              Manage
            </button>
          </div>
        )}

        {/* Drag Handle */}
        <div 
          ref={resizeHandleRef}
          className={`${styles.resizeHandle} ${isResizingInput ? styles.resizing : ''}`}
          onMouseDown={handleResizeStart}
        >
          <div className={styles.resizeDots}>
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>

        <form className={styles.inputForm} onSubmit={handleSubmit}>
          <div className={styles.inputTopBar}>
            <ModelSelector />
            <div className={styles.inputActions}>
              <button
                type="button"
                className={`${styles.actionButton} ${showFileUpload ? styles.active : ''}`}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setShowFileUpload(!showFileUpload);
                }}
                title="Attach files"
              >
                <Paperclip size={18} />
              </button>
            </div>
          </div>
          
          <div className={styles.inputWrapper} style={{ height: `${inputHeight}px` }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask OpenHarness anything..."
              disabled={isBusy}
              className={styles.textarea}
            />
            <div className={styles.inputControls}>
              <div className={styles.resizeButtons}>
                <button
                  type="button"
                  className={styles.resizeButton}
                  onClick={() => handleResize(-40)}
                  title="Decrease height"
                >
                  <Minimize2 size={14} />
                </button>
                <button
                  type="button"
                  className={styles.resizeButton}
                  onClick={() => handleResize(40)}
                  title="Increase height"
                >
                  <Maximize2 size={14} />
                </button>
              </div>
              <button 
                type="submit" 
                disabled={!input.trim() || isBusy}
                className={styles.sendButton}
              >
                <Send size={20} />
              </button>
            </div>
          </div>
          <div className={styles.inputHints}>
            <span>Press <kbd>Enter</kbd> to send</span>
            <span><kbd>Shift+Enter</kbd> for new line</span>
            <span>Drag handle to resize</span>
          </div>
        </form>
      </div>
    </div>
  );
}
