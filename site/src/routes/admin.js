import { Router } from 'express'
import { z } from 'zod'
import { simpleDB } from '../db.js'
import { verifyAccess } from '../utils/jwt.js'

const router = Router()

function requireAdmin(req, res, next) {
  try {
    const auth = req.headers.authorization || ''
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : null
    if (!token) return res.status(401).json({ success: false, error: 'Unauthorized' })
    const payload = verifyAccess(token)
    const u = simpleDB.get('SELECT * FROM users WHERE id = ?', [payload.id])
    if (!u || !u.is_admin) return res.status(403).json({ success: false, error: 'Forbidden' })
    req.user = u
    next()
  } catch { return res.status(401).json({ success: false, error: 'Unauthorized' }) }
}

const productSchema = z.object({
  slug: z.string().min(1),
  title: z.string().min(1),
  category: z.enum(['WEBSITE','TG_BOT','CRM','TG_WA']),
  description: z.string().min(1),
  longDescription: z.string().optional().default(''),
  priceFrom: z.number().int().nonnegative(),
  priceTo: z.number().int().nonnegative(),
  features: z.array(z.string()).optional().default([]),
  images: z.array(z.string()).optional().default([])
})

router.get('/products', requireAdmin, (req, res) => {
  const rows = simpleDB.all('SELECT * FROM products ORDER BY title')
  const items = rows.map(mapProduct)
  res.json({ success: true, data: items })
})

router.post('/products', requireAdmin, (req, res) => {
  const parsed = productSchema.safeParse(req.body||{})
  if (!parsed.success) return res.status(400).json({ success:false, error:'Invalid fields' })
  const p = parsed.data
  const id = cryptoUUID()
  simpleDB.run('INSERT INTO products (id, slug, title, category, description, long_description, price_from, price_to, features, images) VALUES (?,?,?,?,?,?,?,?,?,?)', [id, p.slug, p.title, p.category, p.description, p.longDescription||'', p.priceFrom, p.priceTo, JSON.stringify(p.features||[]), JSON.stringify(p.images||[])])
  const row = simpleDB.get('SELECT * FROM products WHERE id=?',[id])
  res.json({ success:true, data: mapProduct(row) })
})

router.put('/products/:id', requireAdmin, (req, res) => {
  const parsed = productSchema.partial().safeParse(req.body||{})
  if (!parsed.success) return res.status(400).json({ success:false, error:'Invalid fields' })
  const id = req.params.id
  const cur = simpleDB.get('SELECT * FROM products WHERE id=?',[id])
  if (!cur) return res.status(404).json({ success:false, error:'Not found' })
  const p = { ...mapProduct(cur), ...parsed.data }
  simpleDB.run('UPDATE products SET slug=?, title=?, category=?, description=?, long_description=?, price_from=?, price_to=?, features=?, images=? WHERE id=?', [p.slug, p.title, p.category, p.description, p.longDescription||'', p.priceFrom, p.priceTo, JSON.stringify(p.features||[]), JSON.stringify(p.images||[]), id])
  const row = simpleDB.get('SELECT * FROM products WHERE id=?',[id])
  res.json({ success:true, data: mapProduct(row) })
})

router.delete('/products/:id', requireAdmin, (req, res) => {
  simpleDB.run('DELETE FROM products WHERE id=?',[req.params.id])
  res.json({ success:true, data: { id: req.params.id } })
})

// Users management
router.get('/users', requireAdmin, (req, res) => {
  const searchRaw = (String(req.query.search || '')).trim()
  const rows = simpleDB.all('SELECT id, email, nickname, is_admin, created_at, banned, banned_at, banned_reason, banned_until FROM users ORDER BY created_at DESC', [])

  function fold(s){
    try { return String(s||'').normalize('NFKC').toLocaleLowerCase(['ru','en','uk','tr','de','pl','es','fr']) } catch { return String(s||'').toLowerCase() }
  }

  const filtered = searchRaw ? rows.filter(r => {
    const q = fold(searchRaw)
    return fold(r.email).includes(q) || fold(r.nickname).includes(q)
  }) : rows

  const users = filtered.map(r => ({
    id: r.id,
    email: r.email,
    nickname: r.nickname,
    isAdmin: !!r.is_admin,
    createdAt: r.created_at,
    isBanned: !!r.banned || (r.banned_until && Date.parse(r.banned_until) > Date.now()),
    bannedAt: r.banned_at,
    bannedReason: r.banned_reason,
    bannedUntil: r.banned_until || null
  }))
  res.json({ success: true, data: users })
})

