import React, { useState, useEffect, useCallback } from 'react';
import { X, Loader2, AlertTriangle } from 'lucide-react';

interface ConfirmDeleteAllModalProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  count: number;
  isLoading?: boolean;
}

export const ConfirmDeleteAllModal: React.FC<ConfirmDeleteAllModalProps> = ({
  isOpen,
  onConfirm,
  onCancel,
  count,
  isLoading = false
}) => {
  const [confirmText, setConfirmText] = useState('');

  // Reset input when modal opens/closes
  useEffect(() => {
    if (!isOpen) {
      setConfirmText('');
    }
  }, [isOpen]);

  // Handle escape key
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape' && !isLoading) {
      onCancel();
    }
  }, [isLoading, onCancel]);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  if (!isOpen) return null;

  const handleConfirm = () => {
    if (confirmText.toUpperCase() === 'ELIMINA') {
      onConfirm();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setConfirmText(e.target.value);
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && isConfirmEnabled && !isLoading) {
      handleConfirm();
    }
  };

  const isConfirmEnabled = confirmText.toUpperCase() === 'ELIMINA';

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black bg-opacity-60 transition-opacity"
        onClick={!isLoading ? onCancel : undefined}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full transform transition-all">
          {/* Close button */}
          {!isLoading && (
            <button
              onClick={onCancel}
              className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 z-10"
            >
              <X className="w-5 h-5" />
            </button>
          )}

          {/* Red header bar */}
          <div className="bg-red-600 text-white py-3 px-6 rounded-t-lg flex items-center justify-center gap-2">
            <AlertTriangle className="w-6 h-6" />
            <span className="text-xl font-bold">ATTENZIONE</span>
            <AlertTriangle className="w-6 h-6" />
          </div>

          {/* Body */}
          <div className="p-6 text-center">
            <p className="text-lg text-gray-700 dark:text-gray-300 mb-2">
              Stai per eliminare <span className="font-bold">TUTTI gli switch ({count})</span> e tutti i dati associati.
            </p>
            <p className="text-red-600 dark:text-red-400 font-semibold mb-6">
              Questa azione è irreversibile e non può essere annullata.
            </p>

            <div className="bg-gray-100 dark:bg-gray-700 p-4 rounded-lg">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                Per confermare, digita <span className="font-mono font-bold text-red-600 dark:text-red-400">ELIMINA</span> nel campo sottostante:
              </p>
              <input
                type="text"
                value={confirmText}
                onChange={handleInputChange}
                onKeyPress={handleKeyPress}
                placeholder="Scrivi ELIMINA per confermare"
                maxLength={10}
                disabled={isLoading}
                autoFocus
                className="w-full max-w-xs mx-auto block px-4 py-2 border-2 border-gray-300 dark:border-gray-600 rounded-lg text-center text-lg font-mono focus:outline-none focus:border-red-500 dark:bg-gray-800 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed"
              />
            </div>
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-3 p-6 pt-0">
            <button
              onClick={onCancel}
              disabled={isLoading}
              className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Annulla
            </button>
            <button
              onClick={handleConfirm}
              disabled={!isConfirmEnabled || isLoading}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
              Elimina Tutto
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
