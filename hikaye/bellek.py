"""
Bellek stratejileri — deneyin bağımsız değişkeni.

Her strateji modele verilecek bağlamı kurar. Hepsi son birkaç sahneyi
olduğu gibi verir (kısa süreli bellek) ve sahnedeki karakterlerin
kartlarını ekler; fark uzun süreli bellekte:

  son         yalnızca son sahneler — taban çizgisi
  ozet        + her sahneden sonra güncellenen hikâye özeti
  kanon       + dünya ve oyun olguları arasından BM25 ile getirilenler
  ozet+kanon  ikisi birden
"""
from dataclasses import dataclass, field

from . import istem
from .dunya import Dunya
from .durum import Durum, Sahne
from .getirim import BM25, kelimeler, kucult

STRATEJILER = ("son", "ozet", "kanon", "ozet+kanon")


@dataclass
class Baglam:
    """Bir turda modele giden bellek içeriği; *_idleri alanları kayıt içindir."""
    ozet: str
    olgular: list[str]
    karakter_kartlari: list[str]
    son_sahneler: list[str]
    olgu_idleri: list[str] = field(default_factory=list)
    karakter_idleri: list[str] = field(default_factory=list)


class Bellek:
    def __init__(self, strateji: str = "son", son_n: int = 2, olgu_k: int = 6):
        if strateji not in STRATEJILER:
            raise ValueError(f"Bilinmeyen strateji: {strateji} (seçenekler: {', '.join(STRATEJILER)})")
        self.strateji = strateji
        self.ozet_acik = "ozet" in strateji
        self.kanon_acik = "kanon" in strateji
        self.son_n = son_n
        self.olgu_k = olgu_k

    def baglam(self, dunya: Dunya, durum: Durum, eylem: str | None) -> Baglam:
        son = durum.sahneler[-self.son_n:]
        karakter_idleri = _ilgili_karakterler(dunya, son[-1:], eylem)

        olgular, olgu_idleri = [], []
        if self.kanon_acik:
            sorgu = " ".join([eylem or dunya.giris] + [s.metin for s in son[-1:]])
            olgular, olgu_idleri = _olgu_getir(dunya, durum, sorgu, self.olgu_k)

        return Baglam(
            ozet=durum.ozet if self.ozet_acik else "",
            olgular=olgular,
            karakter_kartlari=[dunya.karakterler[k].kart() for k in karakter_idleri],
            son_sahneler=[istem.sahne_metni(s, dunya) for s in son],
            olgu_idleri=olgu_idleri,
            karakter_idleri=karakter_idleri,
        )

    def sahne_sonrasi(self, dunya: Dunya, durum: Durum, llm):
        """Sahne eklendikten sonra çağrılır. Özet stratejisinde özeti günceller;
        yapılan model çağrısının yanıtını (kayıt için) döndürür."""
        if not self.ozet_acik:
            return None
        sistem, kullanici = istem.ozet_istemi(dunya, durum.ozet, durum.sahneler[-1])
        yanit = llm.uret(sistem, kullanici, json_mod=False, sicaklik=0.2)
        durum.ozet = yanit.metin.strip()
        return yanit


def _ilgili_karakterler(dunya: Dunya, son: list[Sahne], eylem: str | None) -> list[str]:
    """Son sahnede bulunan ya da son sahnede / oyuncu eyleminde adı geçen karakterler."""
    secilen = [k for s in son for k in s.karakterler]
    metin = " ".join([eylem or ""] + [s.metin for s in son])
    gecenler = kelimeler(metin)
    for k in dunya.karakterler.values():
        adlar = [kucult(a) for a in (k.adlar or [k.ad])]
        if any(w.startswith(a) for w in gecenler for a in adlar):
            secilen.append(k.id)
    return list(dict.fromkeys(secilen))   # sırayı koruyarak tekrarları at


def _olgu_getir(dunya: Dunya, durum: Durum, sorgu: str, k: int) -> tuple[list[str], list[str]]:
    kayitlar = [(o.id, o.metin) for o in dunya.olgular] + [(o.id, o.metin) for o in durum.olgular]
    if not kayitlar:
        return [], []
    getirici = BM25([metin for _, metin in kayitlar])
    secilen = [kayitlar[i] for i in getirici.en_iyiler(sorgu, k)]
    return [f"[{oid}] {metin}" for oid, metin in secilen], [oid for oid, _ in secilen]
