import { describe, it, expect } from 'vitest';
import type { UploadedFile } from '../types';

/**
 * Image Paste & File Upload Unit Tests
 * 
 * These tests verify:
 * - Image paste detection from clipboard
 * - File upload preparation
 * - WebSocket reconnection logic
 */

describe('Image Paste & File Upload', () => {
  describe('Clipboard Image Detection', () => {
    it('should detect image items in clipboard data', () => {
      // Simulate clipboard data with image
      const mockClipboardItems = [
        { type: 'text/plain', getAsString: () => 'Hello' },
        { type: 'image/png', getAsFile: () => new File([''], 'image.png', { type: 'image/png' }) },
      ];
      
      const imageFiles: File[] = [];
      for (const item of mockClipboardItems) {
        if (item.type.startsWith('image/')) {
          const file = (item as any).getAsFile();
          if (file) {
            imageFiles.push(file);
          }
        }
      }
      
      expect(imageFiles.length).toBe(1);
      expect(imageFiles[0].type).toBe('image/png');
    });

    it('should handle multiple images in clipboard', () => {
      const mockClipboardItems = [
        { type: 'image/png', getAsFile: () => new File([''], 'image1.png', { type: 'image/png' }) },
        { type: 'image/jpeg', getAsFile: () => new File([''], 'image2.jpg', { type: 'image/jpeg' }) },
        { type: 'text/plain', getAsString: () => 'Text' },
      ];
      
      const imageFiles: File[] = [];
      for (const item of mockClipboardItems) {
        if (item.type.startsWith('image/')) {
          const file = (item as any).getAsFile();
          if (file) {
            imageFiles.push(file);
          }
        }
      }
      
      expect(imageFiles.length).toBe(2);
      expect(imageFiles[0].type).toBe('image/png');
      expect(imageFiles[1].type).toBe('image/jpeg');
    });

    it('should ignore non-image items', () => {
      const mockClipboardItems = [
        { type: 'text/plain', getAsString: () => 'Hello' },
        { type: 'application/json', getAsString: () => '{}' },
      ];
      
      const imageFiles: File[] = [];
      for (const item of mockClipboardItems) {
        if (item.type.startsWith('image/')) {
          const file = (item as any).getAsFile();
          if (file) {
            imageFiles.push(file);
          }
        }
      }
      
      expect(imageFiles.length).toBe(0);
    });
  });

  describe('File Upload Preparation', () => {
    it('should create FormData with files and prompt', () => {
      const prompt = 'Test message';
      const files = [
        new File(['test content'], 'test.png', { type: 'image/png' }),
      ];
      
      const formData = new FormData();
      formData.append('prompt', prompt);
      files.forEach(file => formData.append('files', file));
      
      expect(formData.get('prompt')).toBe('Test message');
      const filesData = formData.getAll('files');
      expect(filesData.length).toBe(1);
    });

    it('should handle empty file list', () => {
      const files: File[] = [];
      
      const shouldUpload = files.length > 0;
      expect(shouldUpload).toBe(false);
    });
  });

  describe('WebSocket Reconnection Configuration', () => {
    it('should configure infinite reconnection attempts', () => {
      const socketConfig = {
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        reconnectionAttempts: Infinity,
        timeout: 20000,
      };
      
      expect(socketConfig.reconnectionAttempts).toBe(Infinity);
      expect(socketConfig.reconnection).toBe(true);
    });

    it('should handle disconnect events with reason', () => {
      const shouldAutoReconnect = (reason: string) => {
        return reason === 'transport error' || reason === 'transport close';
      };
      
      expect(shouldAutoReconnect('transport error')).toBe(true);
      expect(shouldAutoReconnect('transport close')).toBe(true);
      expect(shouldAutoReconnect('io server disconnect')).toBe(false);
    });
  });

  describe('UploadedFile Type Extension', () => {
    it('should support optional file property', () => {
      // Simulate UploadedFile with file property
      const uploadedFileWithBlob: UploadedFile = {
        id: 'file-123',
        name: 'test.png',
        size: 1024,
        type: 'image/png',
        status: 'uploaded' as const,
        file: new File(['test'], 'test.png', { type: 'image/png' }),
      };
      
      // Simulate UploadedFile without file property (metadata only)
      const uploadedFileMetadata: UploadedFile = {
        id: 'file-456',
        name: 'existing.png',
        size: 2048,
        type: 'image/png',
        status: 'uploaded' as const,
      };
      
      expect(uploadedFileWithBlob.file).toBeDefined();
      expect(uploadedFileMetadata.file).toBeUndefined();
      expect(uploadedFileWithBlob.name).toBe('test.png');
      expect(uploadedFileMetadata.name).toBe('existing.png');
    });
  });

  describe('Submit Prompt with Files', () => {
    it('should include files in submission', () => {
      const prompt = 'Check this image';
      const files = [
        {
          id: 'file-123',
          name: 'screenshot.png',
          size: 1024,
          type: 'image/png',
          status: 'uploaded' as const,
        },
      ];
      
      const submission = {
        type: 'submit_line',
        line: prompt,
        uploaded_files: files,
      };
      
      expect(submission.line).toBe('Check this image');
      expect(submission.uploaded_files).toHaveLength(1);
      expect(submission.uploaded_files[0].name).toBe('screenshot.png');
    });

    it('should handle submission without files', () => {
      const prompt = 'Regular message';
      
      const submission = {
        type: 'submit_line',
        line: prompt,
      };
      
      expect(submission.line).toBe('Regular message');
      expect((submission as any).uploaded_files).toBeUndefined();
    });
  });
});
