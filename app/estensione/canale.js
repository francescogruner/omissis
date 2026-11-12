// Omissis — apre il canale privato con pagina.js. Gira prima di qualunque script del sito, quindi
// nessuno puo' intercettare la porta; se pagina.js non conferma, riprova un paio di volte.
(() => {
  'use strict';
  const stato = {porta: null, pronta: null};
  stato.pronta = new Promise(ok => {
    let tentativi = 0;
    const prova = () => {
      if (stato.porta || tentativi++ >= 3) return;
      const c = new MessageChannel();
      c.port1.onmessage = ev => {
        if (stato.porta || !ev.data || !ev.data.eccomi) return;
        stato.porta = c.port1;
        ok(c.port1);
      };
      window.postMessage({__msp_pii: 'porta'}, '*', [c.port2]);
      setTimeout(prova, tentativi === 1 ? 40 : 300);
    };
    prova();
  });
  globalThis.mspCanale = stato;
})();
