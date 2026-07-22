/* Melores Mebel — Telegram Mini App. Bitta sahifali ilova: navigatsiya
   stack orqali (Telegram BackButton bilan), asosiy amal doim Telegram
   native MainButton'da. Rol aniqlanishi serverdan (`GET /me`) keladi —
   foydalanuvchi faqat o'z rolining ekranlarini ko'radi. */

const API_BASE = "/api/miniapp";
const root = document.getElementById("app");
const state = { employee: null, lang: "uz" };
const nav = { stack: [] };
let mainButtonHandler = null;

const ROLE_LABELS = {
  uz: {
    worker: "👷 Ishchi", brigadier: "👨‍💼 Brigadir", supervisor: "🕵️ Nazoratchi",
    admin: "👔 Rahbar/Admin", observer: "👀 Kuzatuvchi", seller: "💼 Sotuvchi",
  },
  ru: {
    worker: "👷 Работник", brigadier: "👨‍💼 Бригадир", supervisor: "🕵️ Наблюдатель",
    admin: "👔 Руководитель", observer: "👀 Наблюдатель", seller: "💼 Продавец",
  },
};

function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function t(key, ...args) {
  const entry = I18N[state.lang][key];
  return typeof entry === "function" ? entry(...args) : entry ?? key;
}

function tg() {
  return window.Telegram && window.Telegram.WebApp;
}

function showError(message) {
  const app = tg();
  if (app && app.showAlert) app.showAlert(message);
  else window.alert(message);
}

