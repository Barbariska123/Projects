import express from 'express';
import cors from 'cors';
import cookieParser from 'cookie-parser';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
import rateLimit from 'express-rate-limit';

import authRouter from './routes/auth.js';
import productsRouter from './routes/products.js';
import reviewsRouter from './routes/reviews.js';
import { initDB, migrate, seed } from './db.js';
import { isMailConfigured, verifyMailer } from './mailer.js';
import adminRouter from './routes/admin.js';
import chatRouter from './routes/chat.js';
import fs from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..');
dotenv.config({ path: path.join(rootDir, '.env') });


const app = express();

const CLIENT_ORIGIN = process.env.APP_URL || 'http://localhost:5173';

const corsOptions = {
  origin: (origin, cb) => {
    if (!origin) return cb(null, true);
    try {
      const allow = [CLIENT_ORIGIN];
      if (CLIENT_ORIGIN.includes('localhost')) {
        allow.push(CLIENT_ORIGIN.replace('localhost', '127.0.0.1'));
      }
      if (allow.includes(origin)) return cb(null, true);
      // Allow any localhost/127.0.0.1 dev origin
      if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(origin)) return cb(null, true);
    } catch {}
    return cb(null, false);
  },
  credentials: true
};

app.use(cors(corsOptions));
app.use(express.json());
app.use(cookieParser());

const authLimiter = rateLimit({ windowMs: 15 * 60 * 1000, limit: 100 });
app.use('/api/auth', authLimiter);

// Static for uploads
const uploadsDir = path.join(rootDir, 'uploads');
if (!fs.existsSync(uploadsDir)) fs.mkdirSync(uploadsDir, { recursive: true });
app.use('/uploads', express.static(uploadsDir));

app.get('/api/health', (req, res) => res.json({ success: true, data: 'ok' }));
app.use('/api/auth', authRouter);
app.use('/api/products', productsRouter);
app.use('/api/reviews', reviewsRouter);
app.use('/api/admin', adminRouter);
app.use('/api/chat', chatRouter);

app.use((req, res) => {
  res.status(404).json({ success: false, error: 'Not found' });
});

const PORT = Number(process.env.PORT || 4000);

try {
  await initDB();
  migrate();
  seed();
} catch (e) {
  console.error('DB init error', e);
}

// Log mailer status (dev aid)
verifyMailer().then(ok => {
  const mode = isMailConfigured() ? 'configured' : 'not-configured';
  console.log(`[mail] ${mode}, verify=${ok}`);
}).catch(()=>{
  console.log('[mail] verify error');
});

function start(port, attempt = 1) {
  const server = app
    .listen(port, () => {
      console.log(`Server running on http://localhost:${port}`);
    })
    .on('error', (err) => {
      if (err && err.code === 'EADDRINUSE' && attempt < 3) {
        const next = port + 1;
        console.warn(`Port ${port} in use. Retrying on ${next}...`);
        start(next, attempt + 1);
      } else {
        console.error('Server listen error:', err);
        process.exit(1);
      }
    });
}

start(PORT);
