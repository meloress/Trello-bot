/* Melores Mebel — Telegram Mini App. Bitta sahifali ilova: navigatsiya
   stack orqali (Telegram BackButton bilan), asosiy amal doim Telegram
   native MainButton'da. Rol aniqlanishi serverdan (`GET /me`) keladi —
   foydalanuvchi faqat o'z rolining ekranlarini ko'radi. */

const API_BASE = "/api/miniapp";
const root = document.getElementById("app");
const tabbarRoot = document.getElementById("tabbar");
const state = { employee: null, lang: "uz" };
const nav = { stack: [], section: null, module: null, transition: null };
let mainButtonHandler = null;
const MODULE_STORAGE_KEY = "miniapp_module";

/* Rol bo'yicha pastki tab-bar ta'rifi — har biri {key, icon, label, screen}.
   Birinchi element doim shu rolning "uy" ekrani (routeHome()/screenModuleChooser()
   shundan foydalanadi). Ekranlar/backend endpointlar modulga (mebel/fasad_sex)
   qarab filtrlanmaydi — xodimning o'z tayinlovlari (task_assignments/brigade_id)
   allaqachon qaysi bo'lim ekanidan qat'iy nazar to'g'ri ma'lumot qaytaradi, shu
   sabab tab to'plami faqat ROLga qarab tanlanadi. `module` faqat ishchining
   "Buyurtmalar" tab yorlig'ini Fasad sex uchun "Bosqichlar"ga almashtirish
   uchun ishlatiladi (pastda screenWorkerOrders). */
function tabDefsForRole(role, module) {
  if (role === "worker") {
    return [
      { key: "orders", icon: icon("box"), label: module === "fasad_sex" ? "tab_stages" : "tab_orders", screen: screenWorkerOrders },
      { key: "tasks", icon: icon("list"), label: "tab_tasks", screen: () => screenTaskList("misc") },
      { key: "score", icon: icon("star"), label: "tab_score", screen: screenWorkerScore },
      { key: "profile", icon: icon("user"), label: "tab_profile", screen: screenProfile },
    ];
  }
  if (role === "admin" || role === "supervisor") {
    return [
      { key: "home", icon: icon("home"), label: "tab_home", screen: screenAdminHome },
      { key: "stats", icon: icon("chart"), label: "tab_stats", screen: screenFullStats },
      { key: "employees", icon: icon("users"), label: "tab_employees", screen: screenEmployees },
      { key: "profile", icon: icon("user"), label: "tab_profile", screen: screenProfile },
    ];
  }
  if (role === "brigadier") {
    return [
      { key: "brigade", icon: icon("users"), label: "tab_brigade", screen: screenBrigadierHome },
      { key: "profile", icon: icon("user"), label: "tab_profile", screen: screenProfile },
    ];
  }
  if (role === "seller") {
    return [
      { key: "leads", icon: icon("briefcase"), label: "tab_leads", screen: () => screenSellerHome() },
      { key: "profile", icon: icon("user"), label: "tab_profile", screen: screenProfile },
    ];
  }
  return [{ key: "profile", icon: icon("user"), label: "tab_profile", screen: screenProfile }];
}

function switchTab(tabKey, screenFn) {
  nav.section = tabKey;
  resetTo(screenFn);
}

