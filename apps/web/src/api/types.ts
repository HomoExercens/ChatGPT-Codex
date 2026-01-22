export type Mode = '1v1' | 'team';

export type BlueprintStatus = 'draft' | 'submitted' | 'archived';

export type BlueprintOut = {
  id: string;
  name: string;
  mode: Mode;
  ruleset_version: string;
  status: BlueprintStatus | string;
  spec: unknown;
  spec_hash: string;
  meta: Record<string, unknown>;
  forked_from_id?: string | null;
  build_code?: string | null;
  submitted_at?: string | null;
  updated_at: string;
};

export type GalleryBlueprintRow = {
  blueprint_id: string;
  name: string;
  mode: Mode;
  ruleset_version: string;
  spec_hash: string;
  submitted_at?: string | null;
  build_code?: string | null;
  forked_from_id?: string | null;
  creator: { user_id: string; display_name: string };
  synergy_tags: string[];
  stats: {
    matches: number;
    wins: number;
    losses: number;
    draws: number;
    winrate: number;
    avg_elo_delta: number;
    last_played_at?: string | null;
  };
};

export type BuildOfDay = {
  date: string;
  mode: Mode;
  blueprint: GalleryBlueprintRow | null;
  source?: 'override' | 'auto' | 'none';
  override_blueprint_id?: string | null;
  auto_blueprint_id?: string | null;
};

export type BlueprintLineage = {
  blueprint_id: string;
  chain: Array<{
    blueprint_id: string;
    name: string;
    user_id: string;
    display_name: string;
    status: string;
    submitted_at?: string | null;
    forked_from_id?: string | null;
    build_code?: string | null;
    children_count?: number;
    origin_code_hash?: string | null;
  }>;
  children?: Array<{
    blueprint_id: string;
    name: string;
    user_id: string;
    display_name: string;
    status: string;
    submitted_at?: string | null;
    forked_from_id?: string | null;
    build_code?: string | null;
    children_count?: number;
    origin_code_hash?: string | null;
  }>;
};

export type BuildCodeWarning = {
  type: string;
  message: string;
  expected?: string | null;
  got?: string | null;
};

export type BuildCodeDecodeOut = {
  ok: boolean;
  error?: string | null;
  warnings: BuildCodeWarning[];
  blueprint_spec?: any | null;
  ruleset_version?: string | null;
  pack_hash?: string | null;
  mode?: Mode | null;
};

export type BuildCodeImportOut = {
  ok: boolean;
  warnings: BuildCodeWarning[];
  blueprint?: any | null;
};

export type MatchRow = {
  id: string;
  queue_type?: 'ranked' | 'tournament' | 'all' | string;
  week_id?: string | null;
  mode: Mode;
  portal_id?: string | null;
  augments_a?: Array<{ round: number; augment_id: string }>;
  augments_b?: Array<{ round: number; augment_id: string }>;
  opponent: string;
  opponent_type: 'human' | 'bot';
  opponent_elo?: number | null;
  matchmaking_reason?: string | null;
  status: string;
  progress: number;
  result: 'win' | 'loss' | 'draw' | null;
  elo_change: number;
  error_message?: string | null;
  created_at: string;
};

export type QueueResponse = {
  match_id: string;
  status: 'queued' | 'running';
  progress: number;
};

export type ClipStats = {
  likes: number;
  forks: number;
  views: number;
  shares: number;
  open_ranked: number;
};

export type ClipFeedItem = {
  clip_id: string;
  replay_id: string;
  match_id: string;
  author: { user_id: string; display_name: string };
  blueprint_id: string | null;
  blueprint_name: string | null;
  mode: Mode;
  ruleset_version: string;
  created_at: string;
  best_clip_status: 'ready' | 'rendering' | 'missing';
  vertical_mp4_url: string | null;
  share_url_vertical: string;
  thumb_url: string;
  stats: ClipStats;
  tags: string[];
  featured?: boolean;
};

export type ClipFeedOut = {
  items: ClipFeedItem[];
  next_cursor: string | null;
};

export type FeaturedKind = 'clip' | 'build' | 'user' | 'challenge';

export type FeaturedItem = {
  id: string;
  kind: FeaturedKind;
  target_id: string;
  title_override?: string | null;
  priority: number;
  starts_at?: string | null;
  ends_at?: string | null;
  status: string;
  created_at: string;
  created_by?: string | null;
  href: string;
};

