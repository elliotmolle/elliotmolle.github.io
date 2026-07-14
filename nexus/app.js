const DATA_URL = './news_data.json';
const DEFAULT_TOPIC = 'Energy';
const DEFAULT_CATEGORY = 'All categories';
const DEFAULT_IMPACT = 'All impacts';
const DEFAULT_SORT = 'newest';
const IMPACT_ORDER = {
  High: 3,
  Medium: 2,
  Low: 1,
  Unspecified: 0,
};

const state = {
  allItems: [],
  filteredItems: [],
  activeId: null,
  topic: DEFAULT_TOPIC,
  category: DEFAULT_CATEGORY,
  impact: DEFAULT_IMPACT,
  sort: DEFAULT_SORT,
  search: '',
  loading: true,
  error: null,
  lastFocus: null,
};

const dom = {};

init();

function init() {
  cacheDom();
  bindEvents();
  setBusy(true);
  loadFeed();
}

function cacheDom() {
  dom.main = document.getElementById('main-content');
  dom.banner = document.getElementById('freshness-banner');
  dom.search = document.getElementById('search-input');
  dom.topicGroup = document.getElementById('topic-filter-group');
  dom.category = document.getElementById('category-filter');
  dom.impact = document.getElementById('impact-filter');
  dom.sort = document.getElementById('sort-filter');
  dom.reset = document.getElementById('reset-filters');
  dom.resultCount = document.getElementById('result-count');
  dom.lastUpdated = document.getElementById('last-updated');
  dom.resultsNote = document.getElementById('results-note');
  dom.loading = document.getElementById('loading-state');
  dom.error = document.getElementById('error-state');
  dom.errorMessage = document.getElementById('error-message');
  dom.retry = document.getElementById('retry-load');
  dom.empty = document.getElementById('empty-state');
  dom.resultsList = document.getElementById('results-list');
  dom.detailEmpty = document.getElementById('detail-empty');
  dom.detailContent = document.getElementById('detail-content');
  dom.dialog = document.getElementById('detail-dialog');
  dom.dialogContent = document.getElementById('dialog-content');
  dom.closeDialog = document.getElementById('close-dialog');
  dom.adminLoginBtn = document.getElementById('admin-login-btn');
}

function bindEvents() {
  dom.search.addEventListener('input', onSearchInput);
  dom.category.addEventListener('change', () => {
    state.category = dom.category.value;
    applyFilters();
  });
  dom.impact.addEventListener('change', () => {
    state.impact = dom.impact.value;
    applyFilters();
  });
  dom.sort.addEventListener('change', () => {
    state.sort = dom.sort.value;
    applyFilters();
  });
  dom.reset.addEventListener('click', resetFilters);
  dom.retry.addEventListener('click', loadFeed);
  dom.topicGroup.addEventListener('click', onTopicClick);
  dom.topicGroup.addEventListener('keydown', onTopicKeydown);
  dom.resultsList.addEventListener('click', onResultsClick);
  dom.resultsList.addEventListener('keydown', onResultsKeydown);
  dom.detailContent.addEventListener('click', onDetailActions);
  dom.closeDialog.addEventListener('click', closeDialog);
  dom.dialog.addEventListener('click', onDialogBackdropClick);
  dom.dialog.addEventListener('close', restoreFocusAfterDialog);
  window.addEventListener('keydown', onWindowKeydown);
  if (dom.adminLoginBtn) {
    dom.adminLoginBtn.addEventListener('click', handleAdminLogin);
  }
}

