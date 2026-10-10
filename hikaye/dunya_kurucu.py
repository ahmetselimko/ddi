"""
Dünya kurucu: oyuncunun sorulara verdiği cevaplardan oynanabilir bir dünya dosyası üretir.

Dünyayı oyuncu yazar; bu modül YAZMAZ, yalnızca biçime sokar. Oyunun ihtiyaç duyduğu
teknik alanlar oyuncuya sorulmaz, cevaplardan kurallarla çıkarılır (model kullanılmaz,
her seferinde aynı sonuç):

  - karakter ve mekân kimlikleri ("Kâtip Selvi" → katip_selvi)
  - metinde anılma biçimleri (karakterde özel ad, mekânda "kule*" gibi kök kalıbı)
  - hangi gerçeğin hangi karakter ve mekânla ilgili olduğu (metinde geçen adlardan)
  - karakterlerin sırları → kanon olgusu; hikâyenin kalbindeki soru → başlangıç vaadi
"""
import re
from collections import Counter
from pathlib import Path

import yaml

from .dunya import Dunya, Karakter, Mekan, Olgu, dunya_yukle
from .getirim import kucult

_TR_ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")
# Kişi adı olmayan, unvan ya da hitap bildiren sözcükler ("Nehir Hanım" → özel ad: Nehir)
_UNVANLAR = set("""
hanım bey efendi ağa usta kâtip katip demirci hancı doktor hoca şeyh kaptan komutan
yüzbaşı çavuş dede nine teyze amca dayı abla abi baba ana anne sultan paşa bey hatun
lord leydi sör bay bayan kral kraliçe prens prenses büyücü rahip keşiş
""".split())
# Mekân adlarında kalıp üretilmeyecek genel sözcükler
_GENEL = set("""
eski yeni yıkık büyük küçük kuru uzun kara ak kızıl yüksek alçak derin karanlık ulu
""".split())
# Kısa kökler için olası çekimler ("göl" → göle, gölde, gölü...); uzun kökler önekle eşleşir
_CEKIMLER = ["", "a", "e", "ya", "ye", "da", "de", "ta", "te", "dan", "den", "tan", "ten",
             "ı", "i", "u", "ü", "yı", "yi", "yu", "yü", "ın", "in", "un", "ün", "nın", "nin", "nun", "nün"]
_IYELIK = re.compile(r"(sı|si|su|sü|ı|i|u|ü)$")


class KurucuHatasi(ValueError):
    """Eksik ya da hatalı cevaplar; mesajlar oyuncuya gösterilir."""

    def __init__(self, hatalar: list[str]):
        super().__init__("; ".join(hatalar))
        self.hatalar = hatalar


def kimlik_uret(ad: str, kullanilan: set[str]) -> str:
    temel = re.sub(r"[^a-z0-9]+", "_", kucult(ad).translate(_TR_ASCII)).strip("_") or "x"
    kimlik, n = temel, 2
    while kimlik in kullanilan:
        kimlik, n = f"{temel}_{n}", n + 1
    kullanilan.add(kimlik)
    return kimlik


def _satirlar(metin) -> list[str]:
    if isinstance(metin, list):
        return [str(x).strip() for x in metin if str(x).strip()]
    return [s.strip(" -•\t") for s in str(metin or "").splitlines() if s.strip(" -•\t")]


def _virgullu(metin) -> list[str]:
    if isinstance(metin, list):
        return [str(x).strip() for x in metin if str(x).strip()]
    return [s.strip() for s in re.split(r"[,\n]", str(metin or "")) if s.strip()]


def karakter_ozel_adlari(ad: str, kisa_ad: str = "") -> list[str]:
    """Karakterin metinde anılacağı özel ad(lar). Oyuncu kısa adı verdiyse o; yoksa tam
    adın unvan olmayan sözcükleri ("Kâtip Selvi" → selvi)."""
    if kisa_ad.strip():
        return [kucult(kisa_ad.strip())]
    sozcukler = [s for s in re.findall(r"[^\s']+", ad) if s[:1].isupper()]
    return [kucult(s) for s in sozcukler if kucult(s) not in _UNVANLAR and len(s) >= 3]


def _kokler(ad: str) -> list[str]:
    """Adın sözcükleri ve iyelik eki atılmış halleri: "Gölü" → gölü, göl; "Kulesi" → kulesi, kule.
    İkisi birden tutulur, çünkü "kapı" gibi kökün kendisi de ı/i ile bitebilir."""
    kokler = []
    for sozcuk in kucult(ad).split():
        sozcuk = sozcuk.strip("'’")
        if sozcuk in _GENEL or len(sozcuk) < 3:
            continue
        kokler.append(sozcuk)
        kok = _IYELIK.sub("", sozcuk) if len(sozcuk) >= 4 else sozcuk
        if kok != sozcuk and len(kok) >= 3:
            kokler.append(kok)
    return kokler


