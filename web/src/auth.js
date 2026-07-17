/**
 * 4-band: web panelga kirish — bitta umumiy parol (.env WEB_ADMIN_PASSWORD),
 * foydalanuvchi tasdiqlagan qaror (4-bosqich). Login/parol jadvali yo'q,
 * shu sabab sessiya ham stateless: imzolangan cookie (HMAC-SHA256,
 * WEB_SESSION_SECRET bilan) — server qayta ishga tushsa ham session
 * saqlanib qoladi, alohida session-store/dependency kerak emas.
 */
const crypto = require('crypto');

const COOKIE_NAME = 'session';
const SESSION_TTL_MS = 12 * 60 * 60 * 1000; // 12 soat

function sign(payload) {
  const secret = process.env.WEB_SESSION_SECRET;
  return crypto.createHmac('sha256', secret).update(payload).digest('hex');
}

function issueToken() {
  const expiresAt = Date.now() + SESSION_TTL_MS;
  const payload = String(expiresAt);
  return `${payload}.${sign(payload)}`;
}

function isValidToken(token) {
  if (!token || typeof token !== 'string' || !token.includes('.')) return false;
  const [payload, signature] = token.split('.');
  const expected = sign(payload);
  const sigBuf = Buffer.from(signature, 'hex');
  const expBuf = Buffer.from(expected, 'hex');
  if (sigBuf.length !== expBuf.length || !crypto.timingSafeEqual(sigBuf, expBuf)) return false;
  return Number(payload) > Date.now();
}

function parseCookies(req) {
  const header = req.headers.cookie;
  const cookies = {};
  if (!header) return cookies;
  for (const part of header.split(';')) {
    const idx = part.indexOf('=');
    if (idx === -1) continue;
    cookies[part.slice(0, idx).trim()] = decodeURIComponent(part.slice(idx + 1).trim());
  }
  return cookies;
}

function requireAuth(req, res, next) {
  const token = parseCookies(req)[COOKIE_NAME];
  if (!isValidToken(token)) {
    res.status(401).json({ error: 'Avtorizatsiya talab qilinadi' });
    return;
  }
  next();
}

function login(req, res) {
  const adminPassword = process.env.WEB_ADMIN_PASSWORD;
  if (!adminPassword) {
    res.status(500).json({ error: 'WEB_ADMIN_PASSWORD sozlanmagan (.env)' });
    return;
  }

  const provided = Buffer.from(String(req.body?.password || ''));
  const expected = Buffer.from(adminPassword);
  const providedHash = crypto.createHash('sha256').update(provided).digest();
  const expectedHash = crypto.createHash('sha256').update(expected).digest();
  const match = crypto.timingSafeEqual(providedHash, expectedHash);

  if (!match) {
    res.status(401).json({ error: "Parol noto'g'ri" });
    return;
  }

  const token = issueToken();
  res.cookie(COOKIE_NAME, token, {
    httpOnly: true,
    sameSite: 'strict',
    maxAge: SESSION_TTL_MS,
  });
  res.json({ ok: true });
}

function logout(req, res) {
  res.clearCookie(COOKIE_NAME);
  res.json({ ok: true });
}

module.exports = { requireAuth, login, logout };