async function loadFeed() {
  state.loading = true;
  state.error = null;
  setBusy(true);
  showLoadingState();

  try {
    const response = await fetch(DATA_URL, { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    const payload = await response.json();
    if (!Array.isArray(payload)) {
      throw new Error('Feed payload is not an array.');
    }

    state.allItems = payload.map(normalizeRecord).filter(Boolean).sort(sortNewest);
    configureFilters();
    state.loading = false;
    state.error = null;
    applyFilters(true);
  } catch (error) {
    state.loading = false;
    state.error = error;
    showErrorState(error);
  } finally {
    setBusy(false);
  }
}

async function handleAdminLogin() {
  const passcode = prompt("Enter admin passcode:");
  if (btoa(passcode || "") === "TW9sbGU=") {
    try {
      const response = await fetch('./admin_news_data.json', { cache: 'no-store' });
      if (!response.ok) throw new Error("Admin data not found");
      const payload = await response.json();
      const adminItems = payload.map(normalizeRecord).filter(Boolean);
      
      const existingIds = new Set(state.allItems.map(item => item.id));
      const newItems = adminItems.filter(item => !existingIds.has(item.id));
      
      state.allItems = [...state.allItems, ...newItems].sort(sortNewest);
      configureFilters();
      applyFilters(true);
      dom.adminLoginBtn.style.display = 'none';
    } catch (e) {
      alert("Failed to load admin data.");
    }
  } else if (passcode) {
    alert("Incorrect passcode");
  }
}

function normalizeRecord(record, index) {
  if (!record || typeof record !== 'object') {
    return null;
  }

  const title = cleanText(record.title) || `Report ${index + 1}`;
  const summary = sanitizeSummary(record.summary);
  const source = cleanText(record.source) || 'Unknown source';
  const topic = cleanText(record.topic) || 'Unspecified';
  const category = cleanText(record.category) || 'Unspecified';
  const impact = normalizeImpact(record.impact);
  const sentiment = normalizeSentiment(record.sentiment);
  const url = normalizeUrl(record.url);
  const timestamp = parseTimestamp(record.timestamp);

  return {
    id: cleanText(record.id) || String(index + 1),
    title,
    summary,
    summaryExcerpt: summary || 'No summary text provided in the feed.',
    source,
    topic,
    category,
    impact,
    sentiment,
    url,
    timestamp,
    rawTimestamp: cleanText(record.timestamp),
  };
}

function configureFilters() {
  const topics = uniqueSorted(
    state.allItems.map((item) => item.topic).filter(Boolean)
  );
  const categories = uniqueSorted(
    state.allItems.map((item) => item.category).filter(Boolean)
  );
  const impacts = uniqueSorted(
    state.allItems.map((item) => item.impact).filter(Boolean),
    ['High', 'Medium', 'Low', 'Unspecified']
  );

  state.topic = topics.includes(DEFAULT_TOPIC)
    ? DEFAULT_TOPIC
    : topics[0] || 'All topics';
  renderTopicFilters(topics);
  populateSelect(dom.category, categories, DEFAULT_CATEGORY);
  populateSelect(dom.impact, impacts, DEFAULT_IMPACT);
  dom.category.value = DEFAULT_CATEGORY;
  dom.impact.value = DEFAULT_IMPACT;
  dom.sort.value = DEFAULT_SORT;
  dom.search.value = '';
  updateTopicButtons();
}

function renderTopicFilters(topics) {
  const buttons = ['All topics', ...topics];
  dom.topicGroup.innerHTML = '';

  buttons.forEach((topic) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'chip';
    button.dataset.topic = topic;
    button.textContent = topic;
    button.setAttribute('aria-pressed', String(topic === state.topic));
    dom.topicGroup.appendChild(button);
  });
}

function populateSelect(select, values, allLabel) {
  const currentValue = select.value || allLabel;
  select.innerHTML = '';

  const firstOption = document.createElement('option');
  firstOption.value = allLabel;
  firstOption.textContent = allLabel;
  select.appendChild(firstOption);

  values.forEach((value) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });

  if ([allLabel, ...values].includes(currentValue)) {
    select.value = currentValue;
  } else {
    select.value = allLabel;
  }
}

function onSearchInput(event) {
  state.search = event.target.value;
  applyFilters();
}

