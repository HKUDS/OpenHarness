import { useState, useEffect } from 'react';
import { AlertTriangle, CheckCircle, XCircle, Shield, Loader2, RefreshCw, Info, MessageSquare } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { useBackendConnection } from '../hooks/useBackendConnection';
import type { PermissionModalRequest, QuestionModalRequest } from '../types';
import styles from '../styles/PermissionModal.module.css';

export function PermissionModal() {
  const { activeModal, respondToModal, settings } = useAppStore();
  const { sendPermissionResponse, sendQuestionResponse, connected, connect } = useBackendConnection();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [questionAnswer, setQuestionAnswer] = useState('');
  
  if (!activeModal) {
    return null;
  }
  
  // Check if we're in auto mode - modal shouldn't appear but handle gracefully
  const isAutoMode = settings?.permissionMode === 'full_auto';
  
  // Auto-approve immediately in auto mode to prevent showing the modal
  useEffect(() => {
    if (isAutoMode && activeModal.kind === 'permission') {
      console.log('[PermissionModal] Auto mode detected, auto-approving:', activeModal.request_id);
      const modal = activeModal as PermissionModalRequest;
      // Send approval to backend
      sendPermissionResponse(modal.request_id, true);
      // Clear the modal
      respondToModal(modal.request_id, true);
    }
  }, [isAutoMode, activeModal, sendPermissionResponse, respondToModal]);
  
  // Don't render the modal in auto mode (it will be auto-approved above)
  if (isAutoMode && activeModal.kind === 'permission') {
    return null;
  }
  
  // Handle permission request
  if (activeModal.kind === 'permission') {
    const modal = activeModal as PermissionModalRequest;
    
    const handleApprove = async () => {
      console.log('[PermissionModal] Approve clicked for request:', modal.request_id);
      setIsSubmitting(true);
      setError(null);
      
      try {
        if (!connected) {
          throw new Error('Not connected to backend. Please wait or reconnect.');
        }
        
        // Send permission response to backend
        console.log('[PermissionModal] Sending approval to backend...');
        sendPermissionResponse(modal.request_id, true);
        
        // Small delay to ensure message is sent before closing modal
        await new Promise(resolve => setTimeout(resolve, 100));
        
        // Clear the modal
        respondToModal(modal.request_id, true);
        
        console.log('[PermissionModal] Permission approved and sent to backend');
      } catch (err) {
        console.error('[PermissionModal] Error sending approval:', err);
        setError(err instanceof Error ? err.message : 'Failed to send approval');
        setIsSubmitting(false);
      }
    };
    
    const handleDeny = async () => {
      console.log('[PermissionModal] Deny clicked for request:', modal.request_id);
      setIsSubmitting(true);
      setError(null);
      
      try {
        if (!connected) {
          throw new Error('Not connected to backend. Please wait or reconnect.');
        }
        
        // Send permission response to backend
        console.log('[PermissionModal] Sending denial to backend...');
        sendPermissionResponse(modal.request_id, false);
        
        // Small delay to ensure message is sent before closing modal
        await new Promise(resolve => setTimeout(resolve, 100));
        
        // Clear the modal
        respondToModal(modal.request_id, false);
        
        console.log('[PermissionModal] Permission denied and sent to backend');
      } catch (err) {
        console.error('[PermissionModal] Error sending denial:', err);
        setError(err instanceof Error ? err.message : 'Failed to send denial');
        setIsSubmitting(false);
      }
    };
    
    const handleReconnect = () => {
      console.log('[PermissionModal] Attempting to reconnect...');
      setError(null);
      connect();
    };
    
    return (
      <div className={styles.modalOverlay}>
        <div className={styles.modalContainer}>
          <div className={styles.modalHeader}>
            <Shield size={24} className={styles.icon} />
            <h2>Permission Request</h2>
          </div>
          
          <div className={styles.modalContent}>
            <div className={styles.toolInfo}>
              <span className={styles.toolLabel}>Tool:</span>
              <span className={styles.toolName}>{modal.tool_name}</span>
            </div>
            
            <div className={styles.reasonBox}>
              <AlertTriangle size={16} className={styles.warningIcon} />
              <p className={styles.reason}>{modal.reason}</p>
            </div>
            
            {isAutoMode && (
              <div className={styles.autoModeWarning}>
                <Info size={16} />
                <span>Auto mode is enabled. This request should have been auto-approved.</span>
              </div>
            )}
            
            {!connected && (
              <div className={styles.connectionWarning}>
                <AlertTriangle size={14} />
                <span>Not connected to backend</span>
                <button 
                  className={styles.reconnectButton}
                  onClick={handleReconnect}
                  title="Reconnect"
                >
                  <RefreshCw size={14} />
                </button>
              </div>
            )}
            
            {error && (
              <div className={styles.errorBox}>
                <XCircle size={16} />
                <span>{error}</span>
              </div>
            )}
          </div>
          
          <div className={styles.modalActions}>
            <button 
              className={`${styles.button} ${styles.approveButton}`}
              onClick={handleApprove}
              disabled={isSubmitting || !connected}
            >
              {isSubmitting ? <Loader2 size={18} className={styles.spinning} /> : <CheckCircle size={18} />}
              Approve
            </button>
            <button 
              className={`${styles.button} ${styles.denyButton}`}
              onClick={handleDeny}
              disabled={isSubmitting || !connected}
            >
              {isSubmitting ? <Loader2 size={18} className={styles.spinning} /> : <XCircle size={18} />}
              Deny
            </button>
          </div>
        </div>
      </div>
    );
  }
  
  // Handle question request
  if (activeModal.kind === 'question') {
    const modal = activeModal as QuestionModalRequest;
    
    const handleSubmit = async () => {
      console.log('[PermissionModal] Question answer submitted for request:', modal.request_id);
      setIsSubmitting(true);
      setError(null);
      
      try {
        if (!connected) {
          throw new Error('Not connected to backend. Please wait or reconnect.');
        }
        
        // Send question response to backend
        console.log('[PermissionModal] Sending answer to backend...');
        sendQuestionResponse(modal.request_id, questionAnswer);
        
        // Small delay to ensure message is sent before closing modal
        await new Promise(resolve => setTimeout(resolve, 100));
        
        // Clear the modal
        respondToModal(modal.request_id, questionAnswer);
        
        console.log('[PermissionModal] Question answered and sent to backend');
      } catch (err) {
        console.error('[PermissionModal] Error sending answer:', err);
        setError(err instanceof Error ? err.message : 'Failed to send answer');
        setIsSubmitting(false);
      }
    };
    
    const handleReconnect = () => {
      console.log('[PermissionModal] Attempting to reconnect...');
      setError(null);
      connect();
    };
    
    return (
      <div className={styles.modalOverlay}>
        <div className={styles.modalContainer}>
          <div className={styles.modalHeader}>
            <MessageSquare size={24} className={styles.icon} />
            <h2>Question</h2>
          </div>
          
          <div className={styles.modalContent}>
            <div className={styles.questionBox}>
              <p className={styles.question}>{modal.question}</p>
            </div>
            
            <textarea
              className={styles.answerInput}
              value={questionAnswer}
              onChange={(e) => setQuestionAnswer(e.target.value)}
              placeholder="Type your answer here..."
              rows={4}
              disabled={isSubmitting || !connected}
            />
            
            {!connected && (
              <div className={styles.connectionWarning}>
                <AlertTriangle size={14} />
                <span>Not connected to backend</span>
                <button 
                  className={styles.reconnectButton}
                  onClick={handleReconnect}
                  title="Reconnect"
                >
                  <RefreshCw size={14} />
                </button>
              </div>
            )}
            
            {error && (
              <div className={styles.errorBox}>
                <XCircle size={16} />
                <span>{error}</span>
              </div>
            )}
          </div>
          
          <div className={styles.modalActions}>
            <button 
              className={`${styles.button} ${styles.approveButton}`}
              onClick={handleSubmit}
              disabled={isSubmitting || !connected}
            >
              {isSubmitting ? <Loader2 size={18} className={styles.spinning} /> : <CheckCircle size={18} />}
              Submit
            </button>
          </div>
        </div>
      </div>
    );
  }
  
  return null;
}
