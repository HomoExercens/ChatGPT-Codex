export type NavRoute =
  | '/home'
  | '/training'
  | '/forge'
  | '/gallery'
  | '/ranked'
  | '/tournament'
  | '/analytics'
  | '/meta'
  | '/settings'
  | '/social'
  | '/store';

export interface HomeSummary {
  user: {
    display_name: string;
    division: string;
    elo: number;
    tokens: number;
  };
  recent_matches: Array<{
    id: string;
    opponent: string;
    opponent_archetype: string;
    result: 'win' | 'loss' | 'draw';
    elo_change: number;
    date: string;
    duration: string;
  }>;
  meta_cards: Array<{
    id: string;
    title: string;
    subtitle?: string;
  }>;
}
