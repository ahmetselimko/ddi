"""
Oyun motoru. Bir tur:
  bağlamı kur → yazar modele sor → yanıtı doğrula → durumu güncelle
  → (editör açıksa) sahneyi denetlet → kaydet

Yazar, editör ve özet için ayrı modeller kullanılabilir (ör. özet için daha ucuzu).
"""
import copy
import re

from . import istem
from .bellek import Bellek
from .dunya import Dunya
from .durum import Durum, Replik, Sahne, envanter_oku, envanter_uygula
from .editor import Editor
from .getirim import belirtecle, kelimeler, kucult, ortusme
from .kayit import Kayitci
from .llm import json_coz


SECENEK_TEKRAR_ESIGI = 0.8


class YanitHatasi(ValueError):
    pass


# ── Eylem ön denetimi: model yazmadan ÖNCE, oyuncunun eylemindeki imkânsızlıklar ──
# Testte model, oyuncunun "kılıcımı çekiyorum" demesiyle olmayan bir kılıcı hikâyeye
# soktu. Bu artık modelin takdirine bırakılmaz: eylemde üzerinde olmayan bir eşya
# ya da elinde olmayan kadar akçe geçiyorsa yazara kesin bir not gider.
_ESYA_KALIPLARI = {           # kök kalıbı → eşyanın adı (Türkçe ekler ve İngilizce karşılıklar)
    r"kılı[çc]\w*": "kılıç", r"bıça[kğ]\w*": "bıçak", r"hançer\w*": "hançer", r"balta\w*": "balta",
    r"mızra[kğ]\w*": "mızrak", r"tabanca\w*": "tabanca", r"tüfe[kğ]\w*": "tüfek", r"silah\w*": "silah",
    r"kalkan\w*": "kalkan", r"halat\w*": "halat", r"ip|ipi|ipim\w*|iple|ipe": "ip", r"meşale\w*": "meşale",
    r"çakma[kğ]\w*": "çakmak", r"kibrit\w*": "kibrit", r"fener\w*": "fener", r"anahtar\w*": "anahtar",
    r"swords?": "kılıç", r"knife|knives": "bıçak", r"daggers?": "hançer", r"guns?|pistols?": "silah",
    r"ropes?": "ip", r"torch(es)?": "meşale", r"keys?": "anahtar",
}
_ESYA_DESENI = re.compile(r"(?<!\w)(" + "|".join(f"(?:{k})" for k in _ESYA_KALIPLARI) + r")(?!\w)")
_SAYILAR = {"bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8,
            "dokuz": 9, "on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60,
            "yetmiş": 70, "seksen": 80, "doksan": 90, "yüz": 100, "bin": 1000}
_VERME = re.compile(r"(?<!\w)(ver|öde|teklif|uzat|bırak|give|pay|offer)\w*")


def _esya_adi(sozcuk: str) -> str:
    for kalip, ad in _ESYA_KALIPLARI.items():
        if re.fullmatch(kalip, sozcuk):
            return ad
    return sozcuk


def _akce_miktari(metin: str) -> int | None:
    """"50 akçe", "on beş akçe" gibi ifadelerdeki en büyük miktar."""
    kelimeler_ = kucult(metin).replace("'", " ").split()
    en_buyuk = None
    for i, k in enumerate(kelimeler_):
        if not k.startswith("akçe") and not k.startswith("coin"):
            continue
        toplam, j = 0, i - 1
        while j >= 0 and (kelimeler_[j].isdigit() or kelimeler_[j] in _SAYILAR):
            toplam += int(kelimeler_[j]) if kelimeler_[j].isdigit() else _SAYILAR[kelimeler_[j]]
            j -= 1
        if toplam:
            en_buyuk = max(en_buyuk or 0, toplam)
    return en_buyuk


