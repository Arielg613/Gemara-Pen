import { GOOGLE_CLOUD_VISION_API_KEY } from '../../config';

const VISION_URL =
  'https://vision.googleapis.com/v1/images:annotate?key=' + GOOGLE_CLOUD_VISION_API_KEY;

// Matches a string that is ONLY Hebrew characters (including final forms and marks).
const HEBREW_WORD_RE = /^[א-תװ-״֑-ׇ]+$/;

interface WordAnnotation {
  description: string;
  boundingPoly?: { vertices: Array<{ x?: number; y?: number }> };
}

function wordCenter(ann: WordAnnotation): { x: number; y: number } {
  const verts = ann.boundingPoly?.vertices ?? [];
  const n = Math.max(verts.length, 1);
  return {
    x: verts.reduce((s, v) => s + (v.x ?? 0), 0) / n,
    y: verts.reduce((s, v) => s + (v.y ?? 0), 0) / n,
  };
}

/**
 * Send a base64-encoded JPEG to Google Cloud Vision and return the Hebrew
 * word closest to the centre of the image (simulating the pen tip).
 *
 * Returns null if no Hebrew text is detected.
 * Throws on network/API errors.
 */
export async function recognizeHebrewWord(
  base64Image: string,
  imageWidth: number,
  imageHeight: number
): Promise<string | null> {
  if (GOOGLE_CLOUD_VISION_API_KEY === 'YOUR_GOOGLE_CLOUD_VISION_API_KEY_HERE') {
    throw new Error(
      'No API key set. Copy mobile/config.example.ts → mobile/config.ts and add your Google Cloud Vision key.'
    );
  }

  const res = await fetch(VISION_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      requests: [
        {
          image: { content: base64Image },
          features: [{ type: 'DOCUMENT_TEXT_DETECTION', maxResults: 100 }],
          // 'iw' is the BCP-47 code for Hebrew; Cloud Vision also understands 'he'
          imageContext: { languageHints: ['iw', 'he'] },
        },
      ],
    }),
  });

  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`Cloud Vision error ${res.status}: ${body.slice(0, 120)}`);
  }

  const data = await res.json();
  const annotations: WordAnnotation[] = data.responses?.[0]?.textAnnotations ?? [];

  // Index 0 is the full document text block; individual word tokens start at 1.
  const words = annotations.slice(1).filter((a) => HEBREW_WORD_RE.test(a.description));
  if (words.length === 0) return null;

  // Pick the word whose bounding-box centre is closest to the image centre.
  const cx = imageWidth / 2;
  const cy = imageHeight / 2;
  words.sort((a, b) => {
    const ca = wordCenter(a);
    const cb = wordCenter(b);
    return (ca.x - cx) ** 2 + (ca.y - cy) ** 2 - ((cb.x - cx) ** 2 + (cb.y - cy) ** 2);
  });

  return words[0].description;
}