function onTopicClick(event) {
  const button = event.target.closest('button[data-topic]');
  if (!button) {
    return;
  }

  state.topic = button.dataset.topic || 'All topics';
  updateTopicButtons();
  applyFilters();
}

function onTopicKeydown(event) {
  const button = event.target.closest('button[data-topic]');
  if (!button) {
    return;
  }

  const buttons = Array.from(dom.topicGroup.querySelectorAll('button[data-topic]'));
  const index = buttons.indexOf(button);
  let nextIndex = -1;

  if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
    nextIndex = (index + 1) % buttons.length;
  } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
    nextIndex = (index - 1 + buttons.length) % buttons.length;
  } else if (event.key === 'Home') {
    nextIndex = 0;
  } else if (event.key === 'End') {
    nextIndex = buttons.length - 1;
  }

  if (nextIndex >= 0) {
    event.preventDefault();
    buttons[nextIndex].focus();
    state.topic = buttons[nextIndex].dataset.topic || 'All topics';
    updateTopicButtons();
    applyFilters();
  }
}

function updateTopicButtons() {
  Array.from(dom.topicGroup.querySelectorAll('button[data-topic]')).forEach((button) => {
    const selected = button.dataset.topic === state.topic;
    button.classList.toggle('is-active', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
}

function resetFilters() {
  state.search = '';
  state.topic = state.allItems.some((item) => item.topic === DEFAULT_TOPIC)
    ? DEFAULT_TOPIC
    : 'All topics';
  state.category = DEFAULT_CATEGORY;
  state.impact = DEFAULT_IMPACT;
  state.sort = DEFAULT_SORT;
  dom.search.value = '';
  dom.category.value = DEFAULT_CATEGORY;
  dom.impact.value = DEFAULT_IMPACT;
  dom.sort.value = DEFAULT_SORT;
  updateTopicButtons();
  applyFilters();
}

function applyFilters(forceSelection = false) {
  const search = state.search.trim().toLowerCase();
  const filtered = state.allItems.filter((item) => {
    const matchesTopic = state.topic === 'All topics' || item.topic === state.topic;
    const matchesCategory = state.category === DEFAULT_CATEGORY || item.category === state.category;
    const matchesImpact = state.impact === DEFAULT_IMPACT || item.impact === state.impact;
    const matchesSearch =
      !search ||
      [
        item.title,
        item.summary,
        item.source,
        item.topic,
        item.category,
        item.impact,
        item.sentiment,
        item.id,
      ]
        .join(' ')
        .toLowerCase()
        .includes(search);

    return matchesTopic && matchesCategory && matchesImpact && matchesSearch;
  });

  state.filteredItems = sortRecords(filtered, state.sort);

  if (forceSelection || !state.filteredItems.some((item) => item.id === state.activeId)) {
    state.activeId = state.filteredItems[0] ? state.filteredItems[0].id : null;
  }

  renderView();
}

function sortRecords(items, sortKey) {
  const list = [...items];
  const compareByText = (a, b, key) => a[key].localeCompare(b[key], undefined, { sensitivity: 'base' });

  switch (sortKey) {
    case 'oldest':
      return list.sort((a, b) => sortTimestamp(a, b));
    case 'impact':
      return list.sort((a, b) => {
        const diff = (IMPACT_ORDER[b.impact] || 0) - (IMPACT_ORDER[a.impact] || 0);
        return diff || sortNewest(a, b);
      });
    case 'source':
      return list.sort((a, b) => compareByText(a, b, 'source') || sortNewest(a, b));
    case 'title':
      return list.sort((a, b) => compareByText(a, b, 'title') || sortNewest(a, b));
    case 'newest':
    default:
      return list.sort(sortNewest);
  }
}

function sortNewest(a, b) {
  return sortTimestamp(b, a);
}

function sortTimestamp(a, b) {
  const left = a.timestamp ? a.timestamp.getTime() : -Infinity;
  const right = b.timestamp ? b.timestamp.getTime() : -Infinity;
  return left - right;
}

function renderView() {
  renderStatus();
  renderResults();
  renderDetailPanel();
}

function renderStatus() {
  const total = state.allItems.length;
  const visible = state.filteredItems.length;
  dom.resultCount.textContent = `${visible} of ${total} reports`;

  const latest = latestTimestamp(state.allItems);
  if (latest) {
    const exact = formatTimestamp(latest);
    dom.lastUpdated.textContent = `Last updated ${exact}`;
  } else {
    dom.lastUpdated.textContent = 'Last updated unavailable';
  }

  const freshness = freshnessMessage(latest);
  dom.banner.textContent = freshness.text;
  dom.banner.dataset.tone = freshness.tone;

  const topicLabel = state.topic === 'All topics' ? 'All topics' : state.topic;
  const categoryLabel = state.category === DEFAULT_CATEGORY ? 'All categories' : state.category;
  const impactLabel = state.impact === DEFAULT_IMPACT ? 'All impacts' : state.impact;
  dom.resultsNote.textContent = `${topicLabel}, ${categoryLabel}, and ${impactLabel} are active.`;
}

function renderResults() {
  setStateVisibility();

  if (state.loading) {
    return;
  }

  if (state.error) {
    return;
  }

  if (!state.filteredItems.length) {
    return;
  }

  dom.resultsList.innerHTML = state.filteredItems.map((item) => renderResultItem(item)).join('');
}

function setStateVisibility() {
  dom.loading.hidden = !state.loading;
  dom.error.hidden = !state.error;
  dom.empty.hidden = state.loading || state.error || state.filteredItems.length > 0;
  dom.resultsList.hidden = state.loading || state.error || state.filteredItems.length === 0;
}

function showLoadingState() {
  state.loading = true;
  state.error = null;
  setStateVisibility();
  dom.main.setAttribute('aria-busy', 'true');
  dom.banner.textContent = 'Loading feed data.';
  dom.banner.dataset.tone = 'watch';
  dom.resultCount.textContent = 'Loading reports';
  dom.lastUpdated.textContent = 'Refreshing feed';
  dom.resultsNote.textContent = 'Fetching the latest records.';
  dom.detailEmpty.hidden = false;
  dom.detailContent.hidden = true;
  dom.detailContent.innerHTML = '';
}

function showErrorState(error) {
  state.loading = false;
  state.filteredItems = [];
  state.activeId = null;
  dom.errorMessage.textContent = error instanceof Error ? error.message : 'The feed could not be loaded.';
  setStateVisibility();
  dom.resultsList.innerHTML = '';
  dom.detailEmpty.hidden = false;
  dom.detailContent.hidden = true;
  dom.detailContent.innerHTML = '';
  dom.main.setAttribute('aria-busy', 'false');
  dom.banner.textContent = 'Feed load failed.';
  dom.banner.dataset.tone = 'stale';
  dom.resultCount.textContent = '0 reports';
  dom.lastUpdated.textContent = 'Last updated unavailable';
  dom.resultsNote.textContent = 'Retry to reload the feed.';
}

function renderResultItem(item) {
  const selected = item.id === state.activeId;
  const sourceLink = item.url
    ? `<a class="source-link" href="${escapeAttr(item.url)}" target="_blank" rel="noopener noreferrer">Open source</a>`
    : `<span class="source-link" aria-label="No source URL supplied">No source URL</span>`;

  return `
    <li class="result-item">
      <article class="result-card" data-selected="${selected ? 'true' : 'false'}" aria-labelledby="result-title-${escapeAttr(item.id)}">
        <div class="result-top">
          <p class="eyebrow">Reported fact</p>
          <div class="result-top__tags">
            ${selected ? '<span class="tag tag--muted">Selected</span>' : ''}
            <span class="tag ${impactClass(item.impact)}">${escapeHtml(item.impact)} impact</span>
          </div>
        </div>
        <h3 class="result-title" id="result-title-${escapeAttr(item.id)}">${escapeHtml(item.title)}</h3>
        <p class="result-summary">${escapeHtml(truncateText(item.summaryExcerpt, 220))}</p>
        <dl class="result-meta">
          <div>
            <dt>Source label</dt>
            <dd>${escapeHtml(item.source)}</dd>
          </div>
          <div>
            <dt>Published</dt>
            <dd>${renderTime(item)}</dd>
          </div>
          <div>
            <dt>Topic label</dt>
            <dd>${escapeHtml(item.topic)}</dd>
          </div>
          <div>
            <dt>Category label</dt>
            <dd>${escapeHtml(item.category)}</dd>
          </div>
        </dl>
        <div class="result-actions">
          <button type="button" class="result-open" data-select-id="${escapeAttr(item.id)}">
            Open detail
          </button>
          ${sourceLink}
        </div>
      </article>
    </li>
  `;
}

function renderDetailPanel() {
  const item = state.filteredItems.find((entry) => entry.id === state.activeId) || null;

  if (!item) {
    dom.detailEmpty.hidden = false;
    dom.detailContent.hidden = true;
    dom.detailContent.innerHTML = '';
    return;
  }

  dom.detailEmpty.hidden = true;
  dom.detailContent.hidden = false;
  dom.detailContent.innerHTML = buildDetailMarkup(item, 'panel');
}

function buildDetailMarkup(item, mode) {
  const sourceLink = item.url
    ? `<a class="source-link" href="${escapeAttr(item.url)}" target="_blank" rel="noopener noreferrer">Open source</a>`
    : `<span class="source-link" aria-label="No source URL supplied">No source URL</span>`;
  const openButton =
    mode === 'panel'
      ? `<button type="button" class="result-open" data-open-modal="true">Open expanded view</button>`
      : '';
  const titleId = mode === 'dialog' ? 'modal-title' : 'detail-title';

  return `
    <article class="detail-stack">
      <header class="detail-header">
        <p class="eyebrow">Reported fact</p>
        <h3 class="detail-title" id="${titleId}">${escapeHtml(item.title)}</h3>
        <p class="detail-summary">${escapeHtml(item.summary || 'No summary text provided in the feed.')}</p>
      </header>

      <div class="detail-actions">
        ${sourceLink}
        ${openButton}
      </div>

      <p class="detail-note">
        Feed labels are shown separately from the report text. If a source URL is missing, the feed did not provide one.
      </p>

      <dl class="metadata-list">
        <div>
          <dt>Source label</dt>
          <dd>${escapeHtml(item.source)}</dd>
        </div>
        <div>
          <dt>Published</dt>
          <dd>${renderTime(item)}</dd>
        </div>
        <div>
          <dt>Topic label</dt>
          <dd>${escapeHtml(item.topic)}</dd>
        </div>
        <div>
          <dt>Category label</dt>
          <dd>${escapeHtml(item.category)}</dd>
        </div>
        <div>
          <dt>Impact label</dt>
          <dd><span class="tag ${impactClass(item.impact)}">${escapeHtml(item.impact)} impact</span></dd>
        </div>
        <div>
          <dt>Sentiment label</dt>
          <dd>${escapeHtml(item.sentiment)}</dd>
        </div>
        <div>
          <dt>Record ID</dt>
          <dd>${escapeHtml(item.id)}</dd>
        </div>
        <div>
          <dt>Source URL</dt>
          <dd>${item.url ? escapeHtml(item.url) : 'Not supplied'}</dd>
        </div>
      </dl>
    </article>
  `;
}

function onResultsClick(event) {
  const openButton = event.target.closest('button[data-select-id]');
  if (openButton) {
    state.activeId = openButton.dataset.selectId || null;
    renderView();
    scrollDetailIntoView();
    return;
  }

  const modalButton = event.target.closest('button[data-open-modal]');
  if (modalButton) {
    openDialog();
  }
}

function onResultsKeydown(event) {
  const currentButton = event.target.closest('button[data-select-id]');
  if (!currentButton) {
    return;
  }

  const buttons = Array.from(dom.resultsList.querySelectorAll('button[data-select-id]'));
  const index = buttons.indexOf(currentButton);
  let nextIndex = -1;

  if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
    nextIndex = Math.min(index + 1, buttons.length - 1);
  } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
    nextIndex = Math.max(index - 1, 0);
  } else if (event.key === 'Home') {
    nextIndex = 0;
  } else if (event.key === 'End') {
    nextIndex = buttons.length - 1;
  }

  if (nextIndex >= 0) {
    event.preventDefault();
    buttons[nextIndex].focus();
    state.activeId = buttons[nextIndex].dataset.selectId || null;
    renderView();
  }
}

function onDetailActions(event) {
  const openModal = event.target.closest('[data-open-modal]');
  if (openModal) {
    openDialog();
  }
}

function openDialog() {
  const item = state.filteredItems.find((entry) => entry.id === state.activeId);
  if (!item) {
    return;
  }

  state.lastFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  dom.dialogContent.innerHTML = buildDetailMarkup(item, 'dialog');

  if (typeof dom.dialog.showModal === 'function') {
    dom.dialog.showModal();
  } else {
    dom.dialog.setAttribute('open', 'true');
  }

  const closeButton = dom.dialog.querySelector('#close-dialog');
  if (closeButton instanceof HTMLElement) {
    closeButton.focus();
  }
}

function closeDialog() {
  if (typeof dom.dialog.close === 'function' && dom.dialog.open) {
    dom.dialog.close();
    return;
  }

  dom.dialog.removeAttribute('open');
  restoreFocusAfterDialog();
}

function onDialogBackdropClick(event) {
  if (event.target === dom.dialog) {
    closeDialog();
  }
}

function restoreFocusAfterDialog() {
  if (state.lastFocus && typeof state.lastFocus.focus === 'function') {
    state.lastFocus.focus();
  }
  state.lastFocus = null;
}

function onWindowKeydown(event) {
  if (event.key === 'Escape' && dom.dialog.open) {
    dom.dialog.close();
  }
}

function scrollDetailIntoView() {
  const detailPanel = document.getElementById('detail-panel');
  if (detailPanel) {
    const prefersReducedMotion =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    detailPanel.scrollIntoView({ block: 'nearest', behavior: prefersReducedMotion ? 'auto' : 'smooth' });
  }
}

function setBusy(isBusy) {
  dom.main.setAttribute('aria-busy', String(isBusy));
}

function latestTimestamp(items) {
  const valid = items.filter((item) => item.timestamp);
  if (!valid.length) {
    return null;
  }

  return valid.reduce((latest, current) => {
    if (!latest || current.timestamp.getTime() > latest.getTime()) {
      return current.timestamp;
    }
    return latest;
  }, null);
}

function freshnessMessage(timestamp) {
  if (!timestamp) {
    return {
      tone: 'stale',
      text: 'Feed freshness unavailable.',
    };
  }

  const ageMs = Date.now() - timestamp.getTime();
  const ageText = formatDuration(Math.abs(ageMs));

  if (ageMs < 0) {
    return {
      tone: 'watch',
      text: `Newest record is ${ageText} ahead of this clock.`,
    };
  }

  if (ageMs > 24 * 60 * 60 * 1000) {
    return {
      tone: 'stale',
      text: `Newest record is ${ageText} old. Feed may be stale.`,
    };
  }

  if (ageMs > 6 * 60 * 60 * 1000) {
    return {
      tone: 'watch',
      text: `Newest record is ${ageText} old.`,
    };
  }

  return {
    tone: 'fresh',
    text: `Newest record is ${ageText} old.`,
  };
}

function renderTime(item) {
  if (!item.timestamp) {
    return '<span class="tag tag--muted">Timestamp unavailable</span>';
  }

  return `<time datetime="${escapeAttr(item.timestamp.toISOString())}" title="${escapeAttr(
    formatTimestamp(item.timestamp)
  )}">${escapeHtml(formatRelative(item.timestamp))}</time>`;
}

function parseTimestamp(value) {
  if (value === null || value === undefined) {
    return null;
  }

  const raw = String(value).trim();
  if (!raw) {
    return null;
  }

  const normalized = raw.replace(/(\.\d{3})\d+/, '$1').replace(/([+-]\d{2})(\d{2})$/, '$1:$2');
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatTimestamp(date) {
  if (!date) {
    return 'Timestamp unavailable';
  }

  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  });
}

