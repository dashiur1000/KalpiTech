const element = id => document.getElementById(id);

async function refreshReadiness() {
  const warning = element('readiness-warning');
  try {
    const response = await fetch('/health/ready', { cache: 'no-store' });
    const result = await response.json();
    warning.textContent = response.ok ? '' : result.message;
    warning.hidden = response.ok;
  } catch {
    warning.textContent = 'לא ניתן לבדוק את מוכנות המערכת. יש לבדוק את החיבור לשרת.';
    warning.hidden = false;
  }
}
refreshReadiness();
setInterval(refreshReadiness, 10000);
let csrfToken;
let searchSequence = 0;
let currentAccount = null;
let accountSequence = 0;
let selectedVoterId = null;
let electionActive = false;
let savingVote = false;
let savingImport = false;
let envelopesAllowed = false;
let selectedEnvelopeId = null;
let envelopeSequence = 0;
let searchingEnvelope = false;
let savingEnvelope = false;
let statisticsOpen = false;
let statisticsSequence = 0;
let statisticsRequest = null;
let statisticsReport = null;
let statisticsViewLogged = false;
let stationPage = 1;
const stationPageSize = 20;
let auditOpen = false;
let auditPage = 1;
let auditRequest = null;
let auditViewLogged = false;
let auditSequence = 0;

const heNumber = new Intl.NumberFormat('he-IL', { maximumFractionDigits: 2 });
const israelDateTime = new Intl.DateTimeFormat('he-IL', { timeZone: 'Asia/Jerusalem', dateStyle: 'short', timeStyle: 'short' });

function updateLiveClock() {
  const clockEl = element('live-clock-text');
  if (clockEl) clockEl.textContent = israelDateTime.format(new Date());
}
setInterval(updateLiveClock, 1000);
updateLiveClock();

function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}

function formatPercent(value) { return value === null ? 'אין נתונים' : `${heNumber.format(value)}%`; }
function formatDate(value) { return value ? israelDateTime.format(new Date(value)) : 'לא הוגדר'; }

function closeStatistics() {
  statisticsOpen = false;
  statisticsSequence++;
  element('statistics-panel').hidden = true;
  element('admin-menu').hidden = false;
  document.querySelector('main').classList.remove('dashboard-open');
  statisticsReport = null;
  statisticsViewLogged = false;
  stationPage = 1;
  element('statistics-city').value = '';
  element('station-search').value = '';
  for (const id of ['dashboard-election', 'dashboard-summary', 'hourly-chart', 'cities-table',
    'location-chart', 'stations-table', 'station-pagination']) element(id).replaceChildren();
  element('statistics-status').textContent = '';
}

function closeAudit() {
  auditOpen = false;
  auditSequence++;
  auditRequest = null;
  auditPage = 1;
  auditViewLogged = false;
  element('audit-panel').hidden = true;
  element('admin-menu').hidden = false;
  document.querySelector('main').classList.remove('dashboard-open');
  element('audit-table').replaceChildren();
  element('audit-pagination').replaceChildren();
  element('audit-status').textContent = '';
  element('audit-count').textContent = '';
}

const auditActions = { Login: 'התחברות', VoterSearch: 'חיפוש בוחר', VoteConfirmation: 'אישור הצבעה',
  DoubleEnvelope: 'מעטפה כפולה', DataImport: 'טעינת נתונים', ElectionSchedule: 'קביעת מועדים',
  StatisticsView: 'צפייה בנתונים', AuditView: 'צפייה ביומן', EmailSend: 'שליחת מייל' };
const auditResults = { Success: 'הצלחה', Blocked: 'נחסם', Failed: 'כשל', Skipped: 'דולג' };
const auditRoles = { Admin: 'מנהל הוועדה', Regular: 'קלפי רגילה', Accessible: 'קלפי נגישה' };
const auditTargets = { Voter: 'בוחר', Account: 'חשבון', Election: 'בחירות', Dataset: 'מאגר נתונים',
  Statistics: 'נתוני השתתפות', AuditLog: 'יומן פעולות' };

function auditQuery() {
  const query = new URLSearchParams({ page: String(auditPage), pageSize: '25' });
  query.set('recordView', auditViewLogged ? 'false' : 'true');
  const values = { action: element('audit-action').value, result: element('audit-result').value,
    actorIdentifier: element('audit-actor').value.trim() };
  Object.entries(values).forEach(([key, value]) => { if (value) query.set(key, value); });
  for (const [key, id] of [['from', 'audit-from'], ['to', 'audit-to']]) {
    const value = element(id).value;
    if (value) query.set(key, new Date(value).toISOString());
  }
  return query.toString();
}

