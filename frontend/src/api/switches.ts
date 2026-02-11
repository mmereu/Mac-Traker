import { apiClient } from './client';

export interface DeleteResult {
  deleted_count: number;
  success: boolean;
}

export const deleteSwitchesBulk = async (ids: number[]): Promise<DeleteResult> => {
  // Use separate /switch-actions/ prefix to avoid route ordering issues with /{switch_id}
  return apiClient.post<DeleteResult>('/api/switch-actions/bulk-delete', {
    switch_ids: ids
  });
};

export const deleteAllSwitches = async (): Promise<DeleteResult> => {
  // Use separate /switch-actions/ prefix to avoid route ordering issues with /{switch_id}
  return apiClient.post<DeleteResult>('/api/switch-actions/delete-all', {}, {
    headers: {
      'X-Confirm-Delete-All': 'true'
    }
  });
};