function renderTabBar() {
  if (!tabbarRoot) return;
  if (!nav.module) {
    // Modul hali tanlanmagan (screenModuleChooser ekranida) — tab-bar modulga
    // tegishli, shu sabab modul tanlanmaguncha ko'rsatilmaydi.
    tabbarRoot.innerHTML = "";
    return;
  }
  const defs = tabDefsForRole(state.employee ? state.employee.role : null, nav.module);
  if (defs.length < 2) {
    tabbarRoot.innerHTML = "";
    return;
  }
  tabbarRoot.innerHTML = `
    <nav class="tab-bar">
      <div class="pill-bg" id="tab-pill"></div>
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
  positionTabPill();
}

/* Aktiv tab tugmasi ustida sirg'anib yuruvchi fon — offsetLeft/offsetWidth
   orqali o'lchab joylashtiriladi (CSS Grid emas, tugmalar flex:1 bo'lgani
   uchun kengliklari teng, lekin haqiqiy piksel o'lchash oyna kengligidan
   qat'iy nazar to'g'ri ishlashini kafolatlaydi). */
function positionTabPill() {
  const pill = tabbarRoot.querySelector("#tab-pill");
  const active = tabbarRoot.querySelector('.tab-item[aria-selected="true"]');
  if (!pill || !active) return;
  pill.style.left = `${active.offsetLeft}px`;
  pill.style.width = `${active.offsetWidth}px`;
}
window.addEventListener("resize", () => positionTabPill());

/* Rol nomlari — SOF MATN (ikonkasiz), chunki bular `<option>` ichida ham
   ishlatiladi, u yerda SVG chizilmaydi. Ikonka alohida `ROLE_ICONS`da.
   "Rahbar" = SUPERVISOR: bo'lim boshlig'i, ishchilarning Pauza/Yakunlash
   so'rovlarini tasdiqlaydi. "Admin" = tizimning to'liq egasi. Avval
   SUPERVISOR "Nazoratchi", ADMIN esa "Rahbar/Admin" deb atalardi — ikkalasida
   ham "rahbar" so'zi bo'lgani uchun chalkashlik chiqardi. */
const ROLE_LABELS = {
  uz: {
    worker: "Ishchi", brigadier: "Brigadir", supervisor: "Rahbar",
    admin: "Admin", observer: "Kuzatuvchi", seller: "Sotuvchi",
  },
  ru: {
    worker: "Работник", brigadier: "Бригадир", supervisor: "Руководитель",
    admin: "Админ", observer: "Наблюдатель", seller: "Продавец",
  },
};

const ROLE_ICONS = {
  worker: "user", brigadier: "users", supervisor: "chart",
  admin: "settings", observer: "user", seller: "briefcase",
};

/* Mebel ("Fasad seh") ishlab chiqarishida atigi to'rt rol ishlatiladi —
   ishchi, brigadir, rahbar, admin. Kuzatuvchi/sotuvchi u yerda ma'noga ega
   emas, shuning uchun xodim qo'shish/tahrirlash ro'yxatida ko'rsatilmaydi
   (bo'lim ro'yxati modulga qarab filtrlangani bilan bir xil naqsh).
   fasad_sex ("Nazorat Trello") moduli barcha rollarni saqlab qoladi. */
const MEBEL_ROLES = ["worker", "brigadier", "supervisor", "admin"];

/* Yangi xodim qo'shishda rahbar/admin tanlanmasin — ular boshqaruvchi,
   ishlab chiqarish ishini bajarmaydi, va bu rollar odatda kamdan-kam,
   alohida tayinlanadi (yangi xodim qo'shish orqali emas). Mavjud xodimni
   TAHRIRLASHDA esa cheklanmaydi (masalan ishchini brigadirlikka yoki
   brigadirni rahbarlikka ko'tarish shu orqali qilinadi). */
const NEW_EMPLOYEE_EXCLUDED_ROLES = ["admin", "supervisor"];

/* Claim amali -> i18n kaliti. Uchta amal ham (pauza/yakunlash/davom ettirish)
   rahbar tasdig'ini kutadi, shuning uchun ternary emas, jadval. */
const CLAIM_PENDING_KEYS = {
  pause: "claimPendingPause", finish: "claimPendingFinish", resume: "claimPendingResume",
};
const CLAIM_ACTION_KEYS = {
  pause: "claimActionPause", finish: "claimActionFinish", resume: "claimActionResume",
};

function rolesForModule(alwaysInclude) {
  const all = Object.keys(ROLE_LABELS[state.lang]);
  if (nav.module !== "mebel") return all;
  // Tahrirlashda xodimning JORIY roli ro'yxatdan tushib qolmasligi shart —
  // aks holda saqlash tugmasi uni jimgina boshqa rolga o'zgartirib yuboradi.
  return all.filter((r) => MEBEL_ROLES.includes(r) || r === alwaysInclude);
}

/* Chiziq-uslubidagi SVG ikon — index.html'dagi <symbol id="ic-*"> sprite'idan
   <use> orqali chizadi (emoji glyflar o'rniga, .claude/plans/10-miniapp-qayta-dizayn.md). */
function icon(name) {
  return `<svg class="ic-svg"><use href="#ic-${name}"></use></svg>`;
}

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

/* daysUntil()'ni manfiylab kechikishni hisoblash noto'g'ri (har doim 1 kunga
   yuqoriga yaxlitlaydi, masalan 30 daqiqa kechikish "1 kun kechikdi" bo'lib
   chiqadi) — shuning uchun kechikish uchun alohida, to'g'ri floor yo'nalishi. */
function daysLate(iso) {
  if (!iso) return null;
  return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86400000));
}

/* Ball (KPI) ishorasidan rang klassini aniqlashning YAGONA joyi. Avval har
   bir ekran o'z ternary'sini yozardi va ular bir-biriga mos emas edi —
   ba'zilari manfiy ballni yashil (`>= 0 ? "positive"`), ba'zilari kulrang
   qoldirardi. Ball manfiy bo'lsa DOIM qizil bo'lishi shart: bu jarima,
   xodim uni darhol ko'rishi kerak.
     scoreClass()  -> .pos/.neg/.zero    (matn/raqam uchun)
     heroTone()    -> .positive/.critical (hero-tile uchun, mavjud nomlash)
     scoreSigned() -> "+5" / "-3" / "0"  (musbatga aniq "+" qo'yiladi) */
function scoreClass(value) {
  return value > 0 ? "pos" : value < 0 ? "neg" : "zero";
}

function heroTone(value) {
  return value > 0 ? "positive" : value < 0 ? "critical" : "";
}

function scoreSigned(value) {
  return (value > 0 ? "+" : "") + value;
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
  nav.transition = "fwd";
  await renderCurrent();
}

async function goBack() {
  if (nav.stack.length > 1) {
    nav.stack.pop();
    nav.transition = "back";
    await renderCurrent();
  }
}

async function resetTo(renderFn, ...args) {
  nav.stack = [[renderFn, args]];
  nav.transition = "fade";
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
    setScreen(`<p class="error-banner">${esc(e.message || t("error_generic"))}</p><button class="btn" id="btn-retry">${esc(t("retry"))}</button>`);
    root.querySelector("#btn-retry").onclick = renderCurrent;
  }
  applyStagger();
  animateNumbers();
  if (nav.transition) {
    root.classList.remove("enter-fwd", "enter-back", "enter-fade");
    void root.offsetWidth; // reflow — animatsiyani qayta ishga tushirish uchun
    root.classList.add("enter-" + nav.transition);
    nav.transition = null;
  }
  renderTabBar();
}

/* Har bir ekran render bo'lgach avtomatik ishga tushadi — screen funksiyalarining
   HTML shablonlarini o'zgartirmasdan, kartochka ro'yxatlarga ketma-ket kirish
   animatsiyasini (stagger) qo'shadi. Kamayish (prefers-reduced-motion) CSS'ning
   o'zida hal qilinadi. */
const STAGGER_SELECTOR = ".nav-card, .task-card, .hero-tile, .member-card, .stat-row, " +
  ".emp-row, .lead-card, .alert-card, .fin-card, .kpi-list-item, .settings-row, .toggle-row, .radio-row";
function applyStagger() {
  root.querySelectorAll(STAGGER_SELECTOR).forEach((el, i) => {
    el.classList.add("stagger");
    el.style.setProperty("--i", i);
  });
}

/* Hero-tile va ball raqamlarini 0'dan yakuniy qiymatgacha sanaydi. Matnning
   raqam bo'lmagan qismini (belgi, qo'shimcha matn) o'zgarishsiz qoldiradi;
   raqam ko'rinishida bo'lmagan qiymatlarni (masalan "—", "⚠️", xodim ismi)
   butunlay o'tkazib yuboradi. */
function animateNumbers() {
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  root.querySelectorAll(".hero-tile .num, .chart-head .big").forEach((el) => {
    const m = el.textContent.match(/^([+-]?)(\d+)(.*)$/);
    if (!m) return;
    const [, sign, digits, suffix] = m;
    const target = Number(digits);
    if (!target) return;
    const start = performance.now();
    const dur = 650;
    const step = (now) => {
      const p = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = `${sign}${Math.round(target * eased)}${suffix}`;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
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
  // Muddati o'tgan bo'lsa bu OGOHLANTIRISH emas, KRITIK holat — avval sariq
  // "warn" rangida va "⚠️" belgisi bilan ko'rsatilardi, ya'ni muddati bugun
  // tugaydigan vazifadan farq qilmasdi. Kechikish kunini `daysLate()` bilan
  // hisoblaymiz (`daysUntil()`ni manfiylash 1 kunga yuqoriga yaxlitlaydi).
  const nearestTone = nearestDays === null ? "" : nearestDays <= 0 ? "critical" : nearestDays <= 1 ? "warn" : "";
  const nearestText =
    nearestDays === null
      ? "—"
      : nearestDays <= 0
        ? esc(t("lateUnitShort", daysLate(nearest.deadline)))
        : `${nearestDays}${esc(t("dayUnitShort"))}`;

  setScreen(`
    <p class="greet-wave">${esc(t("greeting"))}</p>
    <p class="greet">${esc(state.employee.full_name)} 👋</p>
    <div class="hero-row">
      <div class="hero-tile ${heroTone(score.total)}"><span class="num">${scoreSigned(score.total)}</span><span class="lbl">${esc(t("currentMonthScore"))}</span></div>
      <div class="hero-tile ${nearestTone}"><span class="num">${nearestText}</span><span class="lbl">${esc(t("nearestDeadline"))}</span></div>
    </div>
    <p class="section-lbl">${esc(t(nav.module === "fasad_sex" ? "myStages" : "myOrders"))}</p>
    ${orders.length ? orders.map((tsk, i) => `
      <button class="task-card ${statusClass(tsk.status)}" data-i="${i}">
        <p class="t-title">${esc(tsk.title)}</p>
        <p class="t-sub">${esc(tsk.department || "")}</p>
        <span class="t-status">${taskStatusLine(tsk)}</span>
      </button>
    `).join("") : `<p class="empty-state">${esc(t(nav.module === "fasad_sex" ? "noStages" : "noOrders"))}</p>`}
  `);
  root.querySelectorAll(".task-card").forEach((el) => {
    const tsk = orders[Number(el.dataset.i)];
    el.onclick = () => show(screenTaskDetail, tsk.id);
  });
}

/* Fasad sex TZ, Phase 9: MISC vazifa kategoriyalari — barqaror ichki
   identifikator, i18n.js'dagi mos "miscCategoryX" kaliti bilan chiqariladi. */
const MISC_CATEGORIES = ["office", "fasad_sex", "installer", "welder"];
function miscCategoryKey(v) {
  return "miscCategory" + v.split("_").map((w) => w[0].toUpperCase() + w.slice(1)).join("");
}

async function screenTaskList(kind, category) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const url = kind === "order" ? "/tasks" : `/misctasks${category ? `?category=${encodeURIComponent(category)}` : ""}`;
  const tasks = await api(url);
  const filterHtml = kind === "misc" ? `
    <div class="field"><label>${esc(t("miscCategoryLabel"))}</label>
      <select id="f-category-filter">
        <option value="">${esc(t("miscCategoryAll"))}</option>
        ${MISC_CATEGORIES.map((c) => `<option value="${c}" ${category === c ? "selected" : ""}>${esc(t(miscCategoryKey(c)))}</option>`).join("")}
      </select>
    </div>` : "";
  if (!tasks.length) {
    setScreen(`<p class="page-title">${esc(kind === "order" ? t("myOrders") : t("myTasks"))}</p>${filterHtml}<p class="empty-state">${esc(kind === "order" ? t("noOrders") : t("noTasks"))}</p>`);
  } else {
    setScreen(`
      <p class="page-title">${esc(kind === "order" ? t("myOrders") : t("myTasks"))}</p>
      ${filterHtml}
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
  const filterSel = root.querySelector("#f-category-filter");
  if (filterSel) filterSel.onchange = () => replaceTop(screenTaskList, kind, filterSel.value || undefined);
}

function taskStatusLine(tsk) {
  if (tsk.status === "stopped") return `${icon("stop")} ${esc(t("statusStopped"))}`;
  if (tsk.status === "overdue") {
    const days = tsk.deadline ? daysLate(tsk.deadline) : null;
    return `${icon("alert")} ${days ? esc(t("daysLate", days)) : esc(t("statusOverdue"))}`;
  }
  if (tsk.status === "active" && tsk.deadline) {
    const days = daysUntil(tsk.deadline);
    return `${icon("clock")} ${esc(t("daysLeft", days))}`;
  }
  return esc(statusLabel(tsk.status));
}

async function screenTaskDetail(taskId) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const tsk = await api(`/tasks/${taskId}`);
  const isMebel = tsk.module === "mebel";
  // STOPPED ham: davom ettirish ham endi tasdiq kutadigan so'rov.
  const pending = isMebel && tsk.status !== "completed" ? (await api(`/tasks/${taskId}/claim-status`)).pending_claim : null;
  const pillClass = tsk.status === "overdue" ? "critical" : tsk.status === "stopped" ? "neutral" : "positive";

  setScreen(`
    <p class="page-title">${esc(tsk.title)}</p>
    <span class="status-pill ${pillClass}">${esc(statusLabel(tsk.status))}</span>
    <div class="panel">
      <div class="kv-row"><span class="k">${esc(t("deadline"))}</span><span class="v">${esc(formatDt(tsk.deadline))}</span></div>
      ${tsk.status === "overdue" && tsk.deadline ? `<div class="kv-row"><span class="k">${esc(t("lateness"))}</span><span class="v">${esc(t("daysLate", daysLate(tsk.deadline)))}</span></div>` : ""}
      <div class="kv-row"><span class="k">${esc(t("department"))}</span><span class="v">${esc(tsk.department || "—")}</span></div>
      ${tsk.client_name ? `<div class="kv-row"><span class="k">${esc(t("client"))}</span><span class="v">${esc(tsk.client_name)}</span></div>` : ""}
    </div>
    ${pending ? `
      <div class="alert-card"><span class="ic">${icon("clock")}</span><span class="grow">${esc(t(CLAIM_PENDING_KEYS[pending.action_type]))}</span></div>
    ` : !isMebel && (tsk.status === "active" || tsk.status === "overdue") ? `<button class="btn" id="btn-stop">${icon("stop")} ${esc(t("stop"))}</button>` : ""}
  `);

  // Mebel: ishchi profilida Pauza/Yakunlash tugmasi umuman yo'q — faqat
  // kelgan ish ma'lumoti (va tepadagi pending-claim holati, bo'lsa) ko'rinadi.
  // Amalni endi faqat brigadir o'zining "Brigada" ekranidan turib bosadi.
  if (isMebel || pending) return;

  const stopBtn = root.querySelector("#btn-stop");
  if (stopBtn) stopBtn.onclick = () => show(screenStopTask, taskId);

  if (tsk.status === "active" || tsk.status === "overdue") {
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
    }, "#158f5c");
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
  }, "#d63356");
}

