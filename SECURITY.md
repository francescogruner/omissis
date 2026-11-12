# Sicurezza

## Segnalare un problema

Per una vulnerabilità o per un caso in cui un dato esce in chiaro, usare la segnalazione privata di
GitHub: scheda **Security** del repository → **Report a vulnerability**. Non aprire una segnalazione
pubblica finché il problema non è corretto. Nella segnalazione non incollare dati personali veri:
bastano il servizio, il tipo di dato e la riga del registro (che contiene solo conteggi e struttura).

For English speakers: please use GitHub's private vulnerability reporting (Security tab → Report a
vulnerability) and never paste real personal data in a report.

## Da cosa difende

Omissis riduce i dati personali che arrivano a un servizio AI **onesto ma curioso**: un fornitore che
elabora, conserva o usa per l'addestramento quello che riceve. Il servizio riceve segnaposto al posto
dei valori; la corrispondenza resta sul computer di chi scrive.

## Da cosa non difende

- **Un sito o un'app che agisce contro l'utente.** Quando la risposta viene ripristinata dentro la
  pagina del servizio, gli script di quella pagina possono leggere i valori veri. Chi ha questo
  timore spegne il ripristino e ripristina il testo copiato con la scorciatoia sugli appunti.
- **Altri programmi sullo stesso computer.** Il motore ascolta su `127.0.0.1` e si protegge con un
  codice salvato in un file: un programma che gira con lo stesso utente può leggerlo. L'archivio
  dei segnaposto è cifrato con la protezione dei dati di Windows legata all'utente: resiste alla
  copia del file, non a un programma che gira nello stesso profilo e chiede a Windows di aprirlo.
- **Gli errori del modello.** Un dato non riconosciuto esce in chiaro. Il registro segnala i casi in
  cui un valore già mascherato ricompare in chiaro in un'altra richiesta, ma non può segnalare ciò
  che non ha mai riconosciuto.
- **I canali non coperti**: WebSocket, immagini senza testo leggibile, processi secondari delle pagine, file caricati
  da chi passa dal solo proxy o dal gateway.

## Scelte di progetto

- Se il motore non risponde, la richiesta viene bloccata.
- Il registro contiene solo conteggi e nomi dei campi, mai i testi.
- Il proxy decifra solo il traffico dei servizi che l'utente ha scelto di proteggere.
- Il pannello risponde solo a `127.0.0.1` e solo con il codice generato a ogni avvio.
- Il programma contatta la rete da solo in due casi soltanto, ed entrambi sono semplici letture di
  file pubblici, senza dati né identificativi: lo scaricamento del modello al primo avvio e il
  controllo quotidiano degli aggiornamenti (che si può spegnere).
- Il modello scaricato viene accettato solo se ha l'impronta SHA-256 scritta nel programma. Un
  aggiornamento viene accettato solo se il suo foglio è firmato (Ed25519) con la chiave dell'autore
  e l'installer ha l'impronta scritta nel foglio; una versione più vecchia non viene mai accettata.
  Chi controllasse la pagina delle versioni o la rete, senza la chiave privata, non potrebbe far
  installare nulla. La chiave privata non sta in nessun repository.
- Installare il certificato del proxy è una scelta dell'utente e vale per il solo utente corrente:
  finché è installato, chi possiede la chiave privata nella cartella `dati\ca` può leggere il suo
  traffico HTTPS. Quella cartella non va mai copiata né condivisa.
