import { Router } from 'express';
import { simpleDB, seed as seedDb } from '../db.js';

const router = Router();

router.get('/', (req, res) => {
  let rows = simpleDB.all('SELECT * FROM products ORDER BY title');
  if (!rows || rows.length === 0) {
    try { seedDb(); rows = simpleDB.all('SELECT * FROM products ORDER BY title') } catch {}
  }
  const items = rows.map(r => ({
    id: r.id,
    slug: r.slug,
    title: r.title,
    category: r.category,
    description: r.description,
    longDescription: r.long_description,
    priceFrom: r.price_from,
    priceTo: r.price_to,
    features: r.features ? JSON.parse(r.features) : [],
    images: r.images ? JSON.parse(r.images) : []
  }));
  res.json({ success: true, data: items });
});

router.get('/:slug', (req, res) => {
  let r = simpleDB.get('SELECT * FROM products WHERE slug = ?', [req.params.slug]);
  if (!r) {
    try { seedDb(); r = simpleDB.get('SELECT * FROM products WHERE slug = ?', [req.params.slug]) } catch {}
  }
  if (!r) return res.status(404).json({ success: false, error: 'Not found' });
  const item = {
    id: r.id,
    slug: r.slug,
    title: r.title,
    category: r.category,
    description: r.description,
    longDescription: r.long_description,
    priceFrom: r.price_from,
    priceTo: r.price_to,
    features: r.features ? JSON.parse(r.features) : [],
    images: r.images ? JSON.parse(r.images) : []
  };
  res.json({ success: true, data: item });
});

export default router;
