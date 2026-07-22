/**
 * 4.1-band "bitta oyna" printsipi: asosiy sahifa statistika jadvali+grafigi,
 * qo'shimcha bo'limlar (reyting, xodim qo'shish) MODAL oynada ochiladi,
 * chuqur navigatsiya yo'q.
 */
(function () {
  const loginScreen = document.getElementById('login-screen');
  const dashboardScreen = document.getElementById('dashboard-screen');
  const loginForm = document.getElementById('login-form');
  const loginError = document.getElementById('login-error');
  const brigadeFilter = document.getElementById('brigade-filter');
  const rankingBtn = document.getElementById('ranking-btn');
  const rankingModal = document.getElementById('ranking-modal');
  const rankingClose = document.getElementById('ranking-close');
  const logoutBtn = document.getElementById('logout-btn');
  const themeToggle = document.getElementById('theme-toggle');
  const tableBody = document.querySelector('#stats-table tbody');

  const addEmployeeBtn = document.getElementById('add-employee-btn');
  const employeeAddModal = document.getElementById('employee-add-modal');
  const employeeAddClose = document.getElementById('employee-add-close');
  const employeeAddForm = document.getElementById('employee-add-form');
  const employeeAddError = document.getElementById('employee-add-error');
  const employeeAddBack = document.getElementById('employee-add-back');
  const employeeAddNext = document.getElementById('employee-add-next');
  const employeeAddSubmit = document.getElementById('employee-add-submit');
  const eaDepartment = document.getElementById('ea-department');
  const eaBrigade = document.getElementById('ea-brigade');
  const eaRuler = document.getElementById('employee-add-ruler');

  const ROLE_LABELS = {
    worker: 'Ishchi',
    brigadier: 'Brigadir',
    supervisor: 'Nazoratchi',
    admin: 'Rahbar/Admin',
    observer: 'Kuzatuvchi',
    seller: 'Sotuvchi',
  };
  let eaStep = 1;
  const EA_STEPS = 5;
  const EA_FIELD_STEP = { full_name: 1, role: 2, trello: 4 };

  let chart = null;
  let lastStats = [];

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  /* ---------- Mavzu (light/dark) ---------- */

  function applyTheme(theme) {
    if (theme) {
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('theme', theme);
    } else {
      document.documentElement.removeAttribute('data-theme');
      localStorage.removeItem('theme');
    }
    if (lastStats.length) renderChart(lastStats);
  }

  function initTheme() {
    const saved = localStorage.getItem('theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
  }

  themeToggle.addEventListener('click', () => {
    const current =
      document.documentElement.getAttribute('data-theme') ||
      (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    applyTheme(current === 'dark' ? 'light' : 'dark');
  });

  initTheme();

  function showLogin() {
    loginScreen.classList.remove('hidden');
    dashboardScreen.classList.add('hidden');
  }

  function showDashboard() {
    loginScreen.classList.add('hidden');
    dashboardScreen.classList.remove('hidden');
  }

  async function api(path, options) {
    const res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    if (res.status === 401) {
      showLogin();
      throw new Error('unauthorized');
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const err = new Error(body.error || `HTTP ${res.status}`);
      err.field = body.field;
      throw err;
    }
    return res.json();
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function initials(fullName) {
    return fullName
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0].toUpperCase())
      .join('');
  }

  function scoreChip(score) {
    const cls = score > 0 ? 'positive' : score < 0 ? 'negative' : 'neutral';
    const sign = score > 0 ? '+' : '';
    return `<span class="chip ${cls}">${sign}${score}</span>`;
  }

  /* ---------- Jadval + tile'lar ---------- */

  function renderTable(stats) {
    tableBody.innerHTML = '';
    for (const s of stats) {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>
          <div class="person">
            <span class="avatar">${escapeHtml(initials(s.full_name))}</span>
            <div>
              <div class="person-name">${escapeHtml(s.full_name)}</div>
              <div class="person-role">${escapeHtml(ROLE_LABELS[s.role] || s.role || '')}</div>
            </div>
          </div>
        </td>
        <td class="num">${s.completed_tasks}</td>
        <td>${scoreChip(s.total_score)}</td>
        <td class="num">${s.penalty_count}</td>
      `;
      tableBody.appendChild(row);
    }
  }

  function renderTiles(stats) {
    const employeeCount = stats.length;
    const completedSum = stats.reduce((sum, s) => sum + s.completed_tasks, 0);
    const avgScore = employeeCount
      ? stats.reduce((sum, s) => sum + s.total_score, 0) / employeeCount
      : 0;
    const top = [...stats].sort((a, b) => b.total_score - a.total_score)[0];

    document.getElementById('tile-employees').textContent = employeeCount;
    document.getElementById('tile-completed').textContent = completedSum;
    document.getElementById('tile-avg-score').textContent =
      (avgScore > 0 ? '+' : '') + avgScore.toFixed(1);
    document.getElementById('tile-top-performer').textContent = top ? top.full_name : '—';
  }

  // Har bir chiziqning oxiriga qiymatni to'g'ridan-to'g'ri yozadi — CVD
  // foydalanuvchisi uchun rang emas, raqamning o'zi ishonchli signal beradi.
  const directLabelPlugin = {
    id: 'directLabel',
    afterDatasetsDraw(c) {
      const { ctx } = c;
      const meta = c.getDatasetMeta(0);
      const ink = cssVar('--ink') || '#1f2420';
      ctx.save();
      ctx.font = "600 12px 'IBM Plex Mono', monospace";
      ctx.fillStyle = ink;
      ctx.textBaseline = 'middle';
      meta.data.forEach((bar, i) => {
        const value = c.data.datasets[0].data[i];
        const label = (value > 0 ? '+' : '') + value;
        ctx.textAlign = value >= 0 ? 'left' : 'right';
        ctx.fillText(label, bar.x + (value >= 0 ? 6 : -6), bar.y);
      });
      ctx.restore();
    },
  };

  function renderChart(stats) {
    const canvas = document.getElementById('score-chart');
    const wrap = canvas.parentElement;
    const positive = cssVar('--positive') || '#008300';
    const negative = cssVar('--critical') || '#e34948';
    const gridColor = cssVar('--line') || '#dde0d4';
    const textColor = cssVar('--ink-soft') || '#57604f';
    const surface = cssVar('--surface') || '#ffffff';
    const inkColor = cssVar('--ink') || '#1f2420';

    // Eng yaxshi natijadan eng yomoniga — reyting sifatida o'qiladi, va uzun
    // ismlar gorizontal ustunlarda burilmasdan, to'liq o'qiladi.
    const sorted = [...stats].sort((a, b) => b.total_score - a.total_score);

    wrap.style.height = `${Math.max(180, sorted.length * 34 + 20)}px`;

    // Chizmaning eng chekka qiymatlaridan tashqarida joy qoldiramiz —
    // aks holda eng uzun ustunning to'g'ridan-to'g'ri yozilgan raqami
    // xodim ismi ustuniga tirqalib qoladi.
    const values = sorted.map((s) => s.total_score);
    const maxVal = Math.max(0, ...values);
    const minVal = Math.min(0, ...values);
    const pad = Math.max(1, Math.round((maxVal - minVal) * 0.18));

    const data = {
      labels: sorted.map((s) => s.full_name),
      datasets: [
        {
          data: sorted.map((s) => s.total_score),
          backgroundColor: sorted.map((s) => (s.total_score >= 0 ? positive : negative)),
          borderRadius: 3,
          barPercentage: 0.62,
          categoryPercentage: 0.9,
        },
      ],
    };
    const options = {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { right: 34, left: 4 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: surface,
          titleColor: inkColor,
          bodyColor: textColor,
          borderColor: gridColor,
          borderWidth: 1,
          padding: 10,
          titleFont: { family: "'IBM Plex Sans', sans-serif", weight: '600' },
          bodyFont: { family: "'IBM Plex Mono', monospace", size: 11 },
          callbacks: {
            label(item) {
              const s = sorted[item.dataIndex];
              const sign = s.total_score > 0 ? '+' : '';
              return [`Ball: ${sign}${s.total_score}`, `Bajarilgan: ${s.completed_tasks}`, `Jarima: ${s.penalty_count}`];
            },
          },
        },
      },
      scales: {
        x: {
          suggestedMin: minVal - pad,
          suggestedMax: maxVal + pad,
          ticks: { color: textColor, font: { family: "'IBM Plex Mono', monospace", size: 11 } },
          grid: { color: gridColor },
          border: { display: false },
        },
        y: {
          ticks: { color: textColor, font: { family: "'IBM Plex Sans', sans-serif", size: 12 } },
          grid: { display: false },
          border: { display: false },
        },
      },
    };
    if (chart) chart.destroy();
    chart = new Chart(canvas, { type: 'bar', data, options, plugins: [directLabelPlugin] });
  }

  async function loadStats(brigadeId) {
    const path = brigadeId ? `/api/stats/brigade/${brigadeId}` : '/api/stats/monthly';
    const { stats } = await api(path);
    lastStats = stats;
    renderTable(stats);
    renderTiles(stats);
    renderChart(stats);
  }

  async function loadBrigades() {
    try {
      const brigades = await api('/api/stats/brigades');
      for (const b of brigades) {
        const opt = document.createElement('option');
        opt.value = b.id;
        opt.textContent = b.name;
        brigadeFilter.appendChild(opt);
      }
    } catch (err) {
      console.error(err);
    }
  }

  async function openRanking() {
    try {
      const { best, worst } = await api('/api/stats/ranking?limit=5');
      const bestList = document.getElementById('ranking-best');
      const worstList = document.getElementById('ranking-worst');
      bestList.innerHTML = best
        .map(
          (s) =>
            `<li><span>${escapeHtml(s.full_name)}</span><span class="rank-score">${s.total_score > 0 ? '+' : ''}${s.total_score}</span></li>`
        )
        .join('');
      worstList.innerHTML = worst
        .map(
          (s) =>
            `<li><span>${escapeHtml(s.full_name)}</span><span class="rank-score">${s.penalty_count}</span></li>`
        )
        .join('');
      rankingModal.classList.remove('hidden');
    } catch (err) {
      if (err.message !== 'unauthorized') console.error(err);
    }
  }

  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    loginError.classList.add('hidden');
    const password = document.getElementById('login-password').value;
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || "Noto'g'ri parol");
      }
      showDashboard();
      await init();
    } catch (err) {
      loginError.textContent = err.message;
      loginError.classList.remove('hidden');
    }
  });

  logoutBtn.addEventListener('click', async () => {
    await fetch('/api/logout', { method: 'POST' });
    showLogin();
  });

  rankingBtn.addEventListener('click', openRanking);
  rankingClose.addEventListener('click', () => rankingModal.classList.add('hidden'));
  rankingModal.addEventListener('click', (e) => {
    if (e.target === rankingModal) rankingModal.classList.add('hidden');
  });

  brigadeFilter.addEventListener('change', () => {
    loadStats(brigadeFilter.value || null).catch((err) => {
      if (err.message !== 'unauthorized') console.error(err);
    });
  });

  /* ---------- Xodim qo'shish formasi ---------- */

  function eaShowStep(n) {
    eaStep = n;
    for (const el of employeeAddForm.querySelectorAll('.form-step')) {
      el.classList.toggle('hidden', Number(el.dataset.step) !== n);
    }
    for (const tick of eaRuler.querySelectorAll('.ruler-tick')) {
      const tickStep = Number(tick.dataset.step);
      tick.classList.toggle('done', tickStep < n);
      tick.classList.toggle('active', tickStep === n);
    }
    employeeAddBack.classList.toggle('hidden', n === 1);
    employeeAddNext.classList.toggle('hidden', n === EA_STEPS);
    employeeAddSubmit.classList.toggle('hidden', n !== EA_STEPS);
    if (n === EA_STEPS) eaFillSummary();
    employeeAddError.classList.add('hidden');
  }

  function eaFillSummary() {
    const name = document.getElementById('ea-full-name').value.trim();
    const phone = document.getElementById('ea-phone').value.trim();
    const role = ROLE_LABELS[document.getElementById('ea-role').value];
    const dept = eaDepartment.selectedOptions[0]?.textContent || '—';
    const brig = eaBrigade.selectedOptions[0]?.textContent || '—';
    const trello = document.getElementById('ea-trello').value.trim() || '—';
    document.getElementById('employee-add-summary').innerHTML = `
      <div><span>Ism</span><span>${escapeHtml(name)}</span></div>
      <div><span>Telefon</span><span>${escapeHtml(phone || '—')}</span></div>
      <div><span>Rol</span><span>${escapeHtml(role)}</span></div>
      <div><span>Yo'nalish</span><span>${escapeHtml(dept)} / ${escapeHtml(brig)}</span></div>
      <div><span>Bog'lanish</span><span>${escapeHtml(trello)}</span></div>
    `;
  }

  function eaValidateStep(n) {
    if (n === 1 && !document.getElementById('ea-full-name').value.trim()) {
      employeeAddError.textContent = 'Ism-familiya kiritilishi shart.';
      employeeAddError.classList.remove('hidden');
      return false;
    }
    return true;
  }

  employeeAddNext.addEventListener('click', () => {
    if (!eaValidateStep(eaStep)) return;
    if (eaStep < EA_STEPS) eaShowStep(eaStep + 1);
  });
  employeeAddBack.addEventListener('click', () => {
    if (eaStep > 1) eaShowStep(eaStep - 1);
  });

  eaDepartment.addEventListener('change', async () => {
    eaBrigade.innerHTML = '<option value="">—</option>';
    eaBrigade.disabled = true;
    if (!eaDepartment.value) return;
    try {
      const brigades = await api(`/api/employees/brigades?department_id=${eaDepartment.value}`);
      for (const b of brigades) {
        const opt = document.createElement('option');
        opt.value = b.id;
        opt.textContent = b.name;
        eaBrigade.appendChild(opt);
      }
      eaBrigade.disabled = false;
    } catch (err) {
      if (err.message !== 'unauthorized') console.error(err);
    }
  });

  function eaReset() {
    employeeAddForm.reset();
    eaBrigade.innerHTML = '<option value="">—</option>';
    eaBrigade.disabled = true;
    employeeAddError.classList.add('hidden');
    eaShowStep(1);
  }

  async function openEmployeeAdd() {
    eaReset();
    try {
      const departments = await api('/api/employees/departments');
      eaDepartment.innerHTML = '<option value="">—</option>';
      for (const d of departments) {
        const opt = document.createElement('option');
        opt.value = d.id;
        opt.textContent = d.name;
        eaDepartment.appendChild(opt);
      }
    } catch (err) {
      if (err.message !== 'unauthorized') console.error(err);
    }
    employeeAddModal.classList.remove('hidden');
  }

  addEmployeeBtn.addEventListener('click', openEmployeeAdd);
  employeeAddClose.addEventListener('click', () => employeeAddModal.classList.add('hidden'));
  employeeAddModal.addEventListener('click', (e) => {
    if (e.target === employeeAddModal) employeeAddModal.classList.add('hidden');
  });

  employeeAddForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      full_name: document.getElementById('ea-full-name').value.trim(),
      phone_number: document.getElementById('ea-phone').value.trim(),
      role: document.getElementById('ea-role').value,
      department_id: eaDepartment.value || null,
      brigade_id: eaBrigade.value || null,
      trello_or_gmail: document.getElementById('ea-trello').value.trim(),
    };
    try {
      await api('/api/employees', { method: 'POST', body: JSON.stringify(payload) });
      employeeAddModal.classList.add('hidden');
      eaReset();
      await loadStats(brigadeFilter.value || null);
    } catch (err) {
      if (err.message === 'unauthorized') return;
      const targetStep = EA_FIELD_STEP[err.field] || eaStep;
      eaShowStep(targetStep);
      employeeAddError.textContent = err.message;
      employeeAddError.classList.remove('hidden');
    }
  });

  async function init() {
    await loadBrigades();
    await loadStats(null);
  }

  // Sahifa ochilganda: sessiya cookie hali kuchidami tekshirish.
  api('/api/stats/monthly')
    .then(({ stats }) => {
      showDashboard();
      lastStats = stats;
      renderTable(stats);
      renderTiles(stats);
      renderChart(stats);
      loadBrigades();
    })
    .catch((err) => {
      if (err.message === 'unauthorized') showLogin();
    });
})();
