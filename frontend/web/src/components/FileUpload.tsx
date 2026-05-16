import { useCallback, useState } from 'react';
import { Upload, X, File, FileText, Image, Code, AlertCircle } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import styles from '../styles/FileUpload.module.css';
import type { UploadedFile } from '../types';

export function FileUpload() {
  const { uploadedFiles, addUploadedFile, removeUploadedFile, clearUploadedFiles, showFileUpload } = useAppStore();
  const [isDragging, setIsDragging] = useState(false);

  const getFileIcon = (type: string) => {
    if (type.startsWith('image/')) return <Image size={20} />;
    if (type.includes('text') || type.endsWith('json') || type.endsWith('xml')) return <FileText size={20} />;
    if (type.includes('script') || type.endsWith('js') || type.endsWith('py') || type.endsWith('ts')) return <Code size={20} />;
    return <File size={20} />;
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    files.forEach(file => {
      const uploadedFile: UploadedFile = {
        id: `file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        name: file.name,
        size: file.size,
        type: file.type,
        status: 'uploaded'
      };
      addUploadedFile(uploadedFile);
    });
  }, [addUploadedFile]);

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    files.forEach(file => {
      const uploadedFile: UploadedFile = {
        id: `file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        name: file.name,
        size: file.size,
        type: file.type,
        status: 'uploaded'
      };
      addUploadedFile(uploadedFile);
    });
  };

  if (!showFileUpload) return null;

  return (
    <div className={styles.fileUploadContainer}>
      <div 
        className={`${styles.dropZone} ${isDragging ? styles.dragging : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          type="file"
          id="file-input"
          multiple
          onChange={handleFileInput}
          className={styles.fileInput}
        />
        <label htmlFor="file-input" className={styles.dropZoneLabel}>
          <div className={styles.dropZoneContent}>
            <Upload size={48} className={styles.uploadIcon} />
            <p className={styles.dropText}>Drag & drop files here</p>
            <p className={styles.orText}>or</p>
            <button className={styles.browseButton}>Browse Files</button>
            <p className={styles.hintText}>Supports multiple files</p>
          </div>
        </label>
      </div>

      {uploadedFiles.length > 0 && (
        <div className={styles.fileList}>
          <div className={styles.fileListHeader}>
            <span className={styles.fileCount}>{uploadedFiles.length} file(s) attached</span>
            <button className={styles.clearButton} onClick={clearUploadedFiles}>
              Clear All
            </button>
          </div>
          <div className={styles.files}>
            {uploadedFiles.map(file => (
              <div key={file.id} className={styles.fileItem}>
                <div className={styles.fileIcon}>
                  {getFileIcon(file.type)}
                </div>
                <div className={styles.fileInfo}>
                  <span className={styles.fileName}>{file.name}</span>
                  <span className={styles.fileSize}>{formatFileSize(file.size)}</span>
                </div>
                {file.status === 'error' && (
                  <AlertCircle size={16} className={styles.errorIcon} />
                )}
                <button 
                  className={styles.removeButton}
                  onClick={() => removeUploadedFile(file.id)}
                  aria-label={`Remove ${file.name}`}
                >
                  <X size={16} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
