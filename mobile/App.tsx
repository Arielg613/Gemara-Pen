import React from 'react';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { StyleSheet, Text, View } from 'react-native';
import { ScanScreen } from './src/screens/ScanScreen';

export default function App() {
  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.root} edges={['top']}>
        <View style={styles.header}>
          <Text style={styles.heTitle}>גמרא פן</Text>
          <Text style={styles.enTitle}>GEMARA PEN</Text>
        </View>
        <ScanScreen />
      </SafeAreaView>
      <StatusBar style="light" backgroundColor="#111" />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#111' },
  header: {
    backgroundColor: '#111',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#2a2a2a',
  },
  heTitle: {
    color: '#f5f0e8',
    fontSize: 20,
    fontWeight: '700',
  },
  enTitle: {
    color: '#6b7280',
    fontSize: 10,
    letterSpacing: 3,
    marginTop: 1,
  },
});
