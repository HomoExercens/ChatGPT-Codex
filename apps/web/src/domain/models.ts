export const RARITY = {
  COMMON: 'Common',
  RARE: 'Rare',
  EPIC: 'Epic',
  LEGENDARY: 'Legendary',
} as const;

export type Rarity = (typeof RARITY)[keyof typeof RARITY];

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
  imageUrl: string;
}

export interface MatchResultRow {
  id: string;
  opponent: string;
  opponentArchetype: string;
  result: 'win' | 'loss' | 'draw';
  eloChange: number;
  date: string;
  duration: string;
}