async function screenWorkerScore() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const data = await api("/score");
  const maxAbs = Math.max(1, ...data.logs.map((l) => Math.abs(l.score)));

  setScreen(`
    <p class="page-title">${esc(t("myScore"))}</p>
    <div class="chart-box">
      <div class="chart-head"><span>${esc(t("currentMonth"))}</span><span class="big ${scoreClass(data.total)}">${scoreSigned(data.total)} ${state.lang === "ru" ? "баллов" : "ball"}</span></div>
      ${data.logs.slice(0, 12).map((l) => `
        <div class="bar-row ${scoreClass(l.score)}">
          <span class="day">${formatDt(l.created_at).slice(0, 5)}</span>
          <div class="bar-track"><div class="bar-fill ${scoreClass(l.score)}" style="width:${(Math.abs(l.score) / maxAbs) * 50}%"></div></div>
          <span class="val">${scoreSigned(l.score)}</span>
        </div>
      `).join("")}
    </div>
    ${data.logs.length ? `<p class="section-lbl">${esc(t("details"))}</p>${data.logs.map((l) => `
      <div class="kpi-list-item ${scoreClass(l.score)}">
        <span class="d">${formatDt(l.created_at).slice(0, 5)}</span>
        <span class="why">${esc(l.reason)}</span>
        <span class="amt">${scoreSigned(l.score)}</span>
      </div>
    `).join("")}` : `<p class="empty-state">${esc(t("noScoreYet"))}</p>`}
  `);
}

/* ---------- Rahbar/Nazoratchi ekranlari ---------- */

async function screenAdminHome() {
  // Mebel ("Fasad seh"): Kunlik hisobot va "barcha vazifalar" ko'rish endi
  // faqat Nazorat Trello (fasad_sex) uchun — bu ikkala nav-card mebel
  // kontekstida umuman ko'rsatilmaydi. Maxsus topshiriq YARATISH ("Yangi
  // vazifa" tugmasi) esa ikkala modulda ham qoladi.
  const mebelOnly = nav.module === "mebel";
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const [d, pendingSetup, reassignCandidates, pendingClaims] = await Promise.all([
    api("/admin/dashboard"), api("/admin/pending-setup"), api("/admin/reassign-candidates"), api("/admin/pending-claims"),
  ]);
  setScreen(`
    <p class="page-title">${esc(t("dashboard"))}</p>
    <div class="hero-row">
      <div class="hero-tile"><span class="num">${d.active_employees}</span><span class="lbl">${esc(t("activeEmployees"))}</span></div>
      <div class="hero-tile positive"><span class="num">${d.completed_this_month}</span><span class="lbl">${esc(t("completedThisMonth"))}</span></div>
    </div>
    <div class="hero-row">
      <div class="hero-tile ${heroTone(d.avg_score)}"><span class="num">${scoreSigned(d.avg_score)}</span><span class="lbl">${esc(t("avgScore"))}</span></div>
      <div class="hero-tile"><span class="num" style="font-size:15px">${esc(d.top_performer || "—")}</span><span class="lbl">${esc(t("topPerformer"))}</span></div>
    </div>
    <button class="nav-card accent" id="nav-newtask"><span class="ic">${icon("plus")}</span><span class="grow">${esc(t("newTaskCta"))}</span><span class="chev">›</span></button>
    ${pendingSetup.length ? `<button class="alert-card" id="nav-pending-setup"><span class="ic">${icon("clock")}</span><span class="grow">${esc(t("pendingSetupAlert", pendingSetup.length))}</span><span class="chev">›</span></button>` : ""}
    ${reassignCandidates.length ? `<button class="alert-card" id="nav-reassign"><span class="ic">${icon("repeat")}</span><span class="grow">${esc(t("reassignAlert", reassignCandidates.length))}</span><span class="chev">›</span></button>` : ""}
    ${pendingClaims.length ? `<button class="alert-card" id="nav-pending-claims"><span class="ic">${icon("list")}</span><span class="grow">${esc(t("pendingClaimsAlert", pendingClaims.length))}</span><span class="chev">›</span></button>` : ""}
    ${mebelOnly ? "" : `<button class="nav-card" id="nav-daily-reports"><span class="ic">${icon("camera")}</span><span class="grow">${esc(t("dailyReportsNav"))}</span><span class="chev">›</span></button>`}
    ${mebelOnly ? "" : `<button class="nav-card" id="nav-misctasks"><span class="ic">${icon("folder")}</span><span class="grow">${esc(t("miscTasksNav"))}</span><span class="chev">›</span></button>`}
  `);
  root.querySelector("#nav-newtask").onclick = () => show(screenNewTaskForm);
  const pendingBtn = root.querySelector("#nav-pending-setup");
  if (pendingBtn) pendingBtn.onclick = () => show(screenPendingSetup);
  const reassignBtn = root.querySelector("#nav-reassign");
  if (reassignBtn) reassignBtn.onclick = () => show(screenReassignList);
  const claimsBtn = root.querySelector("#nav-pending-claims");
  if (claimsBtn) claimsBtn.onclick = () => show(screenPendingClaims);
  const dailyReportsBtn = root.querySelector("#nav-daily-reports");
  if (dailyReportsBtn) dailyReportsBtn.onclick = () => show(screenDailyReports);
  const miscTasksBtn = root.querySelector("#nav-misctasks");
  if (miscTasksBtn) miscTasksBtn.onclick = () => show(screenAdminMiscTasks);
}

async function screenAdminMiscTasks(category) {
  /* Fasad sex TZ, Phase 9 tuzatish: admin/nazoratchi uchun HAMMA MISC
     vazifalar ro'yxati (worker-scoped `/misctasks`dan farqli, faqat o'ziga
     biriktirilganlar bilan cheklanmagan) — `screenTaskList`dagi bitta
     kategoriya-filtri naqshi bilan bir xil. */
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const url = `/admin/misctasks${category ? `?category=${encodeURIComponent(category)}` : ""}`;
  const tasks = await api(url);
  const filterHtml = `
    <div class="field"><label>${esc(t("miscCategoryLabel"))}</label>
      <select id="f-category-filter">
        <option value="">${esc(t("miscCategoryAll"))}</option>
        ${MISC_CATEGORIES.map((c) => `<option value="${c}" ${category === c ? "selected" : ""}>${esc(t(miscCategoryKey(c)))}</option>`).join("")}
      </select>
    </div>`;
  setScreen(`
    <p class="page-title">${esc(t("miscTasksNav"))}</p>
    ${filterHtml}
    ${tasks.length ? tasks.map((tsk) => `
      <div class="fin-card">
        <div class="top"><span class="task">${esc(tsk.title)}</span></div>
        <div class="amount-row">
          ${tsk.misc_category ? `<span class="status-pill neutral">${esc(t(miscCategoryKey(tsk.misc_category)))}</span>` : ""}
          <span class="status-pill ${tsk.status === "active" ? "positive" : tsk.status === "overdue" ? "critical" : "neutral"}">${esc(statusLabel(tsk.status))}</span>
        </div>
        <p class="hint">${esc(tsk.assigned_employee_names.length ? tsk.assigned_employee_names.join(", ") : "—")}</p>
      </div>
    `).join("") : `<p class="empty-state">${esc(t("noMiscTasksAdmin"))}</p>`}
  `);
  const filterSel = root.querySelector("#f-category-filter");
  if (filterSel) filterSel.onchange = () => replaceTop(screenAdminMiscTasks, filterSel.value || undefined);
}

async function screenDailyReports() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const data = await api("/admin/daily-reports");
  setScreen(`
    <p class="page-title">${esc(t("dailyReportsTitle"))}</p>
    <p class="page-sub">${esc(data.date)}</p>
    ${!data.submitted.length && !data.missing.length ? `<p class="empty-state">${esc(t("noDailyReportEmployees"))}</p>` : `
      <p class="section-lbl">${esc(t("submittedLabel"))} (${data.submitted.length})</p>
      ${data.submitted.map((e) => `
        <div class="stat-row"><span class="rank">${icon("check")}</span><span class="nm">${esc(e.full_name)}</span><span class="score"></span></div>
      `).join("")}
      <p class="section-lbl">${esc(t("missingLabel"))} (${data.missing.length})</p>
      ${data.missing.map((e) => `
        <div class="stat-row"><span class="rank">${icon("x")}</span><span class="nm">${esc(e.full_name)}</span><span class="score"></span></div>
      `).join("")}
    `}
  `);
}

