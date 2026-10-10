"""Oyunun değişen durumu: oynanan sahneler, oyunda ortaya çıkan olgular, özet."""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .getirim import kucult, ortusme


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
    zaman: str = ""
    uyarilar: list[str] = field(default_factory=list)   # kodla bulunan sorunlar (yazara geri döner)


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
class KarakterSapmasi:
    """Editörün bulduğu karakter tutarsızlığı. tur: kisilik | konusma | bilgi"""
    sahne_no: int
    karakter: str
    tur: str
    gerekce: str


@dataclass
class KarakterDurumu:
    """Bir karakterin oyun içinde değişen hâli. konumu kod günceller (sahnede görüldüğü yer);
    eşyalarını ve bedenini editör bildirir, kod doğrular."""
    konum: str = ""
    esyalar: list[str] = field(default_factory=list)
    beden: str = ""                 # kalıcı bedensel durum: "sol kolu sarılı"; boşsa sağlıklı
    goruldugu_sahne: int = 0        # 0: oyun başındaki yerinde, henüz görülmedi
    beden_sahnesi: int = 0


@dataclass
class Durum:
    mekan: str
    zaman: str = ""
    sahneler: list[Sahne] = field(default_factory=list)
    olgular: list[OyunOlgusu] = field(default_factory=list)
    ozet: str = ""
    taninan: list[str] = field(default_factory=list)   # oyuncunun adını öğrendiği karakterler
    esyalar: list[str] = field(default_factory=list)   # oyuncunun üzerindekiler
    akce: int = 0
    elden_cikanlar: list[str] = field(default_factory=list)   # verilen/kaybedilen eşyalar
    # Editör açıkken dolanlar
    vaatler: list[Vaat] = field(default_factory=list)
    celiskiler: list[Celiski] = field(default_factory=list)
    karakter_degisimleri: list[KarakterDegisimi] = field(default_factory=list)
    karakter_sapmalari: list[KarakterSapmasi] = field(default_factory=list)
    editor_notu: str = ""
    zanaat_gecmisi: list[list[str]] = field(default_factory=list)   # sahne başına zayıf ölçütler
    karakter_durumlari: dict[str, KarakterDurumu] = field(default_factory=dict)
    dakika: int | None = None          # oyun saati (zaman.py); None: eski kayıt, zaman etiketinden çıkarılır
    cevapsiz_eylem: str = ""           # editöre göre oyuncunun son eyleminin cevapsız kalan kısmı

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


def durum_yukle(s: dict) -> Durum:
    """Durum.kaydet() / asdict(durum) çıktısından Durum'u geri kurar (kayıtlı oyuna devam)."""
    return Durum(
        mekan=s["mekan"],
        zaman=s.get("zaman", ""),
        sahneler=[Sahne(**{**x, "replikler": [Replik(**r) for r in x.get("replikler", [])]})
                  for x in s.get("sahneler", [])],
        olgular=[OyunOlgusu(**o) for o in s.get("olgular", [])],
        ozet=s.get("ozet", ""),
        taninan=list(s.get("taninan", [])),
        esyalar=list(s.get("esyalar", [])),
        akce=s.get("akce", 0),
        elden_cikanlar=list(s.get("elden_cikanlar", [])),
        vaatler=[Vaat(**v) for v in s.get("vaatler", [])],
        celiskiler=[Celiski(**c) for c in s.get("celiskiler", [])],
        karakter_degisimleri=[KarakterDegisimi(**d) for d in s.get("karakter_degisimleri", [])],
        karakter_sapmalari=[KarakterSapmasi(**x) for x in s.get("karakter_sapmalari", [])],
        editor_notu=s.get("editor_notu", ""),
        zanaat_gecmisi=[list(z) for z in s.get("zanaat_gecmisi", [])],
        karakter_durumlari={k: KarakterDurumu(**v) for k, v in (s.get("karakter_durumlari") or {}).items()},
        dakika=s.get("dakika"),
        cevapsiz_eylem=s.get("cevapsiz_eylem", ""),
    )


def _ayni_esya(a: str, b: str) -> bool:
    return kucult(a).strip() == kucult(b).strip() or (ortusme(a, b) >= 0.6 and ortusme(b, a) >= 0.6)


def _en_benzeyen(esyalar: list[str], aranan: str) -> str | None:
    """Aranan eşyaya en çok benzeyen. Tam eşleşme yoksa kök örtüşmesine bakar; iki
    "defter" varken "kalın defter" doğru olanı bulsun diye puanla seçer."""
    for x in esyalar:
        if kucult(x).strip() == kucult(aranan).strip():
            return x
    # Eşitlikte en son eklenen: "defteri geri verdim" büyük ihtimalle yeni alınan defterdir
    puanli = [(ortusme(aranan, x) + ortusme(x, aranan), i, x) for i, x in enumerate(esyalar)
              if ortusme(aranan, x) >= 0.5 or ortusme(x, aranan) >= 0.5]
    return max(puanli)[2] if puanli else None


def _esya_adi(x) -> str:
    """Öğe düz ad ("pusula") ya da {"esya": "pusula", "kime"/"kimden": id} olabilir."""
    return str(x.get("esya") or "").strip() if isinstance(x, dict) else str(x).strip()


