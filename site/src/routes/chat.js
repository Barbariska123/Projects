import { Router } from 'express'
import { z } from 'zod'
import { simpleDB } from '../db.js'
import { verifyAccess } from '../utils/jwt.js'
import { v4 as uuidv4 } from 'uuid'

const router = Router()

function requireAuth(req, res, next) {
  try {
    const auth = req.headers.authorization || ''
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : null
    if (!token) return res.status(401).json({ success: false, error: 'Unauthorized' })
    const payload = verifyAccess(token)
    const u = simpleDB.get('SELECT * FROM users WHERE id = ?', [payload.id])
    if (!u) return res.status(401).json({ success: false, error: 'Unauthorized' })
    if (u.banned) return res.status(403).json({ success: false, error: 'Banned' })
    req.user = u
    next()
  } catch {
    return res.status(401).json({ success: false, error: 'Unauthorized' })
  }
}

const sendSchema = z.object({
  type: z.enum(['global','dm']),
  text: z.string().min(1).max(1000),
  toUserId: z.string().uuid().optional()
})

router.post('/send', requireAuth, (req, res) => {
  const parsed = sendSchema.safeParse(req.body || {})
  if (!parsed.success) return res.status(400).json({ success: false, error: 'Invalid fields' })
  const { type, text } = parsed.data
  const id = uuidv4()
  const created_at = new Date().toISOString()

  if (type === 'global') {
    simpleDB.run('INSERT INTO chat_messages (id, from_user_id, to_user_id, is_dm, text, created_at) VALUES (?,?,?,?,?,?)', [id, req.user.id, null, 0, text, created_at])
    return res.json({ success: true, data: { id, created_at } })
  }

  // DM flow
  let toUserId = req.body?.toUserId
  if (req.user.is_admin) {
    // Admin must specify user to write to
    if (!toUserId) return res.status(400).json({ success: false, error: 'toUserId required for admin DM' })
    const exists = simpleDB.get('SELECT id FROM users WHERE id = ?', [toUserId])
    if (!exists) return res.status(404).json({ success: false, error: 'User not found' })
  } else {
    // Regular user -> DM to any admin (pick first)
    const admin = simpleDB.get('SELECT id FROM users WHERE is_admin = 1 LIMIT 1', [])
    if (!admin) return res.status(400).json({ success: false, error: 'No admin available' })
    toUserId = admin.id
  }

  simpleDB.run('INSERT INTO chat_messages (id, from_user_id, to_user_id, is_dm, text, created_at) VALUES (?,?,?,?,?,?)', [id, req.user.id, toUserId, 1, text, created_at])
  return res.json({ success: true, data: { id, created_at } })
})

// Fetch messages
router.get('/messages', requireAuth, (req, res) => {
  const type = String(req.query.type || 'global')
  if (type !== 'global' && type !== 'dm') return res.status(400).json({ success: false, error: 'Bad type' })
  if (type === 'global') {
    const rows = simpleDB.all('SELECT * FROM chat_messages WHERE is_dm = 0 ORDER BY created_at ASC')
    const cache = new Map()
    const data = rows.map(r => {
      const m = mapMsg(r)
      if (r.from_user_id) {
        let u = cache.get(r.from_user_id)
        if (!u) { u = simpleDB.get('SELECT id, nickname, email, is_admin FROM users WHERE id = ?', [r.from_user_id]); cache.set(r.from_user_id, u) }
        m.fromNickname = u?.nickname || null
        m.fromEmail = u?.email || null
        m.fromIsAdmin = !!u?.is_admin
      }
      return m
    })
    return res.json({ success: true, data: data })
  }
  // DM
  const withId = req.query.with ? String(req.query.with) : null
  if (req.user.is_admin) {
    if (!withId) return res.status(400).json({ success: false, error: 'Missing ?with for admin' })
    const rows = simpleDB.all(
      'SELECT * FROM chat_messages WHERE is_dm = 1 AND ((from_user_id = ? AND to_user_id = ?) OR (from_user_id = ? AND to_user_id = ?)) ORDER BY created_at ASC',
      [req.user.id, withId, withId, req.user.id]
    )
    const cache = new Map()
    const data = rows.map(r => {
      const m = mapMsg(r)
      if (r.from_user_id) {
        let u = cache.get(r.from_user_id)
        if (!u) { u = simpleDB.get('SELECT id, nickname, email, is_admin FROM users WHERE id = ?', [r.from_user_id]); cache.set(r.from_user_id, u) }
        m.fromNickname = u?.nickname || null
        m.fromEmail = u?.email || null
        m.fromIsAdmin = !!u?.is_admin
      }
      return m
    })
    return res.json({ success: true, data: data })
  }
  // Regular user: all their DM thread(s) with admins
  const rows = simpleDB.all(
    'SELECT * FROM chat_messages WHERE is_dm = 1 AND (from_user_id = ? OR to_user_id = ?) ORDER BY created_at ASC',
    [req.user.id, req.user.id]
  )
  const cache = new Map()
  const data = rows.map(r => {
    const m = mapMsg(r)
    if (r.from_user_id) {
      let u = cache.get(r.from_user_id)
      if (!u) { u = simpleDB.get('SELECT id, nickname, email, is_admin FROM users WHERE id = ?', [r.from_user_id]); cache.set(r.from_user_id, u) }
      m.fromNickname = u?.nickname || null
      m.fromEmail = u?.email || null
      m.fromIsAdmin = !!u?.is_admin
    }
    return m
  })
  return res.json({ success: true, data: data })
})

