import jwt from 'jsonwebtoken';

export function requireAuth(req, res, next) {
  try {
    const auth = req.headers.authorization;
    let token = null;
    if (auth && auth.startsWith('Bearer ')) token = auth.slice(7);
    if (!token) return res.status(401).json({ success: false, error: 'Unauthorized' });
    const payload = jwt.verify(token, process.env.JWT_ACCESS_SECRET);
    req.user = payload;
    next();
  } catch (e) {
    return res.status(401).json({ success: false, error: 'Unauthorized' });
  }
}