router.post('/users/:id/admin', requireAdmin, (req, res) => {
  try {
    const schema = z.object({ isAdmin: z.boolean() })
    const parsed = schema.safeParse(req.body || {})
    if (!parsed.success) return res.status(400).json({ success:false, error:'Invalid fields' })
    const user = simpleDB.get('SELECT * FROM users WHERE id = ?', [req.params.id])
    if (!user) return res.status(404).json({ success:false, error:'User not found' })
    simpleDB.run('UPDATE users SET is_admin = ? WHERE id = ?', [parsed.data.isAdmin ? 1 : 0, req.params.id])
    const out = simpleDB.get('SELECT id, email, nickname, is_admin, created_at FROM users WHERE id = ?', [req.params.id])
    res.json({ success: true, data: { id: out.id, email: out.email, nickname: out.nickname, isAdmin: !!out.is_admin, createdAt: out.created_at } })
  } catch (e) {
    res.status(500).json({ success:false, error:'Server error' })
  }
})

// Ban/unban user
router.post('/users/:id/ban', requireAdmin, (req, res) => {
  try {
    const schema = z.object({ banned: z.boolean(), reason: z.string().optional(), until: z.union([z.string(), z.number()]).optional() })
    const parsed = schema.safeParse(req.body || {})
    if (!parsed.success) return res.status(400).json({ success:false, error:'Invalid fields' })
    if (req.params.id === req.user.id) return res.status(400).json({ success:false, error:'Cannot ban yourself' })
    const u = simpleDB.get('SELECT * FROM users WHERE id = ?', [req.params.id])
    if (!u) return res.status(404).json({ success:false, error:'User not found' })
    const now = new Date()
    let banned = parsed.data.banned ? 1 : 0
    let banned_at = parsed.data.banned ? now.toISOString() : null
    let banned_reason = parsed.data.banned ? (parsed.data.reason || null) : null
    let banned_until = null
    if (parsed.data.banned) {
      const until = parsed.data.until
      if (typeof until === 'number' && isFinite(until) && until > 0) {
        banned_until = new Date(now.getTime() + until * 3600 * 1000).toISOString()
        banned = 0 // timed ban via banned_until
      } else if (typeof until === 'string' && until) {
        const ts = Date.parse(until)
        if (!isNaN(ts) && ts > Date.now()) {
          banned_until = new Date(ts).toISOString()
          banned = 0
        }
      }
    }
    simpleDB.run('UPDATE users SET banned = ?, banned_at = ?, banned_reason = ?, banned_until = ? WHERE id = ?', [banned, banned_at, banned_reason, banned_until, req.params.id])
    const out = simpleDB.get('SELECT id, email, nickname, is_admin, created_at, banned, banned_at, banned_reason, banned_until FROM users WHERE id = ?', [req.params.id])
    const isBanned = !!out.banned || (out.banned_until && Date.parse(out.banned_until) > Date.now())
    res.json({ success: true, data: { id: out.id, email: out.email, nickname: out.nickname, isAdmin: !!out.is_admin, createdAt: out.created_at, isBanned, bannedAt: out.banned_at, bannedReason: out.banned_reason, bannedUntil: out.banned_until } })
  } catch (e) {
    res.status(500).json({ success:false, error:'Server error' })
  }
})

// Delete user
router.delete('/users/:id', requireAdmin, (req, res) => {
  try {
    if (req.params.id === req.user.id) return res.status(400).json({ success:false, error:'Cannot delete yourself' })
    const u = simpleDB.get('SELECT * FROM users WHERE id = ?', [req.params.id])
    if (!u) return res.status(404).json({ success:false, error:'User not found' })
    simpleDB.run('DELETE FROM chat_messages WHERE from_user_id = ? OR to_user_id = ?', [req.params.id, req.params.id])
    simpleDB.run('DELETE FROM reviews WHERE user_id = ?', [req.params.id])
    simpleDB.run('DELETE FROM users WHERE id = ?', [req.params.id])
    res.json({ success:true, data: { id: req.params.id } })
  } catch (e) {
    res.status(500).json({ success:false, error:'Server error' })
  }
})

function mapProduct(r){
  return { id:r.id, slug:r.slug, title:r.title, category:r.category, description:r.description, longDescription:r.long_description, priceFrom:r.price_from, priceTo:r.price_to, features:r.features?JSON.parse(r.features):[], images:r.images?JSON.parse(r.images):[] }
}
function cryptoUUID(){ return (globalThis.crypto?.randomUUID?.() || require('crypto').randomUUID()) }

export default router
