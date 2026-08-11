import { Router } from 'express';
import { simpleDB, seed as seedDb } from '../db.js';
import { z } from 'zod';
import { verifyAccess } from '../utils/jwt.js';

const router = Router();

router.get('/', (req, res) => {
  try {
    let rows = simpleDB.all('SELECT * FROM reviews ORDER BY created_at DESC');
    if (!rows || rows.length === 0) { try { seedDb(); rows = simpleDB.all('SELECT * FROM reviews ORDER BY created_at DESC') } catch {} }
    const items = (rows || []).map(r => ({ id: r.id, authorName: r.author_name, rating: Number(r.rating)||0, text: r.text, createdAt: r.created_at }));
    res.json({ success: true, data: items });
  } catch (e) {
    console.error('GET /reviews error', e?.message || e)
    res.status(500).json({ success: false, error: 'Server error' })
  }
});

const reviewSchema = z.object({
  rating: z.coerce.number().int().min(1, 'rating must be 1..5').max(5, 'rating must be 1..5'),
  text: z.string().trim().min(1, 'text is required').max(2000)
})

router.post('/', (req, res) => {
  try {
    const auth = req.headers.authorization || ''
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : null
    if (!token) return res.status(401).json({ success: false, error: 'Unauthorized' })
    let payload
    try { payload = verifyAccess(token) } catch { return res.status(401).json({ success: false, error: 'Unauthorized' }) }
    const user = simpleDB.get('SELECT * FROM users WHERE id = ?', [payload.id])
    if (!user) return res.status(401).json({ success: false, error: 'Unauthorized' })
    const parsed = reviewSchema.safeParse(req.body||{})
    if (!parsed.success) {
      const msg = parsed.error?.issues?.[0]?.message || 'Invalid fields'
      return res.status(400).json({ success: false, error: msg })
    }
    const { rating, text } = parsed.data
    const id = cryptoRandom()
    const created_at = new Date().toISOString()
    try {
      simpleDB.run('INSERT INTO reviews (id, user_id, author_name, avatar_url, rating, text, created_at) VALUES (?,?,?,?,?,?,?)', [id, user.id, user.nickname || 'User', null, rating, text, created_at])
    } catch (e) {
      console.error('INSERT review error', e?.message || e)
      return res.status(500).json({ success: false, error: 'Server error' })
    }
    const r = simpleDB.get('SELECT * FROM reviews WHERE id = ?', [id])
    res.json({ success: true, data: { id: r.id, authorName: r.author_name, rating: r.rating, text: r.text, createdAt: r.created_at } })
  } catch (e) {
    console.error('POST /reviews error', e?.message || e)
    res.status(500).json({ success: false, error: 'Server error' })
  }
})

function cryptoRandom() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') return globalThis.crypto.randomUUID()
  return 'r-' + Math.random().toString(36).slice(2) + Date.now().toString(36)
}
// avatar removed

export default router;