def eylem_denetimi(eylem: str | None, durum: Durum) -> list[str]:
    """Oyuncunun eylemi, üzerinde olmayan bir eşyayı ya da parasını aşan bir ödemeyi
    içeriyor mu? Bulunanlar yazara kesin not olarak gider."""
    if not eylem:
        return []
    notlar, kucuk = [], kucult(eylem)
    uzerindekiler = ", ".join(durum.esyalar) or "hiçbir eşya"
    gorulen = set()
    for eslesme in _ESYA_DESENI.finditer(kucuk):
        ad = _esya_adi(eslesme.group(0))
        if ad in gorulen or any(ad[:4] in kucult(x) for x in durum.esyalar):
            continue
        gorulen.add(ad)
        notlar.append(f"Oyuncunun üzerinde \"{ad}\" YOK (üzerindekiler: {uzerindekiler}). Eylem onu kullanmayı "
                      "gerektiriyorsa (çekmek, vurmak, yakmak, vermek) oyuncunun eli boş kalır ve o eşya hikâyeye "
                      "girmez; ama çevreden almaya, istemeye ya da satın almaya çalışabilir.")
    # Daha önce elinden çıkan eşyalar (dondurma çubuğu, pusula...) sözcük listesinde olmasa da yakalanır
    for esya in durum.elden_cikanlar:
        if esya not in gorulen and ortusme(esya, eylem) >= 0.5 and not any(ortusme(esya, x) >= 0.5 for x in durum.esyalar):
            gorulen.add(esya)
            notlar.append(f"\"{esya}\" artık oyuncuda DEĞİL (daha önce elinden çıktı). Onu kullanamaz.")
    miktar = _akce_miktari(eylem)
    if miktar and miktar > durum.akce and _VERME.search(kucuk):
        notlar.append(f"Oyuncunun yalnızca {durum.akce} akçesi var; {miktar} akçe veremez. Teklif ederse "
                      "elindekinin yetmediği anlaşılır.")
    return notlar


_EDINME = re.compile(r"(?<!\w)(bul|ara|iste|al|satın|ödünç|sor)\w*")


def secenek_esya_denetimi(secenekler: list[str], durum: Durum) -> list[str]:
    """Oyuncuda olmayan bir eşyayı KULLANMAYI öneren seçenekler ("İple tırmanmayı dene").
    Eşyayı bulmayı/istemeyi önerenler serbest. Yalnızca uyarı: yazara geri döner."""
    uyarilar = []
    for s in secenekler:
        kucuk = kucult(s)
        if _EDINME.search(kucuk):
            continue
        for eslesme in _ESYA_DESENI.finditer(kucuk):
            ad = _esya_adi(eslesme.group(0))
            if not any(ad[:4] in kucult(x) for x in durum.esyalar):
                uyarilar.append(f"seçenek oyuncuda olmayan \"{ad}\" eşyasını gerektiriyor: {s!r}")
                break
    return uyarilar


# ── Zaman: gece ya da akşamdan sabaha geçildiyse gün sayısı artar ──
_GUN = re.compile(r"(\d+)\.\s*gün")
_GECE = ("gece", "akşam", "gün batımı", "alacakaranlık", "gece yarısı")
_SABAH = ("sabah", "şafak", "gün doğumu", "öğle", "kuşluk")


def gun_duzelt(onceki: str, yeni: str) -> tuple[str, str | None]:
    """Model gün sayısını ilerletmeyi unutuyor ("dün gece" diyor ama hâlâ 1. gün).
    Gece/akşamdan sabaha geçildiyse ve gün aynı kaldıysa bir artırır; zaman geri
    gidemez. (düzeltilmiş zaman, uyarı ya da None)"""
    e, y = _GUN.search(onceki or ""), _GUN.search(yeni or "")
    if not e or not y:
        return yeni, None
    eski_gun, yeni_gun = int(e.group(1)), int(y.group(1))
    if yeni_gun < eski_gun:
        return onceki, f"zaman geri gidemez: {yeni!r} yerine {onceki!r} korundu"
    gece_idi = any(s in kucult(onceki) for s in _GECE)
    sabah_oldu = any(s in kucult(yeni) for s in _SABAH)
    if yeni_gun == eski_gun and gece_idi and sabah_oldu:
        duzeltilmis = _GUN.sub(f"{eski_gun + 1}. gün", yeni, count=1)
        return duzeltilmis, f"gün sayısı ilerletildi: {yeni!r} → {duzeltilmis!r}"
    return yeni, None


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
                uyarilar.extend(_imza_karismasi(metin, bulunan, dunya))
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
            # Tanıtma sözü adla AYNI cümlede olmalı: "Yusuf'un adını görüyorsun" aynı
            # paragraftaki Selvi'yi tanıtmış saymaz
            for cumle in _CUMLE_SONU.split(metin):
                tanitiliyor = bool(_TANITMA.search(kucult(cumle)))
                for kid in dunya.adi_gecenler(cumle, haric=taninan):
                    if tanitiliyor or kid in tanisilan:
                        taninan.append(kid)
                    else:
                        uyarilar.append(f"anlatım, oyuncunun adını henüz bilmediği {dunya.karakterler[kid].ad} "
                                        "karakterini adıyla andı")
    return "\n".join(satirlar), replikler, list(dict.fromkeys(uyarilar)), taninan


