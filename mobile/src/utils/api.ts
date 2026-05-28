import { LOOKUP_API_BASE } from '../../config';
import { LookupResult } from '../types';

export async function lookupWord(word: string): Promise<LookupResult> {
  const res = await fetch(`${LOOKUP_API_BASE}/lookup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ word }),
  });
  if (!res.ok) throw new Error(`Lookup API returned ${res.status}`);
  return res.json();
}
