import React, { useRef, useState } from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImageManipulator from 'expo-image-manipulator';
import { recognizeHebrewWord } from '../utils/ocr';
import { lookupWord } from '../utils/api';
import { DefinitionCard } from '../components/DefinitionCard';
import { LookupResult } from '../types';

type Mode = 'scan' | 'type';
type State = 'idle' | 'loading' | 'result' | 'error';

export function ScanScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);

  const [mode, setMode] = useState<Mode>('scan');
  const [appState, setAppState] = useState<State>('idle');
  const [result, setResult] = useState<LookupResult | null>(null);
  const [scannedWord, setScannedWord] = useState('');
  const [typedWord, setTypedWord] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  function reset() {
    setAppState('idle');
    setResult(null);
    setScannedWord('');
    setErrorMsg('');
  }

  async function runLookup(word: string) {
    setScannedWord(word);
    setAppState('loading');
    try {
      const res = await lookupWord(word);
      setResult(res);
      setAppState('result');
    } catch (e: any) {
      setErrorMsg(e.message ?? 'Lookup failed.');
      setAppState('error');
    }
  }

  async function handleScan() {
    if (!cameraRef.current) return;
    reset();
    setAppState('loading');

    try {
      const photo = await cameraRef.current.takePictureAsync({ base64: true, quality: 0.9 });
      if (!photo?.base64) throw new Error('Camera capture failed.');

      // Downscale to 1000px wide — enough for OCR, cheaper to send
      const proc = await ImageManipulator.manipulateAsync(
        photo.uri,
        [{ resize: { width: 1000 } }],
        { base64: true, compress: 0.8, format: ImageManipulator.SaveFormat.JPEG }
      );
      if (!proc.base64) throw new Error('Image processing failed.');

      const word = await recognizeHebrewWord(proc.base64, proc.width, proc.height);
      if (!word) throw new Error('No Hebrew text detected.\nTry pointing the camera closer at a single word.');

      await runLookup(word);
    } catch (e: any) {
      setErrorMsg(e.message ?? 'An error occurred.');
      setAppState('error');
    }
  }

  async function handleTypeSubmit() {
    const w = typedWord.trim();
    if (!w) return;
    await runLookup(w);
  }

  // ── Permission gate ──────────────────────────────────────────────────────────
  if (!permission) {
    return <View style={styles.center}><ActivityIndicator size="large" color="#5b21b6" /></View>;
  }

  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.permText}>Camera access is needed to scan words.</Text>
        <TouchableOpacity style={styles.purpleBtn} onPress={requestPermission}>
          <Text style={styles.purpleBtnText}>Grant Camera Access</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Main UI ──────────────────────────────────────────────────────────────────
  const showCamera = mode === 'scan' && appState !== 'result';

  return (
    <View style={styles.container}>

      {/* Camera / type area */}
      {showCamera ? (
        <CameraView ref={cameraRef} style={styles.camera} facing="back">
          <View style={styles.cameraOverlay}>
            {/* Focus frame — tells the user where to aim */}
            <View style={styles.focusOuter}>
              <View style={styles.focusFrame} />
            </View>
            <Text style={styles.cameraHint}>Centre the word in the frame</Text>
          </View>
        </CameraView>
      ) : mode === 'type' && appState !== 'result' ? (
        <View style={styles.typeArea}>
          <Text style={styles.typeLabel}>Type a Hebrew or Aramaic word</Text>
          <TextInput
            style={styles.typeInput}
            value={typedWord}
            onChangeText={setTypedWord}
            placeholder="e.g. מלכא"
            placeholderTextColor="#9ca3af"
            textAlign="right"
            onSubmitEditing={handleTypeSubmit}
            autoFocus
            returnKeyType="search"
          />
        </View>
      ) : null}

      {/* Result fills the bottom sheet */}
      {appState === 'result' && result && (
        <View style={styles.resultWrapper}>
          <DefinitionCard result={result} scannedWord={scannedWord} />
          <TouchableOpacity style={styles.resetBtn} onPress={reset}>
            <Text style={styles.resetBtnText}>{mode === 'scan' ? 'Scan Another' : 'Look Up Another'}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Mode toggle bar (hidden when showing result) */}
      {appState !== 'result' && (
        <View style={styles.modeBar}>
          {(['scan', 'type'] as Mode[]).map((m) => (
            <TouchableOpacity
              key={m}
              style={[styles.modeBtn, mode === m && styles.modeBtnActive]}
              onPress={() => { setMode(m); reset(); }}
            >
              <Text style={[styles.modeBtnText, mode === m && styles.modeBtnTextActive]}>
                {m === 'scan' ? '📷  Scan' : '⌨️  Type'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {/* Action button */}
      {appState === 'idle' && (
        <TouchableOpacity
          style={styles.actionBtn}
          onPress={mode === 'scan' ? handleScan : handleTypeSubmit}
          activeOpacity={0.85}
        >
          <Text style={styles.actionBtnText}>{mode === 'scan' ? 'Scan' : 'Look Up'}</Text>
        </TouchableOpacity>
      )}

      {/* Loading overlay */}
      {appState === 'loading' && (
        <View style={styles.loadingBox}>
          <ActivityIndicator size="large" color="#5b21b6" />
          <Text style={styles.loadingText}>{mode === 'scan' ? 'Scanning…' : 'Looking up…'}</Text>
        </View>
      )}

      {/* Error */}
      {appState === 'error' && (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{errorMsg}</Text>
          <TouchableOpacity onPress={reset}>
            <Text style={styles.retryText}>Try again</Text>
          </TouchableOpacity>
        </View>
      )}

    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },

  // Camera
  camera: { flex: 1 },
  cameraOverlay: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  focusOuter: { alignItems: 'center', justifyContent: 'center' },
  focusFrame: {
    width: 220,
    height: 70,
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.85)',
    borderRadius: 8,
    backgroundColor: 'rgba(255,255,255,0.04)',
  },
  cameraHint: {
    color: 'rgba(255,255,255,0.65)',
    fontSize: 13,
    marginTop: 14,
    textAlign: 'center',
  },

  // Type mode
  typeArea: {
    flex: 1,
    backgroundColor: '#f5f0e8',
    padding: 28,
    justifyContent: 'center',
  },
  typeLabel: { fontSize: 16, color: '#4b5563', marginBottom: 12 },
  typeInput: {
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#d1d5db',
    padding: 16,
    fontSize: 24,
    fontWeight: '600',
    color: '#111',
  },

  // Mode bar
  modeBar: {
    flexDirection: 'row',
    backgroundColor: '#1a1a1a',
    paddingVertical: 6,
    paddingHorizontal: 10,
    gap: 6,
  },
  modeBtn: {
    flex: 1,
    paddingVertical: 9,
    borderRadius: 8,
    alignItems: 'center',
  },
  modeBtnActive: { backgroundColor: '#374151' },
  modeBtnText: { color: '#6b7280', fontSize: 14, fontWeight: '500' },
  modeBtnTextActive: { color: '#fff' },

  // Action button
  actionBtn: {
    backgroundColor: '#5b21b6',
    marginHorizontal: 20,
    marginVertical: 14,
    paddingVertical: 16,
    borderRadius: 14,
    alignItems: 'center',
  },
  actionBtnText: { color: '#fff', fontSize: 18, fontWeight: '700', letterSpacing: 0.3 },

  // Loading
  loadingBox: {
    alignItems: 'center',
    paddingVertical: 28,
  },
  loadingText: { color: '#9ca3af', marginTop: 12, fontSize: 14 },

  // Error
  errorBox: {
    backgroundColor: '#fef2f2',
    marginHorizontal: 20,
    marginVertical: 14,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  errorText: { color: '#dc2626', fontSize: 14, textAlign: 'center', lineHeight: 20 },
  retryText: { color: '#5b21b6', marginTop: 10, fontSize: 14, fontWeight: '600' },

  // Result
  resultWrapper: { flex: 1, justifyContent: 'flex-end', backgroundColor: '#111' },
  resetBtn: {
    backgroundColor: '#374151',
    marginHorizontal: 20,
    marginVertical: 14,
    paddingVertical: 13,
    borderRadius: 12,
    alignItems: 'center',
  },
  resetBtnText: { color: '#fff', fontSize: 15, fontWeight: '600' },

  // Permission
  permText: { fontSize: 16, color: '#374151', textAlign: 'center', marginBottom: 20, lineHeight: 24 },
  purpleBtn: {
    backgroundColor: '#5b21b6',
    paddingHorizontal: 28,
    paddingVertical: 14,
    borderRadius: 12,
  },
  purpleBtnText: { color: '#fff', fontSize: 16, fontWeight: '600' },
});
