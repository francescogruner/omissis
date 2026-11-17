# Plugin di Omissis per le app e gli strumenti AI

[Omissis](https://omissis.eu) è un programma che gira sul tuo PC e tiene i dati personali fuori dai servizi AI. Questi plugin lo
collegano alle app e agli strumenti che hanno un sistema di plugin loro, così **ogni messaggio viene controllato prima
di partire**.

English: [README.md](README.md).

| App | Come entra il plugin | Installazione |
|---|---|---|
| **Kimi** (desktop, Kimi Code) | plugin con un hook `UserPromptSubmit` | `/plugins install https://github.com/francescogruner/omissis` |
| **Claude Code** | plugin da questo mercato | `claude plugin marketplace add francescogruner/omissis` e poi `claude plugin install omissis@omissis` |
| **Codex** | plugin da questo mercato | `codex plugin marketplace add francescogruner/omissis`, accendi Omissis tra i plugin, poi approva il suo controllo con `/hooks` |
| **Gemini CLI** | estensione con un hook `BeforeAgent` | `gemini extensions install https://github.com/francescogruner/omissis` |

## Prima di installare un plugin

1. Installa Omissis (https://omissis.eu) e avvialo.
2. Nel pannello di Omissis, **Collegamenti → App desktop → Plugin per le app e gli strumenti AI**, premi **Installa il
   comando**. Mette un piccolo comando, `omissis-hook`, in una cartella di Omissis e aggiunge quella cartella al tuo
   PATH (solo il tuo).
3. Chiudi e riapri l'app, così vede il comando. Poi installa il plugin con la riga della tabella.

I plugin non contengono codice di Omissis né codici segreti: ognuno dichiara soltanto «prima di mandare un messaggio,
esegui `omissis-hook <app>`». Senza Omissis sul PC quel comando non esiste, e il plugin non fa nulla.

## Che cosa succede a un messaggio

L'app passa il testo a `omissis-hook`, che chiede a Omissis **sul tuo stesso PC** che cosa fare. Non parte nulla verso
nessun altro. La risposta dipende dalla regola che hai scelto per quel servizio nel pannello:

| Regola del servizio | Che cosa succede |
|---|---|
| **Proteggi** | Se nel messaggio ci sono dati personali viene **fermato**, e la versione con i segnaposto finisce negli appunti: la incolli e la invii. Un messaggio senza nulla da sostituire parte com'è |
| **Blocca** | Ogni messaggio viene fermato |
| **Registra**, **Ignora** | Il messaggio parte |

## I limiti, detti chiaramente

- **Un plugin può fermare un messaggio, non riscriverlo.** Gli hook di queste app funzionano così. Quindi, quando c'è
  qualcosa da sostituire, serve un incolla in più.
- **Controlla ciò che scrivi.** I file che l'app legge da sola sul PC mentre lavora non passano da qui.
- **Nelle risposte restano i segnaposto.** Al modello viene detto di lasciarli come sono; i valori veri si rivedono
  solo dove c'è Omissis.
- **Se Omissis non è acceso**, un messaggio verso un servizio su Proteggi o Blocca viene fermato; verso gli altri parte.
- **Se uno strumento passa già dal gateway di Omissis** (Claude Code, Codex), il plugin non interviene: lì i dati
  vengono sostituiti davvero, ed è meglio. Non servono tutti e due.
- **Che cosa è stato provato.** Claude Code: dal vivo, con dati inventati (il messaggio è stato fermato, la versione
  con i segnaposto è partita e ha avuto risposta), e `claude plugin validate` accetta plugin e mercato. Kimi: il suo
  controllo dei plugin lo accetta, ma dentro l'app non è ancora stato provato. Codex: segue la documentazione e non è
  ancora stato provato dentro Codex, che esegue il controllo di un plugin solo dopo che lo approvi con `/hooks`: fino
  ad allora il plugin non protegge. Gemini CLI: segue la documentazione; da novembre 2026 Gemini CLI non accetta più
  gli account Google personali, quindi non è stato provato.
- **Antigravity** (app, CLI e IDE) non ha bisogno di un plugin: nel pannello di Omissis, sotto il comando, premi
  **Collega Antigravity**. Verificato dal vivo nell'app e nella CLI.

## Togliere

Disinstalla il plugin dalla pagina dei plugin dell'app. Per togliere il comando: pannello di Omissis, stesso punto,
**Togli il comando**.

## Licenza

Apache-2.0, come Omissis. Vedi [LICENSE](../LICENSE).
