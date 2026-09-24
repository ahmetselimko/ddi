"""Oyunun değişen durumu: oynanan sahneler, oyunda ortaya çıkan olgular, özet."""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Replik:
    karakter: str
    metin: str


@dataclass
class Sahne:
    no: int
    eylem: str | None          # bu sahneyi doğuran oyuncu eylemi (açılışta None)
    mekan: str
    metin: str
    karakterler: list[str]
    replikler: list[Replik]
    secenekler: list[str]


@dataclass
class OyunOlgusu:
    """Oyun sırasında kesinleşen gerçek; ilerideki sahneler bununla da çelişmemeli."""
    id: str
    metin: str
    ilgili: list[str]
    sahne_no: int


@dataclass
class Durum:
    mekan: str
    sahneler: list[Sahne] = field(default_factory=list)
    olgular: list[OyunOlgusu] = field(default_factory=list)
    ozet: str = ""

    def olgu_ekle(self, metin: str, ilgili: list[str], sahne_no: int) -> OyunOlgusu:
        olgu = OyunOlgusu(id=f"y{len(self.olgular) + 1}", metin=metin,
                          ilgili=ilgili, sahne_no=sahne_no)
        self.olgular.append(olgu)
        return olgu

    def kaydet(self, yol: Path) -> None:
        yol.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
