/* Melores Mebel — Telegram Mini App. Bitta sahifali ilova: navigatsiya
   stack orqali (Telegram BackButton bilan), asosiy amal doim Telegram
   native MainButton'da. Rol aniqlanishi serverdan (`GET /me`) keladi —
   foydalanuvchi faqat o'z rolining ekranlarini ko'radi. */

const API_BASE = "/api/miniapp";
const root = document.getElementById("app");
const tabbarRoot = document.getElementById("tabbar");
const state = { employee: null, lang: "uz" };
const nav = { stack: [], section: null };
let mainButtonHandler = null;

/* Rol bo'yicha pastki tab-bar ta'rifi — har biri {key, icon, label, screen}.
   Birinchi element doim shu rolning "uy" ekrani (routeHome() shundan foydalanadi). */
function tabDefsForRole(role) {
  if (role === "worker") {
    return [
      { key: "orders", icon: "📦", label: "tab_orders", screen: screenWorkerOrders },
      { key: "tasks", icon: "📋", label: "tab_tasks", screen: () => screenTaskList("misc") },
      { key: "score", icon: "⭐", label: "tab_score", screen: screenWorkerScore },
      { key: "profile", icon: "👤", label: "tab_profile", screen: screenProfile },
    ];
  }
  if (role === "admin" || role === "supervisor") {
    return [
      { key: "home", icon: "🏠", label: "tab_home", screen: screenAdminHome },
      { key: "stats", icon: "📊", label: "tab_stats", screen: screenFullStats },
      { key: "employees", icon: "👥", label: "tab_employees", screen: screenEmployees },
      { key: "financial", icon: "💰", label: "tab_financial", screen: screenFinancial },
      { key: "profile", icon: "👤", label: "tab_profile", screen: screenProfile },
    ];
  }
  if (role === "brigadier") {
    return [
      { key: "brigade", icon: "👥", label: "tab_brigade", screen: screenBrigadierHome },
      { key: "profile", icon: "👤", label: "tab_profile", screen: screenProfile },
    ];
  }
  if (role === "seller") {
    return [
      { key: "leads", icon: "💼", label: "tab_leads", screen: () => screenSellerHome() },
      { key: "profile", icon: "👤", label: "tab_profile", screen: screenProfile },
    ];
  }
  return [{ key: "profile", icon: "👤", label: "tab_profile", screen: screenProfile }];
}

function switchTab(tabKey, screenFn) {
  nav.section = tabKey;
  resetTo(screenFn);
}

function renderTabBar() {
  if (!tabbarRoot) return;
  const defs = tabDefsForRole(state.employee ? state.employee.role : null);
  if (defs.length < 2) {
    tabbarRoot.innerHTML = "";
    return;
  }
  tabbarRoot.innerHTML = `
    <nav class="tab-bar">
      ${defs.map((d) => `
        <button class="tab-item" data-key="${d.key}" aria-selected="${d.key === nav.section}">
          <span class="tab-ic">${d.icon}</span><span class="tab-lbl">${esc(t(d.label))}</span>
        </button>
      `).join("")}
    </nav>
  `;
  defs.forEach((d) => {
    tabbarRoot.querySelector(`[data-key="${d.key}"]`).onclick = () => switchTab(d.key, d.screen);
  });
}

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

/* Joriy ekranni (stackning eng ustidagi yozuvini) YANGI ma'lumot bilan
   qayta chizadi — orqaga qaytishni yo'qotmaydi (resetTo kabi butun stackni
   o'chirmaydi) va stackni o'smaydi (show kabi ustiga qo'shib bormaydi).
   "Shu ekranni o'zini yangilash" holatlari uchun (masalan bir amaldan keyin
   yoki forma turini almashtirganda) mo'ljallangan. */
async function replaceTop(renderFn, ...args) {
  nav.stack[nav.stack.length - 1] = [renderFn, args];
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
  renderTabBar();
}

/* ---------- Ishchi ekranlari ---------- */

