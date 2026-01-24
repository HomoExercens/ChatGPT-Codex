export type ReactionType = 'up' | 'lol' | 'wow';

export const LAST_REACTION_KEY = 'neuroleague.last_reaction_type';

export function getLastReactionType(): ReactionType {
  try {
    const raw = (localStorage.getItem(LAST_REACTION_KEY) || '').trim();
    if (raw === 'lol' || raw === 'wow' || raw === 'up') return raw;
  } catch {
    // ignore
  }
  return 'up';
}

export function setLastReactionType(reactionType: ReactionType): void {
  try {
    localStorage.setItem(LAST_REACTION_KEY, reactionType);
  } catch {
    // ignore
  }
}

