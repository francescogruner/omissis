// Omissis — finestrella dell'icona. Le frasi stanno in _locales/<lingua>/messages.json (la lingua è quella del browser).
const el = id => document.getElementById(id);
const T = (key, ...values) => chrome.i18n.getMessage(key, values.map(String)) || key;

document.documentElement.lang = chrome.i18n.getUILanguage();
for (const e of document.querySelectorAll('[data-t]')) e.textContent = T(e.dataset.t);
for (const e of document.querySelectorAll('[data-name]')) { e.setAttribute('aria-label', T(e.dataset.name)); e.placeholder = T(e.dataset.name); }

async function show() {
  const d = await chrome.runtime.sendMessage({t: 'win'});
  const fault = !d.connected ? T('fault_not_connected')
    : !d.health.ok ? T(d.health.reason === 'codice non valido' ? 'fault_code' : 'fault_program') : '';
  const status = fault ? 'not_active' : d.suspended ? 'suspended' : 'active';
  el('title').dataset.status = status;   // il codice dello stato, uguale in ogni lingua (lo leggono le prove)
  el('textTitle').textContent = T('status_' + status);
  el('fault').hidden = !fault;
  el('fault').textContent = fault;
  el('connection').hidden = d.connected && d.health.reason !== 'codice non valido';
  el('service').textContent = d.service ? d.service.name : d.host ? T('site_outside_catalog') : '—';
  const pol = d.service ? (d.service.policy === 'protect' && !d.service.readable ? 'record' : d.service.policy) : null;
  el('policy').textContent = !pol ? '—' : pol === 'protect' && d.suspended ? T('policy_suspended', T('policy_protect')) : T('policy_' + pol);
  const c = d.counts || {messages: 0, replacements: 0, blocked: 0};
  for (const k of ['messages', 'replacements', 'blocked']) el(k).textContent = c[k];
  el('notices').checked = d.notices;
  el('suspended').checked = d.suspended;
  el('version').textContent = T('version', d.version);
}

el('notices').addEventListener('change', e => chrome.runtime.sendMessage({t: 'configure', notices: e.target.checked}));
el('suspended').addEventListener('change', async e => { await chrome.runtime.sendMessage({t: 'configure', suspended: e.target.checked}); show(); });
el('connect').addEventListener('click', async () => {
  const code = el('code').value.trim();
  if (!code) return;
  await chrome.runtime.sendMessage({t: 'connect', token: code});
  el('code').value = '';
  show();
});
show();