def mekan_kaliplari(ad: str, paylasilan: set[str] = frozenset()) -> list[str]:
    """Mekânın metinde anılma kalıpları (Mekan.adlar biçiminde). "Yıkık Gözetleme Kulesi"
    → kule*, gözetleme*; "Kuru Tuz Gölü" → göl, göle, gölde... ("göl*" olmaz: "gölge"yi,
    "han*" olmaz: "hanım"ı yakalar). paylasilan: başka mekânların adında da geçen kökler
    ("Merkez Kubbe" / "Kuzey Kubbesi" → kubbe); bunlar için yalnızca tam ad kalıbı kalır."""
    kaliplar = [kucult(ad).strip()] if " " in ad.strip() else []
    for kok in _kokler(ad):
        if kok in paylasilan:
            continue
        if len(kok) >= 4:
            kaliplar.append(f"{kok}*")
        else:
            kaliplar.extend(kok + ek for ek in _CEKIMLER)
    return list(dict.fromkeys(kaliplar))


def cevaplardan_dunya(c: dict) -> dict:
    """Sihirbaz cevaplarını dünya dosyası sözlüğüne çevirir. Eksikler KurucuHatasi olur."""
    hatalar = []
    ad = str(c.get("ad") or "").strip()
    if not ad:
        hatalar.append("Dünyanın bir adı olmalı.")
    oyuncu = c.get("oyuncu") or {}
    if not str(oyuncu.get("kim") or "").strip():
        hatalar.append("Oyuncunun kim olduğunu yaz.")
    mekan_cevaplari = [m for m in c.get("mekanlar") or [] if str(m.get("ad") or "").strip()]
    karakter_cevaplari = [k for k in c.get("karakterler") or [] if str(k.get("ad") or "").strip()]
    if not mekan_cevaplari:
        hatalar.append("En az bir mekân ekle.")
    if not karakter_cevaplari:
        hatalar.append("En az bir karakter ekle.")
    acilis = c.get("acilis") or {}
    if not str(acilis.get("metin") or "").strip():
        hatalar.append("Açılış sahnesini yaz: oyuncu nerede, ne görüyor?")
    if hatalar:
        raise KurucuHatasi(hatalar)

    # Mekânlar
    kullanilan: set[str] = set()
    mekanlar, mekan_kimligi = [], {}
    kok_sayisi = Counter(k for m in mekan_cevaplari for k in set(_kokler(m["ad"])))
    paylasilan = {k for k, n in kok_sayisi.items() if n > 1}
    for m in mekan_cevaplari:
        mid = kimlik_uret(m["ad"], kullanilan)
        mekan_kimligi[kucult(m["ad"].strip())] = mid
        mekanlar.append({"id": mid, "ad": m["ad"].strip(), "tanim": str(m.get("tanim") or "").strip() or m["ad"].strip(),
                         "adlar": mekan_kaliplari(m["ad"], paylasilan)})

    def mekan_bul(ad_):
        return mekan_kimligi.get(kucult(str(ad_ or "").strip()), "")

    # Karakterler (sırları kanon olgusu olur)
    karakterler, sir_olgulari = [], []
    for k in karakter_cevaplari:
        kid = kimlik_uret(k["ad"], kullanilan)
        adsiz = bool(k.get("adsiz"))
        gorunus = str(k.get("gorunus") or "").strip()
        gorunen = str(k.get("gorunen_ad") or "").strip() or _gorunen_ad_uret(gorunus, k["ad"])
        karakter = {
            "id": kid,
            "ad": k["ad"].strip(),
            "adlar": [] if adsiz else karakter_ozel_adlari(k["ad"], str(k.get("kisa_ad") or "")),
            "gorunen_ad": gorunen,
            "tanim": gorunus or k["ad"].strip(),
            "kisilik": str(k.get("kisilik") or "").strip() or "Belirtilmedi.",
            "konusma": str(k.get("konusma") or "").strip() or "Belirtilmedi.",
            "imza": _virgullu(k.get("imza")),
            "ornek_replikler": _satirlar(k.get("ornek")),
        }
        if mekan_bul(k.get("yer")):
            karakter["yer"] = mekan_bul(k.get("yer"))
        karakterler.append(karakter)
        if str(k.get("sir") or "").strip():
            sir_olgulari.append((f"{k['ad'].strip()} hakkında (henüz kimse bilmiyor): {k['sir'].strip()}",
                                 [kid], [kid]))

    # Kanon: kesin gerçekler + karakter sırları; ilgili alanı sonra metinden çıkarılır
    # (metin, ilgili, bilen): sırları yalnızca sahibi bilir; diğer gerçekleri kasabalılar
    gercekler = [(g, [], None) for g in _satirlar(c.get("gercekler"))] + sir_olgulari

    kurallar = _satirlar(c.get("yoklar"))
    if str(c.get("donem") or "").strip():
        kurallar.insert(0, f"Dönem ve teknoloji: {c['donem'].strip()}")

    esyalar = _virgullu(oyuncu.get("esyalar"))
    try:
        para = int(oyuncu.get("para") or 0)
    except (TypeError, ValueError):
        para = 0
    birim = str(c.get("para_birimi") or "").strip() or "akçe"
    oyuncu_metni = " ".join(x for x in (
        str(oyuncu.get("kim") or "").strip().rstrip(".") + ".",
        (str(oyuncu.get("neden") or "").strip().rstrip(".") + ".") if oyuncu.get("neden") else "",
        f"Yanında {', '.join(esyalar) or 'hiçbir eşya'} ve {para} {birim} var.",
    ) if x)

    baslangic = mekan_bul(acilis.get("mekan")) or mekanlar[0]["id"]
    tur, ton = str(c.get("tur") or "").strip(), str(c.get("ton") or "").strip()
    sonuc = {
        "ad": ad,
        "ton": " ".join(x for x in (f"Tür: {tur}." if tur else "", ton) if x) or "Belirtilmedi.",
        "oyuncu": oyuncu_metni,
        "giris": acilis["metin"].strip(),
        "baslangic_mekan": baslangic,
        "baslangic_zamani": str(acilis.get("zaman") or "").strip() or "1. gün, sabah",
        "para_birimi": birim,
        "oyuncu_esyalar": esyalar,
        "oyuncu_akce": para,
        "kurallar": kurallar,
        "vaatler": _satirlar(c.get("sir")),
        "mekanlar": mekanlar,
        "karakterler": karakterler,
        "olgular": [],
        "kurucu": "oyuncu",                          # dünyayı oyuncu yazdı; model yazmadı
    }

    # İlgili bağlantıları: gerçeğin metninde geçen karakter adları ve mekânlar
    gecici = Dunya(ad=ad, ton="", oyuncu="", giris="", baslangic_mekan=baslangic,
                   karakterler={k["id"]: Karakter(**k) for k in karakterler},
                   mekanlar={m["id"]: Mekan(**m) for m in mekanlar}, olgular=[])
    for i, (metin, ilgili, bilen) in enumerate(gercekler, 1):
        baglar = list(dict.fromkeys(ilgili + gecici.adi_gecenler(metin) + gecici.adi_gecen_mekanlar(metin)))
        olgu = {"id": f"o{i}", "metin": metin, "ilgili": baglar}
        if bilen:
            olgu["bilen"] = bilen
        sonuc["olgular"].append(olgu)
    return sonuc


