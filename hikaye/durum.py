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
class Vaat:
    """Hikâyenin açtığı ve okurun cevabını beklediği soru (Sanderson: vaat-ilerleme-karşılık)."""
    id: str
    metin: str
    acildigi_sahne: int
    ilerledigi_sahneler: list[int] = field(default_factory=list)
    cozuldugu_sahne: int | None = None

    @property
    def acik(self) -> bool:
        return self.cozuldugu_sahne is None


@dataclass
class Celiski:
    sahne_no: int
    iddia: str
    olgu_id: str


@dataclass
class KarakterDegisimi:
    sahne_no: int
    karakter: str
    degisim: str


@dataclass
class Durum:
    mekan: str
    sahneler: list[Sahne] = field(default_factory=list)
    olgular: list[OyunOlgusu] = field(default_factory=list)
    ozet: str = ""
    # Editör açıkken dolanlar
    vaatler: list[Vaat] = field(default_factory=list)
    celiskiler: list[Celiski] = field(default_factory=list)
    karakter_degisimleri: list[KarakterDegisimi] = field(default_factory=list)
    editor_notu: str = ""

    def olgu_ekle(self, metin: str, ilgili: list[str], sahne_no: int) -> OyunOlgusu:
        olgu = OyunOlgusu(id=f"y{len(self.olgular) + 1}", metin=metin,
                          ilgili=ilgili, sahne_no=sahne_no)
        self.olgular.append(olgu)
        return olgu

    def vaat_ac(self, metin: str, sahne_no: int) -> Vaat:
        vaat = Vaat(id=f"v{len(self.vaatler) + 1}", metin=metin, acildigi_sahne=sahne_no)
        self.vaatler.append(vaat)
        return vaat

    @property
    def acik_vaatler(self) -> list[Vaat]:
        return [v for v in self.vaatler if v.acik]

    def kaydet(self, yol: Path) -> None:
        yol.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