async function screenNewTaskForm(kind) {
  // Mebel ("Fasad seh"): buyurtmalar endi faqat Trello orqali yaratiladi
  // (`trello_ingest_job`) — bu ekranda Buyurtma varianti umuman ko'rsatilmaydi,
  // faqat Maxsus topshiriq (misc) qoladi.
  const mebelOnly = nav.module === "mebel";
  kind = mebelOnly ? "misc" : (kind || "order");
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const [departments, employees] = await Promise.all([
    mebelOnly ? Promise.resolve([]) : api("/admin/departments"), api("/admin/employees"),
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
    ${mebelOnly ? "" : `
    <div class="segmented" id="type-toggle">
      <button data-kind="order" aria-selected="${kind === "order"}">${esc(t("orderType"))}</button>
      <button data-kind="misc" aria-selected="${kind === "misc"}">${esc(t("miscType"))}</button>
    </div>
    `}
    ${kind === "order" ? `
      <div class="field"><label>${esc(t("title"))}</label><input id="f-title" type="text" /></div>
      <div class="field"><label>${esc(t("description"))}</label><textarea id="f-desc"></textarea></div>
      <div class="field"><label>${esc(t("deadline"))}</label><input id="f-deadline" type="datetime-local" /></div>
      <div class="field"><label>${esc(t("departmentField"))}</label>
        <select id="f-dept"><option value="">—</option>${departments.filter((d) => d.module !== "mebel").map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join("")}</select>
      </div>
      <p class="section-lbl">${esc(t("brigadierField"))}</p>
      <div id="brigadier-picker"><p class="hint">${esc(t("pickDepartmentFirst"))}</p></div>
      <div class="field"><label>${esc(t("clientName"))}</label><input id="f-client-name" type="text" /></div>
      <div class="field"><label>${esc(t("clientPhone"))}</label><input id="f-client-phone" type="text" inputmode="tel" /></div>
      <p class="section-lbl">${esc(t("sellersField"))} (≤3)</p>
      ${activeEmployees.filter((e) => e.role === "seller").map((e) => `
        <label class="check-row"><input type="checkbox" value="${e.id}" class="f-seller" />${esc(e.full_name)}</label>
      `).join("") || `<p class="hint">${esc(t("noSellers"))}</p>`}
    ` : `
      <div class="field"><label>${esc(t("miscTaskText"))}</label><input id="f-text" type="text" placeholder="${esc(t("miscTaskTextPh"))}" /></div>
      <div class="field"><label>${esc(t("deadline"))}</label><input id="f-deadline" type="datetime-local" /></div>
      <div class="field"><label>${esc(t("miscCategoryLabel"))}</label>
        <select id="f-category">
          <option value="">—</option>
          ${MISC_CATEGORIES.map((c) => `<option value="${c}">${esc(t(miscCategoryKey(c)))}</option>`).join("")}
        </select>
      </div>
      <p class="section-lbl">${esc(t("employeesField"))} (≤3)</p>
      ${activeEmployees.filter((e) => e.role === "worker" || e.role === "brigadier").map((e) => `
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
      const sellerIds = Array.from(root.querySelectorAll(".f-seller:checked")).map((el) => Number(el.value));
      if (sellerIds.length > 3) {
        showError(t("sellersField"));
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
            seller_ids: sellerIds,
          }),
        });
        app.HapticFeedback && app.HapticFeedback.notificationOccurred("success");
        await goBack();
      } catch (e) {
        showError(e.message);
      } finally {
        app.MainButton.hideProgress();
      }
    }, "#4f3ff0");
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
        const category = root.querySelector("#f-category").value || null;
        await api("/admin/misctasks", {
          method: "POST",
          body: JSON.stringify({ text, deadline: new Date(deadlineRaw).toISOString(), employee_ids: empIds, category }),
        });
        app.HapticFeedback && app.HapticFeedback.notificationOccurred("success");
        await goBack();
      } catch (e) {
        showError(e.message);
      } finally {
        app.MainButton.hideProgress();
      }
    }, "#4f3ff0");
  }
}

/* Yuzlab xodim bo'lganda yagona uzun ro'yxat aralashib chalkash bo'ladi —
   shuning uchun avval rol bo'yicha qisqa kategoriya ro'yxati ko'rsatiladi,
   har biri bosilganda o'sha roldagi xodimlarning o'z alohida ro'yxati ochiladi. */
async function screenEmployees() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const employees = await api("/admin/employees");
  const roles = Object.keys(ROLE_LABELS[state.lang]).filter((r) => employees.some((e) => e.role === r));
  setScreen(`
    <p class="page-title">${esc(t("employeesNav"))} (${employees.length})</p>
    ${roles.map((r) => `
        <button class="nav-card" data-role="${r}">
          <span class="ic">${icon(ROLE_ICONS[r])}</span><span class="grow">${esc(ROLE_LABELS[state.lang][r])}</span><span class="badge">${employees.filter((e) => e.role === r).length}</span><span class="chev">›</span>
        </button>
      `).join("")}
  `);
  root.querySelectorAll(".nav-card").forEach((el) => {
    el.onclick = () => show(screenEmployeesByRole, el.dataset.role);
  });
  setMainButton(`➕ ${t("addEmployee")}`, () => show(screenAddEmployee), "#4f3ff0");
}

async function screenEmployeesByRole(role, departmentId) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  // ponytail: to'liq ro'yxatni olib mijozda filtrlaymiz — yuzlab xodim uchun yetarli,
  // minglab bo'lsa /admin/employees?role= kabi serverga filtr qo'shish kerak bo'ladi.
  const all = (await api("/admin/employees")).filter((e) => e.role === role);
  // Bo'lim filtri — faqat shu ro'yxatda haqiqatan uchraydigan bo'limlar
  // (bo'limi yo'q rol, masalan admin, uchun tugmalar umuman chiqmaydi).
  const departments = [...new Map(all.filter((e) => e.department).map((e) => [e.department_id, e.department]))];
  const employees = departmentId ? all.filter((e) => e.department_id === departmentId) : all;
  setScreen(`
    <p class="page-title">${esc(ROLE_LABELS[state.lang][role])} (${employees.length})</p>
    ${departments.length > 1 ? `<div class="lead-brand-row">
      <button class="brand-pill" data-did="" aria-selected="${!departmentId}">${esc(t("allDepartments"))}</button>
      ${departments.map(([id, name]) => `<button class="brand-pill" data-did="${id}" aria-selected="${id === departmentId}">${esc(name)}</button>`).join("")}
    </div>` : ""}
    ${employees.map((e, i) => `
      <button class="emp-row" data-i="${i}">
        <span class="dot-status ${e.is_active ? "on" : "off"}"></span>
        <span class="grow"><div class="name">${esc(e.full_name)}</div>${e.department ? `<div class="role">${esc(e.department)}</div>` : ""}</span>
        <span class="chev">›</span>
      </button>
    `).join("")}
  `);
  root.querySelectorAll(".brand-pill").forEach((btn) => {
    btn.onclick = () => replaceTop(screenEmployeesByRole, role, btn.dataset.did ? Number(btn.dataset.did) : undefined);
  });
  root.querySelectorAll(".emp-row").forEach((el) => {
    const emp = employees[Number(el.dataset.i)];
    el.onclick = () => show(screenEmployeeDetail, emp.id);
  });
}

