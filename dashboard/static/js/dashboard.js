/* =============================================================
   dashboard.js
   Vanilla JS controller for the Lead Generation Dashboard.
   Talks to: /api/stats, /api/charts, /api/leads, /api/export/*,
             and Scraper API endpoints.
   ============================================================= */

(() => {
  "use strict";

  const REFRESH_INTERVAL_MS = 30000;
  const SCRAPE_POLL_MS = 2000;

  const state = {
    search: "",
    priority: "all",
    scoreRange: "",      // "min-max" string from the dropdown
    sortBy: "lead_score",
    sortOrder: "desc",
    page: 1,
    pageSize: 25,
    leadsById: new Map(), // cache of currently-loaded rows, for modal/drawer lookups
    selectedLeadId: null, // tracked for slide-out drawer highlighting
    spin: "all",
    startDate: "",
    endDate: "",
  };

  let scrapeState = {
    polling: false,
    pollTimer: null,
    lastState: "idle",
  };

  let charts = { priority: null, score: null, completeness: null };
  let searchDebounceTimer = null;

  // -----------------------------------------------------------
  // DOM refs
  // -----------------------------------------------------------
  const el = (id) => document.getElementById(id);

  const refs = {
    noDataBanner: el("noDataBanner"),
    dashboardBody: el("dashboardBody"),
    syncDot: el("syncDot"),
    syncText: el("syncText"),
    lastUpdated: el("lastUpdated"),

    statTotal: el("statTotal"),
    statHot: el("statHot"),
    statWarm: el("statWarm"),
    statCold: el("statCold"),
    statAvgScore: el("statAvgScore"),
    statAvgCompleteness: el("statAvgCompleteness"),

    searchInput: el("searchInput"),
    priorityFilter: el("priorityFilter"),
    scoreFilter: el("scoreFilter"),
    pageSizeSelect: el("pageSizeSelect"),
    spinFilter: el("spinFilter"),
    startDateFilter: el("startDateFilter"),
    endDateFilter: el("endDateFilter"),
    filteredLeadsCount: el("filteredLeadsCount"),

    leadTableBody: el("leadTableBody"),
    tableSummary: el("tableSummary"),
    pagination: el("pagination"),

    refreshBtn: el("refreshBtn"),
    exportCsvBtn: el("exportCsvBtn"),
    exportExcelBtn: el("exportExcelBtn"),

    sidebar: el("sidebar"),
    sidebarToggle: el("sidebarToggle"),

    // Scraper elements
    scrapeBusinessType: el("scrapeBusinessType"),
    scrapeCountry: el("scrapeCountry"),
    scrapeMaxCities: el("scrapeMaxCities"),
    scrapeStartBtn: el("scrapeStartBtn"),
    scrapeStopBtn: el("scrapeStopBtn"),
    scraperProgress: el("scraperProgress"),
    scrapeStateBadge: el("scrapeStateBadge"),
    scrapeElapsed: el("scrapeElapsed"),
    scrapeCitiesDone: el("scrapeCitiesDone"),
    scrapeLeadsFound: el("scrapeLeadsFound"),
    scrapeCurrentCity: el("scrapeCurrentCity"),
    scrapeBusinessProgress: el("scrapeBusinessProgress"),
    scrapeProgressBar: el("scrapeProgressBar"),
    scrapeProgressPct: el("scrapeProgressPct"),
    scrapeLog: el("scrapeLog"),

    // New premium visual layout elements
    globalScraperBadge: el("globalScraperBadge"),
    topbarTitle: el("topbarTitle"),
    topbarSubtitle: el("topbarSubtitle"),
    historySection: el("historySection"),
    historyTableBody: el("historyTableBody"),

    // Details Drawer elements
    detailsDrawer: el("detailsDrawer"),
    drawerCloseBtn: el("drawerCloseBtn"),
    drawerBusinessName: el("drawerBusinessName"),
    drawerPriority: el("drawerPriority"),
    drawerScore: el("drawerScore"),
    drawerEmail: el("drawerEmail"),
    drawerPhone: el("drawerPhone"),
    drawerWebsite: el("drawerWebsite"),
    drawerInstagram: el("drawerInstagram"),
    drawerFacebook: el("drawerFacebook"),
    drawerLinkedin: el("drawerLinkedin"),
  };

  // -----------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function safeUrl(value) {
    if (!value) return null;
    const v = String(value).trim();
    if (!v) return null;
    if (/^https?:\/\//i.test(v)) return v;
    return "https://" + v;
  }

  function linkOrDash(value, icon) {
    const url = safeUrl(value);
    if (!url) return '<span class="link-dash">—</span>';
    return `<a class="link-icon" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()" title="${escapeHtml(value)}"><i class="bi ${icon}"></i></a>`;
  }

  async function fetchJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Request failed: ${res.status}`);
    return res.json();
  }

  function buildLeadsQuery(extra = {}) {
    const params = new URLSearchParams();
    if (state.search) params.set("search", state.search);
    if (state.priority && state.priority !== "all") params.set("priority", state.priority);

    if (state.scoreRange) {
      const [min, max] = state.scoreRange.split("-");
      params.set("min_score", min);
      params.set("max_score", max);
    }

    if (state.spin && state.spin !== "all") params.set("spin", state.spin);
    if (state.startDate) params.set("start_date", state.startDate);
    if (state.endDate) params.set("end_date", state.endDate);

    params.set("sort_by", state.sortBy);
    params.set("sort_order", state.sortOrder);

    Object.entries(extra).forEach(([k, v]) => params.set(k, v));
    return params.toString();
  }

  function setSyncStatus(ok) {
    refs.syncDot.style.background = ok ? "#10b981" : "#ef4444";
    refs.syncDot.style.boxShadow = ok ? "0 0 10px rgba(16, 185, 129, 0.4)" : "0 0 10px rgba(239, 68, 68, 0.4)";
    refs.syncText.textContent = ok ? "Live · refreshes every 30s" : "Connection issue";
    refs.lastUpdated.textContent = "Updated " + new Date().toLocaleTimeString();
  }

  // -----------------------------------------------------------
  // Stats
  // -----------------------------------------------------------

  async function loadStats() {
    const data = await fetchJson("/api/stats");
    toggleNoData(!data.has_data);

    refs.statTotal.textContent = data.total_leads.toLocaleString();
    refs.statHot.textContent = data.hot_leads.toLocaleString();
    refs.statWarm.textContent = data.warm_leads.toLocaleString();
    refs.statCold.textContent = data.cold_leads.toLocaleString();
    refs.statAvgScore.textContent = data.has_data ? Math.round(data.avg_score) : "—";
    refs.statAvgCompleteness.textContent = data.has_data ? `${Math.round(data.avg_completeness)}%` : "—";

    return data;
  }

  function toggleNoData(show) {
    refs.noDataBanner.classList.toggle("d-none", !show);
    refs.dashboardBody.style.opacity = show ? "0.45" : "1";
    refs.dashboardBody.style.pointerEvents = show ? "none" : "auto";
  }

  // -----------------------------------------------------------
  // Charts
  // -----------------------------------------------------------

  function destroyChart(key) {
    if (charts[key]) {
      charts[key].destroy();
      charts[key] = null;
    }
  }

  async function loadCharts() {
    const data = await fetchJson("/api/charts");

    const priorityCtx = el("priorityChart").getContext("2d");
    const scoreCtx = el("scoreChart").getContext("2d");
    const completenessCtx = el("completenessChart").getContext("2d");

    destroyChart("priority");
    destroyChart("score");
    destroyChart("completeness");

    charts.priority = new Chart(priorityCtx, {
      type: "pie",
      data: {
        labels: ["Hot", "Warm", "Cold"],
        datasets: [{
          data: [
            data.priority_distribution.Hot,
            data.priority_distribution.Warm,
            data.priority_distribution.Cold,
          ],
          backgroundColor: ["#f43f5e", "#fbbf24", "#38bdf8"],
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 10, color: "#94a3b8", font: { size: 11 } }
          }
        },
      },
    });

    const scoreLabels = Object.keys(data.score_distribution);
    charts.score = new Chart(scoreCtx, {
      type: "bar",
      data: {
        labels: scoreLabels,
        datasets: [{
          label: "Leads",
          data: scoreLabels.map((l) => data.score_distribution[l]),
          backgroundColor: "#6366f1",
          borderRadius: 6,
          maxBarThickness: 36,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { precision: 0, color: "#64748b" },
            grid: { color: "rgba(255, 255, 255, 0.04)" }
          },
          x: {
            ticks: { color: "#64748b" },
            grid: { display: false }
          },
        },
      },
    });

    const completenessLabels = Object.keys(data.completeness_distribution);
    charts.completeness = new Chart(completenessCtx, {
      type: "bar",
      data: {
        labels: completenessLabels,
        datasets: [{
          label: "Leads",
          data: completenessLabels.map((l) => data.completeness_distribution[l]),
          backgroundColor: "#10b981",
          borderRadius: 6,
          maxBarThickness: 36,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { precision: 0, color: "#64748b" },
            grid: { color: "rgba(255, 255, 255, 0.04)" }
          },
          x: {
            ticks: { color: "#64748b" },
            grid: { display: false }
          },
        },
      },
    });
  }

  // -----------------------------------------------------------
  // Table
  // -----------------------------------------------------------

  function renderRow(lead) {
    const completeness = Math.round(lead.contact_completeness);
    const isSelected = String(lead.id) === state.selectedLeadId ? "row-selected" : "";
    return `
      <tr data-id="${lead.id}" class="${isSelected}">
        <td class="biz-name">${escapeHtml(lead.business_name) || "—"}</td>
        <td>${escapeHtml(lead.phone) || "—"}</td>
        <td>${escapeHtml(lead.email) || "—"}</td>
        <td>${linkOrDash(lead.website, "bi-globe")}</td>
        <td>${linkOrDash(lead.instagram, "bi-instagram")}</td>
        <td>${linkOrDash(lead.facebook, "bi-facebook")}</td>
        <td>${linkOrDash(lead.linkedin, "bi-linkedin")}</td>
        <td><span class="score-pill">${Math.round(lead.lead_score)}</span></td>
        <td><span class="badge-priority ${escapeHtml(lead.priority)}">${escapeHtml(lead.priority)}</span></td>
        <td>
          <div class="completeness-bar-wrap">
            <div class="completeness-bar-track"><div class="completeness-bar-fill" style="width:${completeness}%"></div></div>
            <span class="completeness-text">${completeness}%</span>
          </div>
        </td>
      </tr>`;
  }

  function renderPagination(page, totalPages) {
    refs.pagination.innerHTML = "";
    if (totalPages <= 1) return;

    const addItem = (label, targetPage, opts = {}) => {
      const li = document.createElement("li");
      li.className = `page-item ${opts.disabled ? "disabled" : ""} ${opts.active ? "active" : ""}`;
      const a = document.createElement("a");
      a.className = "page-link";
      a.href = "#";
      a.textContent = label;
      a.addEventListener("click", (e) => {
        e.preventDefault();
        if (opts.disabled || opts.active) return;
        state.page = targetPage;
        loadLeads();
      });
      li.appendChild(a);
      refs.pagination.appendChild(li);
    };

    addItem("‹", page - 1, { disabled: page <= 1 });

    const windowSize = 5;
    let start = Math.max(1, page - Math.floor(windowSize / 2));
    let end = Math.min(totalPages, start + windowSize - 1);
    start = Math.max(1, end - windowSize + 1);

    for (let p = start; p <= end; p++) {
      addItem(String(p), p, { active: p === page });
    }

    addItem("›", page + 1, { disabled: page >= totalPages });
  }

  async function loadLeads() {
    const query = buildLeadsQuery({ page: state.page, page_size: state.pageSize });
    const data = await fetchJson(`/api/leads?${query}`);

    state.leadsById = new Map(data.data.map((l) => [String(l.id), l]));

    if (data.data.length === 0) {
      refs.leadTableBody.innerHTML = `<tr class="empty-row"><td colspan="10">No matching leads found.</td></tr>`;
    } else {
      refs.leadTableBody.innerHTML = data.data.map(renderRow).join("");
    }

    const startIdx = data.total === 0 ? 0 : (data.page - 1) * data.page_size + 1;
    const endIdx = Math.min(data.page * data.page_size, data.total);
    refs.tableSummary.textContent = `Showing ${startIdx}-${endIdx} of ${data.total} leads`;

    if (refs.filteredLeadsCount) {
      refs.filteredLeadsCount.textContent = data.total.toLocaleString();
    }

    renderPagination(data.page, data.total_pages);
    updateSortHeaderUI();

    return data;
  }

  function updateSortHeaderUI() {
    document.querySelectorAll("th[data-sort]").forEach((th) => {
      const isActive = th.dataset.sort === state.sortBy;
      th.classList.toggle("sort-active", isActive);
      const icon = th.querySelector("i");
      if (icon) {
        icon.className = isActive
          ? (state.sortOrder === "asc" ? "bi bi-arrow-up" : "bi bi-arrow-down")
          : "bi bi-arrow-down-up";
      }
    });
  }

  // -----------------------------------------------------------
  // Slide-out Drawer details
  // -----------------------------------------------------------

  function openLeadModal(lead) {
    state.selectedLeadId = String(lead.id);

    // Update row highlighting
    document.querySelectorAll("#leadTable tbody tr").forEach((tr) => {
      tr.classList.toggle("row-selected", tr.dataset.id === state.selectedLeadId);
    });

    refs.drawerBusinessName.textContent = lead.business_name || "Lead Details";
    const priorityBadge = refs.drawerPriority;
    priorityBadge.textContent = lead.priority || "—";
    priorityBadge.className = `badge-priority ${lead.priority || ""}`;
    refs.drawerScore.textContent = `Score: ${Math.round(lead.lead_score)}`;

    refs.drawerEmail.textContent = lead.email || "—";
    refs.drawerPhone.textContent = lead.phone || "—";

    const setLink = (id, value) => {
      const url = safeUrl(value);
      el(id).innerHTML = url
        ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(value)}</a>`
        : "—";
    };
    setLink("drawerWebsite", lead.website);
    setLink("drawerInstagram", lead.instagram);
    setLink("drawerFacebook", lead.facebook);
    setLink("drawerLinkedin", lead.linkedin);

    // Slide in the drawer
    refs.detailsDrawer.classList.add("open");
  }

  function closeLeadDrawer() {
    state.selectedLeadId = null;
    document.querySelectorAll("#leadTable tbody tr").forEach((tr) => {
      tr.classList.remove("row-selected");
    });
    refs.detailsDrawer.classList.remove("open");
  }

  // -----------------------------------------------------------
  // Tab Management
  // -----------------------------------------------------------

  function switchTab(tabName) {
    document.querySelectorAll(".nav-link[data-tab]").forEach((link) => {
      link.classList.toggle("active", link.dataset.tab === tabName);
    });

    document.querySelectorAll(".tab-content").forEach((section) => {
      section.classList.toggle("active", section.id === `tab-${tabName}`);
    });

    // Update title/subtitle based on tab
    if (tabName === "scraper") {
      refs.topbarTitle.textContent = "Scraper Control";
      refs.topbarSubtitle.textContent = "Configure and run background scrape jobs.";
    } else if (tabName === "overview") {
      refs.topbarTitle.textContent = "Dashboard Overview";
      refs.topbarSubtitle.textContent = "Overall qualification statistics and metrics.";
    } else if (tabName === "leads") {
      refs.topbarTitle.textContent = "Leads Database";
      refs.topbarSubtitle.textContent = "Browse, filter, and export qualified leads.";
    }

    // Close details drawer when switching tabs to avoid stray UI
    closeLeadDrawer();
  }

  // -----------------------------------------------------------
  // Event wiring
  // -----------------------------------------------------------

  function wireEvents() {
    refs.searchInput.addEventListener("input", (e) => {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => {
        state.search = e.target.value;
        state.page = 1;
        loadLeads();
      }, 300);
    });

    refs.priorityFilter.addEventListener("change", (e) => {
      state.priority = e.target.value;
      state.page = 1;
      loadLeads();
    });

    refs.scoreFilter.addEventListener("change", (e) => {
      state.scoreRange = e.target.value;
      state.page = 1;
      loadLeads();
    });

    refs.pageSizeSelect.addEventListener("change", (e) => {
      state.pageSize = parseInt(e.target.value, 10);
      state.page = 1;
      loadLeads();
    });

    refs.spinFilter.addEventListener("change", (e) => {
      state.spin = e.target.value;
      state.page = 1;
      loadLeads();
    });

    refs.startDateFilter.addEventListener("change", (e) => {
      state.startDate = e.target.value;
      state.page = 1;
      loadLeads();
    });

    refs.endDateFilter.addEventListener("change", (e) => {
      state.endDate = e.target.value;
      state.page = 1;
      loadLeads();
    });

    document.querySelectorAll("th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const col = th.dataset.sort;
        if (state.sortBy === col) {
          state.sortOrder = state.sortOrder === "asc" ? "desc" : "asc";
        } else {
          state.sortBy = col;
          state.sortOrder = "desc";
        }
        state.page = 1;
        loadLeads();
      });
    });

    refs.leadTableBody.addEventListener("click", (e) => {
      const row = e.target.closest("tr[data-id]");
      if (!row) return;
      const lead = state.leadsById.get(row.dataset.id);
      if (lead) openLeadModal(lead);
    });

    refs.drawerCloseBtn.addEventListener("click", closeLeadDrawer);

    refs.refreshBtn.addEventListener("click", () => refreshAll(true));

    refs.exportCsvBtn.addEventListener("click", () => {
      window.location.href = `/api/export/csv?${buildLeadsQuery()}`;
    });

    refs.exportExcelBtn.addEventListener("click", () => {
      window.location.href = `/api/export/excel?${buildLeadsQuery()}`;
    });

    refs.sidebarToggle?.addEventListener("click", () => {
      refs.sidebar.classList.toggle("open");
    });

    // Tab switcher events
    document.querySelectorAll(".nav-link[data-tab]").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        switchTab(link.dataset.tab);
        refs.sidebar.classList.remove("open");
      });
    });



    // Wire Start/Stop scraper actions
    refs.scrapeStartBtn.addEventListener("click", startScrape);
    refs.scrapeStopBtn.addEventListener("click", stopScrape);
  }

  // -----------------------------------------------------------
  // Scraper control
  // -----------------------------------------------------------

  async function startScrape() {
    const businessType = refs.scrapeBusinessType.value.trim();
    const country = refs.scrapeCountry.value.trim();
    const maxCities = parseInt(refs.scrapeMaxCities.value, 10) || 30;

    if (!businessType) { refs.scrapeBusinessType.focus(); return; }
    if (!country) { refs.scrapeCountry.focus(); return; }

    setScraperFormDisabled(true);

    try {
      const res = await fetch("/api/scrape/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ business_type: businessType, country: country, max_cities: maxCities }),
      });
      const data = await res.json();

      if (!data.ok) {
        alert(data.error || "Failed to start scrape");
        setScraperFormDisabled(false);
        return;
      }

      refs.scraperProgress.classList.remove("d-none");
      refs.scrapeLog.textContent = "";
      startScrapePolling();
    } catch (err) {
      console.error("Start scrape failed:", err);
      alert("Failed to start scrape. Check the console.");
      setScraperFormDisabled(false);
    }
  }

  async function stopScrape() {
    try {
      await fetch("/api/scrape/stop", { method: "POST" });
    } catch (err) {
      console.error("Stop scrape failed:", err);
    }
  }

  function setScraperFormDisabled(disabled) {
    refs.scrapeBusinessType.disabled = disabled;
    refs.scrapeCountry.disabled = disabled;
    refs.scrapeMaxCities.disabled = disabled;
    refs.scrapeStartBtn.disabled = disabled;

    if (disabled) {
      refs.scrapeStartBtn.classList.add("d-none");
      refs.scrapeStopBtn.classList.remove("d-none");
    } else {
      refs.scrapeStartBtn.classList.remove("d-none");
      refs.scrapeStopBtn.classList.add("d-none");
    }
  }

  function startScrapePolling() {
    if (scrapeState.polling) return;
    scrapeState.polling = true;
    pollScrapeStatus();
  }

  function stopScrapePolling() {
    scrapeState.polling = false;
    if (scrapeState.pollTimer) {
      clearTimeout(scrapeState.pollTimer);
      scrapeState.pollTimer = null;
    }
  }

  async function pollScrapeStatus() {
    if (!scrapeState.polling) return;

    try {
      const data = await fetchJson("/api/scrape/status");
      updateScrapeUI(data);

      if (data.state === "completed" || data.state === "error") {
        stopScrapePolling();
        setScraperFormDisabled(false);

        // Give the cleaner 2s to write, then refresh
        setTimeout(() => refreshAll(true), 2000);
        return;
      }
    } catch (err) {
      console.error("Scrape status poll failed:", err);
    }

    scrapeState.pollTimer = setTimeout(pollScrapeStatus, SCRAPE_POLL_MS);
  }

  function formatElapsed(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  function renderHistoryRow(run) {
    const statusClasses = {
      completed: "status-completed",
      running: "status-running",
      stopping: "status-stopping",
      error: "status-error",
    };
    const cls = statusClasses[run.status] || "";
    const cleanStatus = run.status.charAt(0).toUpperCase() + run.status.slice(1);
    
    return `
      <tr>
        <td>${escapeHtml(run.timestamp)}</td>
        <td class="fw-semibold text-white">${escapeHtml(run.business_type)}</td>
        <td>${escapeHtml(run.country)}</td>
        <td>${run.max_cities}</td>
        <td>${run.leads_found}</td>
        <td>${escapeHtml(run.duration)}</td>
        <td><span class="${cls} fw-semibold">${cleanStatus}</span></td>
      </tr>`;
  }

  function updateScrapeUI(data) {
    // State badge
    const badge = refs.scrapeStateBadge;
    badge.textContent = data.state.charAt(0).toUpperCase() + data.state.slice(1);
    badge.className = `scraper-state-badge ${data.state}`;

    // Global Topbar Badge
    const isActive = data.state === "running" || data.state === "stopping";
    refs.globalScraperBadge.classList.toggle("active", isActive);

    // Elapsed
    refs.scrapeElapsed.textContent = data.elapsed_seconds ? formatElapsed(data.elapsed_seconds) : "";

    // Stats
    refs.scrapeCitiesDone.textContent = data.cities_completed || "0";
    refs.scrapeLeadsFound.textContent = data.total_leads_found || "0";
    refs.scrapeCurrentCity.textContent = data.current_city || "\u2014";

    if (data.total_businesses > 0) {
      refs.scrapeBusinessProgress.textContent = `${data.current_business_index}/${data.total_businesses}`;
    } else {
      refs.scrapeBusinessProgress.textContent = "\u2014";
    }

    // Progress bar
    const pct = data.progress_pct || 0;
    refs.scrapeProgressBar.style.width = `${pct}%`;
    refs.scrapeProgressPct.textContent = `${pct}%`;

    // Logs
    if (data.logs && data.logs.length > 0) {
      refs.scrapeLog.textContent = data.logs.join("\n");
      refs.scrapeLog.scrollTop = refs.scrapeLog.scrollHeight;
    }

    // History Table
    if (data.run_history && data.run_history.length > 0) {
      refs.historySection.classList.remove("d-none");
      refs.historyTableBody.innerHTML = data.run_history.map(renderHistoryRow).join("");
    } else {
      refs.historySection.classList.add("d-none");
    }

    // Hide stop button if not running
    if (data.state === "stopping") {
      refs.scrapeStopBtn.disabled = true;
      refs.scrapeStopBtn.textContent = "Stopping…";
    }
  }

  // -----------------------------------------------------------
  // Orchestration
  // -----------------------------------------------------------

  async function loadSpins() {
    try {
      const data = await fetchJson("/api/spins");
      const spinFilter = refs.spinFilter;
      if (!spinFilter) return;

      const currentVal = spinFilter.value || "all";

      let html = '<option value="all">All Historical Runs</option>';
      if (data.spins && data.spins.length > 0) {
        data.spins.forEach((s) => {
          html += `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`;
        });
      }
      spinFilter.innerHTML = html;
      spinFilter.value = currentVal;
    } catch (err) {
      console.error("Failed to load spins list:", err);
    }
  }

  async function refreshAll(isManual = false) {
    try {
      await Promise.all([loadStats(), loadCharts(), loadLeads(), loadSpins()]);
      setSyncStatus(true);
    } catch (err) {
      console.error("Dashboard refresh failed:", err);
      setSyncStatus(false);
    }
  }

  async function checkInitialScrapeState() {
    try {
      const data = await fetchJson("/api/scrape/status");
      
      // Load recent runs history initially if present
      if (data.run_history && data.run_history.length > 0) {
        refs.historySection.classList.remove("d-none");
        refs.historyTableBody.innerHTML = data.run_history.map(renderHistoryRow).join("");
      }

      if (data.state === "running" || data.state === "stopping") {
        refs.scraperProgress.classList.remove("d-none");
        setScraperFormDisabled(true);
        updateScrapeUI(data);
        startScrapePolling();
      }
    } catch (err) {
      // Status endpoint not available yet
    }
  }

  function init() {
    wireEvents();
    refreshAll();
    checkInitialScrapeState();
    setInterval(refreshAll, REFRESH_INTERVAL_MS);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
