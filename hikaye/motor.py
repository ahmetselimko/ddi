"""
Oyun motoru. Bir tur:
  bağlamı kur → yazar modele sor → yanıtı doğrula → durumu güncelle
  → (editör açıksa) sahneyi denetlet → kaydet

Yazar, editör ve özet için ayrı modeller kullanılabilir (ör. özet için daha ucuzu).
"""
import re

from . import istem
from .bellek import Bellek
from .dunya import Dunya
from .durum import Durum, Replik, Sahne
from .editor import Editor
from .getirim import belirtecle, kelimeler, kucult, ortusme
from .kayit import Kayitci
from .llm import json_coz


SECENEK_TEKRAR_ESIGI = 0.8


class YanitHatasi(ValueError):
    pass


def tekrar_secenekleri_ayikla(secenekler: list[str], eylemler: list[str]) -> tuple[list[str], list[str]]:
    """Oyuncunun zaten yaptığı şeyi yeniden öneren seçenekleri atar. Geriye ikiden az
    seçenek kalacaksa hepsini bırakır (oyuncu serbest eylem de yazabilir) ama yine uyarır."""
    tekrarlar = [s for s in secenekler
                 if len(set(belirtecle(s))) >= 2
                 and any(ortusme(s, e) >= SECENEK_TEKRAR_ESIGI for e in eylemler)]
    if not tekrarlar:
        return secenekler, []
    uyarilar = [f"seçenek oyuncunun zaten yaptığını tekrar ediyor: {s!r}" for s in tekrarlar]
    kalan = [s for s in secenekler if s not in tekrarlar]
    return (kalan if len(kalan) >= 2 else secenekler), uyarilar


ETIKETLI_SATIR = re.compile(r'^[^:"]{1,40}: "(.*)"$')


def _norm(metin: str) -> str:
    return " ".join(kelimeler(metin))


def sahne_parcalari(metin: str) -> set[str]:
    """Kurulmuş bir sahne metnini (etiketleri atarak) karşılaştırılabilir parçalara böler."""
    parcalar = set()
    for satir in metin.split("\n"):
        eslesme = ETIKETLI_SATIR.match(satir.strip())
        parcalar.add(_norm(eslesme.group(1) if eslesme else satir))
    return parcalar


_TANITMA = re.compile(r"\b(tanıt\w*|adı|adını|adının|adıyla|adım|ismi|ismini|isminin|kendini)\b")


def akisi_birlestir(parcalar, dunya: Dunya, taninan=(), onceki: set[str] = frozenset(),
                    tanisilan=()) -> tuple[str, list[Replik], list[str], list[str]]:
    """Anlatım ve replik parçalarından sahne metnini kurar.

    - Konuşmalar metnin içinden geçtiği için modelin repliği yazıp sahneye koymayı
      unutması imkânsızlaşır; konuşanın kim olduğu da kesin bilinir.
    - Oyuncu adına yazılan replikler atılır: oyuncunun sözünü oyuncu seçer.
    - Oyuncunun adını bilmediği karakterler görünüşleriyle etiketlenir. Karakter
      tanınmış sayılır: adı bir replikte söylendiğinde, ya da anlatım adını anarken
      bir tanıtma sözü geçtiğinde ("adını Nehir olarak tanıtıyor") veya yazar onu bu
      sahnede tanıştı diye bildirdiğinde (tanisilan). Yazarın bildirimi tek başına
      yetmez: ad metinde geçmiyorsa oyuncu onu duymamıştır. Bunlar dışında anlatım
      adı erken kullanırsa uyarı üretir.
    - Önceki sahneden aynen tekrarlanan parçalar atılır (onceki: sahne_parcalari()).
    - Karakter kartındaki örnek replik aynen tekrarlanmışsa uyarı üretir.

    Döndürür: (metin, replikler, uyarılar, güncel tanınanlar)
    """
    taninan = list(taninan)
    satirlar, replikler, uyarilar = [], [], []
    for p in parcalar if isinstance(parcalar, list) else []:
        if not isinstance(p, dict):
            continue
        ham = p.get("replik") if "replik" in p else p.get("anlatim")
        ham = str(ham or "").strip().strip('"“”').strip()
        if len(ham) >= 20 and _norm(ham) in onceki:
            uyarilar.append(f"önceki sahneden aynen tekrarlanan parça atıldı: {ham[:50]!r}")
            continue
        if "replik" in p:
            metin = ham
            if not metin:
                continue
            konusan = p.get("konusan")
            if kucult(str(konusan or "")) in ("oyuncu", "sen"):
                uyarilar.append(f"oyuncu adına replik yazıldı (atıldı): {metin[:60]!r}")
                continue
            bulunan = _konusan_bul(konusan, dunya)
            if bulunan:
                if bulunan != konusan:
                    uyarilar.append(f"konuşan id'si düzeltildi: {konusan!r} → {bulunan}")
                k = dunya.karakterler[bulunan]
                if _ornek_kopyasi_mi(metin, k.ornek_replikler):
                    uyarilar.append(f"örnek replik aynen kullanıldı: {bulunan}")
                ad = k.ad if bulunan in taninan else k.gorunen_ad
                replikler.append(Replik(bulunan, metin))
            else:
                ad = str(konusan or "?")
                uyarilar.append(f"replikte bilinmeyen karakter: {konusan!r}")
            satirlar.append(f'{ad}: "{metin}"')
            taninan.extend(dunya.adi_gecenler(metin, haric=taninan))    # ad sesli söylendi
        else:
            metin = str(p.get("anlatim") or "").strip()
            if not metin:
                continue
            satirlar.append(metin)
            tanitiliyor = bool(_TANITMA.search(kucult(metin)))
            for kid in dunya.adi_gecenler(metin, haric=taninan):
                if tanitiliyor or kid in tanisilan:
                    taninan.append(kid)
                else:
                    uyarilar.append(f"anlatım, oyuncunun adını henüz bilmediği {dunya.karakterler[kid].ad} "
                                    "karakterini adıyla andı")
    return "\n".join(satirlar), replikler, list(dict.fromkeys(uyarilar)), taninan


