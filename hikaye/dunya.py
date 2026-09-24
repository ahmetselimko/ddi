"""
Dünya kanonu: karakterler, mekânlar ve sabit olgular.

Oyun boyunca değişmeyen gerçekler buradan okunur. Oyun sırasında ortaya
çıkan yeni olgular durum.py'de tutulur.
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Karakter:
    id: str
    ad: str
    tanim: str
    kisilik: str
    konusma: str
    adlar: list[str] = field(default_factory=list)   # metinde anılma biçimleri
    ornek_replikler: list[str] = field(default_factory=list)

    def kart(self) -> str:
        """İstemde kullanılan karakter kartı."""
        satirlar = [
            f"{self.ad} [{self.id}]",
            f"  Kim: {self.tanim}",
            f"  Kişilik: {self.kisilik}",
            f"  Konuşma: {self.konusma}",
        ]
        if self.ornek_replikler:
            satirlar.append("  Örnek: " + " / ".join(f'"{r}"' for r in self.ornek_replikler))
        return "\n".join(satirlar)


@dataclass
class Mekan:
    id: str
    ad: str
    tanim: str


@dataclass
class Olgu:
    id: str
    metin: str
    ilgili: list[str] = field(default_factory=list)   # karakter / mekân id'leri


@dataclass
class Dunya:
    ad: str
    ton: str
    oyuncu: str
    giris: str
    baslangic_mekan: str
    karakterler: dict[str, Karakter]
    mekanlar: dict[str, Mekan]
    olgular: list[Olgu]


class DunyaHatasi(ValueError):
    pass


def dunya_yukle(yol: str | Path) -> Dunya:
    ham = yaml.safe_load(Path(yol).read_text(encoding="utf-8"))
    dunya = Dunya(
        ad=ham["ad"],
        ton=ham["ton"],
        oyuncu=ham["oyuncu"],
        giris=ham["giris"],
        baslangic_mekan=ham["baslangic_mekan"],
        karakterler={k["id"]: Karakter(**k) for k in ham.get("karakterler", [])},
        mekanlar={m["id"]: Mekan(**m) for m in ham.get("mekanlar", [])},
        olgular=[Olgu(**o) for o in ham.get("olgular", [])],
    )
    _dogrula(dunya)
    return dunya


def _dogrula(dunya: Dunya) -> None:
    ortak = set(dunya.karakterler) & set(dunya.mekanlar)
    if ortak:
        raise DunyaHatasi(f"Karakter ve mekân aynı id'yi kullanıyor: {', '.join(sorted(ortak))}")
    if dunya.baslangic_mekan not in dunya.mekanlar:
        raise DunyaHatasi(f"Başlangıç mekânı tanımlı değil: {dunya.baslangic_mekan}")

    bilinen = set(dunya.karakterler) | set(dunya.mekanlar)
    gorulen: set[str] = set()
    for o in dunya.olgular:
        if o.id in gorulen:
            raise DunyaHatasi(f"Aynı olgu id'si iki kez kullanılmış: {o.id}")
        gorulen.add(o.id)
        tanimsiz = [i for i in o.ilgili if i not in bilinen]
        if tanimsiz:
            raise DunyaHatasi(f"{o.id} olgusunda tanımsız id: {', '.join(tanimsiz)}")