function formatRelative(date) {
  const diffMs = Date.now() - date.getTime();
  const future = diffMs < 0;
  const absMs = Math.abs(diffMs);

  if (absMs < 60 * 1000) {
    return future ? 'in moments' : 'just now';
  }

  const minutes = Math.round(absMs / 60000);
  if (minutes < 60) {
    return future ? `in ${minutes} min` : `${minutes} min ago`;
  }

  const hours = Math.round(absMs / 3600000);
  if (hours < 24) {
    return future ? `in ${hours} hr` : `${hours} hr ago`;
  }

  const days = Math.round(absMs / 86400000);
  return future ? `in ${days} day${days === 1 ? '' : 's'}` : `${days} day${days === 1 ? '' : 's'} ago`;
}

function formatDuration(ms) {
  const minutes = Math.round(ms / 60000);
  if (minutes < 60) {
    return `${Math.max(minutes, 1)} minute${minutes === 1 ? '' : 's'}`;
  }

  const hours = Math.round(ms / 3600000);
  if (hours < 24) {
    return `${hours} hour${hours === 1 ? '' : 's'}`;
  }

  const days = Math.round(ms / 86400000);
  return `${days} day${days === 1 ? '' : 's'}`;
}

function normalizeImpact(value) {
  const text = cleanText(value);
  if (text === 'High' || text === 'Medium' || text === 'Low') {
    return text;
  }
  return 'Unspecified';
}

