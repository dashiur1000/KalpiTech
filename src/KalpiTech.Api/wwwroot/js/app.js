const element = id => document.getElementById(id);
let csrfToken;

function message(text) { element('message').textContent = text; }

async function api(path, body) {
  let response;
  try {
    response = await fetch(`/api/auth/${path}`, {
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

function showAccount(account) {
  element('login').hidden = !!account;
  element('account').hidden = !account;
  element('admin-tools').hidden = account?.role !== 'Admin';
  document.querySelectorAll('form').forEach(form => form.reset());
  if (account) {
    element('account-title').textContent = { Admin: 'ועדת הבחירות המרכזית', Regular: 'קלפי רגילה', Accessible: 'קלפי נגישה' }[account.role];
    element('account-name').textContent = account.role === 'Admin' ? account.identifier : `מספר קלפי: ${account.kalpiId}`;
  }
}

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
