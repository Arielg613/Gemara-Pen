import React, { useEffect, useRef, useState } from 'react';
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
import { detectHebrewWords, mlKitAvailable } from '../utils/deviceOcr';
import { lookupWord } from '../utils/api';
import { DefinitionCard } from '../components/DefinitionCard';
import { LookupResult } from '../types';

// The fraction of image height captured by the scan-line strip.
const STRIP_FRACTION = 0.12;
// Vertical centre of the strip as a fraction of image height.
const STRIP_CENTRE = 0.5;

type CameraMode = 'tap' | 'auto';
type InputMode = 'camera' | 'type';
type AppState = 'idle' | 'loading' | 'result' | 'error';

// ── Helpers ──────────────────────────────────────────────────────────────────

async function cropToScanStrip(uri: string, photoWidth: number, photoHeight: number) {
  const originY = Math.floor(photoHeight * (STRIP_CENTRE - STRIP_FRACTION / 2));
  const height  = Math.floor(photoHeight * STRIP_FRACTION);
  return ImageManipulator.manipulateAsync(
    uri,
    [
      { crop: { originX: 0, originY, width: photoWidth, height } },
      { resize: { width: 800 } },
    ],
    { base64: true, compress: 0.8, format: ImageManipulator.SaveFormat.JPEG }
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ScanScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);

  const [inputMode, setInputMode]   = useState<InputMode>('camera');
  const [cameraMode, setCameraMode] = useState<CameraMode>('tap');
  const [appState, setAppState]     = useState<AppState>('idle');
  const [result, setResult]         = useState<LookupResult | null>(null);
  const [scannedWord, setScannedWord] = useState('');
  const [typedWord, setTypedWord]   = useState('');
  const [errorMsg, setErrorMsg]     = useState('');
  const [zoom, setZoom]             = useState(0);

  // Auto-scan state
  const [detectedWord, setDetectedWord]   = useState<string | null>(null);
  const isPolling   = useRef(false);
  const isCapturing = useRef(false);
  const stable      = useRef({ word: '', count: 0 });

  // ── State helpers ────────────────────────────────────────────────────────────

  function reset() {
    setAppState('idle');
    setResult(null);
    setScannedWord('');
    setErrorMsg('');
    setDetectedWord(null);
    stable.current = { word: '', count: 0 };
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

  // ── Tap-to-scan ──────────────────────────────────────────────────────────────

  async function handleTapScan() {
    if (!cameraRef.current) return;
    reset();
    setAppState('loading');
    try {
      const photo = await cameraRef.current.takePictureAsync({ base64: true, quality: 0.9 });
      if (!photo?.base64 || !photo.width || !photo.height) throw new Error('Camera capture failed.');

      const proc = await cropToScanStrip(photo.uri, photo.width, photo.height);
      if (!proc.base64) throw new Error('Image processing failed.');

      const word = await recognizeHebrewWord(proc.base64, proc.width, proc.height);
      if (!word) throw new Error('No Hebrew text detected in the scan line.\nTry zooming in or moving closer.');

      await runLookup(word);
    } catch (e: any) {
      setErrorMsg(e.message ?? 'An error occurred.');
      setAppState('error');
    }
  }

  // ── Auto-scan (ML Kit polling) ───────────────────────────────────────────────

  async function pollFrame() {
    if (isCapturing.current || !cameraRef.current) return;
    isCapturing.current = true;
    try {
      // Low quality for speed; skip processing on iOS for extra speed
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.35,
        base64: false,
        // @ts-ignore — skipProcessing is iOS-only and not in the type defs
        skipProcessing: true,
      });
      if (!photo?.width || !photo?.height) return;

      const proc = await cropToScanStrip(photo.uri, photo.width, photo.height);
      const words = await detectHebrewWords(proc.uri);

      if (words.length === 0) {
        stable.current = { word: '', count: 0 };
        setDetectedWord(null);
        return;
      }

      const word = words[0];
      setDetectedWord(word);

      if (word === stable.current.word) {
        stable.current.count++;
        if (stable.current.count >= 2) {
          isPolling.current = false;   // stop polling before await
          await runLookup(word);
        }
      } else {
        stable.current = { word, count: 1 };
      }
    } catch {
      // ignore per-frame failures
    } finally {
      isCapturing.current = false;
    }
  }

  // Start / stop auto-scan polling
  useEffect(() => {
    if (inputMode !== 'camera' || cameraMode !== 'auto' || appState !== 'idle') {
      isPolling.current = false;
      return;
    }
    isPolling.current = true;
    const id = setInterval(() => {
      if (isPolling.current) pollFrame();
    }, 650);
    return () => {
      clearInterval(id);
      isPolling.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputMode, cameraMode, appState]);

  // ── Type mode ────────────────────────────────────────────────────────────────

  async function handleTypeSubmit() {
    const w = typedWord.trim();
    if (!w) return;
    await runLookup(w);
  }

  // ── Permission gate ──────────────────────────────────────────────────────────

  if (!permission) {
    return <View style={s.center}><ActivityIndicator size="large" color="#5b21b6" /></View>;
  }
  if (!permission.granted) {
    return (
      <View style={s.center}>
        <Text style={s.permText}>Camera access is needed to scan words.</Text>
        <TouchableOpacity style={s.purpleBtn} onPress={requestPermission}>
          <Text style={s.purpleBtnText}>Grant Camera Access</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  const showCamera = inputMode === 'camera' && appState !== 'result';

  return (
    <View style={s.root}>

      {/* ── Camera ─────────────────────────────────────────────────────────── */}
      {showCamera && (
        <CameraView ref={cameraRef} style={s.camera} facing="back" zoom={zoom}>

          {/* Scan-line overlay */}
          <View style={s.overlay} pointerEvents="none">

            {/* Corner brackets around the scan strip */}
            <View style={s.bracketTL} /><View style={s.bracketTR} />
            <View style={s.bracketBL} /><View style={s.bracketBR} />

            {/* The scan line itself */}
            <View style={[s.scanLine, cameraMode === 'auto' && detectedWord ? s.scanLineActive : null]} />

            {/* Auto: detected word preview floats above the line */}
            {cameraMode === 'auto' && detectedWord ? (
              <Text style={s.detectedWord}>{detectedWord}</Text>
            ) : null}
          </View>

          {/* Hint text (below the strip) */}
          <Text style={s.hint}>
            {cameraMode === 'auto'
              ? detectedWord ? 'Hold steady…' : 'Align word with line'
              : 'Align word with line, then tap Scan'}
          </Text>

          {/* Zoom controls */}
          <View style={s.zoomCol}>
            <TouchableOpacity
              style={s.zoomBtn}
              onPress={() => setZoom(z => Math.min(0.8, +(z + 0.2).toFixed(1)))}
            >
              <Text style={s.zoomBtnText}>+</Text>
            </TouchableOpacity>
            <Text style={s.zoomLevel}>{Math.round(zoom * 5 + 1)}×</Text>
            <TouchableOpacity
              style={s.zoomBtn}
              onPress={() => setZoom(z => Math.max(0, +(z - 0.2).toFixed(1)))}
            >
              <Text style={s.zoomBtnText}>−</Text>
            </TouchableOpacity>
          </View>

          {/* Tap / Auto sub-toggle */}
          <View style={s.subBar}>
            {(['tap', 'auto'] as CameraMode[]).map((m) => {
              const disabled = m === 'auto' && !mlKitAvailable;
              return (
                <TouchableOpacity
                  key={m}
                  style={[s.subBtn, cameraMode === m && s.subBtnActive, disabled && s.subBtnDisabled]}
                  onPress={() => {
                    if (disabled) return;
                    setCameraMode(m);
                    reset();
                  }}
                >
                  <Text style={[s.subBtnText, cameraMode === m && s.subBtnTextActive]}>
                    {m === 'tap' ? 'Tap' : mlKitAvailable ? 'Auto' : 'Auto *'}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

        </CameraView>
      )}

      {/* Auto mode unavailable notice */}
      {showCamera && cameraMode === 'auto' && !mlKitAvailable && (
        <View style={s.noticeBox}>
          <Text style={s.noticeText}>
            * Auto mode needs a development build.{'\n'}Run <Text style={s.noticeCode}>expo run:ios</Text> to enable it.
          </Text>
        </View>
      )}

      {/* ── Type mode ──────────────────────────────────────────────────────── */}
      {inputMode === 'type' && appState !== 'result' && (
        <View style={s.typeArea}>
          <Text style={s.typeLabel}>Type a Hebrew or Aramaic word</Text>
          <TextInput
            style={s.typeInput}
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
      )}

      {/* ── Result sheet ───────────────────────────────────────────────────── */}
      {appState === 'result' && result && (
        <View style={s.resultWrapper}>
          <DefinitionCard result={result} scannedWord={scannedWord} />
          <TouchableOpacity style={s.resetBtn} onPress={reset}>
            <Text style={s.resetBtnText}>
              {inputMode === 'camera' ? 'Scan Another' : 'Look Up Another'}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {/* ── Bottom bar ─────────────────────────────────────────────────────── */}
      {appState !== 'result' && (
        <View style={s.modeBar}>
          {(['camera', 'type'] as InputMode[]).map((m) => (
            <TouchableOpacity
              key={m}
              style={[s.modeBtn, inputMode === m && s.modeBtnActive]}
              onPress={() => { setInputMode(m); reset(); }}
            >
              <Text style={[s.modeBtnText, inputMode === m && s.modeBtnTextActive]}>
                {m === 'camera' ? '📷  Camera' : '⌨️  Type'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {/* Tap-mode scan button */}
      {appState === 'idle' && inputMode === 'camera' && cameraMode === 'tap' && (
        <TouchableOpacity style={s.actionBtn} onPress={handleTapScan} activeOpacity={0.85}>
          <Text style={s.actionBtnText}>Scan</Text>
        </TouchableOpacity>
      )}

      {/* Type-mode submit button */}
      {appState === 'idle' && inputMode === 'type' && (
        <TouchableOpacity style={s.actionBtn} onPress={handleTypeSubmit} activeOpacity={0.85}>
          <Text style={s.actionBtnText}>Look Up</Text>
        </TouchableOpacity>
      )}

      {/* Loading */}
      {appState === 'loading' && (
        <View style={s.loadingBox}>
          <ActivityIndicator size="large" color="#5b21b6" />
          <Text style={s.loadingText}>
            {inputMode === 'camera' ? 'Scanning…' : 'Looking up…'}
          </Text>
        </View>
      )}

      {/* Error */}
      {appState === 'error' && (
        <View style={s.errorBox}>
          <Text style={s.errorText}>{errorMsg}</Text>
          <TouchableOpacity onPress={reset}>
            <Text style={s.retryText}>Try again</Text>
          </TouchableOpacity>
        </View>
      )}

    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const BRACKET = 22;
const BRACKET_W = 3;

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#111' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },

  // Camera
  camera: { flex: 1 },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
  },

  // Scan line
  scanLine: {
    width: '75%',
    height: 2,
    backgroundColor: 'rgba(255,255,255,0.75)',
  },
  scanLineActive: {
    backgroundColor: '#34d399',  // green when word locked on
    height: 3,
  },

  // Corner brackets
  bracketTL: { position: 'absolute', top: '44%', left: '11%', width: BRACKET, height: BRACKET, borderTopWidth: BRACKET_W, borderLeftWidth: BRACKET_W, borderColor: 'rgba(255,255,255,0.85)', borderRadius: 2 },
  bracketTR: { position: 'absolute', top: '44%', right: '11%', width: BRACKET, height: BRACKET, borderTopWidth: BRACKET_W, borderRightWidth: BRACKET_W, borderColor: 'rgba(255,255,255,0.85)', borderRadius: 2 },
  bracketBL: { position: 'absolute', bottom: '44%', left: '11%', width: BRACKET, height: BRACKET, borderBottomWidth: BRACKET_W, borderLeftWidth: BRACKET_W, borderColor: 'rgba(255,255,255,0.85)', borderRadius: 2 },
  bracketBR: { position: 'absolute', bottom: '44%', right: '11%', width: BRACKET, height: BRACKET, borderBottomWidth: BRACKET_W, borderRightWidth: BRACKET_W, borderColor: 'rgba(255,255,255,0.85)', borderRadius: 2 },

  // Auto: detected word
  detectedWord: {
    position: 'absolute',
    top: '38%',
    color: '#34d399',
    fontSize: 26,
    fontWeight: '700',
    textShadowColor: '#000',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },

  // Camera hint
  hint: {
    position: 'absolute',
    bottom: '42%',
    color: 'rgba(255,255,255,0.6)',
    fontSize: 13,
    textAlign: 'center',
    width: '100%',
  },

  // Zoom controls (right side)
  zoomCol: {
    position: 'absolute',
    right: 16,
    top: '38%',
    alignItems: 'center',
    gap: 4,
  },
  zoomBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  zoomBtnText: { color: '#fff', fontSize: 20, lineHeight: 24 },
  zoomLevel: { color: 'rgba(255,255,255,0.7)', fontSize: 12, marginVertical: 2 },

  // Tap / Auto sub-toggle (bottom of camera)
  subBar: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    flexDirection: 'row',
    backgroundColor: 'rgba(0,0,0,0.55)',
    paddingVertical: 6,
    paddingHorizontal: 10,
    gap: 6,
  },
  subBtn: { flex: 1, paddingVertical: 7, borderRadius: 7, alignItems: 'center' },
  subBtnActive: { backgroundColor: 'rgba(255,255,255,0.15)' },
  subBtnDisabled: { opacity: 0.45 },
  subBtnText: { color: 'rgba(255,255,255,0.55)', fontSize: 13, fontWeight: '500' },
  subBtnTextActive: { color: '#fff' },

  // Dev build notice
  noticeBox: {
    backgroundColor: '#1c1917',
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  noticeText: { color: '#a8a29e', fontSize: 12, textAlign: 'center', lineHeight: 18 },
  noticeCode: { color: '#fbbf24', fontFamily: 'Courier New' },

  // Type mode
  typeArea: { flex: 1, backgroundColor: '#f5f0e8', padding: 28, justifyContent: 'center' },
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

  // Bottom mode bar
  modeBar: {
    flexDirection: 'row',
    backgroundColor: '#1a1a1a',
    paddingVertical: 6,
    paddingHorizontal: 10,
    gap: 6,
  },
  modeBtn: { flex: 1, paddingVertical: 9, borderRadius: 8, alignItems: 'center' },
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
  loadingBox: { alignItems: 'center', paddingVertical: 28 },
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
  purpleBtn: { backgroundColor: '#5b21b6', paddingHorizontal: 28, paddingVertical: 14, borderRadius: 12 },
  purpleBtnText: { color: '#fff', fontSize: 16, fontWeight: '600' },
});
