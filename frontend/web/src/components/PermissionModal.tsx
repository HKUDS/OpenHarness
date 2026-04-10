import { useState } from 'react';
import { AlertTriangle, CheckCircle, XCircle, Shield, Loader2, RefreshCw, Info } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { useBackendConnection } from '../hooks/useBackendConnection';
import type { PermissionModalRequest } from '../types';
import styles from '../styles/PermissionModal.module.css';

export function PermissionModal() {
  const { activeModal, respondToModal, settings } = useAppStore();
  const { sendPermissionResponse, connected, connect } = useBackendConnection();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  if (!activeModal || activeModal.kind !== 'permission') {
    return null;
  }
  
  const modal = activeModal as PermissionModalRequest;
  
  // Check if we're in auto mode - modal shouldn't appear but handle gracefully
  const isAutoMode = settings?.permissionMode === 'full_auto';
  
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