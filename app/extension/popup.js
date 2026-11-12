// Omissis — finestrella dell'icona. Le frasi stanno in _locales/<lingua>/messages.json (la lingua è quella del browser).
const el = id => document.getElementById(id);
const T = (chiave, ...valori) => chrome.i18n.getMessage(chiave, valori.map(String)) || chiave;

document.documentElement.lang = chrome.i18n.getUILanguage();
for (const e of document.querySelectorAll('[data-t]')) e.textContent = T(e.dataset.t);
for (const e of document.querySelectorAll('[data-nome]')) { e.setAttribute('aria-label', T(e.dataset.nome)); e.placeholder = T(e.dataset.nome); }

async function mostra() {
  const d = await chrome.runtime.sendMessage({t: 'finestra'});
  const guasto = !d.collegata ? T('guasto_non_collegata')
    : !d.salute.ok ? T(d.salute.motivo === 'codice non valido' ? 'guasto_codice' : 'guasto_programma') : '';
  const stato = guasto ? 'non_attiva' : d.sospesa ? 'sospesa' : 'attiva';
  el('titolo').dataset.stato = stato;   // il codice dello stato, uguale in ogni lingua (lo leggono le prove)
  el('titoloTesto').textContent = T('stato_' + stato);
  el('guasto').hidden = !guasto;
  el('guasto').textContent = guasto;
  el('collegamento').hidden = d.collegata && d.salute.motivo !== 'codice non valido';
  el('servizio').textContent = d.servizio ? d.servizio.nome : d.host ? T('sito_fuori_catalogo') : '—';
  const pol = d.servizio ? (d.servizio.politica === 'proteggi' && !d.servizio.leggibile ? 'registra' : d.servizio.politica) : null;
  el('politica').textContent = !pol ? '—' : pol === 'proteggi' && d.sospesa ? T('politica_sospeso', T('politica_proteggi')) : T('politica_' + pol);
  const c = d.conteggi || {messaggi: 0, sostituzioni: 0, bloccate: 0};
  for (const k of ['messaggi', 'sostituzioni', 'bloccate']) el(k).textContent = c[k];
  el('avvisi').checked = d.avvisi;
  el('sospesa').checked = d.sospesa;
  el('versione').textContent = T('versione', d.versione);
}

el('avvisi').addEventListener('change', e => chrome.runtime.sendMessage({t: 'imposta', avvisi: e.target.checked}));
el('sospesa').addEventListener('change', async e => { await chrome.runtime.sendMessage({t: 'imposta', sospesa: e.target.checked}); mostra(); });
el('collega').addEventListener('click', async () => {
  const codice = el('codice').value.trim();
  if (!codice) return;
  await chrome.runtime.sendMessage({t: 'collega', token: codice});
  el('codice').value = '';
  mostra();
});
mostra();
