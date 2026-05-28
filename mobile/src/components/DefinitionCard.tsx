import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Entry, LookupResult } from '../types';
import { LanguageBadge } from './LanguageBadge';

function EntryRow({ entry, divider }: { entry: Entry; divider: boolean }) {
  return (
    <View style={[styles.entry, divider && styles.entryDivider]}>
      <LanguageBadge lang={entry.lang} />
      <Text style={styles.hw}>{entry.hw}</Text>
      <Text style={styles.def}>{entry.def}</Text>
    </View>
  );
}

interface Props {
  result: LookupResult;
  scannedWord: string;
}

export function DefinitionCard({ result, scannedWord }: Props) {
  return (
    <View style={styles.card}>
      {/* Word header */}
      <View style={styles.wordRow}>
        <Text style={styles.word}>{scannedWord}</Text>
        {result.match_type === 'root' && result.entries[0] && (
          <Text style={styles.rootNote}>root → {result.entries[0].hw}</Text>
        )}
        {result.match_type === 'prefix' && (
          <Text style={styles.rootNote}>prefix match</Text>
        )}
      </View>

      {result.found ? (
        <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
          {result.entries.map((e, i) => (
            <EntryRow key={i} entry={e} divider={i > 0} />
          ))}
        </ScrollView>
      ) : (
        <Text style={styles.notFound}>Not found in Jastrow's dictionary.</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fffef7',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 8,
    maxHeight: 420,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: -3 },
    shadowOpacity: 0.14,
    shadowRadius: 10,
    elevation: 10,
  },
  wordRow: {
    borderBottomWidth: 1,
    borderBottomColor: '#e5dfc8',
    paddingBottom: 12,
    marginBottom: 4,
  },
  word: {
    fontSize: 32,
    fontWeight: '700',
    textAlign: 'right',
    color: '#111',
    lineHeight: 42,
  },
  rootNote: {
    fontSize: 12,
    color: '#6b7280',
    textAlign: 'right',
    marginTop: 2,
  },
  scroll: {
    flexGrow: 0,
  },
  entry: {
    paddingVertical: 10,
  },
  entryDivider: {
    borderTopWidth: 1,
    borderTopColor: '#e5dfc8',
  },
  hw: {
    fontSize: 18,
    fontWeight: '600',
    textAlign: 'right',
    color: '#1a1a1a',
    marginBottom: 4,
  },
  def: {
    fontSize: 14,
    lineHeight: 21,
    color: '#374151',
  },
  notFound: {
    fontSize: 14,
    color: '#6b7280',
    textAlign: 'center',
    paddingVertical: 24,
  },
});
