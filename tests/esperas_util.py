"""Utilitário de teste: `time.sleep` global que registra só as esperas da thread do teste."""

from __future__ import annotations

import threading
import time


def so_desta_thread(esperas: list) -> object:
    """time.sleep global registra só as esperas da thread do teste: threads de outros testes não contam."""
    dono = threading.get_ident()
    real = time.sleep

    def dormir(s):
        if threading.get_ident() == dono:
            esperas.append(s)
        else:
            real(s)
    return dormir
