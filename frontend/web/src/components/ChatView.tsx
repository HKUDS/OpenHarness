import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Send, Bot, User, AlertCircle, Wrench, Paperclip, Maximize2, Minimize2, ChevronDown, ChevronUp, Sparkles, Brain, Plus, Copy, Check, Clock } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAppStore } from '../store/useAppStore';
import { FileUpload } from './FileUpload';
import { ModelSelector } from './ModelSelector';
import { SlashCommandAutocomplete } from './SlashCommandAutocomplete';
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
  
  const [input, setInput] = useState('');
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [messagePositions, setMessagePositions] = useState<Map<string, number>>(new Map());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const timelineTrackRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const inputContainerRef = useRef<HTMLDivElement>(null);
  const resizeHandleRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Calculate actual message positions for dynamic timeline
  const calculateMessagePositions = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    
    const scrollHeight = container.scrollHeight;
    const newPositions = new Map<string, number>();
    
    messageRefs.current.forEach((element, messageId) => {
      if (!element) return;
      // Calculate position relative to scroll container
      const offsetTop = element.offsetTop;
      // Position as percentage of total scroll height
      const position = scrollHeight > 0 ? offsetTop / scrollHeight : 0;
      newPositions.set(messageId, position);
    });
    
    setMessagePositions(newPositions);
  }, []);

  // Recalculate positions when messages change, expand/collapse, or container resizes
  useEffect(() => {
    // Small delay to allow DOM to update
    const timer = setTimeout(() => {
      calculateMessagePositions();
    }, 100);
    return () => clearTimeout(timer);
  }, [messages, expandedMessages, calculateMessagePositions]);

  // Update positions on scroll to keep timeline markers in sync
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    
    const handleScroll = () => {
      // Recalculate positions on scroll to handle dynamic content
      calculateMessagePositions();
    };
    
    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, [calculateMessagePositions]);

  // Update positions on resize
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    
    const resizeObserver = new ResizeObserver(() => {
      calculateMessagePositions();
    });
    
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, [calculateMessagePositions]);

  // Track scroll position for timeline and sync timeline scroll
  useEffect(() => {
    const container = messagesContainerRef.current;
    const timelineTrack = timelineTrackRef.current;
    const viewportIndicator = timelineTrack?.querySelector(`.${styles.timelineViewport}`) as HTMLElement;
    if (!container || !timelineTrack) return;

    const syncTimelineHeight = () => {
      // Match timeline track height to message container scroll height
      timelineTrack.style.height = `${container.scrollHeight}px`;
    };

    const handleScroll = () => {
      const scrollTop = container.scrollTop;
      const scrollHeight = container.scrollHeight - container.clientHeight;
      const progress = scrollHeight > 0 ? scrollTop / scrollHeight : 0;
      
      // Update viewport indicator position
      if (viewportIndicator) {
        const trackHeight = timelineTrack.clientHeight;
        const viewportHeight = Math.max(20, (container.clientHeight / container.scrollHeight) * trackHeight);
        const viewportTop = progress * (trackHeight - viewportHeight);
        viewportIndicator.style.height = `${viewportHeight}px`;
        viewportIndicator.style.top = `${viewportTop}px`;
      }
    };

    // Initial sync
    syncTimelineHeight();
    handleScroll();
    
    // Sync on scroll
    container.addEventListener('scroll', handleScroll);
    
    // Sync on resize
    const resizeObserver = new ResizeObserver(() => {
      syncTimelineHeight();
      handleScroll();
    });
    resizeObserver.observe(container);
    
    return () => {
      container.removeEventListener('scroll', handleScroll);
      resizeObserver.disconnect();
    };
  }, [messages, styles.timelineViewport]);

  // Clear copied state after 2 seconds
  useEffect(() => {
    if (copiedMessageId) {
      const timer = setTimeout(() => setCopiedMessageId(null), 2000);
      return () => clearTimeout(timer);
    }
  }, [copiedMessageId]);

  const handleCopyMessage = async (content: string, messageId: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);
    } catch (err) {
      console.error('Failed to copy message:', err);
    }
  };

  const handleTimelineClick = (messageId: string) => {
    const messageElement = messageRefs.current.get(messageId);
    if (messageElement) {
      messageElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  // Generate timeline markers based on actual message scroll positions
  const getTimelineMarkers = () => {
    if (messages.length === 0) return [];
    
    const markers: { id: string; position: number; label: string; timestamp: number }[] = [];
    
    // Select messages to show as markers (first, last, and evenly distributed in between)
    const numMarkers = Math.min(8, messages.length);
    
    // Get unique message indices for markers
    const markerIndices: number[] = [];
    if (numMarkers === 1) {
      markerIndices.push(0);
    } else {
      for (let i = 0; i < numMarkers; i++) {
        const index = Math.floor((i / (numMarkers - 1)) * (messages.length - 1));
        if (!markerIndices.includes(index)) {
          markerIndices.push(index);
        }
      }
    }
    
    // Create markers using actual positions from messagePositions state
    markerIndices.forEach(index => {
      const message = messages[index];
      if (!message?.id) return;
      
      // Use actual calculated position if available, otherwise estimate
      const actualPosition = messagePositions.get(message.id);
      let position = actualPosition ?? (index / (messages.length - 1 || 1));
      
      // Clamp position to valid range (0-1) to prevent markers from going out of bounds
      position = Math.max(0, Math.min(1, position));
      
      markers.push({
        id: message.id,
        position,
        label: formatTime(message.timestamp),
        timestamp: message.timestamp,
      });
    });
    
    return markers;
  };

  const formatTimelineLabel = (timestamp: number) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - timestamp;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    
    if (diffMins < 1) return 'Now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

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
      
      <div className={styles.messagesContainer} ref={messagesContainerRef}>
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
            <div className={styles.messagesContent}>
              {messages.filter(msg => msg?.id).map((message) => {
                const isExpanded = expandedMessages.has(message.id);
                const isLongContent = message.content.length > 500;
              
              return (
                <div 
                  key={message.id}
                  ref={(el) => { if (el) messageRefs.current.set(message.id, el); }}
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
                         message.role === 'system' ? 'System' :
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
                    {/* Copy button */}
                    <button
                      className={styles.copyButton}
                      onClick={() => handleCopyMessage(message.content, message.id)}
                      title="Copy message"
                    >
                      {copiedMessageId === message.id ? (
                        <Check size={16} />
                      ) : (
                        <Copy size={16} />
                      )}
                    </button>
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
                    <div className={styles.text}>
                      {message.role === 'assistant' || message.role === 'user' ? (
                        <ReactMarkdown 
                          remarkPlugins={[remarkGfm]}
                          components={{
                            code({ className, children }: React.HTMLAttributes<HTMLElement>) {
                              const match = /language-(\w+)/.exec(className || '');
                              const isInline = !match;
                              return !isInline ? (
                                <pre className={`${className} ${styles.codeBlock}`}>
                                  <code>{String(children).replace(/\n$/, '')}</code>
                                </pre>
                              ) : (
                                <code className={styles.inlineCode}>{String(children)}</code>
                              );
                            },
                            pre({ children }: React.HTMLAttributes<HTMLPreElement>) {
                              return <pre className={styles.markdownPre}>{children}</pre>;
                            },
                            blockquote({ children }: React.HTMLAttributes<HTMLQuoteElement>) {
                              return <blockquote className={styles.blockquote}>{children}</blockquote>;
                            },
                            ul({ children }: React.HTMLAttributes<HTMLUListElement>) {
                              return <ul className={styles.unorderedList}>{children}</ul>;
                            },
                            ol({ children }: React.HTMLAttributes<HTMLOListElement>) {
                              return <ol className={styles.orderedList}>{children}</ol>;
                            },
                            li({ children }: React.HTMLAttributes<HTMLLIElement>) {
                              return <li className={styles.listItem}>{children}</li>;
                            },
                            h1({ children }: React.HTMLAttributes<HTMLHeadingElement>) {
                              return <h1 className={styles.heading1}>{children}</h1>;
                            },
                            h2({ children }: React.HTMLAttributes<HTMLHeadingElement>) {
                              return <h2 className={styles.heading2}>{children}</h2>;
                            },
                            h3({ children }: React.HTMLAttributes<HTMLHeadingElement>) {
                              return <h3 className={styles.heading3}>{children}</h3>;
                            },
                            p({ children }: React.HTMLAttributes<HTMLParagraphElement>) {
                              return <p className={styles.paragraph}>{children}</p>;
                            },
                            strong({ children }: React.HTMLAttributes<HTMLElement>) {
                              return <strong className={styles.strong}>{children}</strong>;
                            },
                            em({ children }: React.HTMLAttributes<HTMLElement>) {
                              return <em className={styles.em}>{children}</em>;
                            },
                            table({ children }: React.HTMLAttributes<HTMLTableElement>) {
                              return <div className={styles.tableWrapper}><table className={styles.table}>{children}</table></div>;
                            },
                            th({ children }: React.HTMLAttributes<HTMLTableCellElement>) {
                              return <th className={styles.tableHeader}>{children}</th>;
                            },
                            td({ children }: React.HTMLAttributes<HTMLTableCellElement>) {
                              return <td className={styles.tableCell}>{children}</td>;
                            },
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      ) : (
                        <div className={styles.plainText}>{message.content}</div>
                      )}
                    </div>
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
          </div>
          {/* Timeline Panel */}
          <div className={styles.timelineBar}>
              <div className={styles.timelineHeader}>
                <Clock size={14} />
                <span>Timeline</span>
              </div>
              <div className={styles.timelineTrack} ref={timelineTrackRef}>
                {getTimelineMarkers().map((marker) => (
                  <div
                    key={marker.id}
                    className={styles.timelineMarker}
                    style={{ top: `${marker.position * 100}%` }}
                    onClick={() => handleTimelineClick(marker.id)}
                    title={`Jump to message at ${marker.label}`}
                  >
                    <div className={styles.markerDot} />
                    <span className={styles.timelineLabel}>
                      {formatTimelineLabel(marker.timestamp)}
                    </span>
                  </div>
                ))}
                {/* Viewport indicator */}
                <div className={styles.timelineViewport} />
              </div>
            </div>
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
            {/* Slash Command Autocomplete Dropdown */}
            <SlashCommandAutocomplete
              input={input}
              setInput={setInput}
              onSubmit={submitPrompt || (() => {})}
              inputRef={inputRef}
            />
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask OpenHarness anything... or type / for commands"
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
            <span>Type <kbd>/</kbd> for commands</span>
            <span><kbd>Enter</kbd> to send</span>
            <span><kbd>Shift+Enter</kbd> new line</span>
          </div>
        </form>
      </div>
    </div>
  );
}
