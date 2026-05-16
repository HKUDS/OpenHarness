import { ChevronDown, Check, Edit3, CheckCircle, RefreshCw, Trash2, Plus, X } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useAppStore } from '../store/useAppStore';
import { sendModelChange } from '../utils/socketManager';
import styles from '../styles/ModelSelector.module.css';

// Default models if backend doesn't provide any - must match useAppStore.ts
const DEFAULT_MODELS = [
  'claude-sonnet-4-6',
  'claude-3-5-sonnet-20241022',
  'claude-3-opus-20240229',
  'claude-3-sonnet-20240229',
  'claude-3-haiku-20240307',
  'gemini-1-5-pro',
  'gemini-1-5-flash',
  'gpt-4-turbo-preview',
  'gpt-4-0125-preview',
  'gpt-3.5-turbo-0125',
];

export function ModelSelector() {
  const { settings, setCurrentModel, availableModels, sessionState, connected, setAvailableModels } = useAppStore();
  const [isOpen, setIsOpen] = useState(false);
  const [isCustomInput, setIsCustomInput] = useState(false);
  const [customModel, setCustomModel] = useState('');
  const [syncStatus, setSyncStatus] = useState<'synced' | 'pending' | 'error'>('synced');
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [editingModel, setEditingModel] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [showManage, setShowManage] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState<{ top: number; left: number; placement: 'up' | 'down' }>({ top: 0, left: 0, placement: 'up' });
  const selectorRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const currentModel = settings.model;
  // Include custom models in the list
  const baseModels = availableModels.length > 0 ? availableModels : DEFAULT_MODELS;
  const models = currentModel && !baseModels.includes(currentModel) 
    ? [currentModel, ...baseModels] 
    : baseModels;

  // Calculate dropdown position when opened
  useEffect(() => {
    if (isOpen && selectorRef.current) {
      const rect = selectorRef.current.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const viewportWidth = window.innerWidth;
      const dropdownHeight = 450; // Approximate max height of dropdown
      const dropdownWidth = 320;
      const spaceBelow = viewportHeight - rect.bottom;
      const spaceAbove = rect.top;
      
      // Position upward if there's not enough space below
      const placement = spaceBelow < dropdownHeight && spaceAbove > spaceBelow ? 'up' : 'down';
      
      // Ensure dropdown doesn't go off-screen horizontally
      let leftPosition = rect.left;
      if (leftPosition + dropdownWidth > viewportWidth) {
        leftPosition = Math.max(0, viewportWidth - dropdownWidth - 16);
      }
      
      setDropdownPosition({
        top: placement === 'up' ? rect.top - dropdownHeight - 8 : rect.bottom + 8,
        left: leftPosition,
        placement
      });
    }
  }, [isOpen]);

  // Check if model is synced with backend
  useEffect(() => {
    if (!connected) {
      setSyncStatus('error');
    } else if (sessionState?.model && sessionState.model !== currentModel) {
      // Backend has a different model - frontend needs to sync
      setSyncStatus('pending');
    } else {
      setSyncStatus('synced');
    }
  }, [sessionState?.model, currentModel, connected]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      // Check if click is outside both the selector and the dropdown
      const selectorElement = selectorRef.current;
      const dropdownElement = document.querySelector('[data-model-selector-dropdown]');
      
      const isClickInsideSelector = selectorElement && selectorElement.contains(event.target as Node);
      const isClickInsideDropdown = dropdownElement && dropdownElement.contains(event.target as Node);
      
      if (!isClickInsideSelector && !isClickInsideDropdown) {
        setIsOpen(false);
        setIsCustomInput(false);
        setShowManage(false);
        setEditingModel(null);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    }
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
    
    console.log('[ModelSelector] Selected model:', model);
    
    // Update local state (skip backend sync - we send via socket below)
    setCurrentModel(model);
    
    // Send to backend via socket
    if (connected) {
      const success = sendModelChange(model);
      setSyncStatus(success ? 'pending' : 'error');
    }
    
    setIsOpen(false);
    setIsCustomInput(false);
    setShowManage(false);
  };

  const handleToggle = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    console.log('[ModelSelector] Toggle clicked, isOpen:', !isOpen);
    setIsOpen(!isOpen);
    setIsCustomInput(false);
    setShowManage(false);
  };

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!customModel.trim()) return;
    
    const modelValue = customModel.trim();
    
    // Save to available models if not already present
    if (!availableModels.includes(modelValue)) {
      setSaveStatus('saving');
      // Persist to localStorage via the store
      setAvailableModels([...availableModels, modelValue]);
      console.log('[ModelSelector] Saved custom model:', modelValue);
      setTimeout(() => setSaveStatus('saved'), 300);
      setTimeout(() => setSaveStatus('idle'), 2000);
    }
    
    // Update local state immediately (skip backend sync - we send via socket)
    setCurrentModel(modelValue);
    
    // Send to backend via socket
    if (connected) {
      const success = sendModelChange(modelValue);
      console.log('[ModelSelector] Sent model to backend:', modelValue, 'success:', success);
      setSyncStatus(success ? 'pending' : 'error');
    } else {
      console.warn('[ModelSelector] Not connected to backend, model change queued');
    }
    
    // Clear and close
    setCustomModel('');
    setIsOpen(false);
    setIsCustomInput(false);
  };

  const handleCustomKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsCustomInput(false);
      setCustomModel('');
    }
  };

  const handleEditModel = (model: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setEditingModel(model);
    setEditValue(model);
  };

  const handleSaveEdit = (oldModel: string, e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!editValue.trim() || editValue === oldModel) {
      setEditingModel(null);
      return;
    }
    
    // Update the model in the list
    const newModels = availableModels.map(m => m === oldModel ? editValue.trim() : m);
    setAvailableModels(newModels);
    
    // If this was the current model, update it (skip backend sync - we send via socket)
    if (currentModel === oldModel) {
      setCurrentModel(editValue.trim());
      if (connected) {
        sendModelChange(editValue.trim());
      }
    }
    
    setEditingModel(null);
    setEditValue('');
  };

  const handleDeleteModel = (model: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    // Remove from available models
    const newModels = availableModels.filter(m => m !== model);
    setAvailableModels(newModels);
    
    // If this was the current model, switch to default (skip backend sync - we send via socket)
    if (currentModel === model) {
      const newCurrent = newModels[0] || DEFAULT_MODELS[0];
      setCurrentModel(newCurrent);
      if (connected) {
        sendModelChange(newCurrent);
      }
    }
  };

  // Check if current model is in the available list
  const isModelInList = models.includes(currentModel);
  
  // Separate default models from custom models
  const defaultModelsSet = new Set(DEFAULT_MODELS);
  const customModels = models.filter(m => !defaultModelsSet.has(m));
  const defaultModels = models.filter(m => defaultModelsSet.has(m));

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

      {isOpen && createPortal(
        <div 
          data-model-selector-dropdown
          className={`${styles.dropdown} ${dropdownPosition.placement === 'up' ? styles.dropdownUp : ''}`}
          style={{
            position: 'fixed',
            top: `${dropdownPosition.top}px`,
            left: `${dropdownPosition.left}px`,
            width: '320px',
          }}
        >
          <div className={styles.dropdownHeader}>
            <span className={styles.dropdownTitle}>Select Model</span>
            <div className={styles.headerActions}>
              <button
                type="button"
                className={`${styles.actionButton} ${showManage ? styles.active : ''}`}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setShowManage(!showManage);
                  setIsCustomInput(false);
                }}
                title="Manage models"
              >
                <Edit3 size={14} />
              </button>
              <button
                type="button"
                className={`${styles.actionButton} ${isCustomInput ? styles.active : ''}`}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setIsCustomInput(!isCustomInput);
                  setShowManage(false);
                }}
                title="Add custom model"
              >
                <Plus size={14} />
              </button>
            </div>
          </div>
          
          {isCustomInput && (
            <form 
              onSubmit={(e) => {
                e.preventDefault();
                e.stopPropagation();
                handleCustomSubmit(e);
              }} 
              className={styles.customInputForm}
            >
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
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  const event = { preventDefault: () => {}, stopPropagation: () => {} } as React.FormEvent;
                  handleCustomSubmit(event);
                }}
                className={`${styles.customSubmit} ${saveStatus === 'saved' ? styles.saved : ''}`}
                disabled={!customModel.trim() || saveStatus === 'saving'}
                title={saveStatus === 'saved' ? 'Saved!' : 'Save and use model'}
              >
                {saveStatus === 'saving' ? (
                  <RefreshCw size={16} className={styles.spinning} />
                ) : saveStatus === 'saved' ? (
                  <Check size={16} />
                ) : (
                  <CheckCircle size={16} />
                )}
              </button>
            </form>
          )}

          {showManage && (
            <div className={styles.manageSection}>
              <div className={styles.manageHeader}>
                <span>Custom Models</span>
              </div>
              {customModels.length === 0 ? (
                <div className={styles.emptyState}>
                  <p>No custom models yet.</p>
                  <p className={styles.emptyStateHint}>Click the + button to add a custom model.</p>
                </div>
              ) : (
                customModels.map(model => (
                  <div key={model} className={styles.manageItem}>
                    {editingModel === model ? (
                      <form 
                        onSubmit={(e) => handleSaveEdit(model, e)}
                        className={styles.editForm}
                      >
                        <input
                          type="text"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          className={styles.editInput}
                          autoFocus
                        />
                        <button type="submit" className={styles.editSaveBtn}>
                          <Check size={14} />
                        </button>
                        <button 
                          type="button" 
                          className={styles.editCancelBtn}
                          onClick={() => setEditingModel(null)}
                        >
                          <X size={14} />
                        </button>
                      </form>
                    ) : (
                      <>
                        <span className={styles.manageModelName}>{model}</span>
                        <div className={styles.manageActions}>
                          <button
                            type="button"
                            className={styles.editModelBtn}
                            onClick={(e) => handleEditModel(model, e)}
                            title="Edit model"
                          >
                            <Edit3 size={14} />
                          </button>
                          <button
                            type="button"
                            className={styles.deleteModelBtn}
                            onClick={(e) => handleDeleteModel(model, e)}
                            title="Delete model"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          <div className={styles.dropdownContent}>
            {customModels.length > 0 && !showManage && (
              <>
                <div className={styles.modelGroupHeader}>Custom</div>
                {customModels.map(model => (
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
                <div className={styles.modelGroupHeader}>Default</div>
              </>
            )}
            
            {defaultModels.map(model => (
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
        </div>, document.body
      )}
    </div>
  );
}