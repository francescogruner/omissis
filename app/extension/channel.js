// Omissis — apre il canale privato con page.js. Gira prima di qualunque script del sito, quindi
// nessuno puo' intercettare la porta; se page.js non conferma, riprova un paio di volte.
(() => {
  'use strict';
  const status = {port: null, ready: null};
  status.ready = new Promise(ok => {
    let attempts = 0;
    const test = () => {
      if (status.port || attempts++ >= 3) return;
      const c = new MessageChannel();
      c.port1.onmessage = ev => {
        if (status.port || !ev.data || !ev.data.hello) return;
        status.port = c.port1;
        ok(c.port1);
      };
      window.postMessage({__msp_pii: 'port'}, '*', [c.port2]);
      setTimeout(test, attempts === 1 ? 40 : 300);
    };
    test();
  });
  globalThis.mspChannel = status;
})();
