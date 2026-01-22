import { useQuery } from '@tanstack/react-query';

import { apiFetch } from './api';

export type ExperimentAssignment = {
  variant: string;
  config: Record<string, unknown>;
};

export type ExperimentsAssignments = Record<string, ExperimentAssignment>;

export const EXPERIMENT_KEYS = ['clip_len_v1', 'clips_feed_algo', 'share_cta_copy', 'quick_battle_default'] as const;

export function useExperiments() {
  const keys = EXPERIMENT_KEYS.join(',');
  return useQuery({
    queryKey: ['experiments', keys],
    queryFn: () => apiFetch<ExperimentsAssignments>(`/api/experiments/assign?keys=${encodeURIComponent(keys)}`),
    staleTime: 60_000,
  });
}

export function getExperimentVariant(
  assignments: ExperimentsAssignments | undefined,
  key: string,
  fallback: string
): string {
  const v = assignments?.[key]?.variant;
  return v && typeof v === 'string' ? v : fallback;
}
