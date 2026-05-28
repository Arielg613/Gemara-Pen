export type Lang = 'hebrew' | 'aramaic' | 'both' | 'unknown';
export type MatchType = 'exact' | 'root' | 'prefix' | 'none';

export interface Entry {
  hw: string;
  def: string;
  lang: Lang;
}

export interface LookupResult {
  word: string;
  found: boolean;
  match_type: MatchType;
  entries: Entry[];
}
