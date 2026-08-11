import { Router } from 'express'
import rateLimit from 'express-rate-limit'
import { v4 as uuidv4 } from 'uuid'
import { z } from 'zod'
import bcrypt from 'bcryptjs'

import { simpleDB } from '../db.js'
import { sendMail, isMailConfigured, verifyMailer } from '../mailer.js'
import { signAccess, signRefresh, verifyAccess, verifyRefresh } from '../utils/jwt.js'

const router = Router()

const emailSchema = z.string().email()
const nicknameSchema = z.string().min(3).max(32).regex(/^[\p{L}\p{N}_.\-]+$/u)
const codeSchema = z.string().length(6).regex(/^[0-9]{6}$/)
const passwordSchema = z.string().min(6).max(72)

const startLimiter = rateLimit({ windowMs: 10 * 60 * 1000, limit: 20 })
router.use(['/register/start', '/login/start'], startLimiter)

// avatars removed

function publicUser(u) {
  return {
    id: u.id,
    email: u.email,
    nickname: u.nickname,
    emailVerifiedAt: u.email_verified ? new Date().toISOString() : null,
    createdAt: u.created_at,
    isAdmin: !!u.is_admin,
    isBanned: !!u.banned || (u.banned_until && Date.parse(u.banned_until) > Date.now())
  }
}

function genCode() {
  return Math.floor(100000 + Math.random() * 900000).toString()
}

// Register: Step 1 — start (sends code)
router.post('/register/start', async (req, res) => {
  try {
    const { email, nickname, password } = req.body || {}
    if (!emailSchema.safeParse(email).success || !nicknameSchema.safeParse(nickname).success || !passwordSchema.safeParse(password).success) {
      return res.status(400).json({ success: false, error: 'Invalid fields' })
    }
    const existsEmail = simpleDB.get('SELECT 1 as one FROM users WHERE email = ?', [email])
    const existsNick = simpleDB.get('SELECT 1 as one FROM users WHERE nickname = ?', [nickname])
    if (existsEmail) return res.status(409).json({ success: false, error: 'Email in use' })
    if (existsNick) return res.status(409).json({ success: false, error: 'Nickname in use' })

    const code = genCode()
    const password_hash = await bcrypt.hash(password, 10)
    const payload = JSON.stringify({ password_hash })
    simpleDB.run(
      'INSERT INTO otp_codes (id, email, nickname, purpose, code, expires_at, used, payload) VALUES (?,?,?,?,?,?,0,?)',
      [uuidv4(), email, nickname, 'register', code, Date.now() + 10 * 60 * 1000, payload]
    )
    try {
      await sendMail({ to: email, subject: 'Verification code', html: `<p>Your code: <b>${code}</b></p><p>Valid for 10 minutes.</p>` })
      res.json({ success: true, data: { message: 'Code sent' } })
    } catch (e) {
      console.error('Mail send error (register/start):', e?.message || e)
      if (!isMailConfigured() || process.env.NODE_ENV !== 'production') {
        // Dev fallback: allow progressing with code in response
        res.json({ success: true, data: { message: 'Dev: mail disabled or failed, use code', devCode: code } })
      } else {
        res.status(500).json({ success: false, error: 'Mail error' })
      }
    }
  } catch (e) {
    res.status(500).json({ success: false, error: 'Server error' })
  }
})

