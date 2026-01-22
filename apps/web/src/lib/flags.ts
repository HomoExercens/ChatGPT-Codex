import { useQuery } from '@tanstack/react-query';

import { apiFetch } from './api';

export type MetaFlags = {
  demo_mode: boolean;
  log_json: boolean;
  alerts_enabled: boolean;
  steam_app_id?: string | null;
  discord_invite_url?: string | null;
};

export function useMetaFlags() {
  return useQuery({
    queryKey: ['metaFlags'],
    queryFn: () => apiFetch<MetaFlags>('/api/meta/flags'),
    staleTime: 30_000,
  });
}