async function screenWorkerOrders() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const [orders, score] = await Promise.all([api("/tasks"), api("/score")]);
  const openTasks = orders.filter((tsk) => tsk.deadline && (tsk.status === "active" || tsk.status === "overdue"));
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
    <p class="section-lbl">${esc(t("myOrders"))}</p>
    ${orders.length ? orders.map((tsk, i) => `
      <button class="task-card ${statusClass(tsk.status)}" data-i="${i}">
        <p class="t-title">${esc(tsk.title)}</p>
        <p class="t-sub">${esc(tsk.department || "")}</p>
        <span class="t-status">${taskStatusLine(tsk)}</span>
      </button>
    `).join("") : `<p class="empty-state">${esc(t("noOrders"))}</p>`}
  `);
  root.querySelectorAll(".task-card").forEach((el) => {
    const tsk = orders[Number(el.dataset.i)];
    el.onclick = () => show(screenTaskDetail, tsk.id);
  });
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
        await replaceTop(screenTaskDetail, taskId);
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
        await replaceTop(screenTaskDetail, taskId);
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
  const [d, pendingSetup, reassignCandidates] = await Promise.all([
    api("/admin/dashboard"), api("/admin/pending-setup"), api("/admin/reassign-candidates"),
  ]);
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
    <button class="nav-card accent" id="nav-newtask"><span class="ic">➕</span><span class="grow">${esc(t("newTaskCta"))}</span><span class="chev">›</span></button>
    ${pendingSetup.length ? `<button class="alert-card" id="nav-pending-setup"><span class="ic">⏳</span><span class="grow">${esc(t("pendingSetupAlert", pendingSetup.length))}</span><span class="chev">›</span></button>` : ""}
    ${reassignCandidates.length ? `<button class="alert-card" id="nav-reassign"><span class="ic">🔁</span><span class="grow">${esc(t("reassignAlert", reassignCandidates.length))}</span><span class="chev">›</span></button>` : ""}
  `);
  root.querySelector("#nav-newtask").onclick = () => show(screenNewTaskForm);
  const pendingBtn = root.querySelector("#nav-pending-setup");
  if (pendingBtn) pendingBtn.onclick = () => show(screenPendingSetup);
  const reassignBtn = root.querySelector("#nav-reassign");
  if (reassignBtn) reassignBtn.onclick = () => show(screenReassignList);
}

