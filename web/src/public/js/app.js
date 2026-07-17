/**
 * 4.1-band "bitta oyna" printsipi: asosiy sahifa statistika jadvali+grafigi,
 * qo'shimcha bo'limlar (reyting) MODAL oynada ochiladi, chuqur navigatsiya yo'q.
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
  const tableBody = document.querySelector('#stats-table tbody');

  let chart = null;

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
      throw new Error(body.error || `HTTP ${res.status}`);
    }
    return res.json();
  }

  function renderTable(stats) {
    tableBody.innerHTML = '';
    for (const s of stats) {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${escapeHtml(s.full_name)}</td>
        <td>${s.completed_tasks}</td>
        <td class="${s.total_score >= 0 ? 'positive' : 'negative'}">${s.total_score > 0 ? '+' : ''}${s.total_score}</td>
        <td>${s.penalty_count}</td>
      `;
      tableBody.appendChild(row);
    }
  }

  function renderChart(stats) {
    const ctx = document.getElementById('score-chart');
    const data = {
      labels: stats.map((s) => s.full_name),
      datasets: [
        {
          label: 'Jami ball (joriy oy)',
          data: stats.map((s) => s.total_score),
          backgroundColor: stats.map((s) => (s.total_score >= 0 ? '#2e7d32' : '#c62828')),
        },
      ],
    };
    if (chart) {
      chart.data = data;
      chart.update();
      return;
    }
    chart = new Chart(ctx, {
      type: 'bar',
      data,
      options: { responsive: true, plugins: { legend: { display: false } } },
    });
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  async function loadStats(brigadeId) {
    const path = brigadeId ? `/api/stats/brigade/${brigadeId}` : '/api/stats/monthly';
    const { stats } = await api(path);
    renderTable(stats);
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
        .map((s) => `<li>${escapeHtml(s.full_name)} — ${s.total_score > 0 ? '+' : ''}${s.total_score}</li>`)
        .join('');
      worstList.innerHTML = worst
        .map((s) => `<li>${escapeHtml(s.full_name)} — ${s.penalty_count} jarima</li>`)
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

  async function init() {
    await loadBrigades();
    await loadStats(null);
  }

  // Sahifa ochilganda: sessiya cookie hali kuchidami tekshirish.
  api('/api/stats/monthly')
    .then(({ stats }) => {
      showDashboard();
      renderTable(stats);
      renderChart(stats);
      loadBrigades();
    })
    .catch((err) => {
      if (err.message === 'unauthorized') showLogin();
    });
})();
