// Domain Models

export enum NavView {
  DASHBOARD = 'dashboard',
  TRAINING = 'training',
  FORGE = 'forge',
  RANKED = 'ranked',
  REPLAY = 'replay',
  ANALYTICS = 'analytics',
  SETTINGS = 'settings'
}

export enum Rarity {
  COMMON = 'Common',
  RARE = 'Rare',
  EPIC = 'Epic',
  LEGENDARY = 'Legendary'
}

export interface Creature {
  id: string;
  name: string;
  role: 'Tank' | 'DPS' | 'Support' | 'Assassin';
  rarity: Rarity;
  stats: {
    hp: number;
    atk: number;
    spd: number;
  };
  synergies: string[];
  imageUrl: string; // Placeholder URL
}

export interface Blueprint {
  id: string;
  name: string;
  version: string;
  isValid: boolean;
  creatures: { slotId: number; creatureId: string }[];
  lastModified: string;
  tags: string[];
}

export interface TrainingRun {
  id: string;
  planType: 'Stable' | 'Aggressive' | 'Counter' | 'Exploratory';
  status: 'queued' | 'running' | 'paused' | 'done' | 'failed';
  progress: number; // 0-100
  budget: number;
  metrics: {
    winRate: number;
    loss: number;
  };
  logs: string[];
  startedAt: Date;
}

export interface MatchResult {
  id: string;
  opponent: string;
  opponentArchetype: string;
  result: 'win' | 'loss' | 'draw';
  eloChange: number;
  date: string;
  duration: string;
}

export interface User {
  displayName: string;
  division: string;
  elo: number;
  tokens: number;
}
