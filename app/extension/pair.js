// Omissis — gira solo nella pagina del pannello (http://127.0.0.1:8766): permette al pannello di
// vedere che l'estensione c'e' e di consegnarle il codice di collegamento con un clic.
(() => {
  'use strict';
  if (location.port !== '8766' || window.top !== window) return;
  const respond = d => window.postMessage({msp_pii: 'extension', ...d}, location.origin);
  const present = () => chrome.runtime.sendMessage({t: 'present'}).then(respond, () => {});
  window.addEventListener('message', ev => {
    const d = ev.data;
    if (ev.source !== window || ev.origin !== location.origin || !d) return;
    if (d.msp_pii === 'ci sei?') present();
    if (d.msp_pii === 'connect' && typeof d.token === 'string') {
      chrome.runtime.sendMessage({t: 'connect', token: d.token, port: d.port})
        .then(r => respond({version: r.version, connected: true, ok: !!r.ok, reason: r.reason, just: true}), () => {});
    }
  });
  present();
})();