function formatDt(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const tash = new Date(d.getTime() + 5 * 3600 * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(tash.getUTCDate())}.${pad(tash.getUTCMonth() + 1)}.${tash.getUTCFullYear()} ${pad(tash.getUTCHours())}:${pad(tash.getUTCMinutes())}`;
}

function daysUntil(iso) {
  if (!iso) return null;
  return Math.floor((new Date(iso).getTime() - Date.now()) / 86400000);
}

function statusClass(status) {
  return { active: "st-active", overdue: "st-overdue", stopped: "st-stopped", completed: "", pending_setup: "st-warn" }[status] || "";
}

function statusLabel(status) {
  return t({ active: "statusActive", overdue: "statusOverdue", stopped: "statusStopped", completed: "statusCompleted", pending_setup: "statusPendingSetup" }[status] || "statusActive");
}

async function api(path, opts = {}) {
  const app = tg();
  const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  if (app && app.initData) headers["X-Telegram-Init-Data"] = app.initData;
  const res = await fetch(API_BASE + path, Object.assign({}, opts, { headers }));
  let body = null;
  try {
    body = await res.json();
  } catch (e) {
    /* bo'sh javob */
  }
  if (!res.ok) {
    const error = new Error((body && body.error) || `HTTP ${res.status}`);
    error.status = res.status;
    throw error;
  }
  return body;
}

function setScreen(html) {
  root.innerHTML = html;
}

function hideMainButton() {
  const app = tg();
  if (!app) return;
  if (mainButtonHandler) {
    app.MainButton.offClick(mainButtonHandler);
    mainButtonHandler = null;
  }
  app.MainButton.hide();
}

function setMainButton(text, onClick, color) {
  const app = tg();
  if (!app) return;
  if (mainButtonHandler) app.MainButton.offClick(mainButtonHandler);
  mainButtonHandler = onClick;
  app.MainButton.setText(text);
  if (color) app.MainButton.setParams({ color });
  app.MainButton.onClick(mainButtonHandler);
  app.MainButton.show();
}

async function show(renderFn, ...args) {
  nav.stack.push([renderFn, args]);
  await renderCurrent();
}

async function goBack() {
  if (nav.stack.length > 1) {
    nav.stack.pop();
    await renderCurrent();
  }
}

async function resetTo(renderFn, ...args) {
  nav.stack = [[renderFn, args]];
  await renderCurrent();
}

async function renderCurrent() {
  const app = tg();
  if (app) {
    if (nav.stack.length > 1) app.BackButton.show();
    else app.BackButton.hide();
  }
  hideMainButton();
  const [fn, args] = nav.stack[nav.stack.length - 1];
  try {
    await fn(...args);
  } catch (e) {
    setScreen(`<p class="error-banner">${esc(e.message || t("error_generic"))}</p>`);
  }
}

/* ---------- Ishchi ekranlari ---------- */

async function screenWorkerHome() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const [orders, misc, score] = await Promise.all([
    api("/tasks"), api("/misctasks"), api("/score"),
  ]);
  const openTasks = [...orders, ...misc].filter((tsk) => tsk.deadline && (tsk.status === "active" || tsk.status === "overdue"));
  const nearest = openTasks.length
    ? openTasks.reduce((a, b) => (new Date(a.deadline) < new Date(b.deadline) ? a : b))
    : null;
  const nearestDays = nearest ? daysUntil(nearest.deadline) : null;

  setScreen(`
    <p class="greet-wave">${esc(t("greeting"))}</p>
    <p class="greet">${esc(state.employee.full_name)} 👋</p>
    <div class="hero-row">
      <div class="hero-tile ${score.total >= 0 ? "positive" : ""}"><span class="num">${score.total > 0 ? "+" : ""}${score.total}</span><span class="lbl">${esc(t("currentMonthScore"))}</span></div>
      <div class="hero-tile ${nearestDays !== null && nearestDays <= 1 ? "warn" : ""}"><span class="num">${nearestDays === null ? "—" : nearestDays <= 0 ? t("statusOverdue")[0] + "!" : nearestDays + "d"}</span><span class="lbl">${esc(t("nearestDeadline"))}</span></div>
    </div>
    <p class="section-lbl">${esc(t("sections"))}</p>
    <button class="nav-card" id="nav-orders"><span class="ic">📦</span><span class="grow">${esc(t("myOrders"))}</span><span class="badge">${orders.length}</span><span class="chev">›</span></button>
    <button class="nav-card" id="nav-misc"><span class="ic">📋</span><span class="grow">${esc(t("myTasks"))}</span><span class="badge">${misc.length}</span><span class="chev">›</span></button>
    <button class="nav-card" id="nav-score"><span class="ic">⭐</span><span class="grow">${esc(t("myScore"))}</span><span class="chev">›</span></button>
    <button class="nav-card" id="nav-profile"><span class="ic">👤</span><span class="grow">${esc(t("profile"))}</span><span class="chev">›</span></button>
  `);
  root.querySelector("#nav-orders").onclick = () => show(screenTaskList, "order");
  root.querySelector("#nav-misc").onclick = () => show(screenTaskList, "misc");
  root.querySelector("#nav-score").onclick = () => show(screenWorkerScore);
  root.querySelector("#nav-profile").onclick = () => show(screenProfile);
}

async function screenTaskList(kind) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const tasks = await api(kind === "order" ? "/tasks" : "/misctasks");
  if (!tasks.length) {
    setScreen(`<p class="page-title">${esc(kind === "order" ? t("myOrders") : t("myTasks"))}</p><p class="empty-state">${esc(kind === "order" ? t("noOrders") : t("noTasks"))}</p>`);
    return;
  }
  setScreen(`
    <p class="page-title">${esc(kind === "order" ? t("myOrders") : t("myTasks"))}</p>
    ${tasks.map((tsk, i) => `
      <button class="task-card ${statusClass(tsk.status)}" data-i="${i}">
        <p class="t-title">${esc(tsk.title)}</p>
        <p class="t-sub">${esc(tsk.department || "")}</p>
        <span class="t-status">${taskStatusLine(tsk)}</span>
      </button>
    `).join("")}
  `);
  root.querySelectorAll(".task-card").forEach((el) => {
    const tsk = tasks[Number(el.dataset.i)];
    el.onclick = () => show(screenTaskDetail, tsk.id);
  });
}

function taskStatusLine(tsk) {
  if (tsk.status === "stopped") return `🛑 ${esc(t("statusStopped"))}`;
  if (tsk.status === "overdue") {
    const days = tsk.deadline ? -daysUntil(tsk.deadline) : null;
    return `⚠ ${days ? esc(t("daysLate", days)) : esc(t("statusOverdue"))}`;
  }
  if (tsk.status === "active" && tsk.deadline) {
    const days = daysUntil(tsk.deadline);
    return `⏱ ${esc(t("daysLeft", days))}`;
  }
  return esc(statusLabel(tsk.status));
}

async function screenTaskDetail(taskId) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const tsk = await api(`/tasks/${taskId}`);
  const pillClass = tsk.status === "overdue" ? "critical" : tsk.status === "stopped" ? "neutral" : "positive";

  setScreen(`
    <p class="page-title">${esc(tsk.title)}</p>
    <span class="status-pill ${pillClass}">${esc(statusLabel(tsk.status))}</span>
    <div class="panel">
      <div class="kv-row"><span class="k">${esc(t("deadline"))}</span><span class="v">${esc(formatDt(tsk.deadline))}</span></div>
      ${tsk.status === "overdue" && tsk.deadline ? `<div class="kv-row"><span class="k">${esc(t("lateness"))}</span><span class="v">${-daysUntil(tsk.deadline)} kun</span></div>` : ""}
      <div class="kv-row"><span class="k">${esc(t("department"))}</span><span class="v">${esc(tsk.department || "—")}</span></div>
      ${tsk.client_name ? `<div class="kv-row"><span class="k">${esc(t("client"))}</span><span class="v">${esc(tsk.client_name)}</span></div>` : ""}
    </div>
    ${tsk.status === "active" ? `<button class="btn" id="btn-stop">🛑 ${esc(t("stop"))}</button>` : ""}
  `);

  const stopBtn = root.querySelector("#btn-stop");
  if (stopBtn) stopBtn.onclick = () => show(screenStopTask, taskId);

  if (tsk.status === "active") {
    setMainButton(`✅ ${t("finish")}`, async () => {
      const app = tg();
      app.MainButton.showProgress();
      try {
        await api(`/tasks/${taskId}/finish`, { method: "POST" });
        await show(screenTaskDetail, taskId);
      } catch (e) {
        showError(e.message);
      } finally {
        app.MainButton.hideProgress();
      }
    }, "#008300");
  } else if (tsk.status === "stopped") {
    setMainButton(`▶️ ${t("resume")}`, async () => {
      const app = tg();
      app.MainButton.showProgress();
      try {
        await api(`/tasks/${taskId}/resume`, { method: "POST" });
        await show(screenTaskDetail, taskId);
      } catch (e) {
        showError(e.message);
      } finally {
        app.MainButton.hideProgress();
      }
    });
  } else if (tsk.status === "pending_setup") {
    // Boshlash odatda admin/nazoratchi tomonidan sozlanadi (deadline/xodim),
    // shu bosqichda ishchi tomonidan amal yo'q.
  }
}

async function screenStopTask(taskId) {
  setScreen(`
    <p class="page-title">${esc(t("stopReasonPrompt"))}</p>
    <div class="field"><textarea id="reason" placeholder="${esc(t("stopReasonPlaceholder"))}"></textarea></div>
  `);
  setMainButton(`🛑 ${t("stop")}`, async () => {
    const reason = root.querySelector("#reason").value.trim();
    if (!reason) {
      showError(t("stopReasonPlaceholder"));
      return;
    }
    const app = tg();
    app.MainButton.showProgress();
    try {
      await api(`/tasks/${taskId}/stop`, { method: "POST", body: JSON.stringify({ reason }) });
      await goBack();
      await show(screenTaskDetail, taskId);
    } catch (e) {
      showError(e.message);
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#e34948");
}

async function screenWorkerScore() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const data = await api("/score");
  const maxAbs = Math.max(1, ...data.logs.map((l) => Math.abs(l.score)));

  setScreen(`
    <p class="page-title">${esc(t("myScore"))}</p>
    <div class="chart-box">
      <div class="chart-head"><span>${esc(t("currentMonth"))}</span><span class="big">${data.total > 0 ? "+" : ""}${data.total} ${state.lang === "ru" ? "баллов" : "ball"}</span></div>
      ${data.logs.slice(0, 12).map((l) => `
        <div class="bar-row ${l.score >= 0 ? "pos" : "neg"}">
          <span class="day">${formatDt(l.created_at).slice(0, 5)}</span>
          <div class="bar-track"><div class="bar-fill ${l.score >= 0 ? "pos" : "neg"}" style="width:${(Math.abs(l.score) / maxAbs) * 50}%"></div></div>
          <span class="val">${l.score > 0 ? "+" : ""}${l.score}</span>
        </div>
      `).join("")}
    </div>
    ${data.logs.length ? `<p class="section-lbl">${esc(t("details"))}</p>${data.logs.map((l) => `
      <div class="kpi-list-item ${l.score >= 0 ? "pos" : "neg"}">
        <span class="d">${formatDt(l.created_at).slice(0, 5)}</span>
        <span class="why">${esc(l.reason)}</span>
        <span class="amt">${l.score > 0 ? "+" : ""}${l.score}</span>
      </div>
    `).join("")}` : `<p class="empty-state">${esc(t("noScoreYet"))}</p>`}
  `);
}

/* ---------- Rahbar/Nazoratchi ekranlari ---------- */

async function screenAdminHome() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const d = await api("/admin/dashboard");
  setScreen(`
    <p class="page-title">${esc(t("dashboard"))}</p>
    <div class="hero-row">
      <div class="hero-tile"><span class="num">${d.active_employees}</span><span class="lbl">${esc(t("activeEmployees"))}</span></div>
      <div class="hero-tile positive"><span class="num">${d.completed_this_month}</span><span class="lbl">${esc(t("completedThisMonth"))}</span></div>
    </div>
    <div class="hero-row">
      <div class="hero-tile ${d.avg_score >= 0 ? "positive" : ""}"><span class="num">${d.avg_score > 0 ? "+" : ""}${d.avg_score}</span><span class="lbl">${esc(t("avgScore"))}</span></div>
      <div class="hero-tile"><span class="num" style="font-size:15px">${esc(d.top_performer || "—")}</span><span class="lbl">${esc(t("topPerformer"))}</span></div>
    </div>
    <p class="section-lbl">${esc(t("management"))}</p>
    <button class="nav-card accent" id="nav-newtask"><span class="ic">➕</span><span class="grow">${esc(t("newTask"))}</span><span class="chev">›</span></button>
    <button class="nav-card" id="nav-employees"><span class="ic">👥</span><span class="grow">${esc(t("employeesNav"))}</span><span class="chev">›</span></button>
    <button class="nav-card" id="nav-financial"><span class="ic">💰</span><span class="grow">${esc(t("financialNav"))}</span>${d.pending_financial ? `<span class="badge warn">${d.pending_financial}</span>` : ""}<span class="chev">›</span></button>
    <button class="nav-card" id="nav-profile"><span class="ic">👤</span><span class="grow">${esc(t("profile"))}</span><span class="chev">›</span></button>
  `);
  root.querySelector("#nav-newtask").onclick = () => show(screenNewTask);
  root.querySelector("#nav-employees").onclick = () => show(screenEmployees);
  root.querySelector("#nav-financial").onclick = () => show(screenFinancial);
  root.querySelector("#nav-profile").onclick = () => show(screenProfile);
}

async function screenNewTask() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const [departments, employees] = await Promise.all([
    api("/admin/departments"), api("/admin/employees"),
  ]);

  setScreen(`
    <p class="page-title">${esc(t("newTask"))}</p>
    <div class="field"><label>${esc(t("title"))}</label><input id="f-title" type="text" /></div>
    <div class="field"><label>${esc(t("description"))}</label><textarea id="f-desc"></textarea></div>
    <div class="field"><label>${esc(t("deadline"))}</label><input id="f-deadline" type="datetime-local" /></div>
    <div class="field"><label>${esc(t("departmentField"))}</label>
      <select id="f-dept"><option value="">—</option>${departments.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join("")}</select>
    </div>
    <p class="section-lbl">${esc(t("employeesField"))}</p>
    ${employees.filter((e) => e.is_active).map((e) => `
      <label class="check-row"><input type="checkbox" value="${e.id}" class="f-emp" />${esc(e.full_name)} — ${esc(e.role_label)}</label>
    `).join("")}
    <div class="field"><label>${esc(t("clientName"))}</label><input id="f-client-name" type="text" /></div>
    <div class="field"><label>${esc(t("clientPhone"))}</label><input id="f-client-phone" type="text" /></div>
  `);

  setMainButton(`➕ ${t("create")}`, async () => {
    const title = root.querySelector("#f-title").value.trim();
    const deptId = root.querySelector("#f-dept").value;
    const deadlineRaw = root.querySelector("#f-deadline").value;
    const empIds = Array.from(root.querySelectorAll(".f-emp:checked")).map((el) => Number(el.value));
    if (!title || !deptId || !deadlineRaw || !empIds.length) {
      showError(`${t("title")}, ${t("departmentField")}, ${t("deadline")}, ${t("employeesField")}`);
      return;
    }
    const app = tg();
    app.MainButton.showProgress();
    try {
      await api("/admin/tasks", {
        method: "POST",
        body: JSON.stringify({
          title,
          description: root.querySelector("#f-desc").value.trim() || null,
          deadline: new Date(deadlineRaw).toISOString(),
          department_id: Number(deptId),
          employee_ids: empIds,
          client_full_name: root.querySelector("#f-client-name").value.trim(),
          client_phone: root.querySelector("#f-client-phone").value.trim(),
        }),
      });
      app.HapticFeedback && app.HapticFeedback.notificationOccurred("success");
      await goBack();
    } catch (e) {
      showError(e.message);
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#2f6f62");
}

async function screenEmployees() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const employees = await api("/admin/employees");
  setScreen(`
    <p class="page-title">${esc(t("employeesNav"))} (${employees.length})</p>
    ${employees.map((e, i) => `
      <div class="emp-row" data-i="${i}">
        <span class="dot-status ${e.is_active ? "on" : "off"}"></span>
        <span class="grow"><div class="name">${esc(e.full_name)}</div><div class="role">${esc(e.role_label)}${e.department ? " · " + esc(e.department) : ""}</div></span>
      </div>
    `).join("")}
  `);
  setMainButton(`➕ ${t("addEmployee")}`, () => show(screenAddEmployee), "#2f6f62");
}

async function screenAddEmployee() {
  const departments = await api("/admin/departments");
  const roleOptions = Object.keys(ROLE_LABELS[state.lang])
    .map((r) => `<option value="${r}">${esc(ROLE_LABELS[state.lang][r])}</option>`).join("");

  setScreen(`
    <p class="page-title">${esc(t("addEmployee"))}</p>
    <div class="field"><label>${esc(t("fullName"))}</label><input id="f-name" type="text" /></div>
    <div class="field"><label>${esc(t("phoneNumber"))}</label><input id="f-phone" type="text" placeholder="+998901234567" /></div>
    <div class="field"><label>${esc(t("role"))}</label><select id="f-role">${roleOptions}</select></div>
    <div class="field"><label>${esc(t("departmentField"))}</label>
      <select id="f-dept"><option value="">—</option>${departments.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join("")}</select>
    </div>
    <div class="field"><label>${esc(t("trelloUsername"))}</label><input id="f-trello" type="text" /></div>
  `);

  setMainButton(`➕ ${t("create")}`, async () => {
    const fullName = root.querySelector("#f-name").value.trim();
    const phone = root.querySelector("#f-phone").value.trim();
    if (!fullName || !phone) {
      showError(t("fullName") + ", " + t("phoneNumber"));
      return;
    }
    const app = tg();
    app.MainButton.showProgress();
    try {
      await api("/admin/employees", {
        method: "POST",
        body: JSON.stringify({
          full_name: fullName,
          phone_number: phone,
          role: root.querySelector("#f-role").value,
          department_id: root.querySelector("#f-dept").value ? Number(root.querySelector("#f-dept").value) : null,
          trello_username: root.querySelector("#f-trello").value.trim() || null,
        }),
      });
      app.HapticFeedback && app.HapticFeedback.notificationOccurred("success");
      await goBack();
      await show(screenEmployees);
    } catch (e) {
      showError(e.message);
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#2f6f62");
}

async function screenFinancial() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const items = await api("/admin/financial");
  if (!items.length) {
    setScreen(`<p class="page-title">${esc(t("financialNav"))}</p><p class="empty-state">${esc(t("noPendingFinancial"))}</p>`);
    return;
  }
  setScreen(`
    <p class="page-title">${esc(t("financialNav"))}</p>
    ${items.map((s, i) => `
      <div class="fin-card" data-i="${i}">
        <div class="top"><span class="task">Task #${s.task_id}${s.task_title ? " — " + esc(s.task_title) : ""}</span><span class="status-pill warn">${esc(t(s.kind))}</span></div>
        ${s.kind === "wage_deduction" && s.suggested_deduction_amount === null ? `
          <div class="amount-row"><input type="number" class="f-amount" placeholder="${esc(t("enterAmount"))}" /><button class="btn primary f-amount-save">${esc(t("save"))}</button></div>
        ` : `<p class="desc">${s.suggested_deduction_amount !== null ? s.suggested_deduction_amount : s.waived_amount}</p>`}
      </div>
    `).join("")}
  `);
  root.querySelectorAll(".fin-card").forEach((card) => {
    const btn = card.querySelector(".f-amount-save");
    if (!btn) return;
    const item = items[Number(card.dataset.i)];
    btn.onclick = async () => {
      const value = card.querySelector(".f-amount").value;
      if (!value) return;
      try {
        await api(`/admin/financial/${item.id}/amount`, { method: "POST", body: JSON.stringify({ amount: Number(value) }) });
        await show(screenFinancial);
      } catch (e) {
        showError(e.message);
      }
    };
  });
}

/* ---------- Brigadir ekranlari ---------- */

async function screenBrigadierHome() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  let brigade;
  try {
    brigade = await api("/brigadier/brigade");
  } catch (e) {
    setScreen(`<p class="empty-state">${esc(t("noBrigade"))}</p>`);
    return;
  }
  setScreen(`
    <p class="page-title">${esc(t("brigade_title"))}: ${esc(brigade.name)}</p>
    ${brigade.members.map((m, i) => `
      <div class="member-card ${m.total_score < 0 ? "low" : m.total_score > 0 ? "high" : ""}" data-i="${i}">
        <div class="member-top"><span class="nm">${esc(m.full_name)}</span><span class="score ${m.total_score > 0 ? "pos" : m.total_score < 0 ? "neg" : "zero"}">${m.total_score > 0 ? "+" : ""}${m.total_score} ${state.lang === "ru" ? "б." : "ball"}</span></div>
        <div class="member-actions"><button class="btn-report">📅 ${esc(t("weeklyReport"))}</button><button class="btn-tasks">📋 ${esc(t("currentTasks"))}</button></div>
      </div>
    `).join("")}
    <button class="nav-card" id="nav-profile" style="margin-top:8px"><span class="ic">👤</span><span class="grow">${esc(t("profile"))}</span><span class="chev">›</span></button>
  `);
  root.querySelector("#nav-profile").onclick = () => show(screenProfile);
  root.querySelectorAll(".member-card").forEach((card) => {
    const member = brigade.members[Number(card.dataset.i)];
    card.querySelector(".btn-report").onclick = async (ev) => {
      ev.stopPropagation();
      const r = await api(`/brigadier/members/${member.employee_id}/report`);
      const app = tg();
      const msg = `${t("completedTasksLbl")}: ${r.completed_tasks}\n${t("totalScoreLbl")}: ${r.total_score > 0 ? "+" : ""}${r.total_score}\n${t("penaltyCountLbl")}: ${r.penalty_count}`;
      if (app && app.showPopup) app.showPopup({ title: r.full_name, message: msg, buttons: [{ type: "close" }] });
      else window.alert(`${r.full_name}\n${msg}`);
    };
    card.querySelector(".btn-tasks").onclick = (ev) => {
      ev.stopPropagation();
      show(screenMemberTasks, member.employee_id, member.full_name);
    };
  });
}

async function screenMemberTasks(employeeId, fullName) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const tasks = await api(`/brigadier/members/${employeeId}/tasks`);
  setScreen(`
    <p class="page-title">${esc(fullName)}</p>
    ${tasks.length ? tasks.map((tsk) => `
      <div class="task-card ${statusClass(tsk.status)}">
        <p class="t-title">${esc(tsk.title)}</p>
        <span class="t-status">${taskStatusLine(tsk)}</span>
      </div>
    `).join("") : `<p class="empty-state">${esc(t("noTasks"))}</p>`}
  `);
}

/* ---------- Sotuvchi ekranlari ---------- */

async function screenSellerHome(brand) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const brands = await api("/seller/brands");
  const activeBrand = brand || brands[0];
  const leads = await api(`/seller/leads?brand=${encodeURIComponent(activeBrand)}`);

  const stageOrder = ["new_lead", "contacted", "offer_sent", "agreed"];
  const groups = stageOrder.map((stage) => ({ stage, leads: leads.filter((l) => l.stage === stage) })).filter((g) => g.leads.length);

  setScreen(`
    <p class="page-title">${esc(t("myLeads"))}</p>
    <div class="lead-brand-row">${brands.map((b) => `<button class="brand-pill" data-brand="${b}" aria-selected="${b === activeBrand}">${esc(b[0].toUpperCase() + b.slice(1))}</button>`).join("")}</div>
    ${groups.length ? groups.map((g) => `
      <p class="stage-lbl">${esc(t("stage_" + g.stage))} <span class="cnt">(${g.leads.length})</span></p>
      ${g.leads.map((l, i) => `<button class="lead-card" data-id="${l.id}"><div class="n">${esc(l.client_name)}</div><div class="p">${esc(l.client_phone || "")}</div></button>`).join("")}
    `).join("<hr class=\"thin-rule\" />") : `<p class="empty-state">${esc(t("noLeads"))}</p>`}
    <button class="nav-card" id="nav-profile" style="margin-top:8px"><span class="ic">👤</span><span class="grow">${esc(t("profile"))}</span><span class="chev">›</span></button>
  `);
  root.querySelectorAll(".brand-pill").forEach((btn) => {
    btn.onclick = () => resetTo(screenSellerHome, btn.dataset.brand);
  });
  root.querySelectorAll(".lead-card").forEach((btn) => {
    btn.onclick = () => show(screenLeadDetail, Number(btn.dataset.id));
  });
  root.querySelector("#nav-profile").onclick = () => show(screenProfile);
}

async function screenLeadDetail(leadId) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const lead = await api(`/seller/leads/${leadId}`);
  const isOpen = lead.stage !== "closed_won" && lead.stage !== "closed_lost";
  const canAdvance = ["new_lead", "contacted", "offer_sent"].includes(lead.stage);

  setScreen(`
    <p class="page-title">${esc(lead.client_name)}</p>
    <span class="status-pill positive">${esc(t("stage_" + lead.stage))}</span>
    <div class="panel">
      <div class="kv-row"><span class="k">${esc(t("phone"))}</span><span class="v">${esc(lead.client_phone || "—")}</span></div>
      <div class="kv-row"><span class="k">${esc(t("lastContact"))}</span><span class="v">${esc(t("daysAgo", Math.max(0, -daysUntil(lead.last_contacted_at))))}</span></div>
    </div>
    <button class="btn" id="btn-call">📞 ${esc(t("addCall"))}</button>
    ${isOpen ? `<button class="btn danger" id="btn-close-lost">❌ ${esc(t("closeLost"))}</button><button class="btn primary" id="btn-close-won">✅ ${esc(t("closeWon"))}</button>` : ""}
  `);
  root.querySelector("#btn-call").onclick = () => show(screenAddCall, leadId);
  if (isOpen) {
    root.querySelector("#btn-close-won").onclick = () => closeLead(leadId, true);
    root.querySelector("#btn-close-lost").onclick = () => closeLead(leadId, false);
  }

  if (canAdvance) {
    setMainButton(`➡️ ${t("nextStage")}`, async () => {
      const app = tg();
      app.MainButton.showProgress();
      try {
        await api(`/seller/leads/${leadId}/advance`, { method: "POST" });
        await show(screenLeadDetail, leadId);
      } catch (e) {
        showError(e.message);
      } finally {
        app.MainButton.hideProgress();
      }
    });
  }
}

async function closeLead(leadId, won) {
  try {
    await api(`/seller/leads/${leadId}/close`, { method: "POST", body: JSON.stringify({ won }) });
    await show(screenLeadDetail, leadId);
  } catch (e) {
    showError(e.message);
  }
}

async function screenAddCall(leadId) {
  setScreen(`
    <p class="page-title">${esc(t("addCall"))}</p>
    <div class="field"><textarea id="f-content" placeholder="${esc(t("callPlaceholder"))}"></textarea></div>
  `);
  setMainButton(`📞 ${t("save")}`, async () => {
    const content = root.querySelector("#f-content").value.trim();
    if (!content) {
      showError(t("callPlaceholder"));
      return;
    }
    const app = tg();
    app.MainButton.showProgress();
    try {
      await api(`/seller/leads/${leadId}/calls`, { method: "POST", body: JSON.stringify({ content }) });
      await goBack();
      await show(screenLeadDetail, leadId);
    } catch (e) {
      showError(e.message);
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#2f6f62");
}

/* ---------- Profil (barcha rollar) ---------- */

async function screenProfile() {
  const me = state.employee;
  const initials = me.full_name.split(" ").map((w) => w[0]).slice(0, 2).join("");
  setScreen(`
    <p class="page-title">${esc(t("profile"))}</p>
    <div class="profile-head">
      <div class="avatar-circle">${esc(initials)}</div>
      <p class="greet" style="margin:2px 0 0">${esc(me.full_name)}</p>
      <p class="greet-wave" style="margin:0">${esc(me.role_label)}${me.brigade ? " · " + esc(me.brigade) : ""}</p>
    </div>
    <div class="panel">
      <div class="kv-row"><span class="k">${esc(t("phone"))}</span><span class="v">${esc(me.phone_number || "—")}</span></div>
      <div class="kv-row"><span class="k">${esc(t("department"))}</span><span class="v">${esc(me.department || "—")}</span></div>
    </div>
    <p class="section-lbl">${esc(t("language"))}</p>
    <div class="lang-row">
      <button class="lang-pill ${state.lang === "uz" ? "active" : ""}" data-lang="uz">🇺🇿 O'zbekcha</button>
      <button class="lang-pill ${state.lang === "ru" ? "active" : ""}" data-lang="ru">🇷🇺 Русский</button>
    </div>
  `);
  root.querySelectorAll(".lang-pill").forEach((btn) => {
    btn.onclick = async () => {
      const lang = btn.dataset.lang;
      if (lang === state.lang) return;
      state.lang = lang;
      try {
        await api("/me/language", { method: "POST", body: JSON.stringify({ language: lang }) });
      } catch (e) {
        /* jim: interfeys baribir yangi tilda ko'rsatiladi, keyingi safar qayta so'raladi */
      }
      await show(screenProfile);
    };
  });
}

/* ---------- Bootstrap ---------- */

function applyTheme(scheme) {
  document.documentElement.setAttribute("data-theme", scheme === "dark" ? "dark" : "light");
}

function routeHome() {
  const role = state.employee.role;
  if (role === "worker") resetTo(screenWorkerHome);
  else if (role === "admin" || role === "supervisor") resetTo(screenAdminHome);
  else if (role === "brigadier") resetTo(screenBrigadierHome);
  else if (role === "seller") resetTo(screenSellerHome);
  else resetTo(screenProfile);
}

async function bootstrap() {
  const app = tg();
  if (app) {
    app.ready();
    app.expand();
    applyTheme(app.colorScheme);
    app.onEvent("themeChanged", () => applyTheme(app.colorScheme));
    app.BackButton.onClick(goBack);
  } else {
    applyTheme("light");
  }

  try {
    state.employee = await api("/me");
    state.lang = state.employee.language || "uz";
  } catch (e) {
    setScreen(`<p class="error-banner">${e.status === 403 ? I18N.uz.not_registered : I18N.uz.error_generic}</p>`);
    return;
  }

  routeHome();
}

bootstrap();