def envanter_oku(ham) -> dict:
    """Model çıktısındaki {"eklenen", "cikan", "akce"} alanını güvenli biçimde okur."""
    ham = ham if isinstance(ham, dict) else {}
    liste = lambda anahtar: [_esya_adi(x) for x in ham.get(anahtar) or [] if _esya_adi(x)]  # noqa: E731
    try:
        akce = int(ham.get("akce") or 0)
    except (TypeError, ValueError):
        akce = 0
    return {"eklenen": liste("eklenen"), "cikan": liste("cikan"), "akce": akce}


def envanter_devirleri(ham, karakterler) -> list[dict]:
    """Oyuncunun envanterindeki el değiştirmeler: [{"esya", "kime"}] (oyuncu verdi) ve
    [{"esya", "kimden"}] (oyuncu aldı). Bilinmeyen karakter atılır."""
    ham = ham if isinstance(ham, dict) else {}
    devirler = []
    for anahtar, yon in (("cikan", "kime"), ("eklenen", "kimden")):
        for x in ham.get(anahtar) or []:
            if isinstance(x, dict) and _esya_adi(x) and x.get(yon) in karakterler:
                devirler.append({"esya": _esya_adi(x), yon: x[yon]})
    return devirler


def devir_uygula(durum: Durum, devirler: list[dict], oyuncunun_onceki: list[str]) -> list[str]:
    """Oyuncunun verdiği eşya ancak gerçekten oyuncudan çıktıysa karaktere geçer; oyuncunun
    aldığı eşya karakterdeyse ondan düşer. Reddedilen uyarı olarak döner."""
    uyarilar = []
    cikanlar = list(oyuncunun_onceki)
    for x in durum.esyalar:                  # sahneden sonra hâlâ oyuncuda olanlar çıkmamıştır
        eslesen = _en_benzeyen(cikanlar, x)
        if eslesen and kucult(eslesen) == kucult(x):
            cikanlar.remove(eslesen)
    for d in devirler:
        kd = durum.karakter_durumlari.get(d.get("kime") or d.get("kimden"))
        if kd is None:
            continue
        if "kime" in d:
            if _en_benzeyen(cikanlar, d["esya"]) is None:
                uyarilar.append(f"karakter durumu reddedildi: {d['kime']} {d['esya']!r} aldı, ama oyuncudan çıkmadı")
            elif not any(_ayni_esya(e, d["esya"]) for e in kd.esyalar):
                kd.esyalar.append(_en_benzeyen(cikanlar, d["esya"]))
        else:
            eslesen = _en_benzeyen(kd.esyalar, d["esya"])
            if eslesen:
                kd.esyalar.remove(eslesen)
    return uyarilar


def karakter_degisimi_uygula(durum: Durum, degisenler: list[dict], sahne_no: int) -> list[str]:
    """Editörün bildirdiği karakter eşya/beden değişimleri. Karakterde olmayan eşya çıkmaz;
    reddedilenler uyarı olarak döner (kayda geçer, yazara gitmez)."""
    uyarilar = []
    for d in degisenler:
        kd = durum.karakter_durumlari.get(d["karakter"])
        if kd is None:
            continue
        for esya in d["cikan"]:
            eslesen = _en_benzeyen(kd.esyalar, esya)
            if eslesen:
                kd.esyalar.remove(eslesen)
            else:
                uyarilar.append(f"karakter durumu reddedildi: {d['karakter']} üzerinde {esya!r} yok")
        for esya in d["eklenen"]:
            if not any(_ayni_esya(x, esya) for x in kd.esyalar):
                kd.esyalar.append(esya)
        if d["beden"]:
            kd.beden = "" if kucult(d["beden"]).strip() in ("iyi", "sağlıklı", "iyileşti") else d["beden"]
            kd.beden_sahnesi = sahne_no
    return uyarilar


def envanter_uygula(durum: Durum, envanter: dict) -> list[str]:
    """Eşya ve akçe değişimini oyuncuya işler. Olmayan eşyanın elden çıkması ya da
    yetmeyen akçenin ödenmesi uygulanmaz, uyarı olarak döner."""
    uyarilar = []
    for esya in envanter["cikan"]:
        eslesen = _en_benzeyen(durum.esyalar, esya)
        if eslesen:
            durum.esyalar.remove(eslesen)
            durum.elden_cikanlar.append(eslesen)
        else:
            uyarilar.append(f"oyuncunun üzerinde olmayan bir eşya kullanıldı ya da elden çıktı: {esya!r}")
    for esya in envanter["eklenen"]:
        if not any(_ayni_esya(x, esya) for x in durum.esyalar):
            durum.esyalar.append(esya)
            geri_gelen = _en_benzeyen(durum.elden_cikanlar, esya)
            if geri_gelen:                              # ör. verilen pusula geri alındı
                durum.elden_cikanlar.remove(geri_gelen)
    if envanter["akce"]:
        yeni = durum.akce + envanter["akce"]
        if yeni < 0:
            uyarilar.append(f"oyuncunun {durum.akce} parası var, {-envanter['akce']} ödeyemez")
        else:
            durum.akce = yeni
    return uyarilar