// Register: Step 2 — verify
router.post('/register/verify', (req, res) => {
  try {
    const { email, nickname, code } = req.body || {}
    if (!emailSchema.safeParse(email).success || !nicknameSchema.safeParse(nickname).success || !codeSchema.safeParse(code).success) {
      return res.status(400).json({ success: false, error: 'Invalid fields' })
    }
    const otp = simpleDB.get(
      'SELECT * FROM otp_codes WHERE email = ? AND nickname = ? AND purpose = ? AND code = ? AND used = 0 AND expires_at > ?',
      [email, nickname, 'register', code, Date.now()]
    )
    if (!otp) return res.status(400).json({ success: false, error: 'Invalid or expired code' })
    const existsEmail = simpleDB.get('SELECT 1 as one FROM users WHERE email = ?', [email])
    const existsNick = simpleDB.get('SELECT 1 as one FROM users WHERE nickname = ?', [nickname])
    if (existsEmail || existsNick) return res.status(409).json({ success: false, error: 'User already exists' })

    const id = uuidv4()
    const created_at = new Date().toISOString()
    let password_hash = null
    try { if (otp.payload) { const p = JSON.parse(otp.payload); password_hash = p.password_hash || null } } catch {}
    const is_admin = process.env.ADMIN_EMAIL && process.env.ADMIN_EMAIL.toLowerCase() === String(email).toLowerCase() ? 1 : 0
    simpleDB.run(
      'INSERT INTO users (id, email, nickname, email_verified, created_at, password_hash, is_admin, avatar_url) VALUES (?,?,?,?,?,?,?,?)',
      [id, email, nickname, 1, created_at, password_hash, is_admin, defaultAvatar(email, nickname)]
    )
    simpleDB.run('UPDATE otp_codes SET used = 1 WHERE id = ?', [otp.id])

    const access = signAccess({ id })
    const refresh = signRefresh({ id })
    res.cookie('refreshToken', refresh, { httpOnly: true, sameSite: 'lax', secure: false, maxAge: 30 * 24 * 60 * 60 * 1000 })
    const user = simpleDB.get('SELECT * FROM users WHERE id = ?', [id])
    res.json({ success: true, data: { accessToken: access, user: publicUser(user) } })
  } catch (e) {
    res.status(500).json({ success: false, error: 'Server error' })
  }
})

// Login: Step 1 — start (nickname + password, then send code)
router.post('/login/start', async (req, res) => {
  try {
    const { nickname, password } = req.body || {}
    if (!nicknameSchema.safeParse(nickname).success || !passwordSchema.safeParse(password).success) {
      return res.status(400).json({ success: false, error: 'Invalid fields' })
    }
    const user = simpleDB.get('SELECT * FROM users WHERE nickname = ?', [nickname])
    if (!user) return res.status(404).json({ success: false, error: 'User not found' })
    if (user.banned || (user.banned_until && Date.parse(user.banned_until) > Date.now())) return res.status(403).json({ success: false, error: 'Banned', data: { reason: user.banned_reason, until: user.banned_until } })
    if (!user.password_hash) return res.status(400).json({ success: false, error: 'Password not set' })
    const ok = await bcrypt.compare(password, user.password_hash)
    if (!ok) return res.status(401).json({ success: false, error: 'Wrong password' })

    const code = genCode()
    simpleDB.run(
      'INSERT INTO otp_codes (id, user_id, email, nickname, purpose, code, expires_at, used) VALUES (?,?,?,?,?,?,?,0)',
      [uuidv4(), user.id, user.email, user.nickname, 'login', code, Date.now() + 10 * 60 * 1000]
    )
    sendMail({ to: user.email, subject: 'Login code', html: `<p>Your login code: <b>${code}</b></p><p>Valid for 10 minutes.</p>` })
      .then(() => res.json({ success: true, data: { message: 'Code sent' } }))
      .catch((e) => {
        console.error('Mail send error (login/start):', e?.message || e)
        if (!isMailConfigured() || process.env.NODE_ENV !== 'production') {
          res.json({ success: true, data: { message: 'Dev: mail disabled or failed, use code', devCode: code } })
        } else {
          res.status(500).json({ success: false, error: 'Mail error' })
        }
      })
  } catch (e) {
    res.status(500).json({ success: false, error: 'Server error' })
  }
})

// Login: Step 2 — verify
router.post('/login/verify', (req, res) => {
  try {
    const { nickname, code } = req.body || {}
    if (!nicknameSchema.safeParse(nickname).success || !codeSchema.safeParse(code).success) return res.status(400).json({ success: false, error: 'Invalid fields' })
    const user = simpleDB.get('SELECT * FROM users WHERE nickname = ?', [nickname])
    if (!user) return res.status(404).json({ success: false, error: 'User not found' })
    if (user.banned || (user.banned_until && Date.parse(user.banned_until) > Date.now())) return res.status(403).json({ success: false, error: 'Banned', data: { reason: user.banned_reason, until: user.banned_until } })
    const otp = simpleDB.get('SELECT * FROM otp_codes WHERE user_id = ? AND purpose = ? AND code = ? AND used = 0 AND expires_at > ?', [user.id, 'login', code, Date.now()])
    if (!otp) return res.status(400).json({ success: false, error: 'Invalid or expired code' })
    simpleDB.run('UPDATE otp_codes SET used = 1 WHERE id = ?', [otp.id])
    const access = signAccess({ id: user.id })
    const refresh = signRefresh({ id: user.id })
    res.cookie('refreshToken', refresh, { httpOnly: true, sameSite: 'lax', secure: false, maxAge: 30 * 24 * 60 * 60 * 1000 })
    res.json({ success: true, data: { accessToken: access, user: publicUser(user) } })
  } catch (e) {
    res.status(500).json({ success: false, error: 'Server error' })
  }
})

