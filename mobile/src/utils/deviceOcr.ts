/**
 * On-device Hebrew text recognition via ML Kit.
 * Requires a development build (`expo run:ios` / `expo run:android`).
 * In Expo Go this module is absent — mlKitAvailable will be false
 * and auto-scan will gracefully degrade to a "needs dev build" prompt.
 */

let _TextRecognition: any = null;
let _Script: any = null;

try {
  // Dynamic require so Expo Go doesn't crash on missing native module
  const m = require('@react-native-ml-kit/text-recognition');
  _TextRecognition = m.default ?? m;
  _Script = m.TextRecognitionScript;
} catch {
  // Not installed / Expo Go environment
}

export const mlKitAvailable: boolean = _TextRecognition !== null;

// Matches a token that is ONLY Hebrew characters (including final forms).
const HEBREW_TOKEN = /^[א-תװ-״]+$/;

/**
 * Run ML Kit text recognition on a local image URI and return every
 * Hebrew word found in the image, in reading order.
 */
export async function detectHebrewWords(imageUri: string): Promise<string[]> {
  if (!_TextRecognition) throw new Error('ML Kit not available');
  // LATIN script covers Hebrew characters in ML Kit's default model
  const script = _Script?.LATIN ?? undefined;
  const result = await _TextRecognition.recognize(imageUri, script);
  return (result.blocks ?? [])
    .flatMap((b: any) => b.lines ?? [])
    .flatMap((l: any) => l.elements ?? [])
    .map((e: any) => (e.text ?? '').trim())
    .filter((t: string) => t.length >= 2 && HEBREW_TOKEN.test(t));
}
