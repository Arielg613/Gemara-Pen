// Receives a scan from the app and keeps it in the private Blob store, so
// Claude can look at real-page scans later (vercel blob list / get).
import { put } from "@vercel/blob";

// Not a real secret (it ships in the page); just keeps random POSTs out.
const KEY = "gemara-pen-scans";

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).json({ error: "POST only" });
  if (req.headers["x-scan-key"] !== KEY) return res.status(403).json({ error: "bad key" });
  const scan = req.body;
  if (!scan || typeof scan.id !== "number") return res.status(400).json({ error: "no scan" });
  const body = JSON.stringify(scan);
  if (body.length > 3_000_000) return res.status(413).json({ error: "too big" });
  const day = new Date(scan.id).toISOString().slice(0, 10);
  await put(`scans/${day}/${scan.id}.json`, body, {
    access: "private", contentType: "application/json", addRandomSuffix: false, allowOverwrite: true,
  });
  res.status(200).json({ ok: true });
}
