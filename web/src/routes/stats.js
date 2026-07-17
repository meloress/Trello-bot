/**
 * 10-band statistika/dashboard: `bot/services/stats_service.py`dagi
 * so'rovlar bilan BIR XIL mantiq (joriy oy, faol xodim, guruhlangan SQL),
 * lekin Node/JS'da qayta yozilgan — web/ Python kodini import qila olmaydi
 * (CLAUDE.md: faqat SQL/ORM darajasida bir xil mantiq takrorlanadi).
 */
const express = require('express');
const pool = require('../config/db');
const { requireAuth } = require('../auth');

const router = express.Router();
router.use(requireAuth);

function monthBounds(reference = new Date()) {
  const since = new Date(Date.UTC(reference.getUTCFullYear(), reference.getUTCMonth(), 1));
  const until = new Date(Date.UTC(reference.getUTCFullYear(), reference.getUTCMonth() + 1, 1));
  return { since, until };
}

const STATS_QUERY = `
  SELECT e.id, e.full_name,
    COALESCE(completed.cnt, 0)::int AS completed_tasks,
    COALESCE(scores.total, 0)::int AS total_score,
    COALESCE(penalties.cnt, 0)::int AS penalty_count
  FROM employees e
  LEFT JOIN (
    SELECT ta.employee_id, COUNT(DISTINCT t.id) AS cnt
    FROM task_assignments ta
    JOIN tasks t ON t.id = ta.task_id
    WHERE t.status = 'completed' AND t.finished_at >= $1 AND t.finished_at < $2
    GROUP BY ta.employee_id
  ) completed ON completed.employee_id = e.id
  LEFT JOIN (
    SELECT employee_id, SUM(score) AS total
    FROM kpi_logs
    WHERE created_at >= $1 AND created_at < $2
    GROUP BY employee_id
  ) scores ON scores.employee_id = e.id
  LEFT JOIN (
    SELECT employee_id, COUNT(*) AS cnt
    FROM kpi_logs
    WHERE created_at >= $1 AND created_at < $2 AND score < 0
    GROUP BY employee_id
  ) penalties ON penalties.employee_id = e.id
  WHERE e.is_active = true
`;

async function fetchMonthlyStats({ brigadeId } = {}) {
  const { since, until } = monthBounds();
  const params = [since, until];
  let query = STATS_QUERY;
  if (brigadeId) {
    params.push(brigadeId);
    query += ` AND e.brigade_id = $3`;
  }
  query += ' ORDER BY e.full_name';
  const { rows } = await pool.query(query, params);
  return { since, until, stats: rows };
}

router.get('/monthly', async (req, res) => {
  try {
    const result = await fetchMonthlyStats();
    res.json(result);
  } catch (err) {
    console.error('stats/monthly xatosi:', err);
    res.status(500).json({ error: 'Statistikani olishda xatolik' });
  }
});

router.get('/brigade/:id', async (req, res) => {
  const brigadeId = Number(req.params.id);
  if (!Number.isInteger(brigadeId)) {
    res.status(400).json({ error: "Noto'g'ri brigade id" });
    return;
  }
  try {
    const result = await fetchMonthlyStats({ brigadeId });
    res.json(result);
  } catch (err) {
    console.error('stats/brigade xatosi:', err);
    res.status(500).json({ error: 'Statistikani olishda xatolik' });
  }
});

router.get('/ranking', async (req, res) => {
  const limit = Math.min(Math.max(Number(req.query.limit) || 5, 1), 20);
  try {
    const { stats } = await fetchMonthlyStats();
    const best = [...stats].sort((a, b) => b.total_score - a.total_score).slice(0, limit);
    const worst = [...stats].sort((a, b) => b.penalty_count - a.penalty_count).slice(0, limit);
    res.json({ best, worst });
  } catch (err) {
    console.error('stats/ranking xatosi:', err);
    res.status(500).json({ error: 'Reytingni olishda xatolik' });
  }
});

router.get('/brigades', async (req, res) => {
  try {
    const { rows } = await pool.query('SELECT id, name FROM brigades ORDER BY name');
    res.json(rows);
  } catch (err) {
    console.error('stats/brigades xatosi:', err);
    res.status(500).json({ error: "Brigadalar ro'yxatini olishda xatolik" });
  }
});

module.exports = router;