def _ayni_esya(a: str, b: str) -> bool:
    return kucult(a).strip() == kucult(b).strip() or (ortusme(a, b) >= 0.6 and ortusme(b, a) >= 0.6)


def envanter_uygula(durum: Durum, envanter: dict) -> list[str]:
    """Yazarın bildirdiği eşya ve akçe değişimini oyuncuya işler. Olmayan eşyanın elden
    çıkması ya da yetmeyen akçenin ödenmesi uygulanmaz, uyarı olarak döner."""
    uyarilar = []
    for esya in envanter["cikan"]:
        eslesen = next((x for x in durum.esyalar if _ayni_esya(x, esya)), None)
        if eslesen:
            durum.esyalar.remove(eslesen)
        else:
            uyarilar.append(f"oyuncunun üzerinde olmayan bir eşya kullanıldı ya da elden çıktı: {esya!r}")
    for esya in envanter["eklenen"]:
        if not any(_ayni_esya(x, esya) for x in durum.esyalar):
            durum.esyalar.append(esya)
    if envanter["akce"]:
        yeni = durum.akce + envanter["akce"]
        if yeni < 0:
            uyarilar.append(f"oyuncunun {durum.akce} akçesi var, {-envanter['akce']} akçe ödeyemez")
        else:
            durum.akce = yeni
    return uyarilar


def _envanter_oku(ham) -> dict:
    ham = ham if isinstance(ham, dict) else {}
    liste = lambda anahtar: [str(x).strip() for x in ham.get(anahtar) or [] if str(x).strip()]  # noqa: E731
    try:
        akce = int(ham.get("akce") or 0)
    except (TypeError, ValueError):
        akce = 0
    return {"eklenen": liste("eklenen"), "cikan": liste("cikan"), "akce": akce}


def _ornek_kopyasi_mi(metin: str, ornekler: list[str]) -> bool:
    norm = _norm(metin)
    for ornek in ornekler:
        o = _norm(ornek)
        if o and (o == norm or (len(o) >= 20 and o in norm)):
            return True
    return False


def _konusan_bul(konusan, dunya: Dunya) -> str | None:
    """Konuşan id'sini karakterle eşler; modelin küçük yazım kaymalarını
    ("tekine", "Nehir Hanım", "iri yapılı kadın") tolere eder."""
    if konusan in dunya.karakterler:
        return konusan
    aranan = kucult(str(konusan or "")).strip()
    if len(aranan) < 3:
        return None
    for kid, k in dunya.karakterler.items():
        adlar = [kid, kucult(k.ad), kucult(k.gorunen_ad)] + [kucult(a) for a in k.adlar]
        if any(aranan.startswith(a) or a.startswith(aranan) for a in adlar):
            return kid
    return None


