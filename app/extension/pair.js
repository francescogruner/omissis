// Omissis — gira solo nella pagina del pannello (http://127.0.0.1:8766): permette al pannello di
// vedere che l'estensione c'e' e di consegnarle il codice di collegamento con un clic.
(() => {
  'use strict';
  if (location.port !== '8766' || window.top !== window) return;
  const rispondi = d => window.postMessage({msp_pii: 'estensione', ...d}, location.origin);
  const presente = () => chrome.runtime.sendMessage({t: 'presente'}).then(rispondi, () => {});
  window.addEventListener('message', ev => {
    const d = ev.data;
    if (ev.source !== window || ev.origin !== location.origin || !d) return;
    if (d.msp_pii === 'ci sei?') presente();
    if (d.msp_pii === 'collega' && typeof d.token === 'string') {
      chrome.runtime.sendMessage({t: 'collega', token: d.token, porta: d.porta})
        .then(r => rispondi({versione: r.versione, collegata: true, ok: !!r.ok, motivo: r.motivo, appena: true}), () => {});
    }
  });
  presente();
})();
