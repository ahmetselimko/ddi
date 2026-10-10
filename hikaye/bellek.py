"""
Bellek stratejileri: modele her turda hikâyenin ne kadarının gideceği.

  tam         (varsayılan) hikâyenin TÜM sahneleri, sohbetin hatırlaması gibi,
              + dünya ve oyun olguları arasından BM25 ile getirilenler

Aşağıdakiler bağlamı kısaltır; çok uzun oyunlarda maliyet ya da hız sorun
olursa, ya da karşılaştırma yapmak istenirse kullanılır. Hepsi son 2 sahneyi
olduğu gibi verir:

  son         yalnızca son sahneler
  ozet        + her sahneden sonra güncellenen hikâye özeti
  kanon       + BM25 ile getirilen olgular
  ozet+kanon  ikisi birden

Tüm stratejilerde sahnedeki karakterlerin kartları da gider.
"""
from dataclasses import dataclass, field

from . import istem
from .dunya import Dunya
from .durum import Durum, Sahne
from .getirim import BM25

STRATEJILER = ("tam", "son", "ozet", "kanon", "ozet+kanon")


@dataclass
class Baglam:
    """Bir turda modele giden bellek içeriği; *_idleri alanları kayıt içindir."""
    ozet: str
    olgular: list[str]
    karakter_kartlari: list[str]
    son_sahneler: list[str]
    olgu_idleri: list[str] = field(default_factory=list)
    karakter_idleri: list[str] = field(default_factory=list)
    # Bulunulan/gidilen mekânla ve ilgili karakterlerle bağlı kesin olgular. Kelime
    # eşleşmesine bırakılmaz (Türkçe kısa köklerde BM25 kaçırabiliyor: "kuleye" ≠ "kulenin").
    odak_olgular: list[str] = field(default_factory=list)


class Bellek:
    def __init__(self, strateji: str = "tam", son_n: int = 2, olgu_k: int = 6):
        if strateji not in STRATEJILER:
            raise ValueError(f"Bilinmeyen strateji: {strateji} (seçenekler: {', '.join(STRATEJILER)})")
        self.strateji = strateji
        self.ozet_acik = "ozet" in strateji
        self.kanon_acik = "kanon" in strateji or strateji == "tam"
        self.son_n = None if strateji == "tam" else son_n      # None: tüm sahneler
        self.olgu_k = olgu_k

    def baglam(self, dunya: Dunya, durum: Durum, eylem: str | None) -> Baglam:
        son = durum.sahneler[-self.son_n:] if self.son_n else list(durum.sahneler)
        # Bulunulan yer ve oyuncunun eyleminde gitmek istediği yerler
        mekanlar = list(dict.fromkeys([durum.mekan] + dunya.adi_gecen_mekanlar(eylem or "")))
        # Sahnedekiler, adı geçenler ve bu yerlerde genelde bulunanlar: demirhaneye
        # gidilince demircinin kartı hazır olsun (yoksa model onu Nehir'in sesiyle konuşturuyor)
        karakter_idleri = list(dict.fromkeys(_ilgili_karakterler(dunya, son[-1:], eylem)
                                             + dunya.sakinler(mekanlar)))
        odak = dunya.ilgili_olgular(mekanlar + karakter_idleri)
        odak_idleri = {o.id for o in odak}

        olgular, olgu_idleri = [], []
        if self.kanon_acik:
            sorgu = " ".join([eylem or dunya.giris] + [s.metin for s in son[-1:]])
            getirilen = _olgu_getir(dunya, durum, sorgu, self.olgu_k)
            secilen = [(m, i) for m, i in zip(*getirilen) if i not in odak_idleri]
            olgular, olgu_idleri = [m for m, _ in secilen], [i for _, i in secilen]

        return Baglam(
            ozet=durum.ozet if self.ozet_acik else "",
            olgular=olgular,
            karakter_kartlari=[dunya.karakterler[k].kart(taninan=k in durum.taninan, adlar=dunya.karakter_adlari)
                               for k in karakter_idleri],
            son_sahneler=[istem.sahne_metni(s, dunya) for s in son],
            olgu_idleri=olgu_idleri,
            karakter_idleri=karakter_idleri,
            odak_olgular=[f"[{o.id}] {o.metin}" for o in odak],
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
    secilen += dunya.adi_gecenler(metin)
    return list(dict.fromkeys(secilen))   # sırayı koruyarak tekrarları at


def _olgu_getir(dunya: Dunya, durum: Durum, sorgu: str, k: int) -> tuple[list[str], list[str]]:
    kayitlar = [(o.id, o.metin) for o in dunya.olgular] + [(o.id, o.metin) for o in durum.olgular]
    if not kayitlar:
        return [], []
    getirici = BM25([metin for _, metin in kayitlar])
    secilen = [kayitlar[i] for i in getirici.en_iyiler(sorgu, k)]
    return [f"[{oid}] {metin}" for oid, metin in secilen], [oid for oid, _ in secilen]
