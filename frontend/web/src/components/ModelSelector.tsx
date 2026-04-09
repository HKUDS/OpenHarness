import { ChevronDown, Check, Edit3, CheckCircle, RefreshCw } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { useAppStore } from '../store/useAppStore';
import { sendModelChange, sendConfigUpdate } from '../utils/socketManager';
import styles from '../styles/ModelSelector.module.css';

// Default models if backend doesn't provide any
const DEFAULT_MODELS = [
  'claude-sonnet-4-6',
  'claude-3-5-sonnet-20241022',
  'claude-3-opus-20240229',
  'claude-3-haiku-20240307',
  'gpt-4-turbo-preview',
  'gpt-4-0125-preview',
  'gpt-3.5-turbo-0125',
  'gemini-1.5-pro',
  'gemini-1.5-flash',
];

export function ModelSelector() {
  const { settings, setCurrentModel, availableModels, sessionState, connected } = useAppStore();
  const [isOpen, setIsOpen] = useState(false);
  const [isCustomInput, setIsCustomInput] = useState(false);
  const [customModel, setCustomModel] = useState('');
  const [syncStatus, setSyncStatus] = useState<'synced' | 'pending' | 'error'>('synced');
  const selectorRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const currentModel = settings.model;
  const models = availableModels.length > 0 ? availableModels : DEFAULT_MODELS;

  // Check if model is synced with backend
  useEffect(() => {
    if (sessionState?.model && sessionState.model !== currentModel) {
      setSyncStatus('pending');
    } else {
      setSyncStatus('synced');
    }
  }, [sessionState?.model, currentModel]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (selectorRef.current && !selectorRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setIsCustomInput(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Focus input when custom input mode is activated
  useEffect(() => {
    if (isCustomInput && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isCustomInput]);

  const handleModelSelect = (model: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    // Update local state
    setCurrentModel(model);
    
    // Send to backend
    if (connected) {
      const success = sendModelChange(model);
      setSyncStatus(success ? 'pending' : 'error');
    }
    
    setIsOpen(false);
    setIsCustomInput(false);
  };

  const handleToggle = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsOpen(!isOpen);
    setIsCustomInput(false);
  };

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (customModel.trim()) {
      // Update local state
      setCurrentModel(customModel.trim());
      
      // Send to backend
      if (connected) {
        const success = sendModelChange(customModel.trim());
        setSyncStatus(success ? 'pending' : 'error');
      }
      
      setCustomModel('');
      setIsOpen(false);
      setIsCustomInput(false);
    }
  };

  const handleCustomKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsCustomInput(false);
      setCustomModel('');
    }
  };

  // Check if current model is in the available list
  const isModelInList = models.includes(currentModel);

  return (
    <div className={styles.modelSelector} ref={selectorRef}>
      <button 
        type="button"
        className={styles.selectorButton}
        onClick={handleToggle}
        aria-label="Select model"
        aria-expanded={isOpen}
      >
        <span className={styles.modelIcon}>🤖</span>
        <span className={styles.modelName}>
          {currentModel}
          {!isModelInList && <span className={styles.customBadge}>custom</span>}
        </span>
        {syncStatus === 'pending' && (
          <RefreshCw size={12} className={styles.syncIcon} />
        )}
        <ChevronDown size={16} className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`} />
      </button>

      {isOpen && (
        <div className={styles.dropdown}>
          <div className={styles.dropdownHeader}>
            <span className={styles.dropdownTitle}>Select Model</span>
            <button
              type="button"
              className={`${styles.customButton} ${isCustomInput ? styles.active : ''}`}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setIsCustomInput(!isCustomInput);
              }}
            >
              <Edit3 size={14} />
              Custom
            </button>
          </div>
          
          {isCustomInput && (
            <form onSubmit={handleCustomSubmit} className={styles.customInputForm}>
              <input
                ref={inputRef}
                type="text"
                value={customModel}
                onChange={(e) => setCustomModel(e.target.value)}
                onKeyDown={handleCustomKeyDown}
                placeholder="Enter model ID (e.g., claude-sonnet-4-6)"
                className={styles.customInput}
              />
              <button
                type="submit"
                className={styles.customSubmit}
                disabled={!customModel.trim()}
              >
                <CheckCircle size={16} />
              </button>
            </form>
          )}

          <div className={styles.dropdownContent}>
            {models.map(model => (
              <button
                type="button"
                key={model}
                className={`${styles.dropdownItem} ${model === currentModel ? styles.selected : ''}`}
                onClick={(e) => handleModelSelect(model, e)}
              >
                <span className={styles.itemName}>{model}</span>
                {model === currentModel && (
                  <Check size={16} className={styles.checkIcon} />
                )}
              </button>
            ))}
          </div>
          
          {/* Sync status indicator */}
          <div className={styles.syncStatus}>
            {syncStatus === 'pending' && (
              <span className={styles.syncPending}>
                <RefreshCw size={12} className={styles.syncIcon} />
                Syncing...
              </span>
            )}
            {syncStatus === 'synced' && sessionState?.model && (
              <span className={styles.synced}>
                <Check size={12} />
                Backend: {sessionState.model}
              </span>
            )}
            {!connected && (
              <span className={styles.disconnected}>
                Not connected to backend
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}