export type QuestDef = {
  id: string;
  cadence: 'daily' | 'weekly';
  key: string;
  title: string;
  description: string;
  goal_count: number;
  event_type: string;
  reward_cosmetic_id: string;
  reward_amount: number;
};

export type QuestAssignment = {
  assignment_id: string;
  period_key: string;
  progress_count: number;
  claimed_at?: string | null;
  claimable: boolean;
  quest: QuestDef;
};

export type QuestsTodayOut = {
  server_time_kst: string;
  ruleset_version: string;
  daily_period_key: string;
  weekly_period_key: string;
  daily: QuestAssignment[];
  weekly: QuestAssignment[];
};

export type ClaimQuestOut = {
  ok: boolean;
  assignment_id: string;
  claimed_at: string;
  reward_cosmetic_id: string;
  reward_granted: boolean;
  cosmetic_points_awarded: number;
  cosmetic_points_balance?: number | null;
};

export type ClipEventResponse = {
  ok: boolean;
  type: string;
  replay_id: string;
  liked?: boolean | null;
  likes?: number | null;
};

export type MatchDetail = {
  id: string;
  queue_type?: 'ranked' | 'tournament' | string;
  week_id?: string | null;
  mode: Mode;
  ruleset_version: string;
  portal_id?: string | null;
  augments_a?: Array<{ round: number; augment_id: string }>;
  augments_b?: Array<{ round: number; augment_id: string }>;
  status: string;
  progress: number;
  result: 'A' | 'B' | 'draw' | 'pending';
  user_a: string;
  user_b: string;
  opponent_display_name: string;
  opponent_type: 'human' | 'bot';
  opponent_elo?: number | null;
  matchmaking_reason?: string | null;
  blueprint_a_id: string | null;
  blueprint_b_id: string | null;
  seed_set_count: number;
  elo_delta_a: number;
  replay_id: string | null;
  highlights: Array<{
    rank: number;
    start_t: number;
    end_t: number;
    title: string;
    summary: string;
    tags: string[];
  }>;
  error_message?: string | null;
};

export type ReplayUnit = {
  unit_id: string;
  team: 'A' | 'B';
  slot_index: number;
  formation: 'front' | 'back';
  creature_id: string;
  creature_name: string;
  role: string;
  tags: string[];
  items: {
    weapon: string | null;
    armor: string | null;
    utility: string | null;
  };
  max_hp: number;
};

export type Replay = {
  header: {
    ruleset_version: string;
    match_id: string;
    seed_index: number;
    seed: number;
    mode: Mode;
    blueprint_a_hash: string;
    blueprint_b_hash: string;
    portal_id?: string | null;
    augments_a?: Array<{ round: number; augment_id: string }>;
    augments_b?: Array<{ round: number; augment_id: string }>;
    units?: ReplayUnit[];
  };
  end_summary: {
    winner: 'A' | 'B' | 'draw';
    duration_ticks: number;
    hp_a: number;
    hp_b: number;
  };
  timeline_events: Array<{
    t: number;
    type: string;
    payload: Record<string, unknown>;
  }>;
  highlights: MatchDetail['highlights'];
  digest: string;
};

export type PortalDef = {
  id: string;
  name: string;
  description: string;
  rarity: number;
  tags: string[];
};

export type AugmentDef = {
  id: string;
  name: string;
  description: string;
  tier: number;
  category: string;
  tags: string[];
};

export type ModifiersMeta = {
  portals: PortalDef[];
  augments: AugmentDef[];
};

export type WeeklyTheme = {
  week_id: string;
  name: string;
  description: string;
  featured_portals: PortalDef[];
  featured_augments: AugmentDef[];
  tournament_rules: { matches_counted: number; queue_open: boolean };
};

export type TournamentMe = {
  week_id: string;
  mode: Mode;
  matches_counted_limit: number;
  matches_counted: number;
  points: number;
  wins: number;
  losses: number;
  draws: number;
  rank?: number | null;
};

export type TournamentRow = {
  rank: number;
  user_id: string;
  display_name: string;
  points: number;
  matches_counted: number;
  wins: number;
  losses: number;
  draws: number;
};
