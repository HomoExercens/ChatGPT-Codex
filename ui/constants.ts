import { Creature, MatchResult, Rarity, User } from './types';

export const CURRENT_USER: User = {
  displayName: "Dr. Kairos",
  division: "Diamond II",
  elo: 2450,
  tokens: 14500
};

export const MOCK_CREATURES: Creature[] = [
  { id: 'c1', name: 'Slime Knight', role: 'Tank', rarity: Rarity.COMMON, stats: { hp: 1200, atk: 50, spd: 0.8 }, synergies: ['Gelatinous', 'Knight'], imageUrl: 'https://picsum.photos/100/100?random=1' },
  { id: 'c2', name: 'Ember Fox', role: 'DPS', rarity: Rarity.RARE, stats: { hp: 600, atk: 180, spd: 1.4 }, synergies: ['Beast', 'Fire'], imageUrl: 'https://picsum.photos/100/100?random=2' },
  { id: 'c3', name: 'Clockwork Golem', role: 'Tank', rarity: Rarity.EPIC, stats: { hp: 2000, atk: 80, spd: 0.5 }, synergies: ['Mech', 'Heavy'], imageUrl: 'https://picsum.photos/100/100?random=3' },
  { id: 'c4', name: 'Shadow Wisp', role: 'Assassin', rarity: Rarity.RARE, stats: { hp: 450, atk: 210, spd: 1.8 }, synergies: ['Spirit', 'Dark'], imageUrl: 'https://picsum.photos/100/100?random=4' },
  { id: 'c5', name: 'Crystal Weaver', role: 'Support', rarity: Rarity.LEGENDARY, stats: { hp: 900, atk: 110, spd: 1.0 }, synergies: ['Crystal', 'Mystic'], imageUrl: 'https://picsum.photos/100/100?random=5' },
];

export const RECENT_MATCHES: MatchResult[] = [
  { id: 'm1', opponent: 'Lab_Alpha', opponentArchetype: 'Mech Rush', result: 'win', eloChange: 24, date: '10m ago', duration: '45s' },
  { id: 'm2', opponent: 'BeastMaster99', opponentArchetype: 'Nature Heal', result: 'loss', eloChange: -18, date: '1h ago', duration: '3m 12s' },
  { id: 'm3', opponent: 'VoidWalker', opponentArchetype: 'Assassin Burst', result: 'win', eloChange: 12, date: '2h ago', duration: '1m 05s' },
];

export const PATCH_NOTES = [
  { version: 'v1.2.4', date: 'Today', title: 'Slime Synergy Buff' },
  { version: 'v1.2.3', date: '2 days ago', title: 'Fixed training budget glitch' },
];
