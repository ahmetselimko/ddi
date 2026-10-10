"""
Dünya kanonu: karakterler, mekânlar ve sabit olgular.

Oyun boyunca değişmeyen gerçekler buradan okunur. Oyun sırasında ortaya
çıkan yeni olgular durum.py'de tutulur.
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .getirim import kelimeler, kucult


@dataclass
class Karakter:
    id: str
    ad: str
    tanim: str
    kisilik: str
    konusma: str
    # Metinde anılma biçimleri. YALNIZCA özel adlar: "yabancı", "çocuk" gibi
    # sıradan kelimeler her geçtiği yerde bu karakter sanılır.
    adlar: list[str] = field(default_factory=list)
    ornek_replikler: list[str] = field(default_factory=list)
    gorunen_ad: str = ""   # oyuncu tanışmadan önce konuşma etiketi ("İri yapılı kadın")
    yer: str = ""          # genelde bulunduğu mekânın id'si; oraya gidilince kartı yazara gider
    imza: list[str] = field(default_factory=list)   # yalnızca bu karaktere ait sözler ("evlat")
    # Manga için görünüş: sac, yuz, kiyafet, ayirt_edici (Türkçe, okumak için) ve prompt_en
    # (görsel modelin kullandığı İngilizce etiketler). İsteğe bağlı; yoksa manga.py üretir.
    gorunum: dict = field(default_factory=dict)
    # Sabit özellikler (isteğe bağlı). esyalar: oyun başında üzerindekiler; oyun içinde değişen
    # hâli durum.karakter_durumlari'nda. iliskiler: diğer karakterin id'si → ona bakışı.
    hedef: str = ""
    yapabilir: list[str] = field(default_factory=list)
    yapamaz: list[str] = field(default_factory=list)
    esyalar: list[str] = field(default_factory=list)
    iliskiler: dict = field(default_factory=dict)

    def __post_init__(self):
        self.gorunen_ad = self.gorunen_ad or self.ad

    def kart(self, taninan: bool = True, adlar: dict | None = None) -> str:
        """İstemde kullanılan karakter kartı. taninan=False: oyuncu adını henüz bilmiyor;
        yazar onu görünüşüyle ansın diye başlıkta görünen ad öne çıkar. adlar: id → ad
        (ilişkilerde diğer karakterlerin adı yazılsın diye)."""
        if taninan:
            baslik = f"{self.ad} [{self.id}]"
        else:
            baslik = (f"{self.gorunen_ad} [{self.id}] — gerçek adı {self.ad}; oyuncu bu adı henüz "
                      "DUYMADI: anlatımda ve seçeneklerde kullanma")
        satirlar = [
            baslik,
            f"  Kim: {self.tanim}",
            f"  Kişilik: {self.kisilik}",
            f"  Konuşma: {self.konusma}",
        ]
        gorunus = "; ".join(v for a, v in self.gorunum.items()
                            if a in ("sac", "yuz", "kiyafet", "ayirt_edici") and v)
        if gorunus:
            satirlar.append(f"  Görünüş: {gorunus}")
        if self.hedef:
            satirlar.append(f"  Hedefi: {self.hedef}")
        if self.yapabilir:
            satirlar.append(f"  Yapabildikleri: {', '.join(self.yapabilir)}")
        if self.yapamaz:
            satirlar.append(f"  Yapamadıkları (bunları yapmaz; kalkışırsa beceremez): {', '.join(self.yapamaz)}")
        if self.iliskiler:
            adlar = adlar or {}
            satirlar.append("  İlişkileri: " + "; ".join(f"{adlar.get(k, k)} — {v}" for k, v in self.iliskiler.items()))
        if self.imza:
            satirlar.append(f"  İmza sözleri (yalnızca bu karaktere ait, başkası kullanmaz): {', '.join(self.imza)}")
        if self.ornek_replikler:
            satirlar.append("  Üslup örnekleri (aynen kullanma, yalnızca sesi yakala): "
                            + " / ".join(f'"{r}"' for r in self.ornek_replikler))
        return "\n".join(satirlar)


@dataclass
class Mekan:
    id: str
    ad: str
    tanim: str
    # Metinde anılma biçimleri: "kule*" önekle eşleşir (kuleye, kulenin); yıldızsız
    # olanlar kelimenin tam kendisiyle ("han" → "han", "Han'a"; ama "hanım" değil)
    adlar: list[str] = field(default_factory=list)
    prompt_en: str = ""    # manga: mekânın İngilizce görsel etiketleri (isteğe bağlı)


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
    baslangic_zamani: str = "1. gün, akşam"
    # Dünyanın değişmez kuralları ("ateşli silah yoktur"); id'leri k1, k2...
    # Olgular gibi çelişki denetiminde kullanılır, ama her istemde her zaman görünür.
    kurallar: list[Olgu] = field(default_factory=list)
    oyuncu_esyalar: list[str] = field(default_factory=list)
    oyuncu_akce: int = 0                  # alan adı tarihsel; birimi para_birimi söyler
    para_birimi: str = "akçe"
    vaatler: list[str] = field(default_factory=list)   # oyun başında açık olan büyük sorular
    gorsel_en: str = ""    # manga: dünyanın dönemi/ortamı, her panele eklenen İngilizce etiketler

    @property
    def karakter_adlari(self) -> dict[str, str]:
        return {k: c.ad for k, c in self.karakterler.items()}

    @property
    def acilis(self) -> Olgu:
        """Açılış metni de kanondur ("ahırda tek bir at bile yok"); a1 id'siyle çelişki
        denetiminde gösterilebilsin diye olgu olarak da sunulur."""
        return Olgu(id="a1", metin=self.giris, ilgili=[self.baslangic_mekan])

    @property
    def sabit_olgular(self) -> list[Olgu]:
        """Çelişki denetiminin karşılaştırdığı değişmez kanon: olgular + kurallar + açılış."""
        return self.olgular + self.kurallar + [self.acilis]

    def adi_gecen_mekanlar(self, metin: str) -> list[str]:
        """Metinde anılan mekânların id'leri (Mekan.adlar kurallarıyla)."""
        gecenler = kelimeler(metin)
        bulunan = []
        for mid, m in self.mekanlar.items():
            for ad in m.adlar:
                ad = kucult(ad)
                if ad.endswith("*"):
                    eslesti = any(w.startswith(ad[:-1]) for w in gecenler)
                elif " " in ad:
                    eslesti = ad in " ".join(gecenler)
                else:
                    eslesti = ad in gecenler
                if eslesti:
                    bulunan.append(mid)
                    break
        return bulunan

    def sakinler(self, mekanlar) -> list[str]:
        """Bu mekânlarda genelde bulunan karakterler (Karakter.yer)."""
        return [kid for kid, k in self.karakterler.items() if k.yer and k.yer in mekanlar]

    def ilgili_olgular(self, idler) -> list[Olgu]:
        """ilgili alanı verilen karakter/mekân id'lerinden birini içeren sabit olgular."""
        idler = set(idler)
        return [o for o in self.olgular + [self.acilis] if idler & set(o.ilgili)]

    def adi_gecenler(self, metin: str, haric=()) -> list[str]:
        """Metinde özel adı (adlar alanı) geçen karakterlerin id'leri; haric dışındakiler.
        Tam kelime eşleşmesi: Türkçede özel ada gelen ek kesmeyle ayrılır ("Tekin'in") ve
        kelimeler() onu atar; önek eşleşmesi ise "tekinsiz"i Tekin sanıyordu."""
        gecenler = set(kelimeler(metin))
        bulunan = []
        for kid, k in self.karakterler.items():
            if kid in haric:
                continue
            if any(kucult(a) in gecenler for a in k.adlar if len(a) >= 3):
                bulunan.append(kid)
        return bulunan


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
        baslangic_zamani=ham.get("baslangic_zamani", "1. gün, akşam"),
        kurallar=[Olgu(id=f"k{i}", metin=m) for i, m in enumerate(ham.get("kurallar") or [], 1)],
        oyuncu_esyalar=list(ham.get("oyuncu_esyalar") or []),
        oyuncu_akce=int(ham.get("oyuncu_akce") or 0),
        para_birimi=str(ham.get("para_birimi") or "akçe"),
        vaatler=[str(v) for v in ham.get("vaatler") or []],
        gorsel_en=str(ham.get("gorsel_en") or ""),
    )
    _dogrula(dunya)
    return dunya


