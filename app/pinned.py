# -*- coding: utf-8 -*-
"""Collegamenti HTTPS verso un servizio dell'organizzazione (la console centrale, un server di inferenza in rete).

Di chi ci si fida: senza altro, del certificato del servizio come farebbe un browser (un nome pubblico, un certificato
valido). Un servizio in rete locale non ha ne' l'uno ne' l'altro: si fa il certificato da se' e da' la sua impronta
insieme alla chiave. Con l'impronta ci si collega SOLO al server che presenta proprio quel certificato, e lo si
controlla prima di mandare qualsiasi cosa.

Solo libreria standard: lo usano sia il programma sia il motore, che gira con un altro Python.
"""
import hashlib
import hmac
import http.client
import ssl
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """La chiave va solo all'indirizzo scelto: un rinvio altrove non viene seguito."""
    def redirect_request(self, *a, **k):
        return None


class Pinned(http.client.HTTPSConnection):
    """Una connessione che vale solo se il certificato del server ha l'impronta attesa. Il controllo avviene appena
    finita la stretta di mano, prima che parta la richiesta: a un server diverso la chiave non arriva mai."""

    def __init__(self, host, pin="", **more):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname, context.verify_mode = False, ssl.CERT_NONE   # al posto dell'autorita' che firma, vale l'impronta
        super().__init__(host, context=context, **more)
        self._pin = pin

    def connect(self):
        super().connect()
        found = hashlib.sha256(self.sock.getpeercert(binary_form=True) or b"").hexdigest()
        if not hmac.compare_digest(found, self._pin):
            self.close()
            raise ssl.SSLCertVerificationError("pin")


class PinnedHandler(urllib.request.HTTPSHandler):
    def __init__(self, pin):
        super().__init__()
        self._pin = pin

    def https_open(self, req):
        return self.do_open(lambda host, **more: Pinned(host, pin=self._pin, **more), req)


def opener(pin=""):
    """Con l'impronta: collegamento diretto (niente proxy in mezzo) al solo server con quel certificato."""
    if pin:
        return urllib.request.build_opener(urllib.request.ProxyHandler({}), PinnedHandler(pin), NoRedirect)
    return urllib.request.build_opener(NoRedirect)