async function screenEmployeeDetail(employeeId) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const [employee, departments] = await Promise.all([
    api(`/admin/employees/${employeeId}`), api("/admin/departments"),
  ]);
  const roleOptions = rolesForModule(employee.role)
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
  // Mebel ("Fasad seh"): kunlik hisobot faqat Nazorat Trello (fasad_sex)
  // uchun qoldi — mebel bo'limidagi xodim uchun bu bayroq umuman ko'rsatilmaydi.
  const employeeDepartment = departments.find((d) => d.id === employee.department_id);
  const hideDailyReport = employeeDepartment && employeeDepartment.module === "mebel";
  // Bitta brigadir bir nechta bo'limga rahbarlik qilishi mumkin (Kraska +
  // Shkurka) — tanlangan har bir bo'lim uchun brigada avtomatik yaratiladi.
  const ledIds = employee.led_department_ids || [];
  const ledOptions = departments
    .filter((d) => d.module === (employeeDepartment ? employeeDepartment.module : nav.module) && d.id !== employee.department_id)
    .map((d) => `<label class="check-row"><input type="checkbox" class="f-led" value="${d.id}" ${ledIds.includes(d.id) ? "checked" : ""} />${esc(d.name)}</label>`)
    .join("");

  setScreen(`
    <p class="page-title">${esc(employee.full_name)}</p>
    <span class="status-pill ${employee.is_active ? "positive" : "neutral"}">${employee.is_active ? esc(t("activeStatus")) : esc(t("inactiveStatus"))}</span>
    <div class="field"><label>${esc(t("fullName"))}</label><input id="f-name" type="text" value="${esc(employee.full_name)}" /></div>
    <div class="field"><label>${esc(t("phoneNumber"))}</label><input id="f-phone" type="text" inputmode="tel" value="${esc(employee.phone_number || "")}" /></div>
    <div class="field"><label>${esc(t("trelloUsername"))}</label><input id="f-trello" type="text" value="${esc(employee.trello_username || "")}" /></div>
    <div class="field"><label>${esc(t("role"))}</label><select id="f-role">${roleOptions}</select></div>
    <div class="field"><label>${esc(t("departmentField"))}</label>
      <select id="f-dept"><option value="">—</option>${departments.map((d) => `<option value="${d.id}" ${d.id === employee.department_id ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select>
    </div>
    <div class="field"><label>${esc(t("brigade"))}</label><select id="f-brigade">${brigadeOptions}</select></div>
    <div class="field" id="led-block" ${employee.role === "brigadier" ? "" : "hidden"}>
      <label>${esc(t("ledDepartments"))}</label>${ledOptions}
    </div>
    ${hideDailyReport ? "" : `<label class="check-row"><input type="checkbox" id="f-daily-report" ${employee.daily_report_required ? "checked" : ""} />${esc(t("dailyReportRequiredField"))}</label>`}
    <button class="btn ${employee.is_active ? "danger" : "primary"}" id="btn-toggle">${employee.is_active ? esc(t("deactivate")) : esc(t("activate"))}</button>
  `);

  root.querySelector("#f-dept").onchange = async (ev) => {
    const brigadeSelect = root.querySelector("#f-brigade");
    brigadeSelect.innerHTML = await renderBrigadeOptions(ev.target.value ? Number(ev.target.value) : null, null);
  };

  root.querySelector("#f-role").onchange = (ev) => {
    root.querySelector("#led-block").hidden = ev.target.value !== "brigadier";
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
      const dailyReportEl = root.querySelector("#f-daily-report");
      const roleVal = root.querySelector("#f-role").value;
      const body = {
        full_name: root.querySelector("#f-name").value.trim(),
        phone_number: root.querySelector("#f-phone").value.trim(),
        trello_username: root.querySelector("#f-trello").value.trim(),
        role: roleVal,
        department_id: deptVal ? Number(deptVal) : null,
        brigade_id: brigadeVal ? Number(brigadeVal) : null,
      };
      if (roleVal === "brigadier") {
        body.led_department_ids = Array.from(root.querySelectorAll(".f-led:checked")).map((el) => Number(el.value));
      }
      if (dailyReportEl) body.daily_report_required = dailyReportEl.checked;
      await api(`/admin/employees/${employeeId}`, { method: "POST", body: JSON.stringify(body) });
      app.HapticFeedback && app.HapticFeedback.notificationOccurred("success");
      await goBack();
    } catch (e) {
      showError(e.message);
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#4f3ff0");
}

async function screenAddEmployee() {
  // Bo'lim ro'yxati ilgari ikkala modul ("Fasad seh"/mebel va Nazorat
  // Trello/fasad_sex) bo'limlarini aralashtirib ko'rsatardi — yangi xodim
  // joriy modulga tegishli BO'LMAGAN bo'limga tasodifan biriktirilishi
  // mumkin edi. Endi faqat joriy `nav.module`ga tegishli bo'limlar ko'rinadi.
  const departments = (await api("/admin/departments")).filter((d) => d.module === nav.module);
  const roleOptions = rolesForModule()
    .filter((r) => !NEW_EMPLOYEE_EXCLUDED_ROLES.includes(r))
    .map((r) => `<option value="${r}">${esc(ROLE_LABELS[state.lang][r])}</option>`).join("");

  setScreen(`
    <p class="page-title">${esc(t("addEmployee"))}</p>
    <div class="field"><label>${esc(t("fullName"))}</label><input id="f-name" type="text" /></div>
    <div class="field"><label>${esc(t("phoneNumber"))}</label><input id="f-phone" type="text" inputmode="tel" placeholder="+998901234567" /></div>
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
  }, "#4f3ff0");
}

async function screenPendingClaims() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const claims = await api("/admin/pending-claims");
  setScreen(`
    <p class="page-title">${esc(t("pendingClaimsTitle"))}</p>
    ${claims.length ? claims.map((c, i) => `
      <div class="fin-card" data-i="${i}">
        <div class="top">
          <span class="task">${esc(c.employee_name || "—")} — ${esc(c.task_title || "")}</span>
          <span class="status-pill warn">${esc(t(CLAIM_ACTION_KEYS[c.action_type]))}</span>
        </div>
        <p class="desc">${esc(formatDt(c.claimed_at))}${c.reason ? " · " + esc(c.reason) : ""}</p>
        <div class="amount-row">
          <button class="btn primary f-approve">${icon("check")} ${esc(t("approveClaimBtn"))}</button>
          <button class="btn danger f-reject">${icon("x")} ${esc(t("rejectClaimBtn"))}</button>
        </div>
      </div>
    `).join("") : `<p class="empty-state">${esc(t("noPendingClaims"))}</p>`}
  `);
  root.querySelectorAll(".fin-card").forEach((card) => {
    const item = claims[Number(card.dataset.i)];
    const approveBtn = card.querySelector(".f-approve");
    if (approveBtn) {
      approveBtn.onclick = async () => {
        try {
          await api(`/admin/claims/${item.id}/approve`, { method: "POST" });
          await replaceTop(screenPendingClaims);
        } catch (e) {
          showError(e.message);
        }
      };
    }
    const rejectBtn = card.querySelector(".f-reject");
    if (rejectBtn) {
      rejectBtn.onclick = async () => {
        try {
          await api(`/admin/claims/${item.id}/reject`, { method: "POST", body: JSON.stringify({}) });
          await replaceTop(screenPendingClaims);
        } catch (e) {
          showError(e.message);
        }
      };
    }
  });
}

function statRowsHtml(stats) {
  return stats.map((s, i) => `
    <div class="stat-row">
      <span class="rank">${i + 1}</span>
      <span class="nm">${esc(s.full_name)}<div class="completed">${s.completed_tasks} ${esc(t("completedThisMonth"))} · ${s.penalty_count} ${esc(t("penaltyCountLbl")).toLowerCase()}</div></span>
      <span class="score ${scoreClass(s.total_score)}">${scoreSigned(s.total_score)}</span>
    </div>
  `).join("");
}

/* Statistikaga faqat ISHCHI/BRIGADIR kiradi (rahbar/nazoratchi/sotuvchida
   KPI yo'q — backend'ning o'zi shularni chiqarib tashlaydi). Xodimlar
   ekranidagi kabi: avval umumiy (aralash, saralangan) reyting, ustida esa
   rol bo'yicha alohida ro'yxatga o'tish tugmalari. */
async function screenFullStats() {
  // Mebel ("Fasad seh"): "Kunlik norma (sig'im)" TZ'da Nazorat Trello
  // (fasad_sex) uchun mo'ljallangan — mebel kontekstida bu nav-card
  // ko'rsatilmaydi, fasad_sex uchun to'liq qoladi.
  const mebelOnly = nav.module === "mebel";
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const stats = await api("/admin/stats");
  if (!stats.length) {
    setScreen(`<p class="page-title">${esc(t("fullStatsTitle"))}</p><p class="empty-state">${esc(t("noStats"))}</p>`);
    return;
  }
  const roles = Object.keys(ROLE_LABELS[state.lang]).filter((r) => stats.some((s) => s.role === r));
  setScreen(`
    <p class="page-title">${esc(t("fullStatsTitle"))}</p>
    ${roles.length > 1 ? roles.map((r) => `
        <button class="nav-card" data-role="${r}">
          <span class="ic">${icon(ROLE_ICONS[r])}</span><span class="grow">${esc(ROLE_LABELS[state.lang][r])}</span><span class="badge">${stats.filter((s) => s.role === r).length}</span><span class="chev">›</span>
        </button>
      `).join("") : ""}
    ${mebelOnly ? "" : `<button class="nav-card" id="nav-capacity"><span class="ic">${icon("ruler")}</span><span class="grow">${esc(t("capacityStatsNav"))}</span><span class="chev">›</span></button>`}
    <p class="section-lbl">${esc(t("overallRanking"))}</p>
    ${statRowsHtml(stats)}
  `);
  root.querySelectorAll(".nav-card[data-role]").forEach((el) => {
    el.onclick = () => show(screenStatsByRole, el.dataset.role);
  });
  const capacityBtn = root.querySelector("#nav-capacity");
  if (capacityBtn) capacityBtn.onclick = () => show(screenCapacityDepartmentPicker);
}

async function screenStatsByRole(role) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const stats = (await api("/admin/stats")).filter((s) => s.role === role);
  setScreen(`
    <p class="page-title">${esc(ROLE_LABELS[state.lang][role])} (${stats.length})</p>
    ${stats.length ? statRowsHtml(stats) : `<p class="empty-state">${esc(t("noStats"))}</p>`}
  `);
}

async function screenCapacityDepartmentPicker() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const departments = await api("/admin/departments");
  setScreen(`
    <p class="page-title">${esc(t("capacityStatsTitle"))}</p>
    <p class="page-sub">${esc(t("capacityPickDepartment"))}</p>
    ${departments.map((d, i) => `
      <button class="nav-card" data-i="${i}"><span class="ic">${icon("factory")}</span><span class="grow">${esc(d.name)}</span><span class="chev">›</span></button>
    `).join("")}
  `);
  root.querySelectorAll(".nav-card").forEach((el) => {
    const dept = departments[Number(el.dataset.i)];
    el.onclick = () => show(screenCapacityStats, dept.id, dept.name);
  });
}