def _dogrula(dunya: Dunya) -> None:
    ortak = set(dunya.karakterler) & set(dunya.mekanlar)
    if ortak:
        raise DunyaHatasi(f"Karakter ve mekân aynı id'yi kullanıyor: {', '.join(sorted(ortak))}")
    if dunya.baslangic_mekan not in dunya.mekanlar:
        raise DunyaHatasi(f"Başlangıç mekânı tanımlı değil: {dunya.baslangic_mekan}")

    for k in dunya.karakterler.values():
        if k.yer and k.yer not in dunya.mekanlar:
            raise DunyaHatasi(f"{k.id} karakterinin yeri tanımlı bir mekân değil: {k.yer}")
        if not isinstance(k.gorunum, dict) or not all(isinstance(v, str) for v in k.gorunum.values()):
            raise DunyaHatasi(f"{k.id} karakterinin gorunum alanı ad: metin çiftlerinden oluşmalı")
        for alan in ("yapabilir", "yapamaz", "esyalar"):
            if not isinstance(getattr(k, alan), list):
                raise DunyaHatasi(f"{k.id} karakterinin {alan} alanı bir liste olmalı")
        if not isinstance(k.iliskiler, dict):
            raise DunyaHatasi(f"{k.id} karakterinin iliskiler alanı karakter_id: bakışı çiftlerinden oluşmalı")
        tanimsiz = [i for i in k.iliskiler if i not in dunya.karakterler or i == k.id]
        if tanimsiz:
            raise DunyaHatasi(f"{k.id} karakterinin ilişkilerinde tanımsız karakter: {', '.join(map(str, tanimsiz))}")

    bilinen = set(dunya.karakterler) | set(dunya.mekanlar)
    gorulen: set[str] = set()
    for o in dunya.olgular:
        if o.id in gorulen:
            raise DunyaHatasi(f"Aynı olgu id'si iki kez kullanılmış: {o.id}")
        gorulen.add(o.id)
        tanimsiz = [i for i in o.ilgili if i not in bilinen]
        if tanimsiz:
            raise DunyaHatasi(f"{o.id} olgusunda tanımsız id: {', '.join(tanimsiz)}")
