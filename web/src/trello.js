/**
 * `bot/trello/client.py`ning Node ekvivalenti — faqat xodim qo'shish formasi
 * uchun kerak bo'lgan bitta chaqiruv (username -> member id). Global `fetch`
 * (Node 18+) yetarli, yangi paket kerak emas.
 */
const TRELLO_BASE = 'https://api.trello.com/1';

class TrelloLookupError extends Error {
  constructor(status, body) {
    super(`Trello API xatosi (status=${status})`);
    this.status = status;
    this.body = body;
  }
}

async function getMemberId(username) {
  const url = `${TRELLO_BASE}/members/${encodeURIComponent(username)}?key=${process.env.TRELLO_API_KEY}&token=${process.env.TRELLO_TOKEN}&fields=id`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new TrelloLookupError(res.status, await res.text().catch(() => ''));
  }
  const data = await res.json();
  return data.id;
}

module.exports = { getMemberId, TrelloLookupError };