def yanit_coz(metin: str, dunya: Dunya, onceki_mekan: str, taninan=(),
              onceki_metin: str = "") -> tuple[dict, list[str]]:
    """Model yanıtını doğrular. Kurtarılabilir sorunları düzeltip uyarı olarak
    döndürür (bilinmeyen id'ler tutarsızlık işaretidir, kayda geçer); sahne ya da
    seçenek yoksa YanitHatasi fırlatır. onceki_metin: bir önceki sahne (tekrar denetimi)."""
    try:
        veri = json_coz(metin)
    except ValueError as e:
        raise YanitHatasi(str(e)) from e

    uyarilar = []
    tanisilan = [k for k in veri.get("tanisilan") or [] if k in dunya.karakterler]
    if veri.get("akis"):
        onceki = sahne_parcalari(onceki_metin) if onceki_metin else frozenset()
        sahne, replikler, akis_uyarilari, taninan = akisi_birlestir(
            veri["akis"], dunya, taninan, onceki, tanisilan)
        uyarilar.extend(akis_uyarilari)
    else:
        # Eski biçim: tek parça metin. Replikler metinden ayrı geldiği için güvenilmez.
        sahne, replikler = str(veri.get("sahne") or "").strip(), []
        adi_gecen = dunya.adi_gecenler(sahne)
        taninan = list(taninan) + [k for k in tanisilan if k not in taninan and k in adi_gecen]
        if sahne:
            uyarilar.append("akış yerine düz sahne metni döndü")
    if not sahne:
        raise YanitHatasi("Sahne metni boş.")
    secenekler = [str(s).strip() for s in veri.get("secenekler") or [] if str(s).strip()]
    if not secenekler:
        raise YanitHatasi("Seçenek yok.")
    for kid in dunya.adi_gecenler(" ".join(secenekler), haric=taninan):
        uyarilar.append(f"seçenekler, oyuncunun adını henüz bilmediği {dunya.karakterler[kid].ad} "
                        "karakterini adıyla andı")

    mekan = veri.get("mekan")
    if mekan not in dunya.mekanlar:
        uyarilar.append(f"bilinmeyen mekân: {mekan!r}")
        mekan = onceki_mekan

    karakterler = []
    for k in veri.get("karakterler") or []:
        if k in dunya.karakterler:
            karakterler.append(k)
        else:
            uyarilar.append(f"bilinmeyen karakter: {k!r}")

    bilinen = set(dunya.karakterler) | set(dunya.mekanlar)
    yeni_olgular = []
    for o in veri.get("yeni_olgular") or []:
        if isinstance(o, dict) and str(o.get("metin") or "").strip():
            ilgili = [i for i in o.get("ilgili") or [] if i in bilinen]
            yeni_olgular.append((str(o["metin"]).strip(), ilgili))

    return {
        "sahne": sahne,
        "mekan": mekan,
        "zaman": str(veri.get("zaman") or "").strip(),
        "karakterler": karakterler,
        "replikler": replikler,
        "taninan": taninan,
        "yeni_olgular": yeni_olgular,
        "envanter": _envanter_oku(veri.get("envanter")),
        "secenekler": secenekler[:4],
    }, uyarilar


