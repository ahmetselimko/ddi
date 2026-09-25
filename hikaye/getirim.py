"""
Türkçe için küçük bir BM25 getiricisi.

Kök bulma olarak kelimenin ilk 5 harfi alınır (F5). Türkçe bilgi
getiriminde bu kaba yöntemin morfolojik çözümlemeye yakın sonuç verdiği
gösterilmiştir (Can vd., 2008, JASIST). Bağımlılık gerektirmediği için
başlangıç için yeterli; daha sonra embedding tabanlı getirimle
karşılaştırılabilir.
"""
import math
import re
from collections import Counter

_TR_KUCUK = str.maketrans({"I": "ı", "İ": "i"})
_KESME_EKI = re.compile(r"[’']\w*")                 # Oruç'un -> Oruç
_KELIME = re.compile(r"[a-zçğıöşüâîû0-9]+")
DURAK = set("""
ve ile de da ki bir bu şu o ama fakat için gibi kadar daha çok en her ne
mi mı mu mü ya veya hem ise değil var yok olan olarak diye sonra önce hiç
""".split())
KOK_UZUNLUGU = 5


def kucult(metin: str) -> str:
    """Türkçe küçük harfe çevirme; str.lower() 'I'yı 'i' yapar, bu 'ı' yapar."""
    return metin.translate(_TR_KUCUK).lower()


def kelimeler(metin: str) -> list[str]:
    return _KELIME.findall(kucult(_KESME_EKI.sub("", metin)))


def ortusme(metin: str, diger: str) -> float:
    """metin'in köklerinin ne kadarı diger'de de geçiyor (0-1). Aynı bilgiyi başka
    sözcüklerle söyleyen iki cümleyi yakalamak için kaba ama modelden bağımsız ölçü."""
    kokler = set(belirtecle(metin))
    if not kokler:
        return 0.0
    return len(kokler & set(belirtecle(diger))) / len(kokler)


def belirtecle(metin: str) -> list[str]:
    return [k[:KOK_UZUNLUGU] for k in kelimeler(metin) if k not in DURAK]


class BM25:
    def __init__(self, belgeler: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self._sayimlar = [Counter(belirtecle(d)) for d in belgeler]
        self._uzunluklar = [sum(c.values()) for c in self._sayimlar]
        self._ort_uzunluk = sum(self._uzunluklar) / len(self._uzunluklar) if belgeler else 0.0

        df: Counter = Counter()
        for c in self._sayimlar:
            df.update(c.keys())
        n = len(belgeler)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def skorlar(self, sorgu: str) -> list[float]:
        terimler = belirtecle(sorgu)
        sonuc = []
        for sayim, uzunluk in zip(self._sayimlar, self._uzunluklar):
            skor = 0.0
            for t in terimler:
                f = sayim.get(t, 0)
                if f:
                    norm = 1 - self.b + self.b * uzunluk / self._ort_uzunluk
                    skor += self._idf[t] * f * (self.k1 + 1) / (f + self.k1 * norm)
            sonuc.append(skor)
        return sonuc

    def en_iyiler(self, sorgu: str, k: int) -> list[int]:
        """Skoru sıfırdan büyük en iyi k belgenin sırası."""
        skorlar = self.skorlar(sorgu)
        sirali = sorted(range(len(skorlar)), key=skorlar.__getitem__, reverse=True)
        return [i for i in sirali[:k] if skorlar[i] > 0]
