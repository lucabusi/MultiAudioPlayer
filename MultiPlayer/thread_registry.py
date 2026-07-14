"""Registro dei QThread in volo.

Un QThread distrutto mentre è ancora in esecuzione crasha il processo;
aspettarlo con wait() blocca la UI. `retain()` tiene un riferimento al
thread finché il suo segnale `finished` non scatta, così i chiamanti
possono scartare i propri riferimenti subito, senza attese bloccanti.
"""
from PyQt5.QtCore import QThread

_LIVE: set[QThread] = set()


def retain(thread: QThread) -> None:
    _LIVE.add(thread)
    thread.finished.connect(lambda t=thread: _LIVE.discard(t))