async function screenNewTaskForm(kind) {
  kind = kind || "order";
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const [departments, employees] = await Promise.all([
    api("/admin/departments"), api("/admin/employees"),
  ]);
  const activeEmployees = employees.filter((e) => e.is_active);
  let selectedBrigadierId = null;

  async function renderBrigadierPicker(departmentId) {
    const container = root.querySelector("#brigadier-picker");
    if (!container) return;
    selectedBrigadierId = null;
    if (!departmentId) {
      container.innerHTML = `<p class="hint">${esc(t("pickDepartmentFirst"))}</p>`;
      return;
    }
    container.innerHTML = `<p class="loading">${esc(t("loading"))}</p>`;
    const brigadiers = await api(`/admin/departments/${departmentId}/brigadiers`);
    if (!brigadiers.length) {
      container.innerHTML = `<p class="empty-state">${esc(t("noBrigadierInDept"))}</p>`;
      return;
    }
    container.innerHTML = brigadiers.map((b, i) => `
      <button class="radio-row" data-i="${i}">${esc(b.brigadier_name)} <span class="hint">(${esc(b.brigade_name)})</span></button>
    `).join("");
    container.querySelectorAll(".radio-row").forEach((el) => {
      const b = brigadiers[Number(el.dataset.i)];
      el.onclick = () => {
        selectedBrigadierId = b.brigadier_id;
        container.querySelectorAll(".radio-row").forEach((r) => r.setAttribute("aria-selected", r === el));
      };
    });
  }

  setScreen(`
    <p class="page-title">${esc(t("newTask"))}</p>
    <div class="segmented" id="type-toggle">
      <button data-kind="order" aria-selected="${kind === "order"}">${esc(t("orderType"))}</button>
      <button data-kind="misc" aria-selected="${kind === "misc"}">${esc(t("miscType"))}</button>
    </div>
    ${kind === "order" ? `
      <div class="field"><label>${esc(t("title"))}</label><input id="f-title" type="text" /></div>
      <div class="field"><label>${esc(t("description"))}</label><textarea id="f-desc"></textarea></div>
      <div class="field"><label>${esc(t("deadline"))}</label><input id="f-deadline" type="datetime-local" /></div>
      <div class="field"><label>${esc(t("departmentField"))}</label>
        <select id="f-dept"><option value="">—</option>${departments.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join("")}</select>
      </div>
      <p class="section-lbl">${esc(t("brigadierField"))}</p>
      <div id="brigadier-picker"><p class="hint">${esc(t("pickDepartmentFirst"))}</p></div>
      <div class="field"><label>${esc(t("clientName"))}</label><input id="f-client-name" type="text" /></div>
      <div class="field"><label>${esc(t("clientPhone"))}</label><input id="f-client-phone" type="text" /></div>
    ` : `
      <div class="field"><label>${esc(t("miscTaskText"))}</label><input id="f-text" type="text" placeholder="${esc(t("miscTaskTextPh"))}" /></div>
      <div class="field"><label>${esc(t("deadline"))}</label><input id="f-deadline" type="datetime-local" /></div>
      <p class="section-lbl">${esc(t("employeesField"))} (≤3)</p>
      ${activeEmployees.map((e) => `
        <label class="check-row"><input type="checkbox" value="${e.id}" class="f-emp" />${esc(e.full_name)} — ${esc(e.role_label)}</label>
      `).join("")}
    `}
  `);

  root.querySelectorAll("#type-toggle button").forEach((btn) => {
    btn.onclick = () => replaceTop(screenNewTaskForm, btn.dataset.kind);
  });

  if (kind === "order") {
    root.querySelector("#f-dept").onchange = (ev) => renderBrigadierPicker(ev.target.value);

    setMainButton(`➕ ${t("create")}`, async () => {
      const title = root.querySelector("#f-title").value.trim();
      const deptId = root.querySelector("#f-dept").value;
      const deadlineRaw = root.querySelector("#f-deadline").value;
      if (!title || !deptId || !deadlineRaw || !selectedBrigadierId) {
        showError(`${t("title")}, ${t("departmentField")}, ${t("deadline")}, ${t("brigadierField")}`);
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
            brigadier_id: selectedBrigadierId,
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
  } else {
    setMainButton(`➕ ${t("create")}`, async () => {
      const text = root.querySelector("#f-text").value.trim();
      const deadlineRaw = root.querySelector("#f-deadline").value;
      const empIds = Array.from(root.querySelectorAll(".f-emp:checked")).map((el) => Number(el.value));
      if (!text || !deadlineRaw || !empIds.length) {
        showError(`${t("miscTaskText")}, ${t("deadline")}, ${t("employeesField")}`);
        return;
      }
      const app = tg();
      app.MainButton.showProgress();
      try {
        await api("/admin/misctasks", {
          method: "POST",
          body: JSON.stringify({ text, deadline: new Date(deadlineRaw).toISOString(), employee_ids: empIds }),
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
}

async function screenEmployees() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const employees = await api("/admin/employees");
  setScreen(`
    <p class="page-title">${esc(t("employeesNav"))} (${employees.length})</p>
    ${employees.map((e, i) => `
      <button class="emp-row" data-i="${i}">
        <span class="dot-status ${e.is_active ? "on" : "off"}"></span>
        <span class="grow"><div class="name">${esc(e.full_name)}</div><div class="role">${esc(e.role_label)}${e.department ? " · " + esc(e.department) : ""}</div></span>
        <span class="chev">›</span>
      </button>
    `).join("")}
  `);
  root.querySelectorAll(".emp-row").forEach((el) => {
    const emp = employees[Number(el.dataset.i)];
    el.onclick = () => show(screenEmployeeDetail, emp.id);
  });
  setMainButton(`➕ ${t("addEmployee")}`, () => show(screenAddEmployee), "#2f6f62");
}

async function screenEmployeeDetail(employeeId) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const [employee, departments] = await Promise.all([
    api(`/admin/employees/${employeeId}`), api("/admin/departments"),
  ]);
  const roleOptions = Object.keys(ROLE_LABELS[state.lang])
    .map((r) => `<option value="${r}" ${r === employee.role ? "selected" : ""}>${esc(ROLE_LABELS[state.lang][r])}</option>`).join("");

  async function renderBrigadeOptions(departmentId, selectedBrigadeId) {
    if (!departmentId) return `<option value="">—</option>`;
    const brigades = await api(`/admin/brigades?department_id=${departmentId}`);
    return (
      `<option value="">—</option>` +
      brigades.map((b) => `<option value="${b.id}" ${b.id === selectedBrigadeId ? "selected" : ""}>${esc(b.name)}</option>`).join("")
    );
  }
  const brigadeOptions = await renderBrigadeOptions(employee.department_id, employee.brigade_id);

  setScreen(`
    <p class="page-title">${esc(employee.full_name)}</p>
    <span class="status-pill ${employee.is_active ? "positive" : "neutral"}">${employee.is_active ? esc(t("activate")) : esc(t("deactivate"))}</span>
    <div class="field"><label>${esc(t("fullName"))}</label><input id="f-name" type="text" value="${esc(employee.full_name)}" /></div>
    <div class="field"><label>${esc(t("phoneNumber"))}</label><input id="f-phone" type="text" value="${esc(employee.phone_number || "")}" /></div>
    <div class="field"><label>${esc(t("trelloUsername"))}</label><input id="f-trello" type="text" value="${esc(employee.trello_username || "")}" /></div>
    <div class="field"><label>${esc(t("role"))}</label><select id="f-role">${roleOptions}</select></div>
    <div class="field"><label>${esc(t("departmentField"))}</label>
      <select id="f-dept"><option value="">—</option>${departments.map((d) => `<option value="${d.id}" ${d.id === employee.department_id ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select>
    </div>
    <div class="field"><label>${esc(t("brigade"))}</label><select id="f-brigade">${brigadeOptions}</select></div>
    <button class="btn ${employee.is_active ? "danger" : "primary"}" id="btn-toggle">${employee.is_active ? esc(t("deactivate")) : esc(t("activate"))}</button>
  `);

  root.querySelector("#f-dept").onchange = async (ev) => {
    const brigadeSelect = root.querySelector("#f-brigade");
    brigadeSelect.innerHTML = await renderBrigadeOptions(ev.target.value ? Number(ev.target.value) : null, null);
  };

  root.querySelector("#btn-toggle").onclick = async () => {
    try {
      await api(`/admin/employees/${employeeId}/toggle-active`, { method: "POST" });
      await replaceTop(screenEmployeeDetail, employeeId);
    } catch (e) {
      showError(e.message);
    }
  };

  setMainButton(`💾 ${t("saveChanges")}`, async () => {
    const app = tg();
    app.MainButton.showProgress();
    try {
      const deptVal = root.querySelector("#f-dept").value;
      const brigadeVal = root.querySelector("#f-brigade").value;
      await api(`/admin/employees/${employeeId}`, {
        method: "POST",
        body: JSON.stringify({
          full_name: root.querySelector("#f-name").value.trim(),
          phone_number: root.querySelector("#f-phone").value.trim(),
          trello_username: root.querySelector("#f-trello").value.trim(),
          role: root.querySelector("#f-role").value,
          department_id: deptVal ? Number(deptVal) : null,
          brigade_id: brigadeVal ? Number(brigadeVal) : null,
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
  setScreen(`
    <p class="page-title">${esc(t("financialNav"))}</p>
    <button class="nav-card accent" id="nav-advance-waiver"><span class="ic">➕</span><span class="grow">${esc(t("advanceWaiverNav"))}</span><span class="chev">›</span></button>
    ${items.length ? items.map((s, i) => `
      <div class="fin-card" data-i="${i}">
        <div class="top"><span class="task">Task #${s.task_id}${s.task_title ? " — " + esc(s.task_title) : ""}</span><span class="status-pill warn">${esc(t(s.kind))}</span></div>
        ${s.kind === "wage_deduction" && s.suggested_deduction_amount === null ? `
          <div class="amount-row"><input type="number" class="f-amount" placeholder="${esc(t("enterAmount"))}" /><button class="btn primary f-amount-save">${esc(t("save"))}</button></div>
        ` : `<p class="desc">${s.suggested_deduction_amount !== null ? s.suggested_deduction_amount : s.waived_amount}</p>`}
      </div>
    `).join("") : `<p class="empty-state">${esc(t("noPendingFinancial"))}</p>`}
  `);
  root.querySelector("#nav-advance-waiver").onclick = () => show(screenAdvanceWaiverForm);
  root.querySelectorAll(".fin-card").forEach((card) => {
    const btn = card.querySelector(".f-amount-save");
    if (!btn) return;
    const item = items[Number(card.dataset.i)];
    btn.onclick = async () => {
      const value = card.querySelector(".f-amount").value;
      if (!value) return;
      try {
        await api(`/admin/financial/${item.id}/amount`, { method: "POST", body: JSON.stringify({ amount: Number(value) }) });
        await replaceTop(screenFinancial);
      } catch (e) {
        showError(e.message);
      }
    };
  });
}

async function screenAdvanceWaiverForm() {
  setScreen(`
    <p class="page-title">${esc(t("advanceWaiverTitle"))}</p>
    <div class="field"><label>${esc(t("taskIdField"))}</label><input id="f-task-id" type="number" /></div>
    <div class="field"><label>${esc(t("advancePercentField"))}</label><input id="f-percent" type="number" min="0" max="100" /></div>
    <div class="field"><label>${esc(t("orderValueField"))}</label><input id="f-value" type="number" min="0" /></div>
    <p class="section-lbl">${esc(t("isLateField"))}</p>
    <div class="segmented" id="late-toggle">
      <button data-late="1" aria-selected="true">${esc(t("statusOverdue"))}</button>
      <button data-late="0" aria-selected="false">${esc(t("statusActive"))}</button>
    </div>
  `);
  let isLate = true;
  root.querySelectorAll("#late-toggle button").forEach((btn) => {
    btn.onclick = () => {
      isLate = btn.dataset.late === "1";
      root.querySelectorAll("#late-toggle button").forEach((b) => b.setAttribute("aria-selected", b === btn));
    };
  });

  setMainButton(`✅ ${t("create")}`, async () => {
    const taskId = root.querySelector("#f-task-id").value;
    const percent = root.querySelector("#f-percent").value;
    const value = root.querySelector("#f-value").value;
    if (!taskId || percent === "" || value === "") {
      showError(`${t("taskIdField")}, ${t("advancePercentField")}, ${t("orderValueField")}`);
      return;
    }
    const app = tg();
    app.MainButton.showProgress();
    try {
      const result = await api("/admin/financial/advance-waiver", {
        method: "POST",
        body: JSON.stringify({
          task_id: Number(taskId), advance_percent_paid: Number(percent),
          order_total_value: Number(value), is_late: isLate,
        }),
      });
      app.HapticFeedback && app.HapticFeedback.notificationOccurred("success");
      app.showPopup
        ? app.showPopup({ message: result.applicable ? t("waiverApplicableYes", result.waived_amount) : t("waiverApplicableNo") })
        : window.alert(result.applicable ? t("waiverApplicableYes", result.waived_amount) : t("waiverApplicableNo"));
      await goBack();
    } catch (e) {
      showError(e.message);
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#2f6f62");
}

async function screenFullStats() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const stats = await api("/admin/stats");
  if (!stats.length) {
    setScreen(`<p class="page-title">${esc(t("fullStatsTitle"))}</p><p class="empty-state">${esc(t("noStats"))}</p>`);
    return;
  }
  setScreen(`
    <p class="page-title">${esc(t("fullStatsTitle"))}</p>
    ${stats.map((s, i) => `
      <div class="stat-row">
        <span class="rank">${i + 1}</span>
        <span class="nm">${esc(s.full_name)}<div class="completed">${s.completed_tasks} ${esc(t("completedThisMonth"))} · ${s.penalty_count} ${esc(t("penaltyCountLbl")).toLowerCase()}</div></span>
        <span class="score ${s.total_score > 0 ? "pos" : s.total_score < 0 ? "neg" : ""}">${s.total_score > 0 ? "+" : ""}${s.total_score}</span>
      </div>
    `).join("")}
  `);
}

/* ---------- Sozlamalar (16-band) ---------- */

const SETTING_FIELDS = [
  "default_penalty_multiplier", "brigade_share_ratio", "balls_per_day_shift",
  "plus_ball_per_day", "plus_ball_max_days", "financial_flag_threshold_days",
  "advance_threshold_percent", "advance_waiver_percent", "report_time",
  "lead_follow_up_threshold_days",
];

async function screenSettings() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const snapshot = await api("/admin/settings");
  setScreen(`
    <p class="page-title">${esc(t("settingsTitle"))}</p>
    ${SETTING_FIELDS.map((field) => `
      <button class="settings-row" data-field="${field}">
        <span class="lbl">${esc(t("setting_" + field))}</span><span class="val">${esc(snapshot[field])}</span>
      </button>
    `).join("")}
    <p class="section-lbl">${esc(t("management"))}</p>
    <button class="nav-card" id="nav-chain"><span class="ic">🔗</span><span class="grow">${esc(t("departmentChainNav"))}</span><span class="chev">›</span></button>
    <button class="nav-card" id="nav-autoreassign"><span class="ic">🔁</span><span class="grow">${esc(t("autoreassignNav"))}</span><span class="chev">›</span></button>
    <button class="nav-card" id="nav-reminders"><span class="ic">🕗</span><span class="grow">${esc(t("remindersNav"))}</span><span class="chev">›</span></button>
  `);
  root.querySelectorAll(".settings-row").forEach((el) => {
    el.onclick = () => show(screenEditSetting, el.dataset.field, snapshot[el.dataset.field]);
  });
  root.querySelector("#nav-chain").onclick = () => show(screenDepartmentChain);
  root.querySelector("#nav-autoreassign").onclick = () => show(screenAutoreassign);
  root.querySelector("#nav-reminders").onclick = () => show(screenReminders);
}

async function screenEditSetting(field, currentValue) {
  setScreen(`
    <p class="page-title">${esc(t("setting_" + field))}</p>
    <div class="field"><input id="f-value" type="text" value="${esc(currentValue)}" /></div>
  `);
  setMainButton(`💾 ${t("saveChanges")}`, async () => {
    const app = tg();
    app.MainButton.showProgress();
    try {
      await api("/admin/settings", { method: "POST", body: JSON.stringify({ [field]: root.querySelector("#f-value").value.trim() }) });
      app.HapticFeedback && app.HapticFeedback.notificationOccurred("success");
      await goBack();
    } catch (e) {
      showError(e.message);
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#2f6f62");
}

async function screenDepartmentChain() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const departments = await api("/admin/departments");
  setScreen(`
    <p class="page-title">${esc(t("departmentChainTitle"))}</p>
    <p class="page-sub">${esc(t("departmentChainPick"))}</p>
    ${departments.map((d, i) => {
      const next = departments.find((x) => x.id === d.next_department_id);
      return `
        <button class="settings-row" data-i="${i}">
          <span class="lbl">${esc(d.name)}</span><span class="val">${esc(next ? t("nextDeptArrow", next.name) : t("noNextDepartment"))}</span>
        </button>
      `;
    }).join("")}
  `);
  root.querySelectorAll(".settings-row").forEach((el) => {
    const dept = departments[Number(el.dataset.i)];
    el.onclick = () => show(screenDepartmentChainEdit, dept, departments);
  });
}

async function screenDepartmentChainEdit(department, departments) {
  const options = departments.filter((d) => d.id !== department.id);
  setScreen(`
    <p class="page-title">${esc(department.name)}</p>
    <p class="page-sub">${esc(t("nextDepartmentPick"))}</p>
    <button class="radio-row" data-id="" aria-selected="${department.next_department_id === null}">${esc(t("noNextDepartment"))}</button>
    ${options.map((d) => `<button class="radio-row" data-id="${d.id}" aria-selected="${d.id === department.next_department_id}">${esc(d.name)}</button>`).join("")}
  `);
  root.querySelectorAll(".radio-row").forEach((el) => {
    el.onclick = async () => {
      try {
        await api(`/admin/departments/${department.id}/chain`, {
          method: "POST",
          body: JSON.stringify({ next_department_id: el.dataset.id ? Number(el.dataset.id) : null }),
        });
        await goBack();
      } catch (e) {
        showError(e.message);
      }
    };
  });
}

async function screenAutoreassign() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const departments = await api("/admin/departments");
  setScreen(`
    <p class="page-title">${esc(t("autoreassignNav"))}</p>
    ${departments.map((d, i) => `
      <button class="toggle-row" data-i="${i}">
        <span>${esc(d.name)}</span>
        <span class="toggle-pill ${d.auto_reassign_after_48h ? "on" : ""}">${d.auto_reassign_after_48h ? "ON" : "OFF"}</span>
      </button>
    `).join("")}
  `);
  root.querySelectorAll(".toggle-row").forEach((el) => {
    const dept = departments[Number(el.dataset.i)];
    el.onclick = async () => {
      try {
        await api(`/admin/departments/${dept.id}/autoreassign`, { method: "POST" });
        await replaceTop(screenAutoreassign);
      } catch (e) {
        showError(e.message);
      }
    };
  });
}

async function screenReminders() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const schedule = await api("/admin/reminders");
  setScreen(`
    <p class="page-title">${esc(t("remindersTitle"))}</p>
    ${schedule.map((entry, i) => `
      <div class="fin-card" data-i="${i}">
        <div class="top"><span class="task">🕗 ${esc(entry.time)}</span><span class="status-pill warn">${esc(t("urgency_" + entry.urgency))}</span></div>
        <div class="amount-row">
          <button class="btn f-edit">✏️ ${esc(t("saveChanges"))}</button>
          <button class="btn danger f-delete">${esc(t("deleteBtn"))}</button>
        </div>
      </div>
    `).join("")}
  `);
  root.querySelectorAll(".fin-card").forEach((card) => {
    const entry = schedule[Number(card.dataset.i)];
    const idx = Number(card.dataset.i);
    card.querySelector(".f-edit").onclick = () => show(screenReminderForm, "edit", idx, entry);
    card.querySelector(".f-delete").onclick = async () => {
      try {
        await api(`/admin/reminders/${idx}`, { method: "DELETE" });
        await replaceTop(screenReminders);
      } catch (e) {
        showError(e.message);
      }
    };
  });
  setMainButton(t("addReminderBtn"), () => show(screenReminderForm, "add", null, null), "#2f6f62");
}

async function screenReminderForm(mode, index, entry) {
  const urgencies = ["info", "warning", "urgent"];
  let urgency = (entry && entry.urgency) || "info";
  setScreen(`
    <p class="page-title">${esc(t("addReminderBtn"))}</p>
    <div class="field"><label>${esc(t("reminderTime"))}</label><input id="f-time" type="text" placeholder="15:00" value="${esc(entry ? entry.time : "")}" /></div>
    <p class="section-lbl">${esc(t("urgency_info")).replace("ℹ️ ", "")}</p>
    <div class="segmented" id="urgency-toggle">
      ${urgencies.map((u) => `<button data-u="${u}" aria-selected="${u === urgency}">${esc(t("urgency_" + u))}</button>`).join("")}
    </div>
  `);
  root.querySelectorAll("#urgency-toggle button").forEach((btn) => {
    btn.onclick = () => {
      urgency = btn.dataset.u;
      root.querySelectorAll("#urgency-toggle button").forEach((b) => b.setAttribute("aria-selected", b === btn));
    };
  });

  setMainButton(`💾 ${t("saveChanges")}`, async () => {
    const time = root.querySelector("#f-time").value.trim();
    if (!time) {
      showError(t("reminderTime"));
      return;
    }
    const app = tg();
    app.MainButton.showProgress();
    try {
      if (mode === "add") {
        await api("/admin/reminders", { method: "POST", body: JSON.stringify({ time, urgency }) });
      } else {
        await api(`/admin/reminders/${index}`, { method: "PUT", body: JSON.stringify({ time, urgency }) });
      }
      app.HapticFeedback && app.HapticFeedback.notificationOccurred("success");
      await goBack();
    } catch (e) {
      showError(e.message);
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#2f6f62");
}

/* ---------- 6.1/7.4-band: Sozlash kutilayotgan bosqichlar ---------- */

async function screenPendingSetup() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const items = await api("/admin/pending-setup");
  if (!items.length) {
    setScreen(`<p class="page-title">${esc(t("pendingSetupTitle"))}</p><p class="empty-state">${esc(t("noPendingSetup"))}</p>`);
    return;
  }
  setScreen(`
    <p class="page-title">${esc(t("pendingSetupTitle"))}</p>
    ${items.map((task, i) => `
      <button class="nav-card" data-i="${i}"><span class="ic">⏳</span><span class="grow">${esc(task.title)}<div class="t-sub">${esc(task.department || "")}</div></span><span class="chev">›</span></button>
    `).join("")}
  `);
  root.querySelectorAll(".nav-card").forEach((el) => {
    const task = items[Number(el.dataset.i)];
    el.onclick = () => show(screenActivateStage, task);
  });
}

async function screenActivateStage(task) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const brigadiers = task.department_id ? await api(`/admin/departments/${task.department_id}/brigadiers`) : [];
  let selectedBrigadierId = null;
  setScreen(`
    <p class="page-title">${esc(task.title)}</p>
    <div class="field"><label>${esc(t("deadline"))}</label><input id="f-deadline" type="datetime-local" /></div>
    <p class="section-lbl">${esc(t("brigadierField"))}</p>
    ${brigadiers.length ? brigadiers.map((b, i) => `
      <button class="radio-row" data-i="${i}">${esc(b.brigadier_name)} <span class="hint">(${esc(b.brigade_name)})</span></button>
    `).join("") : `<p class="empty-state">${esc(t("noBrigadierInDept"))}</p>`}
  `);
  root.querySelectorAll(".radio-row").forEach((el) => {
    const b = brigadiers[Number(el.dataset.i)];
    el.onclick = () => {
      selectedBrigadierId = b.brigadier_id;
      root.querySelectorAll(".radio-row").forEach((r) => r.setAttribute("aria-selected", r === el));
    };
  });
  setMainButton(t("activateStageBtn"), async () => {
    const deadlineRaw = root.querySelector("#f-deadline").value;
    if (!deadlineRaw || !selectedBrigadierId) {
      showError(`${t("deadline")}, ${t("brigadierField")}`);
      return;
    }
    const app = tg();
    app.MainButton.showProgress();
    try {
      await api(`/admin/tasks/${task.id}/activate`, {
        method: "POST",
        body: JSON.stringify({ deadline: new Date(deadlineRaw).toISOString(), brigadier_id: selectedBrigadierId }),
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

/* ---------- 8.3-band: brigadaga o'tkazishni ko'rib chiqish ---------- */

async function screenReassignList() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const items = await api("/admin/reassign-candidates");
  if (!items.length) {
    setScreen(`<p class="page-title">${esc(t("reassignTitle"))}</p><p class="empty-state">${esc(t("noReassignCandidates"))}</p>`);
    return;
  }
  setScreen(`
    <p class="page-title">${esc(t("reassignTitle"))}</p>
    ${items.map((task, i) => `
      <button class="nav-card" data-i="${i}"><span class="ic">🔁</span><span class="grow">${esc(task.title)}<div class="t-sub">${esc(task.department || "")}</div></span><span class="chev">›</span></button>
    `).join("")}
  `);
  root.querySelectorAll(".nav-card").forEach((el) => {
    const task = items[Number(el.dataset.i)];
    el.onclick = () => show(screenReassignForm, task);
  });
}

async function screenReassignForm(task) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const brigades = await api(`/admin/tasks/${task.id}/reassign-brigades`);
  if (!brigades.length) {
    setScreen(`<p class="page-title">${esc(task.title)}</p><p class="empty-state">${esc(t("noBrigadeOptions"))}</p>`);
    return;
  }
  setScreen(`
    <p class="page-title">${esc(task.title)}</p>
    <p class="page-sub">${esc(t("selectBrigadeTitle"))}</p>
    ${brigades.map((b, i) => `<button class="radio-row" data-i="${i}">${esc(b.name)}</button>`).join("")}
  `);
  root.querySelectorAll(".radio-row").forEach((el) => {
    const brigade = brigades[Number(el.dataset.i)];
    el.onclick = async () => {
      try {
        await api(`/admin/tasks/${task.id}/reassign`, { method: "POST", body: JSON.stringify({ brigade_id: brigade.id }) });
        await goBack();
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
  const pendingWork = await api("/brigadier/pending-delegation");
  setScreen(`
    <p class="page-title">${esc(t("brigade_title"))}: ${esc(brigade.name)}</p>
    ${pendingWork.length ? `<button class="alert-card" id="nav-new-work"><span class="ic">🆕</span><span class="grow">${esc(t("newWorkAlert", pendingWork.length))}</span><span class="chev">›</span></button>` : ""}
    ${brigade.members.length ? brigade.members.map((m, i) => `
      <div class="member-card ${m.total_score < 0 ? "low" : m.total_score > 0 ? "high" : ""}" data-i="${i}">
        <div class="member-top"><span class="nm">${esc(m.full_name)}</span><span class="score ${m.total_score > 0 ? "pos" : m.total_score < 0 ? "neg" : "zero"}">${m.total_score > 0 ? "+" : ""}${m.total_score} ${state.lang === "ru" ? "б." : "ball"}</span></div>
        <div class="member-actions"><button class="btn-report">📅 ${esc(t("weeklyReport"))}</button><button class="btn-tasks">📋 ${esc(t("currentTasks"))}</button></div>
      </div>
    `).join("") : `<p class="empty-state">${esc(t("noBrigadeMembers"))}</p>`}
  `);
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
  const newWorkBtn = root.querySelector("#nav-new-work");
  if (newWorkBtn) newWorkBtn.onclick = () => show(screenNewWork);
}

async function screenNewWork() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const items = await api("/brigadier/pending-delegation");
  if (!items.length) {
    setScreen(`<p class="page-title">${esc(t("newWorkTitle"))}</p><p class="empty-state">${esc(t("noNewWork"))}</p>`);
    return;
  }
  setScreen(`
    <p class="page-title">${esc(t("newWorkTitle"))}</p>
    ${items.map((tsk, i) => `
      <button class="nav-card accent" data-i="${i}"><span class="ic">🆕</span><span class="grow">${esc(tsk.title)}<div class="t-sub">${esc(t("deadline"))}: ${esc(formatDt(tsk.deadline))}</div></span><span class="chev">›</span></button>
    `).join("")}
  `);
  root.querySelectorAll(".nav-card").forEach((el) => {
    const tsk = items[Number(el.dataset.i)];
    el.onclick = () => show(screenDelegateTask, tsk);
  });
}

async function screenDelegateTask(task) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const members = await api("/brigadier/brigade-members");
  if (!members.length) {
    setScreen(`<p class="page-title">${esc(task.title)}</p><p class="empty-state">${esc(t("noBrigadeMembers"))}</p>`);
    return;
  }
  setScreen(`
    <p class="page-title">${esc(task.title)}</p>
    <p class="page-sub">${esc(t("delegateWorkers"))}</p>
    ${members.map((m) => `
      <label class="check-row"><input type="checkbox" value="${m.id}" class="f-worker" />${esc(m.full_name)}</label>
    `).join("")}
  `);
  setMainButton(t("delegateBtn"), async () => {
    const workerIds = Array.from(root.querySelectorAll(".f-worker:checked")).map((el) => Number(el.value));
    if (!workerIds.length) {
      showError(t("delegateWorkers"));
      return;
    }
    const app = tg();
    app.MainButton.showProgress();
    try {
      await api(`/brigadier/tasks/${task.id}/delegate`, {
        method: "POST",
        body: JSON.stringify({ employee_ids: workerIds }),
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
  `);
  root.querySelectorAll(".brand-pill").forEach((btn) => {
    btn.onclick = () => replaceTop(screenSellerHome, btn.dataset.brand);
  });
  root.querySelectorAll(".lead-card").forEach((btn) => {
    btn.onclick = () => show(screenLeadDetail, Number(btn.dataset.id));
  });
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
        await replaceTop(screenLeadDetail, leadId);
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
    await replaceTop(screenLeadDetail, leadId);
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
    ${me.role === "admin" || me.role === "supervisor" ? `
      <p class="section-lbl">${esc(t("management"))}</p>
      <button class="nav-card" id="nav-settings"><span class="ic">⚙️</span><span class="grow">${esc(t("settingsNav"))}</span><span class="chev">›</span></button>
    ` : ""}
  `);
  const settingsBtn = root.querySelector("#nav-settings");
  if (settingsBtn) settingsBtn.onclick = () => show(screenSettings);
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
      await replaceTop(screenProfile);
    };
  });
}

/* ---------- Bootstrap ---------- */

function applyTheme(scheme) {
  document.documentElement.setAttribute("data-theme", scheme === "dark" ? "dark" : "light");
}

function routeHome() {
  const defs = tabDefsForRole(state.employee.role);
  nav.section = defs[0].key;
  resetTo(defs[0].screen);
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
