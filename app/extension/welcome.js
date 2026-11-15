// Omissis — la pagina che si apre una volta, appena installata l'estensione: dice che cosa manca perché funzioni
// (il collegamento al programma sul PC) e lo fa fare con un clic. Le frasi stanno in _locales/<lingua>/messages.json.
const el = id => document.getElementById(id);
const T = (key, ...values) => chrome.i18n.getMessage(key, values.map(String)) || key;

document.documentElement.lang = chrome.i18n.getUILanguage();
for (const e of document.querySelectorAll('[data-t]')) e.textContent = T(e.dataset.t);
document.title = 'Omissis · ' + T('welcome_title');
// il pannello del programma, aperto così, consegna da solo il codice di collegamento a questo browser
el('connect').href = 'http://127.0.0.1:8766/#/connect';

async function show() {
  let d = null;
  try { d = await chrome.runtime.sendMessage({t: 'present'}); } catch (e) { /* estensione ricaricata: al prossimo giro */ }
  const ok = !!(d && d.connected && d.ok);
  el('state').dataset.status = ok ? 'connected' : 'to_connect';   // il codice dello stato, uguale in ogni lingua (lo leggono le prove)
  el('stateText').textContent = T(ok ? 'welcome_connected' : 'welcome_to_connect');
  el('steps').hidden = ok;
  el('done').hidden = !ok;
}
show();
setInterval(show, 2000);
