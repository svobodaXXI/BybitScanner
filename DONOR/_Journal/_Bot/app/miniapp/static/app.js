(function () {
  "use strict";

  const state = {
    page: "dashboard",
    journalFilters: { status: "", direction: "", account_id: "", instrument_id: "", from_at: "", to_at: "" },
    statisticsFilters: { status: "CLOSED", direction: "", account_id: "", instrument_id: "", from_at: "", to_at: "" },
    groupBy: "DIRECTION", fieldId: "", minSampleSize: 0, includeMissing: false, offset: 0, attentionTab: "ALL",
  };
  const content = document.getElementById("content");
  const platform = window.TradingJournalPlatform || {
    provider: "none",
    prepare() {},
    authHeaders() { return {}; },
    authErrorMessage: "Требуется авторизация.",
  };
  platform.prepare();

  function format(value) { return value === null || value === undefined || value === "" ? "—" : String(value); }
  function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;"}[char])); }
  function pnlClass(value) { return value === null || value === undefined || value === "" ? "pnl-neutral" : String(value).startsWith("-") ? "pnl-negative" : "pnl-positive"; }
  function statusLabel(value) { return value === "OPEN" ? "OPEN" : value === "READY" ? "✓ ГОТОВА" : value === "INCOMPLETE" ? "⚠ НЕ ГОТОВА" : String(value || "—"); }
  function statusClass(value) { return value === "OPEN" ? "pill-open" : value === "READY" ? "pill-ready" : "pill-incomplete"; }
  function authErrorMessage() { return platform.authErrorMessage || "Требуется авторизация."; }
  function setState(kind, message) {
    const auth = kind === "error" && message === authErrorMessage();
    content.setAttribute("aria-busy", kind === "loading" ? "true" : "false");
    if (kind === "loading") {
      content.innerHTML = `<div class="skeleton-stack" aria-label="${escapeHtml(message)}"><div class="skeleton hero"></div><div class="metric-grid"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div></div>`;
      return;
    }
    const icon = kind === "error" ? "!" : "⌁";
    content.innerHTML = `<div class="state-card ${kind} ${auth ? "auth-error" : ""}"><span class="state-icon" aria-hidden="true">${icon}</span><span>${escapeHtml(message)}</span>${kind === "error" ? '<button id="state-retry" class="secondary-button" type="button">Повторить</button>' : ""}</div>`;
    const retry = document.getElementById("state-retry");
    if (retry) retry.onclick = () => navigate(state.page);
  }
  function queryString(values) {
    const query = new URLSearchParams();
    Object.entries(values).forEach(([key, rawValue]) => {
      let value = rawValue;
      if (value !== "" && value !== null && value !== undefined) {
        if ((key === "from_at" || key === "to_at") && !String(value).endsWith("Z")) value = new Date(value).toISOString();
        query.set(key, value);
      }
    });
    return query.toString();
  }
  async function api(path) {
    const headers = platform.authHeaders();
    const response = await fetch(path, { headers });
    let body = {};
    try { body = await response.json(); } catch (_) {}
    if (!response.ok) {
      const error = body.error || {};
      if (response.status === 401 || response.status === 403) throw new Error(authErrorMessage());
      if (response.status === 404) throw new Error("Объект не найден.");
      if (response.status === 422) throw new Error(error.message || "Проверьте параметры запроса.");
      throw new Error("Сервис временно недоступен.");
    }
    return body;
  }
  async function apiJson(path, method, payload) {
    const headers = {"Content-Type": "application/json", ...platform.authHeaders()};
    const response = await fetch(path, {method, headers, body: JSON.stringify(payload)});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) throw new Error(authErrorMessage());
      throw new Error((body.error || {}).message || "Не удалось сохранить настройки.");
    }
    return body;
  }
  function metric(label, value, extraClass) { return `<div class="metric"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value ${extraClass || ""}">${escapeHtml(format(value))}</div></div>`; }
  function summaryHtml(summary, period) {
    return `<div class="hero-card"><p class="hero-label">Net PnL · ${escapeHtml(summary.currency || "валюта не указана")}</p><p class="hero-value ${pnlClass(summary.net_pnl)}">${escapeHtml(format(summary.net_pnl))}</p><p class="hero-meta">${escapeHtml(period)} · данные с сервера</p></div><div class="metric-grid">
      ${metric("Win rate", summary.win_rate)}${metric("Profit factor", summary.profit_factor)}${metric("Expectancy", summary.expectancy)}${metric("Готовы", summary.ready_count ?? summary.trade_count)}${metric("Не готовы", summary.excluded_incomplete_count)}${metric("Открытые", summary.open_count)}
      ${metric("Комиссии", summary.total_fees)}${metric("Расходы", summary.total_expenses)}${metric("Gross PnL", summary.gross_pnl)}${metric("Средний Net PnL", summary.average_net_pnl)}
    </div>`;
  }
  function periodLabel(filters) {
    if (filters.from_at || filters.to_at) return `${filters.from_at ? "с " + filters.from_at.replace("T", " ") : "за всё время"}${filters.to_at ? " до " + filters.to_at.replace("T", " ") : ""}`;
    return "Закрытые сделки · весь период";
  }
  async function loadDashboard() {
    setState("loading", "Загрузка обзора…");
    try {
      const [body, attention] = await Promise.all([api(`/api/miniapp/dashboard?${queryString(state.statisticsFilters)}`), api("/api/miniapp/attention")]);
      const s = attention.summary;
      const attentionBlock = s.total_attention ? `<button id="attention-card" class="attention-card card" type="button"><div class="section-heading"><strong>⚠ Требуют внимания ${s.total_attention}</strong><span>Открыть →</span></div><div class="attention-counts"><span>Открытые <strong>${s.open_count}</strong></span><span>Не заполнены <strong>${s.incomplete_count}</strong></span></div></button>` : `<div class="attention-ok card">✓ Все сделки обработаны</div>`;
      content.innerHTML = `<div class="section-heading"><h2>Обзор</h2><span class="pill pill-closed">LIVE DATA</span></div>${attentionBlock}${summaryHtml(body.summary, periodLabel(state.statisticsFilters))}`;
      const attentionCard = document.getElementById("attention-card"); if (attentionCard) attentionCard.onclick = () => navigate("attention");
    }
    catch (error) { setState("error", error.message); }
  }
  function filtersHtml(values, prefix) {
    return `<details class="filter-sheet"><summary>Фильтры <span class="muted">· аккаунт, даты, статус</span></summary><div class="filter-inner"><div class="filter-grid">
      <label>Аккаунт <input aria-label="Аккаунт" data-filter="account_id" data-prefix="${prefix}" value="${escapeHtml(values.account_id)}" placeholder="ID аккаунта"></label>
      <label>Статус <select aria-label="Статус" data-filter="status" data-prefix="${prefix}"><option value="">Все</option><option value="OPEN" ${values.status === "OPEN" ? "selected" : ""}>OPEN</option><option value="CLOSED" ${values.status === "CLOSED" ? "selected" : ""}>CLOSED</option></select></label>
      <label>Направление <select aria-label="Направление" data-filter="direction" data-prefix="${prefix}"><option value="">Все</option><option value="LONG" ${values.direction === "LONG" ? "selected" : ""}>LONG</option><option value="SHORT" ${values.direction === "SHORT" ? "selected" : ""}>SHORT</option></select></label>
      <label>Дата от <input aria-label="Дата от" type="datetime-local" data-filter="from_at" data-prefix="${prefix}" value="${escapeHtml(String(values.from_at || "").slice(0, 16))}"></label>
      <label>Дата до <input aria-label="Дата до" type="datetime-local" data-filter="to_at" data-prefix="${prefix}" value="${escapeHtml(String(values.to_at || "").slice(0, 16))}"></label>
    </div></div></details>`;
  }
  async function loadJournal() {
    setState("loading", "Загрузка журнала…");
    try {
      const body = await api(`/api/miniapp/trades?${queryString({...state.journalFilters, limit: 25, offset: state.offset})}`);
      content.innerHTML = `<div class="section-heading"><h2>Журнал</h2><span class="pill">${body.items.length} на странице</span></div><div class="journal-layout">${filtersHtml(state.journalFilters, "journal")}<div><details class="filter-sheet"><summary>Инструмент <span class="muted">· поиск по каталогу</span></summary><div class="filter-inner toolbar"><label>Поиск инструмента <input id="instrument-search" aria-label="Поиск инструмента" placeholder="BTC, акции…"></label><div class="trade-top"><button id="instrument-find" class="secondary-button" type="button">Найти</button><select id="instrument-select" aria-label="Выбранный инструмент"><option value="">Все инструменты</option></select></div></div></details><div id="journal-list" class="trade-list"></div><div class="pagination"><button id="prev" class="secondary-button" type="button">← Назад</button><button id="next" class="secondary-button" type="button">Вперёд →</button></div></div></div>`;
      const list = document.getElementById("journal-list");
      list.innerHTML = body.items.length ? body.items.map(tradeCard).join("") : `<div class="state-card"><span class="state-icon" aria-hidden="true">⌁</span><span>Нет сделок по выбранным фильтрам.</span></div>`;
      document.getElementById("prev").disabled = state.offset === 0; document.getElementById("next").disabled = !body.has_more;
      bindFilterInputs("journal");
      document.getElementById("prev").onclick = () => { state.offset = Math.max(0, state.offset - 25); loadJournal(); };
      document.getElementById("next").onclick = () => { state.offset += 25; loadJournal(); };
      document.getElementById("instrument-find").onclick = searchInstruments;
      list.querySelectorAll("[data-trade-id]").forEach((node) => node.onclick = () => loadDetails(node.dataset.tradeId));
    } catch (error) { setState("error", error.message); }
  }
  function bindFilterInputs(prefix) { content.querySelectorAll(`[data-prefix="${prefix}"]`).forEach((input) => input.onchange = () => { state[`${prefix}Filters`][input.dataset.filter] = input.value; state.offset = 0; prefix === "journal" ? loadJournal() : loadStatistics(); }); }
  function tradeCard(item) {
    const instrument = item.instrument;
    const title = instrument ? `${instrument.symbol}` : "Инструмент недоступен";
    const name = instrument ? instrument.name : "Проверьте каталог инструментов";
    const directionClass = item.direction === "LONG" ? "direction-long" : "direction-short";
    const dataStatus = item.data_status || item.status;
    const missing = (item.missing_reasons || []).map(missingLabel).join(", ");
    return `<button class="trade-card" data-trade-id="${escapeHtml(item.trade_id)}" aria-label="Открыть сделку ${escapeHtml(title)}"><div class="trade-top"><div><div class="trade-title">${escapeHtml(title)}</div><div class="trade-subtitle">${escapeHtml(name)}</div></div><span class="pill ${statusClass(dataStatus)}">${escapeHtml(statusLabel(dataStatus))}</span></div><div class="trade-meta"><span class="${directionClass}">${escapeHtml(item.direction)}</span> · Вход ${escapeHtml(format(item.entry_price))} · Выход ${escapeHtml(format(item.exit_price))}</div>${missing ? `<div class="trade-missing">Не заполнено: ${escapeHtml(missing)}</div>` : ""}<div class="trade-bottom"><span>${escapeHtml(format(item.closed_at || item.opened_at))}</span><strong class="${pnlClass(item.net_pnl)}">${escapeHtml(format(item.net_pnl))} ${escapeHtml(item.currency || "")}</strong></div></button>`;
  }
  function missingLabel(value) { return ({INSTRUMENT:"Инструмент", DIRECTION:"Направление", ENTRY_PRICE:"Вход", QUANTITY:"Количество", EXIT_PRICE:"Выход", NET_PNL:"Net PnL"}[value] || String(value).replace("dynamic_field:", "Поле ")) }
  async function searchInstruments() {
    const query = document.getElementById("instrument-search").value.trim();
    if (!query) return;
    try {
      const body = await api(`/api/miniapp/instruments?query=${encodeURIComponent(query)}`);
      const select = document.getElementById("instrument-select");
      select.innerHTML = `<option value="">Все инструменты</option>` + body.items.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.symbol)} — ${escapeHtml(item.name)}</option>`).join("");
      select.onchange = () => { state.journalFilters.instrument_id = select.value; state.offset = 0; loadJournal(); };
    } catch (error) { setState("error", error.message); }
  }
  async function loadDetails(tradeId) {
    setState("loading", "Загрузка сделки…");
    try { const body = await api(`/api/miniapp/trades/${encodeURIComponent(tradeId)}`); content.innerHTML = detailsHtml(body); document.getElementById("details-back").onclick = loadJournal; }
    catch (error) { setState("error", error.message); }
  }
  function detailsHtml(body) {
    const trade = body.trade; const instrument = body.instrument;
    const values = body.custom_values.length ? body.custom_values.map((item) => `<div class="custom-value"><span>${escapeHtml(item.label || item.code || "Поле")}</span><strong>${escapeHtml(item.option_label || format(item.value))}</strong></div>`).join("") : `<p class="muted">Дополнительных значений нет.</p>`;
    const dataStatus = trade.data_status || trade.status;
    const expenseTotal = trade.expenses.map((item) => item.amount).join(", ") || "—";
    const quality = dataStatus === "INCOMPLETE" ? `<div class="quality-warning">Не участвует в общей статистике до заполнения<br><small>${(trade.missing_reasons || []).map(missingLabel).join(", ")}</small></div>` : "";
    return `<button id="details-back" class="secondary-button" type="button">← К журналу</button><div class="detail-hero card"><span class="pill ${statusClass(dataStatus)}">${escapeHtml(statusLabel(dataStatus))}</span><h2>${escapeHtml(instrument ? instrument.symbol : "Сделка")}</h2><p class="hero-meta">${escapeHtml(instrument ? instrument.name : "Инструмент недоступен")} · <span class="${trade.direction === "LONG" ? "direction-long" : "direction-short"}">${escapeHtml(trade.direction)}</span></p><p class="detail-pnl ${pnlClass(trade.net_pnl)}">${escapeHtml(format(trade.net_pnl))} ${escapeHtml(trade.currency || "")}</p>${quality}</div><section class="detail-section"><h3 class="detail-section-title">Основные данные</h3><div class="card detail-grid">${[["Вход", trade.entry_price],["Выход", trade.exit_price],["Количество", trade.quantity],["Открыта", trade.opened_at],["Закрыта", trade.closed_at]].map(([label, value]) => `<div class="detail-item"><small>${escapeHtml(label)}</small><span>${escapeHtml(format(value))}</span></div>`).join("")}</div></section><section class="detail-section"><h3 class="detail-section-title">Финансы</h3><div class="card detail-grid">${[["Gross PnL", trade.gross_pnl],["Комиссии", trade.fees],["Расходы", expenseTotal],["Net PnL", trade.net_pnl]].map(([label, value]) => `<div class="detail-item"><small>${escapeHtml(label)}</small><span class="${label === "Net PnL" ? pnlClass(value) : ""}">${escapeHtml(format(value))}</span></div>`).join("")}</div></section><section class="detail-section"><h3 class="detail-section-title">Контекст сделки</h3><div class="card">${values}</div></section>`;
  }
  function renderMetricCatalog(layout, definitions) {
    const overview = layout.overview_metric_ids || [], home = layout.home_metric_ids || [];
    const rows = definitions.map((item) => { const selected = overview.includes(item.metric_id), index = overview.indexOf(item.metric_id); return `<div class="settings-row"><label><input type="checkbox" data-metric-toggle="${escapeHtml(item.metric_id)}" ${selected ? "checked" : ""}> ${escapeHtml(item.display_name)}</label><span class="settings-actions"><button class="secondary-button" data-metric-up="${escapeHtml(item.metric_id)}" ${!selected || index === 0 ? "disabled" : ""}>↑</button><button class="secondary-button" data-metric-down="${escapeHtml(item.metric_id)}" ${!selected || index === overview.length - 1 ? "disabled" : ""}>↓</button></span></div>`; }).join("");
    const homeRows = definitions.filter((item) => item.supports_home).map((item) => { const index = home.indexOf(item.metric_id), selected = index >= 0; return `<div class="settings-row"><label><input type="checkbox" data-home-toggle="${escapeHtml(item.metric_id)}" ${selected ? "checked" : ""}> ${escapeHtml(item.display_name)}</label><span class="settings-actions"><button class="secondary-button" data-home-up="${escapeHtml(item.metric_id)}" ${!selected || index === 0 ? "disabled" : ""}>↑</button><button class="secondary-button" data-home-down="${escapeHtml(item.metric_id)}" ${!selected || index === home.length - 1 ? "disabled" : ""}>↓</button></span></div>`; }).join("");
    document.getElementById("metric-catalog").innerHTML = `<p class="muted">Обзор: выберите метрики и меняйте порядок стрелками.</p>${rows}<hr><div class="section-heading"><strong>Главный экран</strong><select id="home-period"><option value="7d" ${layout.home_metric_period === "7d" ? "selected" : ""}>7 дней</option><option value="30d" ${layout.home_metric_period === "30d" ? "selected" : ""}>30 дней</option><option value="90d" ${layout.home_metric_period === "90d" ? "selected" : ""}>90 дней</option><option value="all" ${layout.home_metric_period === "all" ? "selected" : ""}>Весь период</option></select></div><p class="muted">До 6 закреплённых метрик.</p>${homeRows}`;
    const save = async (next) => { try { const saved = await apiJson("/api/miniapp/settings/statistics-layout", "PATCH", next); renderMetricCatalog(saved, definitions); } catch (error) { setState("error", error.message); } };
    document.querySelectorAll("[data-metric-toggle]").forEach((node) => node.onchange = () => { const ids = [...overview], index = ids.indexOf(node.dataset.metricToggle); if (index >= 0) ids.splice(index, 1); else ids.push(node.dataset.metricToggle); save({...layout, overview_metric_ids: ids}); });
    document.querySelectorAll("[data-metric-up], [data-metric-down]").forEach((node) => node.onclick = () => { const ids = [...overview], id = node.dataset.metricUp || node.dataset.metricDown, index = ids.indexOf(id), target = node.dataset.metricUp ? index - 1 : index + 1; if (index >= 0 && target >= 0 && target < ids.length) [ids[index], ids[target]] = [ids[target], ids[index]]; save({...layout, overview_metric_ids: ids}); });
    document.querySelectorAll("[data-home-toggle]").forEach((node) => node.onchange = () => { const ids = [...home], index = ids.indexOf(node.dataset.homeToggle); if (index >= 0) ids.splice(index, 1); else ids.push(node.dataset.homeToggle); save({...layout, home_metric_ids: ids}); });
    document.querySelectorAll("[data-home-up], [data-home-down]").forEach((node) => node.onclick = () => { const ids = [...home], id = node.dataset.homeUp || node.dataset.homeDown, index = ids.indexOf(id), target = node.dataset.homeUp ? index - 1 : index + 1; if (index >= 0 && target >= 0 && target < ids.length) [ids[index], ids[target]] = [ids[target], ids[index]]; save({...layout, home_metric_ids: ids}); });
    document.getElementById("home-period").onchange = (event) => save({...layout, home_metric_period: event.target.value});
  }
  function renderAutomaticCatalog(items) {
    const target = document.getElementById("automatic-catalog");
    target.innerHTML = items.length ? items.map((item) => `<div class="automatic-card"><div><strong>${escapeHtml(item.name)}</strong><p class="muted">${escapeHtml(item.description)}</p><small>Применимость: ${escapeHtml(item.applicability)} · Статус: доступно</small></div><label class="check-row"><input type="checkbox" data-automatic-factor="${escapeHtml(item.factor_id)}" ${item.enabled ? "checked" : ""}> ${item.enabled ? "Включено" : "Выключено"}</label></div>`).join("") : `<p class="muted">Каталог автоматических данных пока пуст.</p>`;
    target.querySelectorAll("[data-automatic-factor]").forEach((node) => node.onchange = async () => { try { await apiJson(`/api/miniapp/settings/automatic-factors/${encodeURIComponent(node.dataset.automaticFactor)}`, "PATCH", {enabled: node.checked}); } catch (error) { node.checked = !node.checked; setState("error", error.message); } });
  }
  async function loadStatistics() {
    setState("loading", "Загрузка статистики…");
    try {
      const [fields, summary, metrics, layout, automatic] = await Promise.all([api("/api/miniapp/dynamic-fields"), api(`/api/miniapp/statistics/summary?${queryString(state.statisticsFilters)}`), api("/api/miniapp/statistics/metrics"), api("/api/miniapp/settings/statistics-layout"), api("/api/miniapp/automatic-factors")]);
      content.innerHTML = `<div class="section-heading"><h2>Статистика</h2><span class="pill pill-closed">CLOSED</span></div>${filtersHtml(state.statisticsFilters, "statistics")}${summaryHtml(summary.summary, periodLabel(state.statisticsFilters))}<details class="filter-sheet"><summary>Настроить обзор</summary><div id="metric-catalog" class="filter-inner"></div></details><details class="filter-sheet"><summary>Автоматические данные</summary><div id="automatic-catalog" class="filter-inner"></div></details><details class="filter-sheet" open><summary>Срезы и Dynamic Statistics</summary><div class="filter-inner toolbar"><label>Группировать по <select id="group-by"><option value="ACCOUNT">Аккаунту</option><option value="INSTRUMENT">Инструменту</option><option value="DIRECTION" selected>Направлению</option><option value="DYNAMIC_FIELD">Dynamic Field</option></select></label><label id="field-wrap" hidden>Поле <select id="field-id"><option value="">Нет доступных полей</option>${fields.items.map((field) => `<option value="${escapeHtml(field.field_id)}">${escapeHtml(field.label)}</option>`).join("")}</select></label><label>Минимум в группе <input id="min-sample" type="number" min="0" step="1" value="${state.minSampleSize}"></label><label class="check-row"><input id="include-missing" type="checkbox" ${state.includeMissing ? "checked" : ""}> Включить missing bucket</label><button id="load-groups" class="primary-button" type="button">Показать группы</button></div></details><div id="groups"></div>`;
      renderMetricCatalog(layout, metrics.items); renderAutomaticCatalog(automatic.items);
      document.getElementById("group-by").onchange = updateGroupControls; document.getElementById("load-groups").onclick = loadGroups; bindFilterInputs("statistics"); updateGroupControls();
    } catch (error) { setState("error", error.message); }
  }
  function updateGroupControls() { document.getElementById("field-wrap").hidden = document.getElementById("group-by").value !== "DYNAMIC_FIELD"; }
  async function loadGroups() {
    const groupBy = document.getElementById("group-by").value; state.minSampleSize = Number(document.getElementById("min-sample").value || 0); state.includeMissing = document.getElementById("include-missing").checked; state.fieldId = document.getElementById("field-id").value;
    if (groupBy === "DYNAMIC_FIELD" && !state.fieldId) { document.getElementById("groups").innerHTML = `<div class="state-card"><span class="state-icon" aria-hidden="true">⌁</span><span>Нет доступных Dynamic Statistics полей.</span></div>`; return; }
    const params = queryString({...state.statisticsFilters, group_by: groupBy, field_id: groupBy === "DYNAMIC_FIELD" ? state.fieldId : "", min_sample_size: state.minSampleSize, include_missing: state.includeMissing});
    const target = document.getElementById("groups"); target.innerHTML = `<div class="skeleton-stack" aria-label="Загрузка групп…"><div class="skeleton"></div><div class="skeleton"></div></div>`;
    try {
      const body = await api(`/api/miniapp/statistics/groups?${params}`);
      const coverage = `<div class="coverage-card card"><div class="section-heading"><strong>Покрытие данных</strong><span class="pill">${escapeHtml(format(body.coverage_rate))}</span></div><div class="coverage-stats"><div class="coverage-stat"><small class="muted">Eligible</small><strong>${body.eligible_trade_count}</strong></div><div class="coverage-stat"><small class="muted">Filled</small><strong>${body.known_value_count}</strong></div><div class="coverage-stat"><small class="muted">Missing</small><strong>${body.missing_value_count}</strong></div></div><p class="muted">Coverage% и группы рассчитаны сервером.</p></div>`;
      target.innerHTML = coverage + (body.groups.length ? `<div class="group-list">${body.groups.map((group) => `<div class="group-card card"><div class="section-heading"><strong>${escapeHtml(group.label)}</strong><span class="pill">n=${group.sample_size}</span></div><div class="detail-grid"><div class="group-metric"><small>Net PnL</small><strong class="${pnlClass(group.net_pnl)}">${escapeHtml(format(group.net_pnl))}</strong></div><div class="group-metric"><small>Win rate</small><strong>${escapeHtml(format(group.win_rate))}</strong></div><div class="group-metric"><small>Profit factor</small><strong>${escapeHtml(format(group.profit_factor))}</strong></div><div class="group-metric"><small>Expectancy</small><strong>${escapeHtml(format(group.expectancy))}</strong></div></div></div>`).join("")}</div>` : `<div class="state-card"><span class="state-icon" aria-hidden="true">⌁</span><span>Нет групп по выбранным условиям.</span></div>`);
    } catch (error) { target.innerHTML = `<div class="state-card error"><span class="state-icon" aria-hidden="true">!</span><span>${escapeHtml(error.message)}</span></div>`; }
  }
  async function loadAttention() {
    setState("loading", "Загрузка центра внимания…");
    try {
      const body = await api("/api/miniapp/attention");
      const tabs = [["ALL", "Все"], ["OPEN", "Открытые"], ["INCOMPLETE", "Не заполнены"]];
      const items = body.items.filter((item) => state.attentionTab === "ALL" || item.data_status === state.attentionTab);
      content.innerHTML = `<div class="section-heading"><h2>Требуют внимания</h2><span class="pill">${body.summary.total_attention}</span></div><div class="attention-tabs">${tabs.map(([key, label]) => `<button class="secondary-button ${state.attentionTab === key ? "active" : ""}" data-attention-tab="${key}" type="button">${label}</button>`).join("")}</div><div class="trade-list">${items.length ? items.map((item) => `<button class="trade-card attention-item" data-trade-id="${escapeHtml(item.trade_id)}" type="button"><div class="trade-top"><strong>${escapeHtml(item.instrument)}</strong><span class="pill ${statusClass(item.data_status)}">${escapeHtml(statusLabel(item.data_status))}</span></div><div class="trade-meta"><span class="${item.direction === "LONG" ? "direction-long" : "direction-short"}">${escapeHtml(item.direction)}</span> · ${escapeHtml(item.lifecycle_status)}</div><div class="trade-missing">Не заполнено: ${escapeHtml(item.missing_reasons.map(missingLabel).join(", ") || "возраст сделки")}</div></button>`).join("") : `<div class="state-card"><span class="state-icon" aria-hidden="true">✓</span><span>Все сделки обработаны.</span></div>`}</div>`;
      content.querySelectorAll("[data-attention-tab]").forEach((node) => node.onclick = () => { state.attentionTab = node.dataset.attentionTab; loadAttention(); });
      content.querySelectorAll("[data-trade-id]").forEach((node) => node.onclick = () => loadDetails(node.dataset.tradeId));
    } catch (error) { setState("error", error.message); }
  }
  function navigate(page) { state.page = page; document.querySelectorAll(".nav-button").forEach((button) => { const active = button.dataset.page === page; button.classList.toggle("active", active); if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current"); }); if (page === "dashboard") loadDashboard(); else if (page === "journal") loadJournal(); else if (page === "attention") loadAttention(); else loadStatistics(); }
  document.querySelectorAll(".nav-button").forEach((button) => button.onclick = () => navigate(button.dataset.page));
  document.getElementById("refresh").onclick = () => navigate(state.page);
  navigate("dashboard");
})();
