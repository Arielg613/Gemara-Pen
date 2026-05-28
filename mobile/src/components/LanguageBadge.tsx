import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Lang } from '../types';

const CONFIG: Record<Lang, { bg: string; fg: string; label: string }> = {
  hebrew:  { bg: '#dbeafe', fg: '#1e40af', label: 'Hebrew' },
  aramaic: { bg: '#fef3c7', fg: '#92400e', label: 'Aramaic' },
  both:    { bg: '#ede9fe', fg: '#5b21b6', label: 'Hebrew & Aramaic' },
  unknown: { bg: '#f3f4f6', fg: '#6b7280', label: '' },
};

export function LanguageBadge({ lang }: { lang: Lang }) {
  const c = CONFIG[lang];
  if (!c.label) return null;
  return (
    <View style={[styles.badge, { backgroundColor: c.bg }]}>
      <Text style={[styles.label, { color: c.fg }]}>{c.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: 'flex-start',
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 3,
    marginBottom: 6,
  },
  label: {
    fontSize: 12,
    fontWeight: '600',
  },
});
