"""Oturum kaydı: her tur bir JSONL satırı. Değerlendirme betikleri bu dosyaları okur."""
import json
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path


def _serilestir(nesne):
    if is_dataclass(nesne):
        return asdict(nesne)
    raise TypeError(f"JSON'a çevrilemiyor: {type(nesne).__name__}")


class Kayitci:
    def __init__(self, klasor: Path, meta: dict):
        klasor.mkdir(parents=True, exist_ok=True)
        zaman = datetime.now().strftime("%Y%m%d-%H%M%S")
        strateji = meta.get("bellek", "bellek").replace("+", "-")
        self.yol = klasor / f"{zaman}_{strateji}_{uuid.uuid4().hex[:6]}.jsonl"
        self._yaz({"tip": "meta", "zaman": zaman, **meta})

    def tur(self, **alanlar) -> None:
        self._yaz({"tip": "tur", **alanlar})

    def _yaz(self, kayit: dict) -> None:
        with self.yol.open("a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False, default=_serilestir) + "\n")
