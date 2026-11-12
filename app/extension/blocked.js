// Omissis — pagina mostrata al posto di un servizio bloccato
const q = new URLSearchParams(location.search);
const T = (chiave, ...valori) => chrome.i18n.getMessage(chiave, valori.map(String)) || chiave;
document.documentElement.lang = chrome.i18n.getUILanguage();
document.title = T('bloccato_scheda') + ' · Omissis';
document.getElementById('segno').textContent = T('bloccato_scheda');
document.getElementById('titolo').textContent = T('bloccato_titolo', q.get('s') || T('bloccato_questo'));
document.getElementById('testo').textContent = T('bloccato_testo');
document.getElementById('chiedi').textContent = T('bloccato_chiedi');
if (q.get('h')) chrome.runtime.sendMessage({t: 'bloccato', host: q.get('h')}).catch(() => {});
