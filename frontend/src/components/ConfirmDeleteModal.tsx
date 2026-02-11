import React, { useEffect, useCallback } from 'react';
import { X, Loader2, AlertTriangle } from 'lucide-react';

interface ConfirmDeleteModalProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  count: number;
  type: 'selected' | 'all';
  isLoading?: boolean;
}

export const ConfirmDeleteModal: React.FC<ConfirmDeleteModalProps> = ({
  isOpen,
  onConfirm,
  onCancel,
  count,
  type,
  isLoading = false
}) => {
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

  const getModalTitle = () => {
    if (type === 'all') {
      return 'Eliminazione Tutti Gli Switch';
    }
    return 'Eliminazione Switch Selezionati';
  };

  const getModalMessage = () => {
    if (type === 'all') {
      return `Attenzione: Stai per eliminare TUTTI gli switch (${count}) e tutti i dati associati. Questa azione è irreversibile e non può essere annullata.`;
    }
    return `Stai per eliminare ${count} switch e tutti i dati associati. Questa azione è irreversibile.`;
  };

  const getConfirmButtonText = () => {
    if (type === 'all') {
      return 'Elimina Tutto';
    }
    return 'Elimina Selezionati';
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={!isLoading ? onCancel : undefined}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full p-6 transform transition-all">
          {/* Close button */}
          {!isLoading && (
            <button
              onClick={onCancel}
              className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <X className="w-5 h-5" />
            </button>
          )}

          {/* Warning icon */}
          <div className="flex justify-center mb-4">
            <div className="p-3 bg-red-100 dark:bg-red-900/30 rounded-full">
              <AlertTriangle className="w-8 h-8 text-red-600 dark:text-red-400" />
            </div>
          </div>

          {/* Title */}
          <h3 className="text-xl font-semibold text-center text-red-600 dark:text-red-400 mb-4">
            {getModalTitle()}
          </h3>

          {/* Message */}
          <p className="text-center text-gray-600 dark:text-gray-400 mb-6">
            {getModalMessage()}
          </p>

          {/* Buttons */}
          <div className="flex justify-end gap-3">
            <button
              onClick={onCancel}
              disabled={isLoading}
              className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Annulla
            </button>
            <button
              onClick={onConfirm}
              disabled={isLoading}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
              {getConfirmButtonText()}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
