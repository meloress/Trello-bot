/**
 * Xodim qo'shish (5.1-band) — web panelda birinchi marta. Validatsiya
 * `bot/services/employee_service.py` + `handlers/admin/employee_management.py`
 * qoidalarini takrorlaydi (CLAUDE.md: web/ Python kodini import qila olmaydi,
 * mantiq qo'lda takrorlanadi — stats.js'dagi bilan bir xil naqsh).
 */
const express = require('express');
const pool = require('../config/db');
const { requireAuth } = require('../auth');
const { getMemberId, TrelloLookupError } = require('../trello');

const router = express.Router();
router.use(requireAuth);

const VALID_ROLES = ['admin', 'supervisor', 'brigadier', 'worker', 'seller', 'observer'];
const PHONE_RE = /^\+?\d{7,15}$/;

function nextPaymentDate() {
  // Employee modelidagi Python-side default (oyning 15-kuni) — DB default
  // emas, shu sababli bu yerda qo'lda hisoblanishi shart.
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 15));
}

router.get('/departments', async (req, res) => {
  try {
    const { rows } = await pool.query('SELECT id, name FROM departments ORDER BY name');
    res.json(rows);
  } catch (err) {
    console.error('employees/departments xatosi:', err);
    res.status(500).json({ error: "Yo'nalishlar ro'yxatini olishda xatolik" });
  }
});

router.get('/brigades', async (req, res) => {
  const departmentId = Number(req.query.department_id);
  if (!Number.isInteger(departmentId)) {
    res.status(400).json({ error: "Noto'g'ri department_id" });
    return;
  }
  try {
    const { rows } = await pool.query(
      'SELECT id, name FROM brigades WHERE department_id = $1 ORDER BY name',
      [departmentId]
    );
    res.json(rows);
  } catch (err) {
    console.error('employees/brigades xatosi:', err);
    res.status(500).json({ error: "Brigadalar ro'yxatini olishda xatolik" });
  }
});

router.post('/', async (req, res) => {
  const fullName = String(req.body?.full_name || '').trim();
  const rawPhone = String(req.body?.phone_number || '').trim();
  const role = String(req.body?.role || '').trim();
  const departmentId = req.body?.department_id ? Number(req.body.department_id) : null;
  const brigadeId = req.body?.brigade_id ? Number(req.body.brigade_id) : null;
  const trelloOrGmail = String(req.body?.trello_or_gmail || '').trim();

  if (!fullName) {
    res.status(400).json({ error: "Ism-familiya bo'sh bo'lishi mumkin emas", field: 'full_name' });
    return;
  }

  const phone = rawPhone.replace(/[\s-]/g, '');
  if (phone && !PHONE_RE.test(phone)) {
    res.status(400).json({
      error: "Telefon format noto'g'ri (masalan: +998901234567)",
      field: 'full_name',
    });
    return;
  }

  if (!VALID_ROLES.includes(role)) {
    res.status(400).json({ error: "Noma'lum rol", field: 'role' });
    return;
  }

  try {
    const dup = await pool.query('SELECT id FROM employees WHERE full_name ILIKE $1', [fullName]);
    if (dup.rows.length > 0) {
      res.status(409).json({ error: "Bu ism bilan xodim allaqachon mavjud", field: 'full_name' });
      return;
    }

    if (phone) {
      const dupPhone = await pool.query('SELECT id FROM employees WHERE phone_number = $1', [phone]);
      if (dupPhone.rows.length > 0) {
        res.status(409).json({ error: 'Bu telefon raqami allaqachon mavjud', field: 'full_name' });
        return;
      }
    }

    let trelloUsername = null;
    let trelloMemberId = null;
    let gmail = null;

    if (trelloOrGmail.includes('@')) {
      gmail = trelloOrGmail;
    } else if (trelloOrGmail) {
      try {
        trelloMemberId = await getMemberId(trelloOrGmail);
        trelloUsername = trelloOrGmail;
      } catch (err) {
        if (err instanceof TrelloLookupError && err.status === 404) {
          res.status(400).json({ error: 'Bunday Trello username topilmadi', field: 'trello' });
          return;
        }
        console.error('Trello lookup xatosi:', err);
        res.status(502).json({ error: "Trello bilan bog'lanishda xatolik. Birozdan keyin qayta urinib ko'ring." });
        return;
      }
    }

    const { rows } = await pool.query(
      `INSERT INTO employees
         (full_name, phone_number, role, department_id, brigade_id, trello_username, trello_member_id, gmail, next_payment_date, is_active)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, true)
       RETURNING id, full_name, role, department_id, brigade_id, trello_username, gmail`,
      [fullName, phone || null, role, departmentId, brigadeId, trelloUsername, trelloMemberId, gmail, nextPaymentDate()]
    );

    res.status(201).json(rows[0]);
  } catch (err) {
    console.error('employees/create xatosi:', err);
    res.status(500).json({ error: "Xodim qo'shishda xatolik" });
  }
});

module.exports = router;