def _gorunen_ad_uret(gorunus: str, ad: str) -> str:
    """Oyuncu 'tanışmadan önce nasıl anılır' yazmadıysa görünüşün ilk bölümü: "İri yapılı,
    elli yaşlarında bir kadın" → "İri yapılı". Görünüş de yoksa "Tanımadığın biri"."""
    ilk = re.split(r"[,.;]", gorunus)[0].strip()
    if not ilk:
        return "Tanımadığın biri"
    ilk = " ".join(ilk.split()[:4])
    return ilk[:1].upper() + ilk[1:]


def ipuclari(dunya_sozlugu: dict) -> list[str]:
    """Hata değil ama tutarlılığı güçlendirecek öneriler (oyuncuya gösterilir)."""
    oneriler = []
    if len(dunya_sozlugu["olgular"]) < 3:
        oneriler.append("En az 3 kesin gerçek yazarsan oyun tutarlılığı daha iyi korur (sayılar, kim neyi biliyor, ne kilitli).")
    for k in dunya_sozlugu["karakterler"]:
        if k["konusma"] == "Belirtilmedi.":
            oneriler.append(f"{k['ad']} nasıl konuşuyor? Yazmazsan bütün karakterler birbirine benzeyebilir.")
    if not dunya_sozlugu["kurallar"]:
        oneriler.append("Bu dünyada neyin olmadığını yazarsan (ör. 'ateşli silah yok') model onu uydurmaz.")
    if not dunya_sozlugu["vaatler"]:
        oneriler.append("Hikâyenin kalbindeki soruyu yazarsan oyun merak zincirini onun etrafında kurar.")
    return oneriler


def _metin(x, ayirici: str) -> str:
    """Model liste de dize de döndürebilir; sihirbazın metin kutuları dize bekler."""
    if isinstance(x, list):
        return ayirici.join(str(o).strip() for o in x if str(o).strip())
    return str(x or "").strip()