// Admin: list conversations (unique users) who have DM-ed with any admin
router.get('/conversations', requireAuth, (req, res) => {
  if (!req.user.is_admin) return res.status(403).json({ success: false, error: 'Forbidden' })
  const admins = simpleDB.all('SELECT id FROM users WHERE is_admin = 1', [])?.map(r => r.id) || []
  const msgs = simpleDB.all('SELECT * FROM chat_messages WHERE is_dm = 1', [])
  const set = new Map()
  for (const m of msgs) {
    const aToB = admins.includes(m.from_user_id) && !admins.includes(m.to_user_id)
    const bToA = admins.includes(m.to_user_id) && !admins.includes(m.from_user_id)
    if (aToB) set.set(m.to_user_id, m)
    if (bToA) set.set(m.from_user_id, m)
  }
  const list = Array.from(set.keys()).map(uid => {
    const u = simpleDB.get('SELECT id, email, nickname FROM users WHERE id = ?', [uid])
    return { id: u?.id, nickname: u?.nickname, email: u?.email }
  }).filter(Boolean)
  res.json({ success: true, data: list })
})

function mapMsg(r) {
  return {
    id: r.id,
    fromUserId: r.from_user_id || null,
    toUserId: r.to_user_id || null,
    isDM: !!r.is_dm,
    text: r.text,
    createdAt: r.created_at,
    updatedAt: r.updated_at || null
  }
}

// Edit message (owner or admin)
router.put('/messages/:id', requireAuth, (req, res) => {
  const schema = z.object({ text: z.string().min(1).max(1000) })
  const parsed = schema.safeParse(req.body || {})
  if (!parsed.success) return res.status(400).json({ success: false, error: 'Invalid fields' })
  const msg = simpleDB.get('SELECT * FROM chat_messages WHERE id = ?', [req.params.id])
  if (!msg) return res.status(404).json({ success: false, error: 'Not found' })
  if (!(req.user.is_admin || msg.from_user_id === req.user.id)) {
    return res.status(403).json({ success: false, error: 'Forbidden' })
  }
  const now = new Date().toISOString()
  simpleDB.run('UPDATE chat_messages SET text = ?, updated_at = ? WHERE id = ?', [parsed.data.text, now, req.params.id])
  const row = simpleDB.get('SELECT * FROM chat_messages WHERE id = ?', [req.params.id])
  return res.json({ success: true, data: mapMsg(row) })
})

// Delete message (owner or admin)
router.delete('/messages/:id', requireAuth, (req, res) => {
  const msg = simpleDB.get('SELECT * FROM chat_messages WHERE id = ?', [req.params.id])
  if (!msg) return res.status(404).json({ success: false, error: 'Not found' })
  if (!(req.user.is_admin || msg.from_user_id === req.user.id)) {
    return res.status(403).json({ success: false, error: 'Forbidden' })
  }
  simpleDB.run('DELETE FROM chat_messages WHERE id = ?', [req.params.id])
  return res.json({ success: true, data: { id: req.params.id } })
})

export default router
