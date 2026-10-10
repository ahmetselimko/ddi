"""
Oyun saati. Saati kod tutar; model yalnızca bir sahnenin ne kadar sürdüğünü tahmin eder
(Intra'daki <action minutes="5"> gibi). Böylece zaman hep ileri akar, gün gece yarısı
kendiliğinden geçer ve "gün batımı" on üç sahne boyunca takılı kalmaz.

Saat oyun başından beri geçen dakikadır (0 = 1. gün, gece yarısı). Yazara saat rakamı değil
yalnızca vakit adı gider: bazı dünyalarda "saat" kavramı yoktur.
"""
import re

from .getirim import kucult

GUN = 24 * 60
EN_UZUN_SAHNE = 12 * 60        # bir sahne en fazla yarım gün sürebilir (uyku dahil)
VARSAYILAN_SURE = 10           # süre bildirilmezse
EN_AZ_YOL = 10                 # mekân değiştiyse en az bu kadar yürünmüştür

# (başlangıç saati, ad): saat bu değerden büyük ya da eşitse bu vakit
VAKITLER = [(0, "gece"), (5, "şafak"), (7, "sabah"), (11, "öğle"), (14, "ikindi"),
            (17, "gün batımı"), (19, "akşam"), (22, "gece")]

# Etiketteki sözcük → saat (eski kayıtlar ve dünya dosyasındaki başlangıç zamanı için)
_ETIKET_SAATI = [("gece yarısı", 0), ("şafak", 5.5), ("tan", 5.5), ("gün doğumu", 6), ("sabah", 8),
                 ("kuşluk", 10), ("öğleden sonra", 15), ("öğle", 12), ("ikindi", 15),
                 ("gün batımı", 18), ("akşamüstü", 18), ("alacakaranlık", 18.5), ("akşam", 20), ("gece", 23)]
_GUN_NO = re.compile(r"(\d+)\.\s*gün")


def vakit_adi(dakika: int) -> str:
    """Oyun dakikasından "2. gün, sabah"."""
    gun, saat = dakika // GUN + 1, (dakika % GUN) / 60
    ad = next(a for s, a in reversed(VAKITLER) if saat >= s)
    return f"{gun}. gün, {ad}"


VAKIT_ADLARI = {ad for _, ad in VAKITLER}


def vakte_ilerlet(dakika: int, vakit: str) -> int:
    """Anlatım sahnenin sonunda açıkça bir vakit söylediyse ("sabahın ilk ışıkları") saati o vaktin
    başına ileri sarar. Saat zaten o vakitteyse ya da vakit tanınmıyorsa dokunmaz; geri gitmez."""
    if vakit not in VAKIT_ADLARI or vakit_adi(dakika).endswith(vakit):
        return dakika
    baslangic = next(s for s, a in reversed(VAKITLER) if a == vakit)
    aday = dakika // GUN * GUN + baslangic * 60
    return aday if aday > dakika else aday + GUN


def etiket_dakika(etiket: str) -> int:
    """"1. gün, gün batımı" → dakika. Tanınmayan vakit (ör. "vardiya başı") sabah 8 sayılır."""
    metin = kucult(etiket or "")
    e = _GUN_NO.search(metin)
    gun = int(e.group(1)) if e else 1
    saat = next((s for sozcuk, s in _ETIKET_SAATI if sozcuk in metin), 8)
    return (gun - 1) * GUN + int(saat * 60)


def sure_oku(ham) -> int | None:
    """Modelin bildirdiği süre (dakika); geçersizse None."""
    try:
        sure = int(float(ham))
    except (TypeError, ValueError):
        return None
    return sure if sure >= 0 else None


def sure_belirle(bildirilen: int | None, mekan_degisti: bool) -> int:
    """Kod kuralları: bildirim yoksa varsayılan, yer değiştiyse en az yol süresi, üst sınır yarım gün."""
    sure = VARSAYILAN_SURE if bildirilen is None else bildirilen
    if mekan_degisti:
        sure = max(sure, EN_AZ_YOL)
    return max(1, min(sure, EN_UZUN_SAHNE))