function normalizeSentiment(value) {
  const text = cleanText(value);
  if (text === 'Positive' || text === 'Neutral' || text === 'Negative') {
    return text;
  }
  return 'Unspecified';
}

function normalizeUrl(value) {
  const raw = cleanText(value);
  if (!raw || raw === '#') {
    return '';
  }

  try {
    const url = new URL(raw, window.location.href);
    if (url.protocol === 'http:' || url.protocol === 'https:') {
      return url.href;
    }
  } catch (error) {
    return '';
  }

  return '';
}

function sanitizeSummary(value) {
  const raw = cleanText(value);
  if (!raw) {
    return '';
  }

  const template = document.createElement('template');
  template.innerHTML = raw;
  template.content
    .querySelectorAll('script, style, iframe, object, embed, link, meta')
    .forEach((node) => node.remove());

  return cleanText(template.content.textContent);
}

function cleanText(value) {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
}

function truncateText(text, maxLength) {
  const cleaned = cleanText(text);
  if (cleaned.length <= maxLength) {
    return cleaned;
  }

  return `${cleaned.slice(0, Math.max(0, maxLength - 3)).trimEnd()}...`;
}

function impactClass(impact) {
  switch (impact) {
    case 'High':
      return 'tag--impact-high';
    case 'Medium':
      return 'tag--impact-medium';
    case 'Low':
      return 'tag--impact-low';
    default:
      return 'tag--muted';
  }
}

function uniqueSorted(values, preferredOrder = []) {
  const unique = Array.from(new Set(values.filter(Boolean)));
  if (!preferredOrder.length) {
    return unique.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
  }

  const ranked = preferredOrder.filter((value) => unique.includes(value));
  const rest = unique.filter((value) => !preferredOrder.includes(value)).sort((a, b) =>
    a.localeCompare(b, undefined, { sensitivity: 'base' })
  );
  return [...ranked, ...rest];
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttr(value) {
  return escapeHtml(value);
}
