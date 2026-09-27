"""
Oturum kaydı ve oyun kayıtları.

  Kayitci      her tur bir JSONL satırı (oturumlar/*.jsonl); değerlendirme bu dosyaları okur.
               Kayıtlı bir oyuna devam edilince aynı dosyaya eklemeye sürer.
  oyun_kaydet  oyunun devam edilebilir hâli (kayitlar/*.json): durum, ayarlar, harcama
"""
import json
import os
import re
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

KAYIT_KIMLIGI = re.compile(r"^[\w-]{1,80}$")   # dosya adı olarak güvenli (../ gibi yollar geçmez)


def _serilestir(nesne):
    if is_dataclass(nesne):
        return asdict(nesne)
    raise TypeError(f"JSON'a çevrilemiyor: {type(nesne).__name__}")


class Kayitci:
    def __init__(self, klasor: Path, meta: dict, yol: Path | None = None):
        """yol verilirse (kayıtlı oyuna devam) o dosyaya eklemeye sürer."""
        klasor.mkdir(parents=True, exist_ok=True)
        zaman = datetime.now().strftime("%Y%m%d-%H%M%S")
        if yol is not None and Path(yol).exists():
            self.yol = Path(yol)
            self._yaz({"tip": "devam", "zaman": zaman, **meta})
            return
        strateji = meta.get("bellek", "bellek").replace("+", "-")
        self.yol = klasor / f"{zaman}_{strateji}_{uuid.uuid4().hex[:6]}.jsonl"
        self._yaz({"tip": "meta", "zaman": zaman, **meta})

    @property
    def kimlik(self) -> str:
        return self.yol.stem

    def tur(self, **alanlar) -> None:
        self._yaz({"tip": "tur", **alanlar})

    def geri_al(self, no: int) -> None:
        """Oyuncu son sahneyi yeniden yazdırdı: bu numaralı önceki tur kaydı geçersiz."""
        self._yaz({"tip": "geri_al", "no": no})

    def _yaz(self, kayit: dict) -> None:
        with self.yol.open("a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False, default=_serilestir) + "\n")


def oyun_kaydet(klasor: Path, kimlik: str, veri: dict) -> Path:
    """Önce geçici dosyaya yazıp sonra yerine koyar: yazarken kapanırsa eski kayıt bozulmaz."""
    klasor.mkdir(parents=True, exist_ok=True)
    yol = klasor / f"{kimlik}.json"
    gecici = yol.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, default=_serilestir), encoding="utf-8")
    os.replace(gecici, yol)
    return yol


def oyun_oku(klasor: Path, kimlik: str) -> dict:
    if not KAYIT_KIMLIGI.match(kimlik or ""):
        raise ValueError("Geçersiz kayıt.")
    yol = klasor / f"{kimlik}.json"
    if not yol.exists():
        raise ValueError("Kayıt bulunamadı.")
    return json.loads(yol.read_text(encoding="utf-8"))


def oyunlari_listele(klasor: Path) -> list[dict]:
    """Kayıtlı oyunların özeti, en son oynanan başta."""
    liste = []
    for yol in klasor.glob("*.json") if klasor.exists() else []:
        try:
            v = json.loads(yol.read_text(encoding="utf-8"))
            liste.append({
                "kimlik": yol.stem,
                "dunya": v["ayar"]["dunya"],
                "dunya_ad": v.get("dunya_ad", v["ayar"]["dunya"]),
                "sahne": len(v["oyun"]["durum"]["sahneler"]),
                "zaman": v.get("kaydedildi", ""),
                "oyun_zamani": v["oyun"]["durum"].get("zaman", ""),
                "ayar": v["ayar"],
            })
        except (OSError, ValueError, KeyError, TypeError):
            continue                                   # bozuk kayıt listeyi düşürmesin
    return sorted(liste, key=lambda x: x["zaman"], reverse=True)


def oyun_sil(klasor: Path, kimlik: str) -> None:
    if not KAYIT_KIMLIGI.match(kimlik or ""):
        raise ValueError("Geçersiz kayıt.")
    (klasor / f"{kimlik}.json").unlink(missing_ok=True)