_CUMLE_SONU = re.compile(r"(?<=[.!?…])\s+")


def _imza_karismasi(metin: str, konusan: str, dunya: Dunya) -> list[str]:
    """Konuşan, başka bir karakterin imza sözünü ("evlat") kullandı mı? Karakter sesinin
    kodla ölçülebilen bir göstergesi; model bunu sık yapıyor."""
    kendi = {kucult(s) for s in dunya.karakterler[konusan].imza}
    kucuk = kucult(metin)
    uyarilar = []
    for kid, k in dunya.karakterler.items():
        if kid == konusan:
            continue
        for soz in k.imza:
            s = kucult(soz)
            if s not in kendi and re.search(rf"(?<!\w){re.escape(s)}(?!\w)", kucuk):
                uyarilar.append(f"ses karışması: {dunya.karakterler[konusan].ad}, "
                                f"{k.ad} karakterinin imza sözü \"{soz}\"u kullandı")
    return uyarilar


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
    aranan = _ascii(str(konusan or "")).strip()
    if len(aranan) < 3:
        return None
    for kid, k in dunya.karakterler.items():
        adlar = [_ascii(a) for a in [kid, k.ad, k.gorunen_ad] + k.adlar]
        if any(aranan.startswith(a) or a.startswith(aranan) for a in adlar):
            return kid
    return None


_TR_ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def _ascii(metin: str) -> str:
    """Model bazen Türkçe harfsiz yazıyor ("yasli demirci"); karşılaştırma harf bağımsız olsun."""
    return kucult(metin).translate(_TR_ASCII)


