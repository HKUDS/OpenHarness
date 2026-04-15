import React, { useRef, useEffect, useLayoutEffect, useState, useCallback } from 'react';
import { Send, Bot, User, AlertCircle, Wrench, Paperclip, Maximize2, Minimize2, ChevronDown, ChevronUp, Sparkles, Brain, Plus, Copy, Check, Clock, X, ArrowUpToLine, ArrowDownToLine } from 'lucide-react';
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
    clearMessages,
    timelineWidth,
    setTimelineWidth,
    isResizingTimeline,
    setIsResizingTimeline,
    scrollToMessageId,
    setScrollToMessageId
  } = useAppStore();
  
  const [input, setInput] = useState('');
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [messagePositions, setMessagePositions] = useState<Map<string, number>>(new Map());
  const [pastedImages, setPastedImages] = useState<File[]>([]);
  const [pastedImagePreview, setPastedImagePreview] = useState<string[]>([]);
  const [userHasManuallyScrolled, setUserHasManuallyScrolled] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContentRef = useRef<HTMLDivElement>(null);
  const timelineTrackRef = useRef<HTMLDivElement>(null);
  const timelineContentRef = useRef<HTMLDivElement>(null);
  const timelineBarRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const inputContainerRef = useRef<HTMLDivElement>(null);
  const resizeHandleRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const isJumpingRef = useRef(false);
  const prevMessageCountRef = useRef(0);

  const scrollToBottom = (instant = false) => {
    const container = messagesContentRef.current;
    const endElement = messagesEndRef.current;
    if (!container || !endElement) return;
    
    // Use instant scroll to avoid animation conflicts
    endElement.scrollIntoView({ behavior: instant ? 'auto' : 'smooth', block: 'end' });
  };

  // Scroll to a specific message when navigating from search results
  useEffect(() => {
    if (!scrollToMessageId) return;
    
    // Use requestAnimationFrame to ensure DOM is ready after chat switch
    const timer = setTimeout(() => {
      const messageElement = messageRefs.current.get(scrollToMessageId);
      const container = messagesContentRef.current;
      
      if (messageElement && container) {
        // Calculate position relative to the scrollable container
        const elementOffset = messageElement.offsetTop - container.offsetTop;
        // Scroll to show the element centered in the viewport
        const scrollTarget = elementOffset - (container.clientHeight / 2) + (messageElement.offsetHeight / 2);
        
        // Set flag to prevent auto-scroll interference
        isJumpingRef.current = true;
        setUserHasManuallyScrolled(true);
        
        container.scrollTo({ top: Math.max(0, scrollTarget), behavior: 'smooth' });
        
        // Highlight the message briefly
        messageElement.classList.add(styles.highlighted);
        setTimeout(() => {
          messageElement.classList.remove(styles.highlighted);
        }, 2000);
        
        // Reset flag after scroll completes
        setTimeout(() => {
          isJumpingRef.current = false;
        }, 500);
      }
      
      // Clear the scroll target
      setScrollToMessageId(null);
    }, 100);
    
    return () => clearTimeout(timer);
  }, [scrollToMessageId, setScrollToMessageId]);

  // Only auto-scroll to bottom when new messages are added AND user was already at bottom
  useEffect(() => {
    const container = messagesContentRef.current;
    if (!container) return;
    
    const newMessageCount = messages.length;
    const hasNewMessages = newMessageCount > prevMessageCountRef.current;
    prevMessageCountRef.current = newMessageCount;
    
    // Don't auto-scroll if user is actively jumping
    if (isJumpingRef.current) return;
    
    // Use requestAnimationFrame to ensure DOM is fully updated
    requestAnimationFrame(() => {
      if (!container) return;
      
      // Check if user is near bottom (within 150px) after DOM update
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150;
      
      // Auto-scroll only if: new messages arrived AND (user is near bottom OR never manually scrolled)
      if (hasNewMessages && (isNearBottom || !userHasManuallyScrolled)) {
        scrollToBottom(true); // Use instant scroll for new messages
      }
    });
  }, [messages, userHasManuallyScrolled]);

  // Calculate actual message positions for dynamic timeline
  const calculateMessagePositions = useCallback(() => {
    const container = messagesContentRef.current;
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

  // Cleanup message refs when messages are removed
  useEffect(() => {
    const currentMessageIds = new Set(messages.map(m => m.id).filter(Boolean));
    const refsToRemove: string[] = [];
    
    messageRefs.current.forEach((_, messageId) => {
      if (!currentMessageIds.has(messageId)) {
        refsToRemove.push(messageId);
      }
    });
    
    refsToRemove.forEach(id => messageRefs.current.delete(id));
  }, [messages]);

  // Update positions on scroll to keep timeline markers in sync
  useEffect(() => {
    const container = messagesContentRef.current;
    if (!container) return;
    
    const handleScroll = () => {
      // Recalculate positions on scroll to handle dynamic content
      calculateMessagePositions();
      
      // Track manual scrolling (but not during jump operations)
      if (!isJumpingRef.current) {
        setUserHasManuallyScrolled(true);
        
        // Reset manual scroll flag when user scrolls back to bottom
        const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50;
        if (isAtBottom) {
          setUserHasManuallyScrolled(false);
        }
      }
    };
    
    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, [calculateMessagePositions]);

  // Update positions on resize
  useEffect(() => {
    const container = messagesContentRef.current;
    if (!container) return;
    
    const resizeObserver = new ResizeObserver(() => {
      calculateMessagePositions();
    });
    
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, [calculateMessagePositions]);

  // Track scroll position for timeline and sync timeline scroll
  // Sync timeline scroll with messages and update viewport indicator
  // Use useLayoutEffect to ensure sync happens after DOM updates
  useLayoutEffect(() => {
    const container = messagesContentRef.current;
    const timelineTrack = timelineTrackRef.current;
    const timelineContent = timelineContentRef.current;
    const viewportIndicator = timelineContent?.querySelector(`.${styles.timelineViewport}`) as HTMLElement;
    if (!container || !timelineTrack || !timelineContent) return;

    let isSyncingFromTimeline = false;
    let isSyncingFromMessages = false;

    // Set timeline content height to match messages scroll height
    // This ensures markers are correctly positioned relative to scroll
    const syncTimelineHeight = () => {
      const messagesScrollHeight = container.scrollHeight;
      const messagesClientHeight = container.clientHeight;
      
      // Calculate the scale factor between timeline track and messages
      // The timeline content should be tall enough to accommodate all markers
      // with proper spacing that matches the messages scroll
      const timelineTrackHeight = timelineTrack.clientHeight;
      
      // Set timeline content height proportional to messages scroll height
      // This ensures the scroll ratio is 1:1
      if (messagesClientHeight > 0) {
        const scrollRatio = messagesScrollHeight / messagesClientHeight;
        const timelineContentHeight = timelineTrackHeight * scrollRatio;
        timelineContent.style.height = `${Math.max(timelineContentHeight, timelineTrackHeight)}px`;
      }
    };

    const handleMessagesScroll = () => {
      if (isSyncingFromTimeline) return;
      // Skip sync during jump operations to prevent interference
      if (isJumpingRef.current) return;
      isSyncingFromMessages = true;
      
      const scrollTop = container.scrollTop;
      const maxScroll = container.scrollHeight - container.clientHeight;
      const progress = maxScroll > 0 ? scrollTop / maxScroll : 0;
      
      // Sync timeline scroll position based on progress
      const timelineMaxScroll = timelineTrack.scrollHeight - timelineTrack.clientHeight;
      if (timelineMaxScroll > 0) {
        timelineTrack.scrollTop = progress * timelineMaxScroll;
      }
      
      // Update viewport indicator position (relative to timeline content)
      if (viewportIndicator) {
        const contentHeight = timelineContent.clientHeight;
        const viewportHeight = Math.max(20, (container.clientHeight / container.scrollHeight) * contentHeight);
        const viewportTop = progress * (contentHeight - viewportHeight);
        viewportIndicator.style.height = `${viewportHeight}px`;
        viewportIndicator.style.top = `${viewportTop}px`;
      }
      
      isSyncingFromMessages = false;
    };

    const handleTimelineScroll = () => {
      if (isSyncingFromMessages) return;
      // Skip sync during jump operations to prevent interference
      if (isJumpingRef.current) return;
      isSyncingFromTimeline = true;
      
      const scrollTop = timelineTrack.scrollTop;
      const maxScroll = timelineTrack.scrollHeight - timelineTrack.clientHeight;
      const progress = maxScroll > 0 ? scrollTop / maxScroll : 0;
      
      // Sync messages scroll position based on progress
      const messagesMaxScroll = container.scrollHeight - container.clientHeight;
      if (messagesMaxScroll > 0) {
        container.scrollTop = progress * messagesMaxScroll;
      }
      
      isSyncingFromTimeline = false;
    };

    // Initial sync - defer to allow DOM to update
    requestAnimationFrame(() => {
      syncTimelineHeight();
      // Wait for height to be applied before syncing scroll
      requestAnimationFrame(() => {
        handleMessagesScroll();
      });
    });
    
    // Sync on scroll
    container.addEventListener('scroll', handleMessagesScroll, { passive: true });
    timelineTrack.addEventListener('scroll', handleTimelineScroll, { passive: true });
    
    // Sync on resize
    const resizeObserver = new ResizeObserver(() => {
      syncTimelineHeight();
      // Defer scroll sync to allow height update to apply
      requestAnimationFrame(() => {
        handleMessagesScroll();
      });
    });
    resizeObserver.observe(container);
    
    return () => {
      container.removeEventListener('scroll', handleMessagesScroll);
      timelineTrack.removeEventListener('scroll', handleTimelineScroll);
      resizeObserver.disconnect();
    };
  }, [messages, styles.timelineViewport, styles.timelineContent]);

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
    if (messageElement && messagesContentRef.current) {
      // Calculate position relative to the scrollable container
      const container = messagesContentRef.current;
      const elementOffset = messageElement.offsetTop - container.offsetTop;
      // Scroll to show the element centered in the viewport
      const scrollTarget = elementOffset - (container.clientHeight / 2) + (messageElement.offsetHeight / 2);
      
      // Set flag to prevent auto-scroll interference
      isJumpingRef.current = true;
      setUserHasManuallyScrolled(true);
      
      container.scrollTo({ top: scrollTarget, behavior: 'auto' });
      
      // Reset flag after scroll completes
      setTimeout(() => {
        isJumpingRef.current = false;
      }, 100);
    }
  };
  
  // Quick navigation handlers
  const handleJumpToFirst = () => {
    if (messages.length === 0) {
      console.warn('[ChatView] No messages to jump to');
      return;
    }
    if (!messagesContentRef.current) {
      console.error('[ChatView] Messages container ref is null');
      return;
    }
    
    console.log('[ChatView] Jump to first message');
    const container = messagesContentRef.current;
    
    // Set flag to prevent auto-scroll interference
    isJumpingRef.current = true;
    setUserHasManuallyScrolled(true);
    
    // Use requestAnimationFrame to ensure DOM is ready for scrolling
    requestAnimationFrame(() => {
      try {
        // Force a reflow to ensure scrollHeight is accurate
        void container.offsetHeight;
        
        // Scroll to top instantly for reliable navigation
        if (typeof container.scrollTo === 'function') {
          container.scrollTo({ top: 0, behavior: 'auto' });
        } else {
          // Fallback for browsers that don't support scrollTo
          container.scrollTop = 0;
        }
        
        console.log('[ChatView] Successfully jumped to first message');
        
        // Reset flag after scroll completes
        setTimeout(() => {
          isJumpingRef.current = false;
        }, 100);
      } catch (err) {
        console.error('[ChatView] Error jumping to first message:', err);
        isJumpingRef.current = false;
      }
    });
  };
  
  const handleJumpToLast = () => {
    if (messages.length === 0) {
      console.warn('[ChatView] No messages to jump to');
      return;
    }
    if (!messagesContentRef.current) {
      console.error('[ChatView] Messages container ref is null');
      return;
    }
    
    console.log('[ChatView] Jump to last message');
    const container = messagesContentRef.current;
    
    // Set flag to prevent auto-scroll interference
    isJumpingRef.current = true;
    setUserHasManuallyScrolled(true);
    
    // Use requestAnimationFrame to ensure DOM is ready for scrolling
    requestAnimationFrame(() => {
      try {
        // Force a reflow to ensure scrollHeight is accurate
        void container.offsetHeight;
        
        // Calculate scroll target (bottom of container)
        const scrollTarget = container.scrollHeight - container.clientHeight;
        
        console.log('[ChatView] Scroll target:', scrollTarget, 'Container height:', container.clientHeight, 'Scroll height:', container.scrollHeight);
        
        // Scroll to bottom instantly for reliable navigation
        if (typeof container.scrollTo === 'function') {
          container.scrollTo({ top: scrollTarget, behavior: 'auto' });
        } else {
          // Fallback for browsers that don't support scrollTo
          container.scrollTop = scrollTarget;
        }
        
        console.log('[ChatView] Successfully jumped to last message');
        
        // Reset flag after scroll completes
        setTimeout(() => {
          isJumpingRef.current = false;
        }, 100);
      } catch (err) {
        console.error('[ChatView] Error jumping to last message:', err);
        isJumpingRef.current = false;
      }
    });
  };

  // Generate timeline markers - show ALL messages for easy navigation
  const getTimelineMarkers = () => {
    if (messages.length === 0) return [];
    
    const markers: { id: string; position: number; label: string; timestamp: number; role: string; index: number }[] = [];
    
    // Show all messages for navigation purposes
    messages.forEach((message, index) => {
      if (!message?.id) return;
      
      // Use actual calculated position if available, otherwise estimate
      const actualPosition = messagePositions.get(message.id);
      let position = actualPosition ?? (index / (messages.length - 1 || 1));
      
      // Clamp position to valid range (0-1) to prevent markers from going out of bounds
      position = Math.max(0, Math.min(1, position));
      
      markers.push({
        id: message.id,
        position,
        label: formatTimelineLabel(message.timestamp),
        timestamp: message.timestamp,
        role: message.role,
        index,
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

  // Drag to resize input area with requestAnimationFrame for smooth performance
  useEffect(() => {
    let rafId: number | null = null;
    let lastHeight = inputHeight;
    
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingInput || !inputContainerRef.current) return;
      
      // Cancel pending frame if exists
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      
      // Schedule update on next frame
      rafId = requestAnimationFrame(() => {
        const containerRect = inputContainerRef.current!.getBoundingClientRect();
        const newHeight = containerRect.bottom - e.clientY;
        const clampedHeight = Math.max(100, Math.min(400, newHeight));
        
        // Only update if height actually changed
        if (clampedHeight !== lastHeight) {
          lastHeight = clampedHeight;
          setInputHeight(clampedHeight);
        }
        rafId = null;
      });
    };

    const handleMouseUp = () => {
      setIsResizingInput(false);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = 'auto';
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
    };

    if (isResizingInput) {
      document.addEventListener('mousemove', handleMouseMove, { passive: true });
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'ns-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [isResizingInput, setInputHeight, setIsResizingInput]);

  // Drag to resize timeline with requestAnimationFrame for smooth performance
  useEffect(() => {
    let rafId: number | null = null;
    let lastWidth = timelineWidth;
    
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingTimeline) return;
      
      // Cancel pending frame if exists
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      
      // Schedule update on next frame
      rafId = requestAnimationFrame(() => {
        const windowWidth = window.innerWidth;
        const newWidth = windowWidth - e.clientX;
        const clampedWidth = Math.max(40, Math.min(150, newWidth));
        
        // Only update if width actually changed
        if (clampedWidth !== lastWidth) {
          lastWidth = clampedWidth;
          setTimelineWidth(clampedWidth);
        }
        rafId = null;
      });
    };

    const handleMouseUp = () => {
      setIsResizingTimeline(false);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = 'auto';
      // Re-enable transitions
      if (timelineBarRef.current) {
        timelineBarRef.current.style.transition = '';
      }
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
    };

    if (isResizingTimeline) {
      // Disable transitions during drag
      if (timelineBarRef.current) {
        timelineBarRef.current.style.transition = 'none';
      }
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
  }, [isResizingTimeline, setTimelineWidth, setIsResizingTimeline]);

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizingInput(true);
  };

  const handleTimelineResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizingTimeline(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Don't submit if resizing, busy, or no input
    if (isResizingInput || !input.trim() || isBusy || !submitPrompt) return;
    
    // Submit with files (uploaded + pasted)
    submitPrompt(input.trim(), [...uploadedFiles, ...pastedImages.map(file => ({
      id: `pasted-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      name: file.name || `image-${Date.now()}.png`,
      size: file.size,
      type: file.type,
      status: 'uploaded' as const,
      file: file,
    }))]);
    setInput('');
    setPastedImages([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const items = e.clipboardData.items;
    const imageFiles: File[] = [];
    
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          imageFiles.push(file);
          // Create preview URL
          const reader = new FileReader();
          reader.onload = (event) => {
            if (event.target?.result) {
              setPastedImagePreview(prev => [...prev, event.target!.result as string]);
            }
          };
          reader.readAsDataURL(file);
        }
      }
    }
    
    if (imageFiles.length > 0) {
      e.preventDefault();
      setPastedImages(prev => [...prev, ...imageFiles]);
    }
  }, []);
  
  const handleRemovePastedImage = (index: number) => {
    setPastedImages(prev => prev.filter((_, i) => i !== index));
    setPastedImagePreview(prev => prev.filter((_, i) => i !== index));
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
        return <Bot size={20} />; // Same as assistant for consistent styling
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
            <div className={styles.messagesContent} ref={messagesContentRef}>
              {messages.filter(msg => msg?.id).map((message) => {
                const isExpanded = expandedMessages.has(message.id);
                const isLongContent = message.content.length > 500;
                const isUser = message.role === 'user';
              
              return (
                <div 
                  key={message.id}
                  ref={(el) => { 
                    if (el) {
                      messageRefs.current.set(message.id, el);
                    } else {
                      messageRefs.current.delete(message.id);
                    }
                  }}
                  className={`${styles.message} ${styles[message.role]}`}
                >
                  {/* User messages: right-aligned container */}
                  {isUser ? (
                    <div className={styles.userMessageWrapper}>
                      <div className={styles.userMessageBubble}>
                        <div className={styles.messageHeader}>
                          <div className={`${styles.roleIcon} ${styles[message.role]}`}>
                            {getRoleIcon(message.role)}
                          </div>
                          <div className={styles.messageInfo}>
                            <span className={styles.roleName}>You</span>
                            <span className={styles.timestamp}>
                              {formatTime(message.timestamp)}
                            </span>
                          </div>
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
                        </div>
                        <div 
                          className={`${styles.messageContent} ${isExpanded ? styles.expanded : ''}`}
                        >
                          <div className={styles.text}>
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
                                p({ children }: React.HTMLAttributes<HTMLParagraphElement>) {
                                  return <p className={styles.paragraph}>{children}</p>;
                                },
                              }}
                            >
                              {message.content}
                            </ReactMarkdown>
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    /* Non-user messages: standard left-aligned layout */
                    <>
                  <div className={styles.messageHeader}>
                    <div className={`${styles.roleIcon} ${styles[message.role]}`}>
                      {getRoleIcon(message.role)}
                    </div>
                    <div className={styles.messageInfo}>
                      <span className={styles.roleName}>
                        {message.role === 'assistant' ? 'OpenHarness' : 
                         message.role === 'system' ? 'System' :
                         message.tool_name ? message.tool_name :
                         message.role}
                      </span>
                      <span className={styles.timestamp}>
                        {formatTime(message.timestamp)}
                      </span>
                    </div>
                    {/* Response time and token usage for assistant/tool messages */}
                    {(message.role === 'assistant' || message.role === 'tool' || message.role === 'tool_result') && (message.responseTime || message.tokenUsage) && (
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
                      <div className={styles.error} role="alert">
                        <AlertCircle size={16} />
                        <div className={styles.errorContent}>
                          <span className={styles.errorTitle}>Error occurred</span>
                          {message.content && message.content !== 'Error occurred' && (
                            <div className={styles.errorDetails}>{message.content}</div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                    </>
                  )}
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
          <div className={styles.timelineBar} ref={timelineBarRef} style={{ width: `${timelineWidth}px`, minWidth: `${timelineWidth}px` }}>
              {/* Timeline Resize Handle */}
              <div 
                className={`${styles.timelineDragHandle} ${isResizingTimeline ? styles.resizing : ''}`}
                onMouseDown={handleTimelineResizeStart}
              />
              <div className={styles.timelineHeader}>
                <Clock size={14} />
                <span>Timeline</span>
              </div>
              
              {/* Quick Navigation Buttons */}
              <div className={styles.timelineNavButtons}>
                <button 
                  className={styles.timelineNavBtn}
                  onClick={handleJumpToFirst}
                  title="Jump to first message"
                  disabled={messages.length === 0}
                >
                  <ArrowUpToLine size={14} />
                </button>
                <button 
                  className={styles.timelineNavBtn}
                  onClick={handleJumpToLast}
                  title="Jump to last message"
                  disabled={messages.length === 0}
                >
                  <ArrowDownToLine size={14} />
                </button>
              </div>
              
              <div className={styles.timelineTrack} ref={timelineTrackRef}>
                <div className={styles.timelineContent} ref={timelineContentRef}>
                  {/* Message count indicator */}
                  <div className={styles.timelineInfo}>
                    {messages.length} messages
                  </div>
                  {/* Timeline markers */}
                  {getTimelineMarkers().map((marker) => (
                    <div
                      key={marker.id}
                      className={`${styles.timelineMarker} ${styles[`marker-${marker.role}`] || ''}`}
                      style={{ top: `${marker.position * 100}%` }}
                      onClick={() => handleTimelineClick(marker.id)}
                      title={`${marker.role === 'user' ? 'Your message' : marker.role === 'assistant' ? 'Assistant' : 'Tool'} - ${marker.label}`}
                    >
                      <div className={`${styles.markerDot} ${styles[`dot-${marker.role}`] || ''}`} />
                      <span className={styles.timelineLabel}>
                        {marker.role === 'user' ? '👤' : marker.role === 'assistant' ? '🤖' : '🔧'}
                      </span>
                    </div>
                  ))}
                  {/* Viewport indicator */}
                  <div className={styles.timelineViewport} />
                </div>
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

        {/* Pasted Images Preview */}
        {pastedImages.length > 0 && (
          <div className={styles.pastedImagesPreview}>
            {pastedImagePreview.map((preview, index) => (
              <div key={index} className={styles.pastedImageItem}>
                <img src={preview} alt={`Pasted image ${index + 1}`} className={styles.pastedImageThumbnail} />
                <button 
                  className={styles.removePastedImage}
                  onClick={() => handleRemovePastedImage(index)}
                  title="Remove image"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
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
              onPaste={handlePaste}
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
