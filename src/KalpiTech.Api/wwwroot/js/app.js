const element = id => document.getElementById(id);
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

function closeStatistics() {
  statisticsOpen = false;
  statisticsSequence++;
  element('statistics-panel').hidden = true;
  element('admin-menu').hidden = false;
  statisticsReport = null;
  element('statistics-city').value = '';
  element('statistics-cities').replaceChildren();
  element('overall-statistics').replaceChildren();
  element('city-statistics').replaceChildren();
  element('city-statistics').hidden = true;
  element('statistics-status').textContent = '';
  element('statistics-city-message').textContent = '';
}

function renderParticipation(target, counts) {
  target.replaceChildren();
  const numbers = new Intl.NumberFormat('he-IL', { maximumFractionDigits: 2 });
  const metrics = document.createElement('dl');
  for (const [label, value] of [['מספר בוחרים', numbers.format(counts.total)],
    ['מספר מצביעים', numbers.format(counts.voted)],
    ['אחוז השתתפות', counts.percentage === null ? 'אין נתונים' : `${numbers.format(counts.percentage)}%`]]) {
    const term = document.createElement('dt');
    term.textContent = label;
    const amount = document.createElement('dd');
    amount.textContent = value;
    metrics.append(term, amount);
  }
  target.append(metrics);
  if (counts.percentage === null) return;
  const graph = document.createElement('div');
  graph.className = 'participation-bar';
  graph.setAttribute('role', 'img');
  graph.setAttribute('aria-label', `השתתפות: ${numbers.format(counts.percentage)} אחוזים`);
  const voted = document.createElement('div');
  voted.className = 'participation-voted';
  voted.style.width = `${counts.percentage}%`;
  graph.append(voted);
  const legend = document.createElement('p');
  legend.className = 'participation-legend';
  legend.textContent = `כחול: הצביעו (${numbers.format(counts.voted)}) | אפור: טרם הצביעו (${numbers.format(counts.total - counts.voted)})`;
  target.append(graph, legend);
}

function renderCityStatistics() {
  const cityName = element('statistics-city').value;
  const city = statisticsReport?.cities.find(item => item.city === cityName);
  element('city-statistics').hidden = !city;
  element('statistics-city-message').textContent = city ? `עיר: ${city.city}`
    : cityName ? 'יש לבחור עיר קיימת מתוך ההשלמה.' : 'בחר עיר להצגת נתוניה.';
  if (city) renderParticipation(element('city-statistics'), city.counts);
  else element('city-statistics').replaceChildren();
}

async function refreshStatistics() {
  if (!statisticsOpen || currentAccount?.role !== 'Admin' || statisticsRequest) return;
  const sequence = statisticsSequence;
  const request = requestApi('/api/statistics');
  statisticsRequest = request;
  try {
    const report = await request;
    if (!statisticsOpen || sequence !== statisticsSequence) return;
    statisticsReport = report;
    renderParticipation(element('overall-statistics'), report.overall);
    element('statistics-cities').replaceChildren(...report.cities.map(city => {
      const option = document.createElement('option');
      option.value = city.city;
      return option;
    }));
    renderCityStatistics();
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

function message(text, kind = 'info') {
  const notice = element('message');
  notice.dataset.kind = kind;
  notice.textContent = text;
  // Results must be visible even when the operator is at the bottom of the form.
  if (text) notice.scrollIntoView({ block: 'center', behavior: 'auto' });
  // Keep the required wording and make duplicate-vote errors explicit at the point of action.
  const duplicate = kind === 'error' && (text === 'הצבעה כפולה! הבוחר כבר מימש את זכות הבחירה'
    || text === 'שגיאה! הבוחר כבר הצביע ככל הנראה במקום אחר');
  const dialog = element('duplicate-vote-dialog');
  if (duplicate) {
    element('duplicate-vote-message').textContent = text;
    if (!dialog.open) dialog.showModal();
  } else if (dialog.open) dialog.close();
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
  electionActive = false;
  envelopesAllowed = false;
  closeEnvelopes();
  currentAccount = account;
  accountSequence++;
  clearVoter();
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
  closeStatistics();
  statisticsOpen = true;
  element('import-panel').hidden = true;
  element('admin-menu').hidden = true;
  element('statistics-panel').hidden = false;
  element('statistics-status').textContent = 'טוען נתוני השתתפות…';
  message('');
  element('statistics-title').focus();
  await refreshStatistics();
});
element('statistics-city').addEventListener('input', renderCityStatistics);
element('close-statistics').addEventListener('click', closeStatistics);
setInterval(refreshStatistics, 5000);

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