def yanit_coz(metin: str, dunya: Dunya, onceki_mekan: str, taninan=(),
              onceki_metin: str = "", hafif: bool = False) -> tuple[dict, list[str]]:
    """Model yanıtını doğrular. Kurtarılabilir sorunları düzeltip uyarı olarak
    döndürür (bilinmeyen id'ler tutarsızlık işaretidir, kayda geçer); sahne ya da
    seçenek yoksa YanitHatasi fırlatır. onceki_metin: bir önceki sahne (tekrar denetimi).
    hafif: yazardan mekân/zaman/karakter istenmedi; yoklukları uyarı sayılmaz."""
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
        if mekan is not None or not hafif:
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
        "envanter": envanter_oku(veri.get("envanter")),
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
        self._tur_oncesi: tuple[Durum, str | None] | None = None   # "yeniden yaz" için

    @property
    def hafif_yazar(self) -> bool:
        """Editör açıkken yazar yalnızca sahneyi yazar; sahnenin bilgilerini editör çıkarır."""
        return self.editor is not None

    def yeniden_yaz(self) -> Sahne:
        """Son sahneyi geri alıp aynı eylemle yeniden yazdırır. Durum, son turdan
        önceki hâline döner (olgular, vaatler, eşyalar dahil)."""
        if self._tur_oncesi is None:
            raise RuntimeError("Yeniden yazılacak sahne yok.")
        onceki_durum, eylem = self._tur_oncesi
        geri_alinan = len(self.durum.sahneler)
        self.durum = copy.deepcopy(onceki_durum)
        if self.kayitci:
            self.kayitci.geri_al(geri_alinan)
        return self._tur(eylem)

    def basla(self) -> Sahne:
        if self.durum.sahneler:
            raise RuntimeError("Oyun zaten başladı.")
        return self._tur(None)

    def oyna(self, eylem: str) -> Sahne:
        if not self.durum.sahneler:
            raise RuntimeError("Önce basla() çağrılmalı.")
        return self._tur(eylem)

    def _tur(self, eylem: str | None) -> Sahne:
        self._tur_oncesi = (copy.deepcopy(self.durum), eylem)
        hafif = self.hafif_yazar
        baglam = self.bellek.baglam(self.dunya, self.durum, eylem)
        ek = self.editor.yazara_bolumler(self.dunya, self.durum) if self.editor else []
        onceki_eylemler = [s.eylem for s in self.durum.sahneler if s.eylem]
        eylem_notlari = eylem_denetimi(eylem, self.durum)
        sistem = istem.sistem_istemi(self.dunya, hafif=hafif)
        kullanici = istem.sahne_istemi(self.dunya, baglam, eylem, ek, zaman=self.durum.zaman,
                                       taninan=self.durum.taninan, eylemler=onceki_eylemler,
                                       esyalar=self.durum.esyalar, akce=self.durum.akce,
                                       eylem_notlari=eylem_notlari)

        yanitlar, hatalar = [], []
        istek = kullanici
        for _ in range(self.deneme):
            yanit = self.llm.uret(sistem, istek)
            yanitlar.append(yanit)
            try:
                onceki_metin = self.durum.sahneler[-1].metin if self.durum.sahneler else ""
                cozum, uyarilar = yanit_coz(yanit.metin, self.dunya, self.durum.mekan,
                                            self.durum.taninan, onceki_metin, hafif=hafif)
                break
            except YanitHatasi as e:
                hatalar.append(str(e))
                istek = f"{kullanici}\n\nÖnceki yanıtın geçersizdi ({e}). Yalnızca istenen JSON'u döndür."
        else:
            raise YanitHatasi(f"Model {self.deneme} denemede geçerli yanıt vermedi: {hatalar}")

        cozum["secenekler"], tekrar_uyarilari = tekrar_secenekleri_ayikla(
            cozum["secenekler"], onceki_eylemler + ([eylem] if eylem else []))
        uyarilar.extend(tekrar_uyarilari)
        uyarilar.extend(secenek_esya_denetimi(cozum["secenekler"], self.durum))

        no = len(self.durum.sahneler) + 1
        konusanlar = list(dict.fromkeys(r.karakter for r in cozum["replikler"]))
        sahne = Sahne(
            no=no,
            eylem=eylem,
            mekan=cozum["mekan"],                      # hafif yazarda geçici: editör düzeltir
            metin=cozum["sahne"],
            karakterler=cozum["karakterler"] or konusanlar,
            replikler=cozum["replikler"],
            secenekler=cozum["secenekler"],
            zaman=cozum["zaman"] or self.durum.zaman,
            uyarilar=uyarilar,
        )
        self.durum.sahneler.append(sahne)
        self.durum.taninan = cozum["taninan"]
        olgu_sayisi = len(self.durum.olgular)

        # Editör açıksa sahnenin bilgilerini (mekân, zaman, karakterler, eşyalar) ve yeni
        # olguları editör çıkarır; kapalıysa ya da başarısız olursa yazarın bildirdikleri.
        # Editör, durumun SAHNEDEN ÖNCEKİ hâlini görür (ör. oyuncunun üzerindekiler).
        self.son_bulgular, editor_yanitlari = None, []
        if self.editor:
            self.son_bulgular, editor_yanitlari = self.editor.denetle(self.dunya, self.durum, self.editor_llm)
        envanter = cozum["envanter"]
        if self.son_bulgular is not None:
            sb = self.son_bulgular["sahne_bilgisi"]
            sahne.mekan = sb["mekan"] or sahne.mekan
            sahne.zaman = sb["zaman"] or sahne.zaman
            if sb["karakterler"]:
                sahne.karakterler = list(dict.fromkeys(sb["karakterler"] + konusanlar))
            envanter = sb["envanter"]
        else:
            for m, ilgili in cozum["yeni_olgular"]:
                self.durum.olgu_ekle(m, ilgili, no)
        sahne.zaman, zaman_uyarisi = gun_duzelt(self.durum.zaman, sahne.zaman)
        if zaman_uyarisi:
            uyarilar.append(zaman_uyarisi)
        uyarilar.extend(f"eylem denetimi: {n}" for n in eylem_notlari)
        self.durum.mekan, self.durum.zaman = sahne.mekan, sahne.zaman
        uyarilar.extend(envanter_uygula(self.durum, envanter))
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
                editor_hatalari=self.editor.son_hatalar if self.editor and self.son_bulgular is None else [],
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
