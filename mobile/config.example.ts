// ─── SETUP ────────────────────────────────────────────────────────────────────
// 1. Copy this file to config.ts  (cp config.example.ts config.ts)
// 2. Fill in your Google Cloud Vision API key below.
//    Enable it at: https://console.cloud.google.com → APIs → Cloud Vision API
// 3. config.ts is gitignored — it will NEVER be committed.
// ─────────────────────────────────────────────────────────────────────────────

export const GOOGLE_CLOUD_VISION_API_KEY = 'YOUR_GOOGLE_CLOUD_VISION_API_KEY_HERE';

// The live Gemara Pen lookup API. Change to http://localhost:5000 for local dev.
export const LOOKUP_API_BASE = 'https://gemarapen.up.railway.app';