router.post('/refresh', (req, res) => {
  try {
    const token = req.cookies.refreshToken
    if (!token) return res.status(401).json({ success: false, error: 'No refresh' })
    const payload = verifyRefresh(token)
    const user = simpleDB.get('SELECT * FROM users WHERE id = ?', [payload.id])
    if (!user) return res.status(401).json({ success: false, error: 'Invalid refresh' })
    if (user.banned || (user.banned_until && Date.parse(user.banned_until) > Date.now())) return res.status(403).json({ success: false, error: 'Banned', data: { reason: user.banned_reason, until: user.banned_until } })
    const access = signAccess({ id: user.id })
    res.json({ success: true, data: { accessToken: access, user: publicUser(user) } })
  } catch (e) {
    res.status(401).json({ success: false, error: 'Invalid refresh' })
  }
})

router.post('/logout', (req, res) => {
  res.clearCookie('refreshToken')
  res.json({ success: true, data: { message: 'Logged out' } })
})

router.get('/me', (req, res) => {
  try {
    const auth = req.headers.authorization || ''
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : null
    if (!token) return res.status(401).json({ success: false, error: 'Unauthorized' })
    const payload = verifyAccess(token)
    const user = simpleDB.get('SELECT * FROM users WHERE id = ?', [payload.id])
    if (!user) return res.status(404).json({ success: false, error: 'Not found' })
    if (user.banned || (user.banned_until && Date.parse(user.banned_until) > Date.now())) return res.status(403).json({ success: false, error: 'Banned', data: { reason: user.banned_reason, until: user.banned_until } })
    res.json({ success: true, data: publicUser(user) })
  } catch {
    res.status(401).json({ success: false, error: 'Unauthorized' })
  }
})

router.post('/update-profile', (req, res) => {
  try {
    const auth = req.headers.authorization || ''
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : null
    if (!token) return res.status(401).json({ success: false, error: 'Unauthorized' })
    let payload
    try { payload = verifyAccess(token) } catch { return res.status(401).json({ success: false, error: 'Unauthorized' }) }
    const { nickname } = req.body || {}
    const nextNick = typeof nickname === 'string' ? nickname.trim() : ''
    if (!nicknameSchema.safeParse(nextNick).success) return res.status(400).json({ success: false, error: 'Invalid nickname' })
    const current = simpleDB.get('SELECT * FROM users WHERE id = ?', [payload.id])
    if (current && current.nickname === nextNick) {
      return res.json({ success: true, data: publicUser(current) })
    }
    const conflict = simpleDB.get('SELECT 1 as one FROM users WHERE nickname = ? AND id <> ?', [nextNick, payload.id])
    if (conflict) return res.status(409).json({ success: false, error: 'Nickname in use' })
    try {
      simpleDB.run('UPDATE users SET nickname = ? WHERE id = ?', [nextNick, payload.id])
    } catch (e) {
      const msg = (e && e.message) || ''
      if (msg.includes('UNIQUE') && msg.toLowerCase().includes('nickname')) {
        return res.status(409).json({ success: false, error: 'Nickname in use' })
      }
      throw e
    }
    const user = simpleDB.get('SELECT * FROM users WHERE id = ?', [payload.id])
    res.json({ success: true, data: publicUser(user) })
  } catch (e) {
    res.status(500).json({ success: false, error: 'Server error' })
  }
})

// avatar endpoints removed

export default router
// Quick status to debug mail issues
router.get('/mail-status', async (req, res) => {
  try {
    const configured = isMailConfigured()
    const verified = await verifyMailer()
    res.json({ success: true, data: { configured, verified } })
  } catch (e) {
    res.status(200).json({ success: true, data: { configured: false, verified: false } })
  }
})
