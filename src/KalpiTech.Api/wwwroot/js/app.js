const element = id => document.getElementById(id);
let csrfToken;
let searchSequence = 0;
let currentAccount = null;
let accountSequence = 0;

function message(text) { element('message').textContent = text; }

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
  searchSequence++;
  element('voter-confirmation').hidden = true;
  element('voter-search').hidden = false;
  element('voter-name').textContent = '';
  element('voter-details').textContent = '';
}

function showAccount(account) {
  currentAccount = account;
  accountSequence++;
  clearVoter();
  element('login').hidden = !!account;
  element('account').hidden = !account;
  element('admin-tools').hidden = account?.role !== 'Admin';
  element('poll-tools').hidden = !['Regular', 'Accessible'].includes(account?.role);
  document.querySelectorAll('form').forEach(form => form.reset());
  if (account) {
    element('account-title').textContent = { Admin: 'ועדת הבחירות המרכזית', Regular: 'קלפי רגילה', Accessible: 'קלפי נגישה' }[account.role];
    element('account-name').textContent = account.role === 'Admin' ? account.identifier : `מספר קלפי: ${account.kalpiId}`;
    refreshElection(true).catch(handleElectionError);
  }
}

function handleElectionError(error) {
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
  message(result.message);
  await refreshElection(true);
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
      message(error.message);
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

handleForm('kalpi-form', async () => {
  const result = await api('kalpi-password', { kalpiId: Number(element('kalpi-id').value), newPassword: element('kalpi-password').value });
  element('kalpi-form').reset();
  message(result.message);
});

handleForm('admin-form', async () => {
  const result = await api('admin-password', { currentPassword: element('current-password').value, newPassword: element('new-password').value });
  showAccount(null);
  await refreshToken();
  message(result.message);
});

handleForm('voter-form', async () => {
  clearVoter();
  const requestSequence = searchSequence;
  const voter = await requestApi('/api/voters/search', { id: element('voter-id').value });
  // Ignore a late result if the user has signed out or changed screens meanwhile.
  if (requestSequence !== searchSequence) return;
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

element('logout').addEventListener('click', async () => {
  if (!window.confirm('האם לצאת מהמערכת?')) return;
  try {
    const result = await api('logout', {});
    showAccount(null);
    await refreshToken();
    message(result.message);
  } catch (error) {
    if (error.status === 401) { showAccount(null); await refreshToken().catch(() => {}); }
    message(error.message);
  }
});

async function start() {
  try {
    let account = null;
    try { account = await api('me'); } catch (error) { if (error.status !== 401) throw error; }
    showAccount(account);
    await refreshToken();
  } catch (error) { showAccount(null); message(error.message); }
}
start();