def taslagi_duzenle(ham: dict) -> dict:
    """Modelin ürettiği taslağı sihirbazın cevap biçimine getirir (liste → metin, eksik → boş)."""
    oyuncu = ham.get("oyuncu") if isinstance(ham.get("oyuncu"), dict) else {}
    acilis = ham.get("acilis") if isinstance(ham.get("acilis"), dict) else {}
    try:
        para = int(oyuncu.get("para") or 0)
    except (TypeError, ValueError):
        para = 0
    return {
        "ad": _metin(ham.get("ad"), " "), "tur": _metin(ham.get("tur"), " "), "ton": _metin(ham.get("ton"), " "),
        "donem": _metin(ham.get("donem"), " "), "yoklar": _metin(ham.get("yoklar"), "\n"),
        "para_birimi": _metin(ham.get("para_birimi"), " ") or "akçe",
        "oyuncu": {"kim": _metin(oyuncu.get("kim"), " "), "neden": _metin(oyuncu.get("neden"), " "),
                   "esyalar": _metin(oyuncu.get("esyalar"), ", "), "para": para},
        "sir": _metin(ham.get("sir"), "\n"),
        "mekanlar": [{"ad": _metin(m.get("ad"), " "), "tanim": _metin(m.get("tanim"), " ")}
                     for m in ham.get("mekanlar") or [] if isinstance(m, dict)],
        "karakterler": [{
            "ad": _metin(k.get("ad"), " "), "kisa_ad": _metin(k.get("kisa_ad"), " "), "adsiz": bool(k.get("adsiz")),
            "gorunus": _metin(k.get("gorunus"), " "), "gorunen_ad": _metin(k.get("gorunen_ad"), " "),
            "kisilik": _metin(k.get("kisilik"), " "), "konusma": _metin(k.get("konusma"), " "),
            "imza": _metin(k.get("imza"), ", "), "ornek": _metin(k.get("ornek"), "\n"),
            "sir": _metin(k.get("sir"), " "), "yer": _metin(k.get("yer"), " "),
        } for k in ham.get("karakterler") or [] if isinstance(k, dict)],
        "gercekler": _metin(ham.get("gercekler"), "\n"),
        "acilis": {"mekan": _metin(acilis.get("mekan"), " "), "zaman": _metin(acilis.get("zaman"), " "),
                   "metin": _metin(acilis.get("metin"), " ")},
    }


def taslak_uret(istek: dict, llm, deneme: int = 2) -> dict:
    """Oyuncunun kısa fikrinden (tür, birkaç cümle, isteğe bağlı oyuncu/istekler) modelle tam
    dünya taslağı üretir. Taslak kaydedilmez: oyuncu önizler, düzenler ya da yeniden ürettirir.
    Geçerliliği, kaydedilecekmiş gibi cevaplardan_dunya ile denetlenir."""
    from . import istem
    from .llm import json_coz

    if not str(istek.get("fikir") or "").strip():
        raise KurucuHatasi(["Hikâyeni birkaç cümleyle anlat."])
    sistem, kullanici = istem.dunya_istemi(istek)
    hatalar, istek_metni, yanitlar = [], kullanici, []
    for _ in range(deneme):
        yanit = llm.uret(sistem, istek_metni, sicaklik=0.9)
        yanitlar.append(yanit)
        try:
            taslak = taslagi_duzenle(json_coz(yanit.metin))
            sozluk = cevaplardan_dunya(taslak)                 # geçerli mi?
            return {"taslak": taslak, "ipuclari": ipuclari(sozluk), "yanitlar": yanitlar}
        except (ValueError, KurucuHatasi) as e:
            hata = "; ".join(e.hatalar) if isinstance(e, KurucuHatasi) else str(e)
            hatalar.append(hata)
            istek_metni = f"{kullanici}\n\nÖnceki yanıtın geçersizdi ({hata}). Yalnızca istenen JSON'u eksiksiz döndür."
    raise KurucuHatasi([f"Model geçerli bir dünya üretemedi, tekrar dene. ({hatalar[-1]})"])


def dunya_kaydet(dunya_sozlugu: dict, klasor: Path) -> str:
    """Dosyaya yazar, oyunun yükleyicisiyle doğrular; hatalıysa dosyayı siler.
    Mevcut dünyaların üzerine yazmaz. Dosya adını (uzantısız) döndürür."""
    klasor.mkdir(parents=True, exist_ok=True)
    mevcut = {p.stem for p in klasor.glob("*.yaml")}
    ad = kimlik_uret(dunya_sozlugu["ad"], set(mevcut))
    yol = klasor / f"{ad}.yaml"
    yol.write_text(yaml.safe_dump(dunya_sozlugu, allow_unicode=True, sort_keys=False, width=100),
                   encoding="utf-8")
    try:
        dunya_yukle(yol)
    except Exception as e:
        yol.unlink(missing_ok=True)
        raise KurucuHatasi([f"Dünya doğrulanamadı: {e}"]) from e
    return ad