async function screenCapacityStats(departmentId, departmentName) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const cap = await api(`/admin/stats/capacity?department_id=${departmentId}`);
  setScreen(`
    <p class="page-title">${esc(departmentName)}</p>
    <div class="hero-row">
      <div class="hero-tile"><span class="num">${cap.worker_count}</span><span class="lbl">${esc(t("workerCountLabel"))}</span></div>
      <div class="hero-tile"><span class="num">${cap.planned_points}</span><span class="lbl">${esc(t("plannedPointsLabel"))}</span></div>
    </div>
    <div class="hero-row">
      <div class="hero-tile"><span class="num">${cap.actual_points}</span><span class="lbl">${esc(t("actualPointsLabel"))}</span></div>
    </div>
    <p class="page-sub">${esc(t("capacityActualCaption"))}</p>
  `);
}

/* ---------- Sozlamalar (16-band) ---------- */

const SETTING_FIELDS = [
  "default_penalty_multiplier", "brigade_share_ratio", "balls_per_day_shift",
  "plus_ball_per_day", "plus_ball_max_days", "report_time",
  "lead_follow_up_threshold_days", "daily_quota_points_per_worker", "daily_report_time",
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
    <button class="nav-card" id="nav-chain"><span class="ic">${icon("link")}</span><span class="grow">${esc(t("departmentChainNav"))}</span><span class="chev">›</span></button>
    <button class="nav-card" id="nav-autoreassign"><span class="ic">${icon("repeat")}</span><span class="grow">${esc(t("autoreassignNav"))}</span><span class="chev">›</span></button>
    <button class="nav-card" id="nav-reminders"><span class="ic">${icon("clock")}</span><span class="grow">${esc(t("remindersNav"))}</span><span class="chev">›</span></button>
    <button class="nav-card" id="nav-departments"><span class="ic">${icon("factory")}</span><span class="grow">${esc(t("departmentsNav"))}</span><span class="chev">›</span></button>
  `);
  root.querySelectorAll(".settings-row").forEach((el) => {
    el.onclick = () => show(screenEditSetting, el.dataset.field, snapshot[el.dataset.field]);
  });
  root.querySelector("#nav-chain").onclick = () => show(screenDepartmentChain);
  root.querySelector("#nav-autoreassign").onclick = () => show(screenAutoreassign);
  root.querySelector("#nav-reminders").onclick = () => show(screenReminders);
  root.querySelector("#nav-departments").onclick = () => show(screenDepartments);
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
  }, "#4f3ff0");
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

/* ---------- Fasad sex TZ: Bo'limlar CRUD (Phase 2 infratuzilma) ---------- */

async function screenDepartments() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const departments = await api("/admin/departments");
  setScreen(`
    <p class="page-title">${esc(t("departmentsNav"))}</p>
    <button class="nav-card accent" id="nav-material-template"><span class="ic">${icon("material")}</span><span class="grow">${esc(t("addMaterialTemplateNav"))}</span><span class="chev">›</span></button>
    ${departments.length ? departments.map((d, i) => `
      <button class="fin-card" data-i="${i}" style="cursor:pointer;text-align:left;font:inherit;color:inherit;">
        <div class="top"><span class="task">${esc(d.name)}</span><span class="chev">›</span></div>
        <div class="amount-row">
          <span class="status-pill ${d.auto_reassign_after_48h ? "positive" : "neutral"}">${esc(t("autoreassignNav"))}: ${d.auto_reassign_after_48h ? "ON" : "OFF"}</span>
          <span class="status-pill ${d.starts_stopped ? "positive" : "neutral"}">${esc(t("startsStoppedField"))}: ${d.starts_stopped ? "ON" : "OFF"}</span>
        </div>
      </button>
    `).join("") : `<p class="empty-state">${esc(t("noDepartments"))}</p>`}
  `);
  root.querySelector("#nav-material-template").onclick = () => show(screenAddMaterialTemplate);
  root.querySelectorAll(".fin-card").forEach((el) => {
    const dept = departments[Number(el.dataset.i)];
    el.onclick = () => show(screenDepartmentEdit, dept, departments);
  });
  setMainButton(`➕ ${t("addDepartmentBtn")}`, () => show(screenAddDepartment), "#4f3ff0");
}

async function screenDepartmentEdit(department, allDepartments) {
  setScreen(`
    <p class="page-title">${esc(department.name)}</p>
    <div class="field"><label>${esc(t("departmentNameField"))}</label><input id="f-name" type="text" value="${esc(department.name)}" /></div>
    <div class="field"><label>${esc(t("trelloListIdField"))}</label><input id="f-trello-list" type="text" value="${esc(department.trello_list_id || "")}" /></div>
    <label class="check-row"><input type="checkbox" id="f-autoreassign" ${department.auto_reassign_after_48h ? "checked" : ""} />${esc(t("autoreassignNav"))}</label>
    <label class="check-row"><input type="checkbox" id="f-starts-stopped" ${department.starts_stopped ? "checked" : ""} />${esc(t("startsStoppedField"))}</label>
    <div class="field"><label>${esc(t("autoResumeHoursField"))}</label><input id="f-auto-resume" type="number" min="1" value="${department.stopped_auto_resume_after_hours ?? ""}" /></div>
    <label class="check-row"><input type="checkbox" id="f-requires-join" ${department.requires_join ? "checked" : ""} />${esc(t("requiresJoinField"))}</label>
    <div class="field"><label>${esc(t("factoryNameField"))}</label><input id="f-factory" type="text" value="${esc(department.factory_name || "")}" /></div>
    <div class="field"><label>${esc(t("stopTargetListField"))}</label><input id="f-stop-target" type="text" value="${esc(department.stop_target_list_id || "")}" /></div>
    <p class="section-lbl">${esc(t("departmentAdvancedSection"))}</p>
    <button class="nav-card" id="nav-dept-chain"><span class="ic">${icon("link")}</span><span class="grow">${esc(t("departmentChainNav"))}</span><span class="chev">›</span></button>
    <button class="nav-card" id="nav-dept-fork"><span class="ic">${icon("branch")}</span><span class="grow">${esc(t("forkTargetsNav"))}</span><span class="chev">›</span></button>
  `);
  root.querySelector("#nav-dept-chain").onclick = () => show(screenDepartmentChainEdit, department, allDepartments);
  root.querySelector("#nav-dept-fork").onclick = () => show(screenDepartmentForkTargets, department, allDepartments);

  setMainButton(`💾 ${t("saveChanges")}`, async () => {
    const name = root.querySelector("#f-name").value.trim();
    if (!name) {
      showError(t("departmentNameField"));
      return;
    }
    const autoResumeRaw = root.querySelector("#f-auto-resume").value.trim();
    const app = tg();
    app.MainButton.showProgress();
    try {
      await api(`/admin/departments/${department.id}`, {
        method: "POST",
        body: JSON.stringify({
          name,
          trello_list_id: root.querySelector("#f-trello-list").value.trim() || null,
          auto_reassign_after_48h: root.querySelector("#f-autoreassign").checked,
          starts_stopped: root.querySelector("#f-starts-stopped").checked,
          stopped_auto_resume_after_hours: autoResumeRaw ? Number(autoResumeRaw) : null,
          requires_join: root.querySelector("#f-requires-join").checked,
          factory_name: root.querySelector("#f-factory").value.trim() || null,
          stop_target_list_id: root.querySelector("#f-stop-target").value.trim() || null,
        }),
      });
      app.HapticFeedback && app.HapticFeedback.notificationOccurred("success");
      await goBack();
    } catch (e) {
      showError(e.message);
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#4f3ff0");
}

async function screenDepartmentForkTargets(department, allDepartments) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const current = await api(`/admin/departments/${department.id}/fork-targets`);
  const selectedIds = new Set(current.map((c) => c.target_department_id));
  const options = allDepartments.filter((d) => d.id !== department.id);
  setScreen(`
    <p class="page-title">${esc(department.name)}</p>
    <p class="page-sub">${esc(t("forkTargetsPick"))}</p>
    ${options.length ? options.map((d) => `
      <label class="check-row"><input type="checkbox" value="${d.id}" class="f-target" ${selectedIds.has(d.id) ? "checked" : ""} />${esc(d.name)}</label>
    `).join("") : `<p class="empty-state">${esc(t("noDepartments"))}</p>`}
  `);
  setMainButton(`💾 ${t("saveChanges")}`, async () => {
    const targetIds = Array.from(root.querySelectorAll(".f-target:checked")).map((el) => Number(el.value));
    const app = tg();
    app.MainButton.showProgress();
    try {
      await api(`/admin/departments/${department.id}/fork-targets`, {
        method: "POST",
        body: JSON.stringify({ target_department_ids: targetIds }),
      });
      app.HapticFeedback && app.HapticFeedback.notificationOccurred("success");
      await goBack();
    } catch (e) {
      showError(e.message);
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#4f3ff0");
}

async function screenAddDepartment() {
  setScreen(`
    <p class="page-title">${esc(t("addDepartmentBtn"))}</p>
    <div class="field"><label>${esc(t("departmentNameField"))}</label><input id="f-name" type="text" /></div>
    <div class="field"><label>${esc(t("trelloListIdField"))}</label><input id="f-trello-list" type="text" /></div>
    <label class="check-row"><input type="checkbox" id="f-autoreassign" />${esc(t("autoreassignNav"))}</label>
    <label class="check-row"><input type="checkbox" id="f-starts-stopped" />${esc(t("startsStoppedField"))}</label>
  `);
  setMainButton(`💾 ${t("create")}`, async () => {
    const name = root.querySelector("#f-name").value.trim();
    if (!name) {
      showError(t("departmentNameField"));
      return;
    }
    const app = tg();
    app.MainButton.showProgress();
    try {
      await api("/admin/departments", {
        method: "POST",
        body: JSON.stringify({
          name,
          trello_list_id: root.querySelector("#f-trello-list").value.trim() || null,
          auto_reassign_after_48h: root.querySelector("#f-autoreassign").checked,
          starts_stopped: root.querySelector("#f-starts-stopped").checked,
        }),
      });
      app.HapticFeedback && app.HapticFeedback.notificationOccurred("success");
      await goBack();
    } catch (e) {
      showError(e.message);
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#4f3ff0");
}

async function screenAddMaterialTemplate() {
  setScreen(`
    <p class="page-title">${esc(t("materialTemplateTitle"))}</p>
    <div class="field"><label>${esc(t("materialNameLabel"))}</label><input id="f-material" type="text" /></div>
    <p class="hint">${esc(t("materialTemplateHint"))}</p>
  `);
  setMainButton(`💾 ${t("create")}`, async () => {
    const material = root.querySelector("#f-material").value.trim();
    if (!material) {
      showError(t("materialNameLabel"));
      return;
    }
    const stageNames = [
      `${material} fayl tashaldi`,
      `${material} ishlab chiqarishda tasdiqlandi`,
      `${material} 100% tayyor`,
    ];
    const app = tg();
    app.MainButton.showProgress();
    let done = 0;
    try {
      const created = [];
      for (const name of stageNames) {
        created.push(await api("/admin/departments", { method: "POST", body: JSON.stringify({ name }) }));
        done++;
      }
      for (let i = 0; i < created.length - 1; i++) {
        await api(`/admin/departments/${created[i].id}/chain`, {
          method: "POST",
          body: JSON.stringify({ next_department_id: created[i + 1].id }),
        });
        done++;
      }
      app.HapticFeedback && app.HapticFeedback.notificationOccurred("success");
      await goBack();
    } catch (e) {
      showError(t("materialTemplateFailed", done, stageNames.length + 2, e.message));
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#4f3ff0");
}

async function screenReminders() {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const schedule = await api("/admin/reminders");
  setScreen(`
    <p class="page-title">${esc(t("remindersTitle"))}</p>
    ${schedule.map((entry, i) => `
      <div class="fin-card" data-i="${i}">
        <div class="top"><span class="task">${icon("clock")} ${esc(entry.time)}</span><span class="status-pill warn">${esc(t("urgency_" + entry.urgency))}</span></div>
        <div class="amount-row">
          <button class="btn f-edit">${esc(t("edit"))}</button>
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
  setMainButton(t("addReminderBtn"), () => show(screenReminderForm, "add", null, null), "#4f3ff0");
}

async function screenReminderForm(mode, index, entry) {
  const urgencies = ["info", "warning", "urgent"];
  let urgency = (entry && entry.urgency) || "info";
  setScreen(`
    <p class="page-title">${esc(t("addReminderBtn"))}</p>
    <div class="field"><label>${esc(t("reminderTime"))}</label><input id="f-time" type="text" placeholder="15:00" value="${esc(entry ? entry.time : "")}" /></div>
    <p class="section-lbl">${esc(t("urgencyLevel"))}</p>
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
  }, "#4f3ff0");
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
      <button class="nav-card" data-i="${i}"><span class="ic">${icon("clock")}</span><span class="grow">${esc(task.title)}<div class="t-sub">${esc(task.department || "")}</div></span><span class="chev">›</span></button>
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
  }, "#4f3ff0");
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
      <button class="nav-card" data-i="${i}"><span class="ic">${icon("repeat")}</span><span class="grow">${esc(task.title)}<div class="t-sub">${esc(task.department || "")}</div></span><span class="chev">›</span></button>
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