async function refreshAudit() {
  if (!auditOpen || currentAccount?.role !== 'Admin' || auditRequest) return;
  const sequence = auditSequence;
  element('audit-status').textContent = 'טוען את יומן הפעולות…';
  const pending = requestApi(`/api/audit?${auditQuery()}`); auditRequest = pending;
  try {
    const report = await pending;
    if (!auditOpen || sequence !== auditSequence) return;
    auditViewLogged = true;
    element('audit-count').textContent = `${heNumber.format(report.totalCount)} רשומות בסך הכול`;
    const rows = report.items.map(item => [formatDate(item.occurredAtUtc),
      item.actorIdentifier ? `${auditRoles[item.actorRole] || item.actorRole || 'משתמש'} — ${item.actorIdentifier}` : 'לא מזוהה',
      auditActions[item.action] || item.action,
      item.targetType ? `${auditTargets[item.targetType] || item.targetType}${item.targetIdentifier ? ` — ${item.targetIdentifier}` : ''}` : '—',
      auditResults[item.result] || item.result, item.details || '—']);
    element('audit-table').replaceChildren(table(['תאריך ושעה', 'משתמש', 'פעולה', 'יעד', 'תוצאה', 'פרטים'], rows));
    const nav = element('audit-pagination'); nav.replaceChildren();
    if (report.totalPages > 1) {
      const previous = node('button', 'הקודם'); previous.type = 'button'; previous.disabled = report.page <= 1;
      previous.addEventListener('click', () => { auditPage--; refreshAudit(); });
      const label = node('span', `עמוד ${heNumber.format(report.page)} מתוך ${heNumber.format(report.totalPages)}`);
      const next = node('button', 'הבא'); next.type = 'button'; next.disabled = report.page >= report.totalPages;
      next.addEventListener('click', () => { auditPage++; refreshAudit(); });
      nav.append(previous, label, next);
    }
    element('audit-status').textContent = report.items.length ? '' : 'לא נמצאו רשומות המתאימות לסינון.';
  } catch (error) {
    if (!auditOpen || sequence !== auditSequence) return;
    element('audit-status').textContent = `טעינת היומן נכשלה: ${error.message}`;
    if (error.status === 401) { showAccount(null); await refreshToken().catch(() => {}); }
  } finally { if (auditRequest === pending) auditRequest = null; }
}

function renderElection(report) {
  const target = element('dashboard-election');
  target.replaceChildren();
  const states = { Preparation: ['טרם החלו', 'preparation'], Active: ['פעילות', 'active'], Finished: ['הסתיימו', 'finished'] };
  const [label, css] = states[report.election.state] || [report.election.state, 'finished'];
  const facts = node('div', undefined, 'election-facts');
  facts.append(node('span', `מצב: ${label}`, `state-${css}`),
    node('span', `התחלה: ${formatDate(report.election.startsAt)}`),
    node('span', `סיום: ${formatDate(report.election.endsAt)}`));
  if (report.election.state === 'Active' && report.election.endsAt) {
    const seconds = Math.max(0, Math.floor((new Date(report.election.endsAt) - new Date()) / 1000));
    const hours = Math.floor(seconds / 3600), minutes = Math.floor((seconds % 3600) / 60);
    facts.append(node('span', `נותרו: ${heNumber.format(hours)} שעות ו־${heNumber.format(minutes)} דקות`, 'state-active'));
  }
  target.append(facts);
}

function renderSummary(summary) {
  const values = [['👥', 'בעלי זכות בחירה', summary.total, 'blue'], ['✓', 'הצביעו', summary.voted, 'green'],
    ['%', 'אחוז הצבעה', formatPercent(summary.percentage), 'green'], ['…', 'טרם הצביעו', summary.notVoted, 'orange'],
    ['⌂', 'קלפיות עם פעילות', summary.activeStations, 'blue'], ['✉', 'מעטפות כפולות', summary.doubleEnvelopes, 'orange']];
  element('dashboard-summary').replaceChildren(...values.map(([icon, label, value, tone]) => {
    const card = node('article', undefined, 'summary-card'); card.dataset.tone = tone;
    card.append(node('span', icon, 'summary-icon'), node('span', label, 'summary-label'),
      node('strong', typeof value === 'number' ? heNumber.format(value) : value, 'summary-value'));
    return card;
  }));
}