class Motor:
    def __init__(self, dunya: Dunya, llm, bellek: Bellek, kayitci: Kayitci | None = None,
                 editor: Editor | None = None, deneme: int = 2, editor_llm=None, ozet_llm=None):
        self.dunya = dunya
        self.llm = llm                          # yazar
        self.editor_llm = editor_llm or llm
        self.ozet_llm = ozet_llm or llm
        self.bellek = bellek
        self.kayitci = kayitci
        self.editor = editor if editor and editor.acik else None
        self.deneme = deneme
        self.durum = Durum(mekan=dunya.baslangic_mekan, zaman=dunya.baslangic_zamani,
                           esyalar=list(dunya.oyuncu_esyalar), akce=dunya.oyuncu_akce)
        self.son_bulgular: dict | None = None     # editörün son sahne için bulguları
        self.son_kullanim: dict[str, tuple[int, int]] = {}

    def basla(self) -> Sahne:
        if self.durum.sahneler:
            raise RuntimeError("Oyun zaten başladı.")
        return self._tur(None)

    def oyna(self, eylem: str) -> Sahne:
        if not self.durum.sahneler:
            raise RuntimeError("Önce basla() çağrılmalı.")
        return self._tur(eylem)

    def _tur(self, eylem: str | None) -> Sahne:
        baglam = self.bellek.baglam(self.dunya, self.durum, eylem)
        ek = self.editor.yazara_bolumler(self.dunya, self.durum) if self.editor else []
        onceki_eylemler = [s.eylem for s in self.durum.sahneler if s.eylem]
        sistem = istem.sistem_istemi(self.dunya)
        kullanici = istem.sahne_istemi(self.dunya, baglam, eylem, ek, zaman=self.durum.zaman,
                                       taninan=self.durum.taninan, eylemler=onceki_eylemler,
                                       esyalar=self.durum.esyalar, akce=self.durum.akce)

        yanitlar, hatalar = [], []
        istek = kullanici
        for _ in range(self.deneme):
            yanit = self.llm.uret(sistem, istek)
            yanitlar.append(yanit)
            try:
                onceki_metin = self.durum.sahneler[-1].metin if self.durum.sahneler else ""
                cozum, uyarilar = yanit_coz(yanit.metin, self.dunya, self.durum.mekan,
                                            self.durum.taninan, onceki_metin)
                break
            except YanitHatasi as e:
                hatalar.append(str(e))
                istek = f"{kullanici}\n\nÖnceki yanıtın geçersizdi ({e}). Yalnızca istenen JSON'u döndür."
        else:
            raise YanitHatasi(f"Model {self.deneme} denemede geçerli yanıt vermedi: {hatalar}")

        cozum["secenekler"], tekrar_uyarilari = tekrar_secenekleri_ayikla(
            cozum["secenekler"], onceki_eylemler + ([eylem] if eylem else []))
        uyarilar.extend(tekrar_uyarilari)

        no = len(self.durum.sahneler) + 1
        sahne = Sahne(
            no=no,
            eylem=eylem,
            mekan=cozum["mekan"],
            metin=cozum["sahne"],
            karakterler=cozum["karakterler"],
            replikler=cozum["replikler"],
            secenekler=cozum["secenekler"],
            zaman=cozum["zaman"] or self.durum.zaman,
            uyarilar=uyarilar,
        )
        self.durum.sahneler.append(sahne)
        self.durum.mekan = sahne.mekan
        self.durum.zaman = sahne.zaman
        self.durum.taninan = cozum["taninan"]
        olgu_sayisi = len(self.durum.olgular)

        # Editör açıksa yeni olguların kaynağı editördür (kanona karşı sınıflanmış
        # iddialar); kapalıysa ya da başarısız olursa yazarın bildirdikleri.
        self.son_bulgular, editor_yanitlari = None, []
        if self.editor:
            self.son_bulgular, editor_yanitlari = self.editor.denetle(self.dunya, self.durum, self.editor_llm)
        if self.son_bulgular is None:
            for m, ilgili in cozum["yeni_olgular"]:
                self.durum.olgu_ekle(m, ilgili, no)
        # Eşya/akçe değişimi editörden SONRA: editör, sahneden önceki envantere bakarak
        # oyuncunun üzerinde olmayan bir şeyi kullanıp kullanmadığını denetler
        uyarilar.extend(envanter_uygula(self.durum, cozum["envanter"]))
        yeni_olgular = self.durum.olgular[olgu_sayisi:]
        ozet_yaniti = self.bellek.sahne_sonrasi(self.dunya, self.durum, self.ozet_llm)

        # Bu turun toplam kullanımı (arayüzdeki harcama sayacı için): rol -> (girdi, çıktı)
        self.son_kullanim = {
            rol: (_topla(c.girdi_token for c in liste) or 0, _topla(c.cikti_token for c in liste) or 0)
            for rol, liste in (("yazar", yanitlar), ("editor", editor_yanitlari),
                               ("ozet", [ozet_yaniti] if ozet_yaniti else []))
        }

        if self.kayitci:
            cagrilar = yanitlar + editor_yanitlari + ([ozet_yaniti] if ozet_yaniti else [])
            self.kayitci.tur(
                no=no,
                eylem=eylem,
                sahne=sahne,
                yeni_olgular=yeni_olgular,
                yazar_olgulari=[m for m, _ in cozum["yeni_olgular"]],
                editor=self.son_bulgular,
                editor_basarisiz=bool(self.editor) and self.son_bulgular is None,
                acik_vaatler=[v.id for v in self.durum.acik_vaatler],
                taninan=self.durum.taninan,
                envanter=cozum["envanter"],
                esyalar=self.durum.esyalar,
                akce=self.durum.akce,
                uyarilar=uyarilar,
                hatalar=hatalar,
                baglam={
                    "olgu_idleri": baglam.olgu_idleri,
                    "karakter_idleri": baglam.karakter_idleri,
                    "ozet": baglam.ozet,
                    "editor_bolumleri": len(ek),
                    "istem_karakter": len(sistem) + len(kullanici),
                },
                ozet=self.durum.ozet,
                girdi_token=_topla(c.girdi_token for c in cagrilar),
                cikti_token=_topla(c.cikti_token for c in cagrilar),
                sure=round(sum(c.sure for c in cagrilar), 2),
            )
        return sahne


def _topla(sayilar) -> int | None:
    liste = [s for s in sayilar if s is not None]
    return sum(liste) if liste else None
