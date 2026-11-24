# -*- coding: utf-8 -*-
"""La versione del programma: la leggono il pannello, il controllo degli aggiornamenti e chi costruisce l'installer."""
# 0.1.9: l'app desktop di Claude si protegge dalla casella di scrittura, in chat e nella scheda Code (il proxy porta
# nella sua pagina il codice dell'estensione: inpage.py); il pannello avvisa quando un'app cambia e prepara la
# segnalazione (report.py). Lo stesso numero per Windows, Mac e Linux.
# 0.1.10: «da ricontrollare» su un'app compare solo per un messaggio non letto: le chiamate di servizio senza nulla di
# scritto restano fuori dal registro, e conta la versione dell'app in uso (activity.written, panel.proxy_state).
# 0.1.11: se la porta del proxy è occupata da un altro programma, Omissis ne prende da solo una libera, la salva e lo
# dice; quando un processo si chiude, il pannello dice quale e con che codice (panel.free_port, Supervisor._proxy_port,
# closed_for).
VERSION = "0.1.11"
