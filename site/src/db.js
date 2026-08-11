import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import initSqlJs from 'sql.js'
import { v4 as uuidv4 } from 'uuid'
import bcrypt from 'bcryptjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const rootDir = path.resolve(__dirname, '..')
const envPath = process.env.DB_FILE || 'db.sqlite'
const dbFile = path.isAbsolute(envPath) ? envPath : path.join(rootDir, envPath)
const dir = path.dirname(dbFile)
if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })

let SQL = null
let db = null

function locateFile(file) {
  // Resolve wasm inside server/node_modules/sql.js/dist regardless of cwd
  return path.join(rootDir, 'node_modules', 'sql.js', 'dist', file)
}

export async function initDB() {
  if (!SQL) SQL = await initSqlJs({ locateFile })
  const fileBuffer = fs.existsSync(dbFile) ? fs.readFileSync(dbFile) : null
  db = fileBuffer ? new SQL.Database(new Uint8Array(fileBuffer)) : new SQL.Database()
}

function commit() {
  const data = db.export()
  const buffer = Buffer.from(data)
  fs.writeFileSync(dbFile, buffer)
}

export function migrate() {
  if (!db) throw new Error('DB not initialized')
  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      email TEXT UNIQUE NOT NULL,
      nickname TEXT UNIQUE NOT NULL,
      email_verified INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      password_hash TEXT,
      is_admin INTEGER NOT NULL DEFAULT 0,
      avatar_url TEXT,
      banned INTEGER NOT NULL DEFAULT 0,
      banned_at TEXT,
      banned_reason TEXT,
      banned_until TEXT
    );
    CREATE TABLE IF NOT EXISTS otp_codes (
      id TEXT PRIMARY KEY,
      user_id TEXT,
      email TEXT,
      nickname TEXT,
      purpose TEXT NOT NULL,
      code TEXT NOT NULL,
      expires_at INTEGER NOT NULL,
      used INTEGER NOT NULL DEFAULT 0,
      payload TEXT
    );
    CREATE TABLE IF NOT EXISTS products (
      id TEXT PRIMARY KEY,
      slug TEXT UNIQUE NOT NULL,
      title TEXT NOT NULL,
      category TEXT NOT NULL,
      description TEXT NOT NULL,
      long_description TEXT,
      price_from INTEGER NOT NULL,
      price_to INTEGER NOT NULL,
      features TEXT,
      images TEXT
    );
    CREATE TABLE IF NOT EXISTS reviews (
      id TEXT PRIMARY KEY,
      user_id TEXT,
      author_name TEXT NOT NULL,
      avatar_url TEXT,
      rating INTEGER NOT NULL,
      text TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS chat_messages (
      id TEXT PRIMARY KEY,
      from_user_id TEXT,
      to_user_id TEXT,
      is_dm INTEGER NOT NULL DEFAULT 0,
      text TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT,
      deleted_at TEXT
    );
  `)
  // Add missing columns if migrating existing DB
  const hasPwd = get("SELECT 1 as one FROM pragma_table_info('users') WHERE name='password_hash'")
  if (!hasPwd) {
    run('ALTER TABLE users ADD COLUMN password_hash TEXT')
  }
  const hasAdmin = get("SELECT 1 as one FROM pragma_table_info('users') WHERE name='is_admin'")
  if (!hasAdmin) {
    run('ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0')
  }
  const hasAvatar = get("SELECT 1 as one FROM pragma_table_info('users') WHERE name='avatar_url'")
  if (!hasAvatar) {
    run('ALTER TABLE users ADD COLUMN avatar_url TEXT')
  }
  const hasBanned = get("SELECT 1 as one FROM pragma_table_info('users') WHERE name='banned'")
  if (!hasBanned) {
    run('ALTER TABLE users ADD COLUMN banned INTEGER NOT NULL DEFAULT 0')
  }
  const hasBannedAt = get("SELECT 1 as one FROM pragma_table_info('users') WHERE name='banned_at'")
  if (!hasBannedAt) {
    run('ALTER TABLE users ADD COLUMN banned_at TEXT')
  }
  const hasBannedReason = get("SELECT 1 as one FROM pragma_table_info('users') WHERE name='banned_reason'")
  if (!hasBannedReason) {
    run('ALTER TABLE users ADD COLUMN banned_reason TEXT')
  }
  const hasBannedUntil = get("SELECT 1 as one FROM pragma_table_info('users') WHERE name='banned_until'")
  if (!hasBannedUntil) {
    run('ALTER TABLE users ADD COLUMN banned_until TEXT')
  }
  const hasPayload = get("SELECT 1 as one FROM pragma_table_info('otp_codes') WHERE name='payload'")
  if (!hasPayload) {
    run('ALTER TABLE otp_codes ADD COLUMN payload TEXT')
  }
  const hasUserIdOnReview = get("SELECT 1 as one FROM pragma_table_info('reviews') WHERE name='user_id'")
  if (!hasUserIdOnReview) {
    run('ALTER TABLE reviews ADD COLUMN user_id TEXT')
  }
  const hasChatUpdated = get("SELECT 1 as one FROM pragma_table_info('chat_messages') WHERE name='updated_at'")
  if (!hasChatUpdated) {
    run('ALTER TABLE chat_messages ADD COLUMN updated_at TEXT')
  }
  const hasChatDeleted = get("SELECT 1 as one FROM pragma_table_info('chat_messages') WHERE name='deleted_at'")
  if (!hasChatDeleted) {
    run('ALTER TABLE chat_messages ADD COLUMN deleted_at TEXT')
  }
  commit()
}

function run(sql, params = []) {
  const stmt = db.prepare(sql)
  stmt.bind(params)
  stmt.step()
  stmt.free()
  commit()
}

function get(sql, params = []) {
  const stmt = db.prepare(sql)
  stmt.bind(params)
  const row = stmt.step() ? stmt.getAsObject() : undefined
  stmt.free()
  return row
}

function all(sql, params = []) {
  const stmt = db.prepare(sql)
  stmt.bind(params)
  const rows = []
  while (stmt.step()) rows.push(stmt.getAsObject())
  stmt.free()
  return rows
}

export const simpleDB = { run, get, all }

export function seed() {
  // Seed or update admin user from env
  try {
    const adminEmail = process.env.ADMIN_EMAIL && String(process.env.ADMIN_EMAIL).trim()
    const adminNick = (process.env.ADMIN_NICKNAME && String(process.env.ADMIN_NICKNAME).trim()) || null
    const adminPassword = process.env.ADMIN_PASSWORD && String(process.env.ADMIN_PASSWORD)
    if (adminEmail && adminPassword) {
      const existingByEmail = get('SELECT * FROM users WHERE email = ?', [adminEmail])
      const existingByNick = adminNick ? get('SELECT * FROM users WHERE nickname = ?', [adminNick]) : null
      const now = new Date().toISOString()
      const hash = bcrypt.hashSync(adminPassword, 10)
      if (existingByEmail) {
        // Update existing admin
        run('UPDATE users SET is_admin = 1, email_verified = 1, password_hash = ?, nickname = COALESCE(?, nickname) WHERE id = ?', [hash, adminNick, existingByEmail.id])
      } else if (existingByNick) {
        run('UPDATE users SET is_admin = 1, email = ?, email_verified = 1, password_hash = ? WHERE id = ?', [adminEmail, hash, existingByNick.id])
      } else {
        const id = uuidv4()
        run('INSERT INTO users (id, email, nickname, email_verified, created_at, password_hash, is_admin, avatar_url) VALUES (?,?,?,?,?,?,?,?)', [id, adminEmail, adminNick || 'admin', 1, now, hash, 1, null])
      }
      commit()
    }
  } catch {}

  const cnt = get('SELECT COUNT(*) as c FROM products', [])?.c || 0
  if (cnt > 0) return
  const products = [
    { id: uuidv4(), slug: 'tg-bot-starter', title: 'Telegram-бот (Starter)', category: 'TG_BOT', description: 'Простой бот: команды, ответы, вебхуки.', long_description: 'Идеально для быстрых MVP и FAQ. Включает интеграцию с Telegram API, простую админку и логирование.', price_from: 10000, price_to: 20000, features: JSON.stringify(['Команды','Webhook','Логирование']), images: JSON.stringify(['/images/tg-bot-1.png']) },
    { id: uuidv4(), slug: 'tg-bot-pro', title: 'Telegram-бот (Pro)', category: 'TG_BOT', description: 'Бот с интеграцией API и оплатами.', long_description: 'Подключим оплаты, CRM, внешние API. Роли пользователей, мультиязычность и аналитика.', price_from: 20000, price_to: 60000, features: JSON.stringify(['Оплаты','Интеграции','Админка']), images: JSON.stringify(['/images/tg-bot-2.png']) },
    { id: uuidv4(), slug: 'website-landing', title: 'Сайт (Landing)', category: 'WEBSITE', description: 'Одностраничник с анимациями и SEO.', long_description: 'Красивые переливы, быстрая загрузка, адаптив. Подготовка мета-тегов и базовое SEO.', price_from: 25000, price_to: 50000, features: JSON.stringify(['SEO','Анимации','Дизайн']), images: JSON.stringify(['/images/site-landing.png']) },
    { id: uuidv4(), slug: 'website-corp', title: 'Сайт (Corporate)', category: 'WEBSITE', description: 'Многостраничный сайт с блогом.', long_description: 'Корпоративный сайт с CMS, блогом и формами. Ролевая модель доступа и интеграции.', price_from: 50000, price_to: 100000, features: JSON.stringify(['Блог','CMS','Формы']), images: JSON.stringify(['/images/site-corp.png']) },
    { id: uuidv4(), slug: 'crm-basic', title: 'CRM (Basic)', category: 'CRM', description: 'Базовая CRM для лидов и задач.', long_description: 'Карточки сделок, статусы, задачи и отчёты. Импорт/экспорт данных.', price_from: 30000, price_to: 60000, features: JSON.stringify(['Лиды','Задачи','Отчёты']), images: JSON.stringify(['/images/crm-basic.png']) },
    { id: uuidv4(), slug: 'crm-advanced', title: 'CRM (Advanced)', category: 'CRM', description: 'Расширенная CRM с ролями и интеграциями.', long_description: 'Расширенная аналитика, роли, интеграции с мессенджерами и платёжками.', price_from: 60000, price_to: 120000, features: JSON.stringify(['Роли','Интеграции','Дашборды']), images: JSON.stringify(['/images/crm-advanced.png']) },
    { id: uuidv4(), slug: 'mailer-tg-wa-basic', title: 'TG+WhatsApp рассылка (Basic)', category: 'TG_WA', description: 'Базовые рассылки по спискам.', long_description: 'Быстрый запуск рассылок, группы, шаблоны писем и статистика доставок.', price_from: 30000, price_to: 45000, features: JSON.stringify(['Списки','Шаблоны','Статистика']), images: JSON.stringify(['/images/mailer-basic.png']) },
    { id: uuidv4(), slug: 'mailer-tg-wa-pro', title: 'TG+WhatsApp рассылка (Pro)', category: 'TG_WA', description: 'Автоматизации и A/B тесты.', long_description: 'Автоворонки, сегментация, A/B тесты и экспорт данных. Поддержка вебхуков.', price_from: 45000, price_to: 65000, features: JSON.stringify(['Автоворонки','A/B тесты','Сегменты']), images: JSON.stringify(['/images/mailer-pro.png']) },
    { id: uuidv4(), slug: 'website-ecommerce', title: 'Сайт (E-commerce)', category: 'WEBSITE', description: 'Магазин с оплатами и каталогом.', long_description: 'Каталог, корзина, оплаты, кабинет пользователя. Интеграции с CRM.', price_from: 80000, price_to: 100000, features: JSON.stringify(['Каталог','Оплаты','ЛК']), images: JSON.stringify(['/images/site-shop.png']) },
    { id: uuidv4(), slug: 'tg-bot-crm', title: 'TG-бот + CRM', category: 'TG_BOT', description: 'Комплекс: бот для заявок + CRM.', long_description: 'Бот принимает заявки и отправляет их в CRM. Уведомления и аналитика.', price_from: 60000, price_to: 110000, features: JSON.stringify(['Синхронизация','Уведомления','Аналитика']), images: JSON.stringify(['/images/tg-bot-crm.png']) }
  ]
  for (const p of products) {
    run(`INSERT INTO products (id, slug, title, category, description, long_description, price_from, price_to, features, images) VALUES (?,?,?,?,?,?,?,?,?,?)`,
      [p.id, p.slug, p.title, p.category, p.description, p.long_description, p.price_from, p.price_to, p.features, p.images])
  }
  const reviews = [
    { id: uuidv4(), author_name: 'Иван', avatar_url: '/avatars/1.png', rating: 5, text: 'Отличная команда! Быстро и качественно.', created_at: '2024-06-01T10:00:00Z' },
    { id: uuidv4(), author_name: 'Анна', avatar_url: '/avatars/2.png', rating: 5, text: 'Сайт получился очень стильный.', created_at: '2024-06-12T12:00:00Z' },
    { id: uuidv4(), author_name: 'Олег', avatar_url: '/avatars/3.png', rating: 4, text: 'Бот закрывает все задачи.', created_at: '2024-07-03T08:30:00Z' },
    { id: uuidv4(), author_name: 'Мария', avatar_url: '/avatars/4.png', rating: 5, text: 'CRM ускорила работу отдела продаж.', created_at: '2024-08-20T09:20:00Z' },
    { id: uuidv4(), author_name: 'Дмитрий', avatar_url: '/avatars/5.png', rating: 4, text: 'Рассылка помогла вернуть клиентов.', created_at: '2024-09-01T15:45:00Z' }
  ]
  for (const r of reviews) {
    run(`INSERT INTO reviews (id, author_name, avatar_url, rating, text, created_at) VALUES (?,?,?,?,?,?)`, [r.id, r.author_name, r.avatar_url, r.rating, r.text, r.created_at])
  }
}

export { db }
