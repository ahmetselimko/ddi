"""
Oyun motoru. Bir tur:
  bağlamı kur → yazar modele sor → yanıtı doğrula → durumu güncelle
  → (editör açıksa) sahneyi denetlet → kaydet
"""
from . import istem
from .bellek import Bellek
from .dunya import Dunya
from .durum import Durum, Replik, Sahne
from .editor import Editor
from .kayit import Kayitci
from .llm import json_coz


class YanitHatasi(ValueError):
    pass


def yanit_coz(metin: str, dunya: Dunya, onceki_mekan: str) -> tuple[dict, list[str]]:
    """Model yanıtını doğrular. Kurtarılabilir sorunları düzeltip uyarı olarak
    döndürür (bilinmeyen id'ler tutarsızlık işaretidir, kayda geçer); sahne ya da
    seçenek yoksa YanitHatasi fırlatır."""
    try:
        veri = json_coz(metin)
    except ValueError as e:
        raise YanitHatasi(str(e)) from e

    sahne = str(veri.get("sahne") or "").strip()
    if not sahne:
        raise YanitHatasi("Sahne metni boş.")
    secenekler = [str(s).strip() for s in veri.get("secenekler") or [] if str(s).strip()]
    if not secenekler:
        raise YanitHatasi("Seçenek yok.")

    uyarilar = []
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

    replikler = []
    for r in veri.get("replikler") or []:
        if not isinstance(r, dict) or not str(r.get("metin") or "").strip():
            continue
        if r.get("karakter") in dunya.karakterler:
            replikler.append(Replik(r["karakter"], str(r["metin"]).strip()))
        else:
            uyarilar.append(f"replikte bilinmeyen karakter: {r.get('karakter')!r}")

    bilinen = set(dunya.karakterler) | set(dunya.mekanlar)
    yeni_olgular = []
    for o in veri.get("yeni_olgular") or []:
        if isinstance(o, dict) and str(o.get("metin") or "").strip():
            ilgili = [i for i in o.get("ilgili") or [] if i in bilinen]
            yeni_olgular.append((str(o["metin"]).strip(), ilgili))

    return {
        "sahne": sahne,
        "mekan": mekan,
        "karakterler": karakterler,
        "replikler": replikler,
        "yeni_olgular": yeni_olgular,
        "secenekler": secenekler[:4],
    }, uyarilar


class Motor:
    def __init__(self, dunya: Dunya, llm, bellek: Bellek, kayitci: Kayitci | None = None,
                 editor: Editor | None = None, deneme: int = 2):
        self.dunya = dunya
        self.llm = llm
        self.bellek = bellek
        self.kayitci = kayitci
        self.editor = editor if editor and editor.acik else None
        self.deneme = deneme
        self.durum = Durum(mekan=dunya.baslangic_mekan)
        self.son_bulgular: dict | None = None     # editörün son sahne için bulguları

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
        sistem = istem.sistem_istemi(self.dunya)
        kullanici = istem.sahne_istemi(self.dunya, baglam, eylem, ek)

        yanitlar, hatalar = [], []
        istek = kullanici
        for _ in range(self.deneme):
            yanit = self.llm.uret(sistem, istek)
            yanitlar.append(yanit)
            try:
                cozum, uyarilar = yanit_coz(yanit.metin, self.dunya, self.durum.mekan)
                break
            except YanitHatasi as e:
                hatalar.append(str(e))
                istek = f"{kullanici}\n\nÖnceki yanıtın geçersizdi ({e}). Yalnızca istenen JSON'u döndür."
        else:
            raise YanitHatasi(f"Model {self.deneme} denemede geçerli yanıt vermedi: {hatalar}")

        no = len(self.durum.sahneler) + 1
        sahne = Sahne(
            no=no,
            eylem=eylem,
            mekan=cozum["mekan"],
            metin=cozum["sahne"],
            karakterler=cozum["karakterler"],
            replikler=cozum["replikler"],
            secenekler=cozum["secenekler"],
        )
        self.durum.sahneler.append(sahne)
        self.durum.mekan = sahne.mekan
        olgu_sayisi = len(self.durum.olgular)

        # Editör açıksa yeni olguların kaynağı editördür (kanona karşı sınıflanmış
        # iddialar); kapalıysa ya da başarısız olursa yazarın bildirdikleri.
        self.son_bulgular, editor_yanitlari = None, []
        if self.editor:
            self.son_bulgular, editor_yanitlari = self.editor.denetle(self.dunya, self.durum, self.llm)
        if self.son_bulgular is None:
            for m, ilgili in cozum["yeni_olgular"]:
                self.durum.olgu_ekle(m, ilgili, no)
        yeni_olgular = self.durum.olgular[olgu_sayisi:]
        ozet_yaniti = self.bellek.sahne_sonrasi(self.dunya, self.durum, self.llm)

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