function renderHourly() {
  const target = element('hourly-chart'); target.replaceChildren();
  const rows = statisticsReport?.hourly || [];
  if (!rows.length || !rows.some(row => row.votes)) { target.append(node('p', 'עדיין לא נרשמו הצבעות.', 'chart-empty')); return; }
  const mode = element('hourly-view').value, width = Math.max(620, rows.length * 58), height = 270;
  const pad = { x: 50, top: 18, bottom: 42 }, innerWidth = width - pad.x - 18, innerHeight = height - pad.top - pad.bottom;
  const series = mode === 'hourly' ? ['votes'] : mode === 'cumulative' ? ['cumulative'] : ['votes', 'cumulative'];
  const max = Math.max(1, ...rows.flatMap(row => series.map(key => row[key])));
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`); svg.setAttribute('class', 'line-chart');
  svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', 'גרף קצב הצבעה לפי שעה');
  for (let tick = 0; tick <= 4; tick++) {
    const y = pad.top + innerHeight * tick / 4;
    const line = document.createElementNS(svg.namespaceURI, 'line');
    line.setAttribute('x1', pad.x); line.setAttribute('x2', width - 18); line.setAttribute('y1', y); line.setAttribute('y2', y); line.setAttribute('class', 'chart-grid'); svg.append(line);
    const label = document.createElementNS(svg.namespaceURI, 'text'); label.setAttribute('x', pad.x - 8); label.setAttribute('y', y + 4); label.setAttribute('text-anchor', 'end'); label.setAttribute('class', 'chart-axis'); label.textContent = heNumber.format(Math.round(max * (4 - tick) / 4)); svg.append(label);
  }
  const xAt = index => pad.x + (rows.length === 1 ? innerWidth / 2 : innerWidth * index / (rows.length - 1));
  const yAt = value => pad.top + innerHeight * (1 - value / max);
  const timeFormat = new Intl.DateTimeFormat('he-IL', { timeZone: 'Asia/Jerusalem', hour: '2-digit', minute: '2-digit' });
  series.forEach(key => {
    const path = document.createElementNS(svg.namespaceURI, 'polyline');
    path.setAttribute('points', rows.map((row, i) => `${xAt(i)},${yAt(row[key])}`).join(' '));
    path.setAttribute('class', key === 'votes' ? 'chart-hourly' : 'chart-cumulative'); svg.append(path);
    rows.forEach((row, i) => {
      const circle = document.createElementNS(svg.namespaceURI, 'circle');
      circle.setAttribute('cx', xAt(i)); circle.setAttribute('cy', yAt(row[key])); circle.setAttribute('r', 5);
      circle.setAttribute('class', `chart-point ${key === 'votes' ? 'hourly' : 'cumulative'}`);
      const title = document.createElementNS(svg.namespaceURI, 'title');
      title.textContent = `${timeFormat.format(new Date(row.bucketStart))}: ${key === 'votes' ? 'בשעה' : 'מצטבר'} ${heNumber.format(row[key])}`;
      circle.append(title); svg.append(circle);
    });
  });
  rows.forEach((row, i) => {
    if (rows.length > 14 && i % Math.ceil(rows.length / 12) !== 0 && i !== rows.length - 1) return;
    const label = document.createElementNS(svg.namespaceURI, 'text'); label.setAttribute('x', xAt(i)); label.setAttribute('y', height - 12); label.setAttribute('text-anchor', 'middle'); label.setAttribute('class', 'chart-axis'); label.textContent = timeFormat.format(new Date(row.bucketStart)); svg.append(label);
  });
  const legend = node('p', undefined, 'chart-legend');
  if (series.includes('votes')) { const item = node('span', 'הצבעות בשעה'); item.style.setProperty('--legend', '#174e80'); legend.append(item); }
  if (series.includes('cumulative')) { const item = node('span', 'מצטבר'); item.style.setProperty('--legend', '#177245'); legend.append(item); }
  target.append(svg, legend);
}

function table(headers, rows) {
  if (!rows.length) return node('p', 'אין נתונים להצגה.', 'table-empty');
  const wrapper = node('div', undefined, 'data-table-wrap'), result = node('table', undefined, 'data-table');
  const head = node('thead'), tr = node('tr'); headers.forEach(text => tr.append(node('th', text))); head.append(tr);
  const body = node('tbody'); rows.forEach(cells => { const row = node('tr'); if (cells.inactive) row.className = 'inactive-row'; cells.forEach(value => row.append(node('td', value))); body.append(row); });
  result.append(head, body); wrapper.append(result); return wrapper;
}

function renderCities() {
  const query = element('statistics-city').value.trim();
  const sort = element('city-sort').value;
  const rows = [...(statisticsReport?.cities || [])].filter(row => row.city.includes(query));
  rows.sort((a, b) => sort === 'voted' ? b.counts.voted - a.counts.voted
    : sort === 'percentage' ? (b.counts.percentage ?? -1) - (a.counts.percentage ?? -1)
      : a.city.localeCompare(b.city, 'he'));
  element('cities-table').replaceChildren(table(['עיר', 'בעלי זכות', 'הצביעו', 'טרם הצביעו', 'אחוז'],
    rows.map(row => [row.city, heNumber.format(row.counts.total), heNumber.format(row.counts.voted),
      heNumber.format(row.counts.notVoted), formatPercent(row.counts.percentage)])));
}

function renderLocations() {
  const target = element('location-chart'), values = statisticsReport.votingLocations;
  target.replaceChildren();
  if (!values.total) { target.append(node('p', 'עדיין לא נרשמו הצבעות.', 'chart-empty')); return; }
  const parts = [['בקלפי המשויכת', values.assignedStation, '#174e80'], ['בקלפי אחרת', values.otherStation, '#d97706'], ['מעטפות כפולות', values.doubleEnvelopes, '#7c3aed']];
  let angle = 0; const stops = [];
  parts.forEach(([, value, color]) => { const next = angle + value / values.total * 360; stops.push(`${color} ${angle}deg ${next}deg`); angle = next; });
  const visual = node('div'); const donut = node('div', undefined, 'donut'); donut.style.background = `conic-gradient(${stops.join(',')})`;
  donut.setAttribute('role', 'img'); donut.setAttribute('aria-label', 'חלוקת מקום ההצבעה בפועל');
  visual.append(donut, node('p', `${heNumber.format(values.total)} הצבעות`, 'donut-total'));
  const list = node('ul', undefined, 'location-list');
  parts.forEach(([label, value, color]) => { const item = node('li'); const swatch = node('span', undefined, 'legend-color'); swatch.style.background = color; item.append(swatch, node('span', label), node('strong', `${heNumber.format(value)} · ${formatPercent(values.total ? value / values.total * 100 : 0)}`)); list.append(item); });
  target.append(visual, list);
}

function renderStations() {
  const query = element('station-search').value.trim(), sort = element('station-sort').value;
  const rows = [...(statisticsReport?.stations || [])].filter(row => String(row.kalpiId).includes(query) || row.city.includes(query));
  rows.sort((a, b) => sort === 'percentage' ? (b.assigned.percentage ?? -1) - (a.assigned.percentage ?? -1)
    : sort === 'lastVote' ? (new Date(b.lastVoteAt || 0) - new Date(a.lastVoteAt || 0)) : a.kalpiId - b.kalpiId);
  const pages = Math.max(1, Math.ceil(rows.length / stationPageSize)); stationPage = Math.min(stationPage, pages);
  const page = rows.slice((stationPage - 1) * stationPageSize, stationPage * stationPageSize);
  const mapped = page.map(row => { const values = [row.kalpiId, row.city, row.kalpiType === 'Accessible' ? 'נגישה' : 'רגילה',
    heNumber.format(row.assigned.total), heNumber.format(row.assigned.voted), formatPercent(row.assigned.percentage), heNumber.format(row.actualVotes),
    row.lastVoteAt ? formatDate(row.lastVoteAt) : 'אין פעילות']; values.inactive = !row.lastVoteAt; return values; });
  element('stations-table').replaceChildren(table(['קלפי', 'עיר', 'סוג', 'בעלי זכות', 'הצביעו', 'אחוז', 'נרשמו בפועל', 'פעילות אחרונה'], mapped));
  const nav = element('station-pagination'); nav.replaceChildren();
  if (pages > 1) for (let pageNumber = 1; pageNumber <= pages; pageNumber++) { const button = node('button', heNumber.format(pageNumber)); button.type = 'button'; button.disabled = pageNumber === stationPage; button.addEventListener('click', () => { stationPage = pageNumber; renderStations(); }); nav.append(button); }
}

function renderDashboard(report) {
  renderElection(report); renderSummary(report.summary); renderHourly(); renderCities(); renderLocations(); renderStations();
}

async function refreshStatistics() {
  if (!statisticsOpen || currentAccount?.role !== 'Admin' || statisticsRequest) return;
  const sequence = statisticsSequence;
  const request = requestApi(`/api/statistics?recordView=${statisticsViewLogged ? 'false' : 'true'}`);
  statisticsRequest = request;
  try {
    const report = await request;
    if (!statisticsOpen || sequence !== statisticsSequence) return;
    statisticsReport = report;
    statisticsViewLogged = true;
    renderDashboard(report);
    const localTime = new Intl.DateTimeFormat('he-IL', { timeZone: 'Asia/Jerusalem',
      hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(report.updatedAt));
    element('statistics-status').textContent = `עודכן ב־${localTime} (שעון ישראל). מתעדכן כל חמש שניות.`;
  } catch (error) {
    if (!statisticsOpen || sequence !== statisticsSequence) return;
    element('statistics-status').textContent = `העדכון נכשל: ${error.message}. ${statisticsReport ? 'מוצגים הנתונים האחרונים שהתקבלו.' : 'טרם התקבלו נתונים.'}`;
    if (error.status === 401) { showAccount(null); await refreshToken().catch(() => {}); }
  } finally { if (statisticsRequest === request) statisticsRequest = null; }
}

function updateEnvelopeButtons() {
  element('open-envelopes').disabled = !envelopesAllowed || savingImport;
  element('search-envelope').disabled = !envelopesAllowed || searchingEnvelope || savingEnvelope;
  element('confirm-envelope').disabled = !envelopesAllowed || !selectedEnvelopeId || savingEnvelope;
  element('envelope-availability').textContent = savingEnvelope ? 'שומר הצבעה…'
    : envelopesAllowed ? 'חלון הזנת מעטפות כפולות פתוח.'
      : 'הזנת מעטפות כפולות אפשרית רק בתוך 36 שעות ממועד תחילת הבחירות.';
}

function closeEnvelopes() {
  selectedEnvelopeId = null;
  envelopeSequence++;
  element('envelope-panel').hidden = true;
  element('admin-menu').hidden = false;
  element('envelope-search-form').hidden = false;
  element('envelope-confirm-form').hidden = true;
  element('envelope-search-form').reset();
  element('envelope-confirm-form').reset();
  element('envelope-voter-name').textContent = '';
  element('envelope-voter-details').textContent = '';
  updateEnvelopeButtons();
}

function updateVoteButton() {
  element('confirm-voter').disabled = savingVote || !selectedVoterId || !electionActive;
  element('vote-availability').textContent = savingVote ? 'שומר הצבעה…'
    : electionActive ? '' : 'אישור הצבעה אפשרי בזמן פעילות הבחירות בלבד.';
}

let fireworksActive = false;
let fireworksAnimId = null;

function launchCelebration(messageText) {
  const overlay = element('celebration-overlay');
  const canvas = element('fireworks-canvas');
  if (!overlay || !canvas) return;

  if (messageText) element('celebration-message').textContent = messageText;
  overlay.hidden = false;
  fireworksActive = true;

  const ctx = canvas.getContext('2d');
  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();

  const particles = [];
  const colors = ['#00e5ff', '#38bdf8', '#8b5cf6', '#c084fc', '#10b981', '#fbbf24', '#f43f5e', '#ffffff'];

  function createBurst(x, y) {
    const count = 80 + Math.floor(Math.random() * 40);
    const baseColor = colors[Math.floor(Math.random() * colors.length)];
    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = Math.random() * 7 + 2;
      particles.push({
        x: x, y: y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        alpha: 1,
        color: Math.random() > 0.35 ? baseColor : colors[Math.floor(Math.random() * colors.length)],
        radius: Math.random() * 2.8 + 1.2,
        decay: Math.random() * 0.018 + 0.012
      });
    }
  }

  let lastBurst = 0;
  function animate(timestamp) {
    if (!fireworksActive) return;
    if (timestamp - lastBurst > 320) {
      lastBurst = timestamp;
      createBurst(
        canvas.width * (0.2 + Math.random() * 0.6),
        canvas.height * (0.18 + Math.random() * 0.42)
      );
    }

    ctx.globalCompositeOperation = 'destination-out';
    ctx.fillStyle = 'rgba(0, 0, 0, 0.18)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.globalCompositeOperation = 'lighter';

    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.07;
      p.vx *= 0.985;
      p.vy *= 0.985;
      p.alpha -= p.decay;

      if (p.alpha <= 0) {
        particles.splice(i, 1);
        continue;
      }

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = p.color;
      ctx.globalAlpha = p.alpha;
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    fireworksAnimId = requestAnimationFrame(animate);
  }

  createBurst(canvas.width * 0.5, canvas.height * 0.3);
  createBurst(canvas.width * 0.35, canvas.height * 0.25);
  createBurst(canvas.width * 0.65, canvas.height * 0.28);
  fireworksAnimId = requestAnimationFrame(animate);

  setTimeout(() => { if (fireworksActive) closeCelebration(); }, 7000);
}

function closeCelebration() {
  fireworksActive = false;
  if (fireworksAnimId) cancelAnimationFrame(fireworksAnimId);
  const overlay = element('celebration-overlay');
  if (overlay) overlay.hidden = true;
}

const closeCelBtn = element('close-celebration');
if (closeCelBtn) closeCelBtn.addEventListener('click', closeCelebration);

function showLargeError(text) {
  const modal = element('large-error-modal');
  const msg = element('large-error-text');
  if (modal && msg && text) {
    msg.textContent = text;
    if (!modal.open) modal.showModal();
  }
}

function message(text, kind = 'info') {
  const notice = element('message');
  if (notice) {
    notice.dataset.kind = kind;
    notice.textContent = text;
  }
  const accountNotice = element('account-message');
  if (accountNotice) {
    accountNotice.dataset.kind = kind;
    accountNotice.textContent = text;
  }
  if (kind === 'error' && text) {
    const duplicate = (text === 'הצבעה כפולה! הבוחר כבר מימש את זכות הבחירה'
      || text === 'שגיאה! הבוחר כבר הצביע ככל הנראה במקום אחר');
    if (duplicate) {
      const dialog = element('duplicate-vote-dialog');
      if (dialog) {
        element('duplicate-vote-message').textContent = text;
        if (!dialog.open) dialog.showModal();
      }
    } else {
      showLargeError(text);
    }
  } else if (!text) {
    const errorModal = element('large-error-modal');
    if (errorModal && errorModal.open) errorModal.close();
    const dupModal = element('duplicate-vote-dialog');
    if (dupModal && dupModal.open) dupModal.close();
  }
}

async function api(path, body) {
  return requestApi(`/api/auth/${path}`, body);
}

async function requestApi(url, body) {
  let response;
  try {
    response = await fetch(url, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': csrfToken },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
  } catch { throw new Error('השרת אינו זמין'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.message || 'הבקשה אינה תקינה. יש לרענן את העמוד ולנסות שוב.');
    error.status = response.status;
    throw error;
  }
  return data;
}

async function refreshToken() { csrfToken = (await api('csrf')).token; }

function clearVoter() {
  selectedVoterId = null;
  updateVoteButton();
  searchSequence++;
  element('voter-confirmation').hidden = true;
  element('voter-search').hidden = false;
  element('voter-name').textContent = '';
  element('voter-details').textContent = '';
}

function showAccount(account) {
  closeStatistics();
  closeAudit();
  electionActive = false;
  envelopesAllowed = false;
  closeEnvelopes();
  currentAccount = account;
  accountSequence++;
  clearVoter();
  document.body.classList.toggle('is-authenticated', !!account);
  element('login').hidden = !!account;
  element('account').hidden = !account;
  element('admin-tools').hidden = account?.role !== 'Admin';
  element('poll-tools').hidden = !['Regular', 'Accessible'].includes(account?.role);
  document.querySelectorAll('form').forEach(form => form.reset());
  element('import-panel').hidden = true;
  if (account) {
    element('account-title').textContent = { Admin: 'ועדת הבחירות המרכזית', Regular: 'קלפי רגילה', Accessible: 'קלפי נגישה' }[account.role];
    element('account-name').textContent = account.role === 'Admin' ? account.identifier : `מספר קלפי: ${account.kalpiId}`;
    refreshElection(true).catch(handleElectionError);
    if (account.role === 'Admin') {
      setTimeout(() => { if (!statisticsOpen && !auditOpen) element('open-statistics').click(); }, 60);
    }
  }
}

function handleElectionError(error) {
  electionActive = false;
  envelopesAllowed = false;
  updateEnvelopeButtons();
  updateVoteButton();
  element('election-status').textContent = error.message;
  element('election-times').textContent = '';
  element('election-window').textContent = '';
  element('save-election').disabled = true;
  if (error.status === 401) { showAccount(null); refreshToken().catch(() => {}); }
}

function displayTime(value) { return value ? value.replace('T', ' ') : 'טרם נקבע'; }

async function refreshElection(fillForm = false) {
  const sequence = accountSequence;
  const election = await requestApi('/api/election');
  if (sequence !== accountSequence || !currentAccount) return;
  electionActive = election.state === 'Active';
  envelopesAllowed = election.doubleEnvelopesAllowed;
  updateEnvelopeButtons();
  updateVoteButton();
  element('election-status').textContent = `מצב: ${{ Preparation: 'הכנה', Active: 'פעילות', Finished: 'סיום' }[election.state]}`;
  element('election-times').textContent = `שעון ישראל — התחלה: ${displayTime(election.startsAtIsrael)} | סיום: ${displayTime(election.endsAtIsrael)}`;
  element('election-window').textContent = election.loadLocked
    ? `טעינת נתונים נעולה; חלון מעטפות כפולות פתוח עד ${displayTime(election.loadLockedUntilIsrael)} (שעון ישראל).`
    : 'חלון מעטפות כפולות סגור. החלפת נתונים כפופה גם לכך שאין הצבעות במאגר.';
  element('save-election').disabled = !election.canEdit;
  element('election-start').disabled = !election.canEdit;
  element('election-end').disabled = !election.canEdit;
  if (fillForm) {
    element('election-start').value = election.startsAtIsrael || '';
    element('election-end').value = election.endsAtIsrael || '';
  }
}

handleForm('election-form', async () => {
  if (!window.confirm('לשמור את מועדי הבחירות לפי שעון ישראל? המערכת תעבור אוטומטית לפעילות במועד ההתחלה ולסיום במועד הסיום.')) return;
  const result = await requestApi('/api/election/schedule', {
    startsAt: element('election-start').value, endsAt: element('election-end').value
  });
  message(result.message, 'success');
  await refreshElection(true);
});

element('open-statistics').addEventListener('click', async () => {
  if (savingImport || currentAccount?.role !== 'Admin') return;
  closeEnvelopes();
  closeAudit();
  closeStatistics();
  statisticsOpen = true;
  element('import-panel').hidden = true;
  element('admin-menu').hidden = true;
  element('statistics-panel').hidden = false;
  document.querySelector('main').classList.add('dashboard-open');
  element('statistics-status').textContent = 'טוען נתוני השתתפות…';
  message('');
  element('statistics-title').focus();
  await refreshStatistics();
});
element('statistics-city').addEventListener('input', renderCities);
element('city-sort').addEventListener('change', renderCities);
element('hourly-view').addEventListener('change', renderHourly);
element('station-search').addEventListener('input', () => { stationPage = 1; renderStations(); });
element('station-sort').addEventListener('change', () => { stationPage = 1; renderStations(); });
element('close-statistics').addEventListener('click', closeStatistics);
setInterval(refreshStatistics, 5000);

element('open-audit').addEventListener('click', async () => {
  if (savingImport || currentAccount?.role !== 'Admin') return;
  closeEnvelopes(); closeStatistics(); closeAudit();
  auditOpen = true;
  element('admin-menu').hidden = true;
  element('audit-panel').hidden = false;
  document.querySelector('main').classList.add('dashboard-open');
  message(''); element('audit-title').focus();
  await refreshAudit();
});
element('close-audit').addEventListener('click', closeAudit);
element('audit-filter-form').addEventListener('submit', event => { event.preventDefault(); auditPage = 1; refreshAudit(); });
element('clear-audit-filters').addEventListener('click', () => {
  element('audit-filter-form').reset(); auditPage = 1; refreshAudit();
});

// The display refreshes; authorization and time decisions remain on the server.
setInterval(() => { if (currentAccount) refreshElection().catch(handleElectionError); }, 5000);

function handleForm(id, action) {
  element(id).addEventListener('submit', async event => {
    event.preventDefault();
    const button = event.target.querySelector('button');
    button.disabled = true;
    message('');
    try { await action(); }
    catch (error) {
      message(error.message, 'error');
      if (error.status === 401) { showAccount(null); await refreshToken().catch(() => {}); }
    } finally { button.disabled = false; }
  });
}

handleForm('login-form', async () => {
  const account = await api('login', { identifier: element('identifier').value.trim(), password: element('password').value });
  showAccount(account);
  // CSRF tokens are bound to the current identity, so refresh after sign-in/out.
  await refreshToken();
  message('ההתחברות בוצעה בהצלחה.');
});

handleForm('voter-form', async () => {
  clearVoter();
  const requestSequence = searchSequence;
  const voter = await requestApi('/api/voters/search', { id: element('voter-id').value });
  // Ignore a late result if the user has signed out or changed screens meanwhile.
  if (requestSequence !== searchSequence) return;
  selectedVoterId = voter.id;
  updateVoteButton();
  element('voter-name').textContent = `${voter.firstName} ${voter.lastName}`;
  element('voter-details').textContent = `ת״ז: ${voter.id} | קלפי משויכת: ${voter.kalpiId}`;
  element('voter-search').hidden = true;
  element('voter-confirmation').hidden = false;
  element('confirmation-title').focus();
});

element('cancel-voter').addEventListener('click', () => {
  clearVoter();
  element('voter-form').reset();
  message('');
  element('voter-id').focus();
});

element('confirm-voter').addEventListener('click', async () => {
  if (savingVote || !selectedVoterId || !electionActive) return;
  savingVote = true;
  updateVoteButton();
  element('cancel-voter').disabled = true;
  element('logout').disabled = true;
  message('');
  try {
    // Only the selected Id is submitted. The server supplies time and actual station.
    const result = await requestApi('/api/voters/confirm', { id: selectedVoterId });
    message(result.message, 'success');
    launchCelebration(result.message);
  } catch (error) {
    message(error.message, 'error');
    if (error.status === 401) { showAccount(null); await refreshToken().catch(() => {}); }
    // No automatic retry: if the response was lost, search again to check the stored state.
  } finally {
    savingVote = false;
    element('cancel-voter').disabled = false;
    element('logout').disabled = false;
    clearVoter();
    element('voter-form').reset();
    if (currentAccount) element('voter-id').focus();
  }
});

element('logout').addEventListener('click', async () => {
  if (!window.confirm('האם לצאת מהמערכת?')) return;
  try {
    const result = await api('logout', {});
    showAccount(null);
    await refreshToken();
    message(result.message, 'success');
  } catch (error) {
    if (error.status === 401) { showAccount(null); await refreshToken().catch(() => {}); }
    message(error.message, 'error');
  }
});

document.querySelectorAll('.btn-logout-action').forEach(btn => {
  btn.addEventListener('click', () => element('logout').click());
});

async function start() {
  try {
    let account = null;
    try { account = await api('me'); } catch (error) { if (error.status !== 401) throw error; }
    showAccount(account);
    await refreshToken();
  } catch (error) { showAccount(null); message(error.message, 'error'); }
}
start();

element('open-import').addEventListener('click', async () => {
  try {
    const state = await requestApi('/api/data');
    if (!state.canImport) { message(state.message); return; }
    if (state.hasData && !window.confirm('הטעינה תחליף את כל הקלפיות והבוחרים הקיימים. האם להמשיך?')) return;
    element('import-form').reset();
    element('import-panel').hidden = false;
    message('');
  } catch (error) { message(error.message, 'error'); }
});

element('cancel-import').addEventListener('click', () => {
  if (savingImport) return;
  element('import-form').reset();
  element('import-panel').hidden = true;
  message('');
});

handleForm('import-form', async () => {
  if (savingImport) return;
  savingImport = true;
  element('open-statistics').disabled = true;
  element('open-audit').disabled = true;
  updateEnvelopeButtons();
  for (const id of ['logout', 'open-import', 'cancel-import']) element(id).disabled = true;
  try {
    const body = new FormData();
    body.append('kalpiFile', element('kalpi-file').files[0]);
    body.append('peopleFile', element('people-file').files[0]);
    body.append('confirmed', 'true');
    message('בודק וטוען את הנתונים…');
    const response = await fetch('/api/data/import', { method: 'POST', credentials: 'same-origin',
      headers: { 'X-CSRF-TOKEN': csrfToken }, body });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(result.message || 'הטעינה לא קיבלה אישור הצלחה. יש לבדוק את המאגר לפני ניסיון נוסף.');
      error.status = response.status;
      throw error;
    }
    message(`${result.message} (${result.kalpiCount} קלפיות, ${result.peopleCount} בוחרים).`);
    element('import-form').reset();
    setTimeout(() => { element('import-panel').hidden = true; }, 3000);
  } catch (error) {
    if (error instanceof TypeError) throw new Error('הטעינה לא קיבלה אישור הצלחה. יש לבדוק את המאגר לפני ניסיון נוסף.');
    throw error;
  } finally {
    savingImport = false;
    element('open-statistics').disabled = false;
    element('open-audit').disabled = false;
    updateEnvelopeButtons();
    for (const id of ['logout', 'open-import', 'cancel-import']) element(id).disabled = false;
  }
});

element('open-envelopes').addEventListener('click', async () => {
  try {
    await refreshElection();
    if (!currentAccount || currentAccount.role !== 'Admin') return;
    if (!envelopesAllowed) { message('הזנת מעטפות כפולות אפשרית רק בתוך 36 שעות ממועד תחילת הבחירות.'); return; }
    closeEnvelopes();
    element('import-panel').hidden = true;
    element('admin-menu').hidden = true;
    element('envelope-panel').hidden = false;
    message('');
    element('envelope-id').focus();
  } catch (error) { handleElectionError(error); message(error.message, 'error'); }
});

element('envelope-search-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (searchingEnvelope || !envelopesAllowed) return;
  searchingEnvelope = true;
  const sequence = ++envelopeSequence;
  updateEnvelopeButtons();
  message('');
  try {
    const voter = await requestApi('/api/envelopes/search', { id: element('envelope-id').value });
    if (sequence !== envelopeSequence || currentAccount?.role !== 'Admin') return;
    selectedEnvelopeId = voter.id;
    element('envelope-voter-name').textContent = `${voter.firstName} ${voter.lastName}`;
    element('envelope-voter-details').textContent = `ת״ז: ${voter.id} | קלפי משויכת: ${voter.kalpiId}`;
    element('envelope-search-form').hidden = true;
    element('envelope-confirm-form').hidden = false;
    element('envelope-confirm-title').focus();
  } catch (error) {
    if (sequence !== envelopeSequence) return;
    message(error.message, 'error');
    if (error.status === 401) { showAccount(null); await refreshToken().catch(() => {}); }
  } finally { searchingEnvelope = false; updateEnvelopeButtons(); }
});

element('cancel-envelope').addEventListener('click', () => {
  if (savingEnvelope) return;
  closeEnvelopes();
  message('');
});

element('envelope-confirm-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (savingEnvelope || !selectedEnvelopeId || !envelopesAllowed) return;
  savingEnvelope = true;
  updateEnvelopeButtons();
  element('cancel-envelope').disabled = true;
  element('logout').disabled = true;
  message('');
  try {
    // The server supplies both the committee location (0) and VotedAt.
    const result = await requestApi('/api/envelopes/confirm', { id: selectedEnvelopeId });
    message(result.message, 'success');
    launchCelebration(result.message);
  } catch (error) {
    message(error.message, 'error');
    if (error.status === 401) { showAccount(null); await refreshToken().catch(() => {}); }
    // No automatic retry: search again if the response was lost.
  } finally {
    savingEnvelope = false;
    element('cancel-envelope').disabled = false;
    element('logout').disabled = false;
    closeEnvelopes();
  }
});
