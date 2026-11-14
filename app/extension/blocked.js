// Omissis — pagina mostrata al posto di un servizio bloccato
const q = new URLSearchParams(location.search);
const T = (key, ...values) => chrome.i18n.getMessage(key, values.map(String)) || key;
document.documentElement.lang = chrome.i18n.getUILanguage();
document.title = T('blocked_card') + ' · Omissis';
document.getElementById('sign').textContent = T('blocked_card');
document.getElementById('title').textContent = T('blocked_title', q.get('s') || T('blocked_this_one'));
document.getElementById('text').textContent = T('blocked_text');
document.getElementById('ask').textContent = T('blocked_ask');
if (q.get('h')) chrome.runtime.sendMessage({t: 'blocked', host: q.get('h')}).catch(() => {});