async function screenBrigadierHome(brigadeId) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  let brigade;
  try {
    brigade = await api(`/brigadier/brigade${brigadeId ? `?brigade_id=${brigadeId}` : ""}`);
  } catch (e) {
    setScreen(`<p class="empty-state">${esc(t("noBrigade"))}</p>`);
    return;
  }
  const pendingWork = await api("/brigadier/pending-delegation");
  // Bitta brigadir bir nechta bo'limga rahbarlik qilishi mumkin (masalan
  // Kraska + Shkurka) — tanlov shu yerda, sotuvchining brend tanlovi bilan
  // bir xil ko'rinishda. Bitta brigadasi bo'lsa hech narsa ko'rinmaydi.
  const myBrigades = brigade.brigades || [];
  // Ball brigadadan MUSTAQIL (backend `own_score`ni o'zi hisoblaydi) — aks
  // holda ikkinchi brigada ekranida o'z bali "—" bo'lib qolar edi.
  const workers = brigade.members.filter((m) => m.employee_id !== state.employee.id);
  setScreen(`
    <p class="page-title">${esc(t("brigade_title"))}: ${esc(brigade.name)}</p>
    ${myBrigades.length > 1 ? `<div class="lead-brand-row">${myBrigades.map((b) => `
      <button class="brand-pill" data-bid="${b.id}" aria-selected="${b.id === brigade.id}">${esc(b.name.split(" — ")[0])}</button>
    `).join("")}</div>` : ""}
    <div class="hero-tile ${heroTone(brigade.own_score)}">
      <span class="num">${scoreSigned(brigade.own_score)}</span>
      <span class="lbl">${esc(t("currentMonthScore"))}</span>
    </div>
    ${pendingWork.length ? `<button class="alert-card" id="nav-new-work"><span class="ic">${icon("inbox")}</span><span class="grow">${esc(t("newWorkAlert", pendingWork.length))}</span><span class="chev">›</span></button>` : ""}
    ${workers.length ? workers.map((m, i) => `
      <div class="member-card ${m.total_score < 0 ? "low" : m.total_score > 0 ? "high" : ""}" data-i="${i}">
        <div class="member-top"><span class="nm">${esc(m.full_name)}</span><span class="score ${scoreClass(m.total_score)}">${scoreSigned(m.total_score)} ${state.lang === "ru" ? "б." : "ball"}</span></div>
        <div class="member-actions"><button class="btn-report">${icon("calendar")} ${esc(t("weeklyReport"))}</button><button class="btn-tasks">${icon("list")} ${esc(t("currentTasks"))}</button></div>
      </div>
    `).join("") : `<p class="empty-state">${esc(t("noBrigadeMembers"))}</p>`}
  `);
  root.querySelectorAll(".brand-pill").forEach((btn) => {
    btn.onclick = () => replaceTop(screenBrigadierHome, Number(btn.dataset.bid));
  });
  root.querySelectorAll(".member-card").forEach((card) => {
    const member = workers[Number(card.dataset.i)];
    card.querySelector(".btn-report").onclick = async (ev) => {
      ev.stopPropagation();
      const r = await api(`/brigadier/members/${member.employee_id}/report`);
      const app = tg();
      const msg = `${t("completedTasksLbl")}: ${r.completed_tasks}\n${t("totalScoreLbl")}: ${scoreSigned(r.total_score)}\n${t("penaltyCountLbl")}: ${r.penalty_count}`;
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
    ${items.map((tsk, i) => tsk.module === "mebel" ? `
      <div class="nav-card" data-i="${i}"><span class="ic">${icon("inbox")}</span><span class="grow">${esc(tsk.title)}<div class="t-sub">${esc(t("deadline"))}: ${esc(formatDt(tsk.deadline))}</div><div class="t-sub">${esc(t("assignViaTrelloHint"))}</div></span></div>
    ` : `
      <button class="nav-card accent" data-i="${i}"><span class="ic">${icon("inbox")}</span><span class="grow">${esc(tsk.title)}<div class="t-sub">${esc(t("deadline"))}: ${esc(formatDt(tsk.deadline))}</div></span><span class="chev">›</span></button>
    `).join("")}
  `);
  root.querySelectorAll("button.nav-card").forEach((el) => {
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
  }, "#4f3ff0");
}

async function screenMemberTasks(employeeId, fullName) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const tasks = await api(`/brigadier/members/${employeeId}/tasks`);
  setScreen(`
    <p class="page-title">${esc(fullName)}</p>
    ${tasks.length ? tasks.map((tsk, i) => `
      <button class="task-card ${statusClass(tsk.status)}" data-i="${i}">
        <p class="t-title">${esc(tsk.title)}</p>
        <span class="t-status">${taskStatusLine(tsk)}</span>
      </button>
    `).join("") : `<p class="empty-state">${esc(t("noTasks"))}</p>`}
  `);
  root.querySelectorAll(".task-card").forEach((el) => {
    const tsk = tasks[Number(el.dataset.i)];
    el.onclick = () => show(screenMemberTaskDetail, employeeId, fullName, tsk.id);
  });
}

/* Brigadir o'z brigadasidagi bitta ishchining bitta vazifasini ko'radi —
   mebel uchun bu yerda Pauza/Yakunlash (claim) tugmalari bor, chunki ishchi
   profilida ular endi umuman yo'q (`screenTaskDetail`ga qarang). Fasad sex
   uchun bu ekran faqat ma'lumot — amal ishchining o'z profilida qoladi
   (u yerda odatdagidek ishchi o'zi boshqaradi). */
async function screenMemberTaskDetail(employeeId, fullName, taskId) {
  setScreen(`<p class="loading">${esc(t("loading"))}</p>`);
  const tsk = await api(`/brigadier/members/${employeeId}/tasks/${taskId}`);
  const isMebel = tsk.module === "mebel";
  // STOPPED ham tekshiriladi: davom ettirish endi darhol emas, rahbar
  // tasdig'ini kutadigan so'rov (Pauza/Yakunlash bilan bir xil qoida).
  const isOpen = tsk.status === "active" || tsk.status === "overdue" || tsk.status === "stopped";
  const pending = isMebel && isOpen
    ? (await api(`/brigadier/members/${employeeId}/tasks/${taskId}/claim-status`)).pending_claim
    : null;
  const pillClass = tsk.status === "overdue" ? "critical" : tsk.status === "stopped" ? "neutral" : "positive";

  setScreen(`
    <p class="page-title">${esc(fullName)}</p>
    <p class="t-sub" style="margin-top:-8px">${esc(tsk.title)}</p>
    <span class="status-pill ${pillClass}">${esc(statusLabel(tsk.status))}</span>
    <div class="panel">
      <div class="kv-row"><span class="k">${esc(t("deadline"))}</span><span class="v">${esc(formatDt(tsk.deadline))}</span></div>
      ${tsk.status === "overdue" && tsk.deadline ? `<div class="kv-row"><span class="k">${esc(t("lateness"))}</span><span class="v">${esc(t("daysLate", daysLate(tsk.deadline)))}</span></div>` : ""}
      <div class="kv-row"><span class="k">${esc(t("department"))}</span><span class="v">${esc(tsk.department || "—")}</span></div>
    </div>
    ${pending ? `
      <div class="alert-card"><span class="ic">${icon("clock")}</span><span class="grow">${esc(t(CLAIM_PENDING_KEYS[pending.action_type]))}</span></div>
    ` : isMebel && (tsk.status === "active" || tsk.status === "overdue") ? `<button class="btn" id="btn-stop">${icon("stop")} ${esc(t("stop"))}</button>` : ""}
  `);

  if (!isMebel || pending) return;

  const stopBtn = root.querySelector("#btn-stop");
  if (stopBtn) stopBtn.onclick = () => show(screenMemberPauseClaim, employeeId, fullName, taskId);

  if (tsk.status === "active" || tsk.status === "overdue") {
    setMainButton(`✅ ${t("finish")}`, async () => {
      const app = tg();
      app.MainButton.showProgress();
      try {
        await api(`/brigadier/members/${employeeId}/tasks/${taskId}/finish-claim`, { method: "POST" });
        await replaceTop(screenMemberTaskDetail, employeeId, fullName, taskId);
      } catch (e) {
        showError(e.message);
      } finally {
        app.MainButton.hideProgress();
      }
    }, "#158f5c");
  } else if (tsk.status === "stopped") {
    setMainButton(`▶️ ${t("resume")}`, async () => {
      const app = tg();
      app.MainButton.showProgress();
      try {
        await api(`/brigadier/members/${employeeId}/tasks/${taskId}/resume-claim`, { method: "POST" });
        await replaceTop(screenMemberTaskDetail, employeeId, fullName, taskId);
      } catch (e) {
        showError(e.message);
      } finally {
        app.MainButton.hideProgress();
      }
    });
  }
}

async function screenMemberPauseClaim(employeeId, fullName, taskId) {
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
      await api(`/brigadier/members/${employeeId}/tasks/${taskId}/pause-claim`, { method: "POST", body: JSON.stringify({ reason }) });
      await goBack();
    } catch (e) {
      showError(e.message);
    } finally {
      app.MainButton.hideProgress();
    }
  }, "#d63356");
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
      <div class="kv-row"><span class="k">${esc(t("lastContact"))}</span><span class="v">${lead.last_contacted_at ? esc(t("daysAgo", Math.max(0, -daysUntil(lead.last_contacted_at)))) : "—"}</span></div>
    </div>
    <button class="btn" id="btn-call">${icon("phone")} ${esc(t("addCall"))}</button>
    ${isOpen ? `<button class="btn danger" id="btn-close-lost">${icon("x")} ${esc(t("closeLost"))}</button><button class="btn primary" id="btn-close-won">${icon("check")} ${esc(t("closeWon"))}</button>` : ""}
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
  }, "#4f3ff0");
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
      <button class="nav-card" id="nav-settings"><span class="ic">${icon("settings")}</span><span class="grow">${esc(t("settingsNav"))}</span><span class="chev">›</span></button>
    ` : ""}
    ${(me.available_modules || []).length > 1 ? `
      <button class="nav-card" id="nav-switch-module"><span class="ic">${icon("repeat")}</span><span class="grow">${esc(t("switchModuleLabel"))}</span><span class="chev">›</span></button>
    ` : ""}
  `);
  const settingsBtn = root.querySelector("#nav-settings");
  if (settingsBtn) settingsBtn.onclick = () => show(screenSettings);
  const switchModuleBtn = root.querySelector("#nav-switch-module");
  if (switchModuleBtn) {
    switchModuleBtn.onclick = () => {
      localStorage.removeItem(MODULE_STORAGE_KEY);
      nav.module = null;
      resetTo(screenModuleChooser);
    };
  }
  root.querySelectorAll(".lang-pill").forEach((btn) => {
    btn.onclick = async () => {
      const lang = btn.dataset.lang;
      if (lang === state.lang) return;
      state.lang = lang;
      document.documentElement.lang = lang;
      try {
        await api("/me/language", { method: "POST", body: JSON.stringify({ language: lang }) });
      } catch (e) {
        /* jim: interfeys baribir yangi tilda ko'rsatiladi, keyingi safar qayta so'raladi */
      }
      await replaceTop(screenProfile);
    };
  });
}

/* ---------- Modul tanlash (Fasad sex TZ, Phase 0) ---------- */

/* "mebel"/"fasad_sex" — bir nechta modulga ega foydalanuvchi (masalan ADMIN)
   birini tanlaydi, tanlov localStorage'da saqlanadi (theme'ning saqlanish
   uslubi bilan bir xil kalit nomlash: MODULE_STORAGE_KEY). */
async function screenModuleChooser() {
  setScreen(`
    <p class="page-title">${esc(t("chooseModuleTitle"))}</p>
    <button class="nav-card" data-module="mebel">
      <span class="ic">${icon("chair")}</span>
      <span class="grow">
        <span style="display:block">${esc(t("mebelModuleName"))}</span>
        <span style="display:block;font-size:12px;color:var(--ink-soft)">${esc(t("mebelModulePath"))}</span>
      </span>
      <span class="chev">›</span>
    </button>
    <button class="nav-card" data-module="fasad_sex">
      <span class="ic">${icon("building")}</span>
      <span class="grow">
        <span style="display:block">${esc(t("fasadModuleName"))}</span>
        <span style="display:block;font-size:12px;color:var(--ink-soft)">${esc(t("fasadModulePath"))}</span>
      </span>
      <span class="chev">›</span>
    </button>
  `);
  root.querySelectorAll("[data-module]").forEach((el) => {
    el.onclick = () => {
      const module = el.dataset.module;
      nav.module = module;
      localStorage.setItem(MODULE_STORAGE_KEY, module);
      const defs = tabDefsForRole(state.employee.role, nav.module);
      nav.section = defs[0].key;
      resetTo(defs[0].screen);
    };
  });
}

/* ---------- Bootstrap ---------- */

function applyTheme(scheme) {
  document.documentElement.setAttribute("data-theme", scheme === "dark" ? "dark" : "light");
}

function routeHome() {
  const defs = tabDefsForRole(state.employee.role, nav.module);
  nav.section = defs[0].key;
  resetTo(defs[0].screen);
}

async function bootstrap() {
  const splash = window.MeloresSplash;
  await Promise.all([_bootstrap(), splash ? splash.ready : Promise.resolve()]);
  if (splash) splash.hide();
}

async function _bootstrap() {
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
    document.documentElement.lang = state.lang;
  } catch (e) {
    if (e.status === 403) {
      setScreen(`<p class="error-banner">${I18N.uz.not_registered}</p>`);
      return;
    }
    setScreen(`<p class="error-banner">${I18N.uz.error_generic}</p><button class="btn" id="btn-retry">${I18N.uz.retry}</button>`);
    root.querySelector("#btn-retry").onclick = bootstrap;
    return;
  }

  const modules = state.employee.available_modules || ["mebel"];
  if (modules.length === 1) {
    nav.module = modules[0];
    routeHome();
    return;
  }
  const saved = localStorage.getItem(MODULE_STORAGE_KEY);
  if (saved && modules.includes(saved)) {
    nav.module = saved;
    routeHome();
    return;
  }
  nav.module = null;
  nav.section = null;
  resetTo(screenModuleChooser);
}

bootstrap();
