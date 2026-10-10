"""
Editör: her sahneden sonra ikinci bir model çağrısı. Sahneyi yazmaz, denetler.

  yok      editör kapalı; yeni olguları yazar modelin kendisi bildirir
  denetim  sahnedeki iddiaları kanona karşı sınıflar (yeni / biliniyor / çelişiyor),
           karakterleri kartlarına karşı denetler (kişilik, konuşma, bilgi sızıntısı),
           vaat defterini ve karakter değişimlerini tutar
  tam      + usta yazarların derslerinden çıkarılmış ölçütlerle değerlendirme
           ve yazara bir sonraki sahne için not (ilkeler/zanaat.yaml)

Editörün yanıtı kodla da süzülür (modelden bağımsız, her seferinde aynı sonuç):
tahmin bildiren iddialar atılır, kanonla büyük ölçüde örtüşen "yeni" iddialar
"biliniyor"a çevrilir, kanıtsız vaat ilerlemesi sayılmaz, tekrar eden vaat açılmaz.
Bu düzeltmeler "otomatik" alanında kayda geçer; editörün hata oranı buradan da izlenir.

Bulgular bir sonraki turda yazara geri döner. Böylece editör yalnızca ölçmez, yönlendirir de.
"""
import re
from pathlib import Path

import yaml

from . import istem
from .dunya import Dunya
from .durum import Celiski, Durum, KarakterDegisimi, KarakterSapmasi, envanter_devirleri, envanter_oku
from .getirim import BM25, belirtecle, kucult, ortusme, tekrarlanan_sozcukler
from .llm import json_coz

MODLAR = ("yok", "denetim", "tam")
ILKE_DOSYASI = Path(__file__).parent.parent / "ilkeler" / "zanaat.yaml"
_IDDIA_DURUMLARI = {"yeni", "biliniyor", "celisiyor"}
# Tahmin ve zihinsel durum bildiren sözcükler: bunlar olgu değil; tutum değişimi
# karakter_degisimleri'ne aittir.
_TAHMIN = re.compile(r"\b(görünüyor\w*|gibi|sanki|düşün\w*|hisse\w*|olabilir\w*|muhtemelen|belki|"
                     r"galiba|anlaşılan|sanıyor\w*|zannet\w*|varsay\w*|beklemiyor\w*|istekli|hale geldi|"
                     r"karşıladı|önemli görüyor\w*|merak\w*|tahmin\w*|hâlâ|halen)\b")
BILINIYOR_ESIGI = 0.6      # iddianın köklerinin bu kadarı tek bir kanon metninde geçiyorsa
YENI_OLGU_SINIRI = 3       # sahne başına kanona eklenecek en fazla yeni olgu
VAAT_TEKRAR_ESIGI = 0.5
VAAT_ILERLEME_SINIRI = 2   # bir sahnede ilerleyebilecek en fazla vaat (şişmeye karşı)
_KANONA_GIRMEYEN_TURLER = {"duygu", "kisilik", "anlik"}
TEKRAR_SAHNE_SAYISI = 4    # tekrarlanan sözcükler son kaç sahnenin anlatımında aranır
_ETIKETLI_SATIR = re.compile(r'^[^:"]{1,40}: "')
EDITOR_OLGU_SINIRI = 15    # editöre giden oyun olgusu sayısı (uzun oyunlarda şişmesin)
_SAPMA_TURLERI = {"kisilik": "sapma", "konusma": "sapma", "bilgi": "sizinti"}
_TUR_ADLARI = {"kisilik": "kişilik", "konusma": "konuşma üslubu", "bilgi": "bilgi sızıntısı"}


class EditorHatasi(ValueError):
    pass


def ilkeleri_yukle(yol: str | Path = ILKE_DOSYASI) -> list[dict]:
    return yaml.safe_load(Path(yol).read_text(encoding="utf-8"))["ilkeler"]


def _kanon_metinleri(dunya: Dunya, durum: Durum) -> list[tuple[str | None, str]]:
    """(olgu id'si ya da None, metin): iddiaların karşılaştırılacağı her şey."""
    metinler = [(o.id, o.metin) for o in dunya.sabit_olgular] + [(o.id, o.metin) for o in durum.olgular]
    metinler += [(None, f"{m.ad} {m.tanim}") for m in dunya.mekanlar.values()]
    metinler += [(None, f"{k.ad} {k.tanim}") for k in dunya.karakterler.values()]
    metinler.append((None, dunya.oyuncu))          # açılış metni sabit_olgular'da (a1)
    return metinler


def _zaten_biliniyor(iddia: str, kanon: list[tuple[str | None, str]]) -> tuple[bool, str | None]:
    if len(set(belirtecle(iddia))) < 3:
        return False, None
    for oid, metin in kanon:
        if ortusme(iddia, metin) >= BILINIYOR_ESIGI:
            return True, oid
    return False, None


def editor_yanit_coz(metin: str, dunya: Dunya, durum: Durum) -> dict:
    """Editör yanıtını doğrular, bilinmeyen id'leri ayıklar ve kodla süzer."""
    try:
        veri = json_coz(metin)
    except ValueError as e:
        raise EditorHatasi(str(e)) from e

    otomatik = {"yeniden_siniflanan": [], "atilan_tahmin": [], "atilan_tur": [], "fazla_olgu": [],
                "tekrar_vaat": [], "kanitsiz_vaat": [], "fazla_ilerleme": []}
    bilinen = set(dunya.karakterler) | set(dunya.mekanlar)
    olgu_idleri = {o.id for o in dunya.sabit_olgular} | {o.id for o in durum.olgular}
    kanon = _kanon_metinleri(dunya, durum)

    iddialar = []
    for i in veri.get("iddialar") or []:
        if not isinstance(i, dict) or i.get("durum") not in _IDDIA_DURUMLARI:
            continue
        metin_ = str(i.get("metin") or "").strip()
        if not metin_:
            continue
        durum_ = i["durum"]
        olgu = i.get("olgu") if i.get("olgu") in olgu_idleri else None
        if durum_ == "celisiyor" and olgu is None:
            continue                        # neyle çeliştiği belli olmayan çelişki sayılmaz
        if durum_ == "yeni":
            if i.get("tur") in _KANONA_GIRMEYEN_TURLER:
                otomatik["atilan_tur"].append(metin_)
                continue
            if _TAHMIN.search(kucult(metin_)):
                otomatik["atilan_tahmin"].append(metin_)
                continue
            biliniyor, oid = _zaten_biliniyor(metin_, kanon)
            if biliniyor:
                otomatik["yeniden_siniflanan"].append(metin_)
                durum_, olgu = "biliniyor", oid
            elif sum(x["durum"] == "yeni" for x in iddialar) >= YENI_OLGU_SINIRI:
                otomatik["fazla_olgu"].append(metin_)
                continue
        iddialar.append({
            "metin": metin_,
            "durum": durum_,
            "olgu": olgu,
            "ilgili": [x for x in i.get("ilgili") or [] if x in bilinen],
        })

    acik = {v.id: v.metin for v in durum.acik_vaatler}
    ham = veri.get("vaatler") or {}
    acilan = []
    for m in ham.get("acilan") or []:
        m = str(m).strip()
        if not m:
            continue
        if any(ortusme(m, onceki) >= VAAT_TEKRAR_ESIGI for onceki in list(acik.values()) + acilan):
            otomatik["tekrar_vaat"].append(m)
            continue
        acilan.append(m)

    def kanitli(liste):
        sonuc = []
        for x in liste or []:
            if isinstance(x, dict) and x.get("id") in acik and str(x.get("kanit") or "").strip():
                sonuc.append({"id": x["id"], "kanit": str(x["kanit"]).strip()})
            elif x:
                otomatik["kanitsiz_vaat"].append(x.get("id") if isinstance(x, dict) else x)
        return sonuc

    ilerleyen = kanitli(ham.get("ilerleyen"))
    otomatik["fazla_ilerleme"] = [x["id"] for x in ilerleyen[VAAT_ILERLEME_SINIRI:]]
    vaatler = {"acilan": acilan[:2], "ilerleyen": ilerleyen[:VAAT_ILERLEME_SINIRI],
               "cozulen": kanitli(ham.get("cozulen"))}

    karakter_denetimi = []
    for d in veri.get("karakter_denetimi") or []:
        if not isinstance(d, dict) or d.get("karakter") not in dunya.karakterler:
            continue
        denetim = {"karakter": d["karakter"], "gerekce": str(d.get("gerekce") or "").strip()}
        for alan, kotu in _SAPMA_TURLERI.items():
            denetim[alan] = kotu if d.get(alan) == kotu else "uygun"
        karakter_denetimi.append(denetim)

    degisimler = [
        {"karakter": d["karakter"], "degisim": str(d.get("degisim") or "").strip()}
        for d in veri.get("karakter_degisimleri") or []
        if isinstance(d, dict) and d.get("karakter") in dunya.karakterler and str(d.get("degisim") or "").strip()
    ]

    zanaat = [
        {"ilke": z["ilke"], "sonuc": z["sonuc"], "gerekce": str(z.get("gerekce") or "").strip()}
        for z in veri.get("zanaat") or []
        if isinstance(z, dict) and z.get("ilke") and z.get("sonuc") in ("iyi", "zayif")
    ]

    sb = veri.get("sahne_bilgisi") if isinstance(veri.get("sahne_bilgisi"), dict) else {}
    sahne_bilgisi = {
        "mekan": sb.get("mekan") if sb.get("mekan") in dunya.mekanlar else None,
        "zaman": str(sb.get("zaman") or "").strip(),
        "karakterler": [k for k in sb.get("karakterler") or [] if k in dunya.karakterler],
        "envanter": envanter_oku(sb.get("envanter")),
        "devirler": envanter_devirleri(sb.get("envanter"), dunya.karakterler),
        "karakterler_degisen": _karakter_degisenleri(sb.get("karakterler_degisen"), dunya),
    }

    return {
        "sahne_bilgisi": sahne_bilgisi,
        "iddialar": iddialar,
        "vaatler": vaatler,
        "karakter_denetimi": karakter_denetimi,
        "oyuncu_bilgi_sizintisi": str(veri.get("oyuncu_bilgi_sizintisi") or "").strip(),
        "karakter_degisimleri": degisimler,
        "zanaat": zanaat,
        "yazar_notu": str(veri.get("yazar_notu") or "").strip(),
        "otomatik": otomatik,
    }


def _karakter_degisenleri(ham, dunya: Dunya) -> list[dict]:
    """[{karakter, eklenen, cikan, beden}]: bilinmeyen karakter ve boş bildirim atılır."""
    sonuc = []
    for d in ham if isinstance(ham, list) else []:
        if not isinstance(d, dict) or d.get("karakter") not in dunya.karakterler:
            continue
        e = envanter_oku(d)
        beden = str(d.get("beden") or "").strip()
        if e["eklenen"] or e["cikan"] or beden:
            sonuc.append({"karakter": d["karakter"], "eklenen": e["eklenen"], "cikan": e["cikan"], "beden": beden})
    return sonuc


class Editor:
    def __init__(self, mod: str = "tam", ilkeler: list[dict] | None = None):
        if mod not in MODLAR:
            raise ValueError(f"Bilinmeyen editör modu: {mod} (seçenekler: {', '.join(MODLAR)})")
        self.mod = mod
        self.acik = mod != "yok"
        self.zanaat_acik = mod == "tam"
        if ilkeler is None:
            ilkeler = ilkeleri_yukle() if self.zanaat_acik else []
        self.ilkeler = ilkeler
        self.son_hatalar: list[str] = []

    def denetle(self, dunya: Dunya, durum: Durum, llm, deneme: int = 2):
        """Son sahneyi denetler ve durumu günceller. (bulgular, yanıtlar) döndürür;
        editör geçerli yanıt veremezse bulgular None olur ve oyun sürer."""
        sahne = durum.sahneler[-1]
        sistem, kullanici = istem.editor_istemi(dunya, durum, sahne, self.ilkeler, self.zanaat_acik,
                                                oyun_olgulari=_ilgili_oyun_olgulari(durum, sahne.metin))
        yanitlar, istek = [], kullanici
        self.son_hatalar = []                       # başarısızlıkta nedeni kayda geçsin
        for _ in range(deneme):
            yanit = llm.uret(sistem, istek, sicaklik=0.2)
            yanitlar.append(yanit)
            try:
                bulgular = editor_yanit_coz(yanit.metin, dunya, durum)
                break
            except EditorHatasi as e:
                self.son_hatalar.append(f"{e} | yanıtın başı: {yanit.metin[:200]!r}")
                istek = f"{kullanici}\n\nÖnceki yanıtın geçersizdi ({e}). Yalnızca istenen JSON'u döndür."
        else:
            return None, yanitlar
        self._uygula(bulgular, durum, sahne.no)
        return bulgular, yanitlar

    def _uygula(self, bulgular: dict, durum: Durum, no: int) -> None:
        for i in bulgular["iddialar"]:
            if i["durum"] == "yeni":
                durum.olgu_ekle(i["metin"], i["ilgili"], no)
            elif i["durum"] == "celisiyor":
                durum.celiskiler.append(Celiski(sahne_no=no, iddia=i["metin"], olgu_id=i["olgu"]))

        vaatler = {v.id: v for v in durum.vaatler}
        for x in bulgular["vaatler"]["ilerleyen"]:
            vaatler[x["id"]].ilerledigi_sahneler.append(no)
        for x in bulgular["vaatler"]["cozulen"]:
            vaatler[x["id"]].cozuldugu_sahne = no
        for metin in bulgular["vaatler"]["acilan"]:
            durum.vaat_ac(metin, no)

        for d in bulgular["karakter_denetimi"]:
            for alan, kotu in _SAPMA_TURLERI.items():
                if d[alan] == kotu:
                    durum.karakter_sapmalari.append(
                        KarakterSapmasi(sahne_no=no, karakter=d["karakter"], tur=alan, gerekce=d["gerekce"]))
        if bulgular["oyuncu_bilgi_sizintisi"]:
            durum.karakter_sapmalari.append(KarakterSapmasi(
                sahne_no=no, karakter="oyuncu", tur="bilgi", gerekce=bulgular["oyuncu_bilgi_sizintisi"]))

        for d in bulgular["karakter_degisimleri"]:
            durum.karakter_degisimleri.append(KarakterDegisimi(sahne_no=no, **d))
        if self.zanaat_acik:
            durum.editor_notu = bulgular["yazar_notu"]
            durum.zanaat_gecmisi.append([z["ilke"] for z in bulgular["zanaat"] if z["sonuc"] == "zayif"])

    def yazara_bolumler(self, dunya: Dunya, durum: Durum) -> list[str]:
        """Bir sonraki sahneyi yazacak modele gidecek editör bölümleri."""
        if not self.acik or not durum.sahneler:
            return []
        bolumler = []
        son = durum.sahneler[-1]
        simdiki = son.no

        if durum.acik_vaatler:
            bolumler.append(
                "[AÇIK VAATLER — okurun cevabını beklediği sorular. Unutma, ilerlet; "
                "ama hepsini birden çözme. En son açılan en önce kapanır.]\n"
                + "\n".join(f"- [{v.id}] {v.metin} ({simdiki - v.acildigi_sahne + 1} sahnedir açık)"
                            for v in durum.acik_vaatler)
            )

        # Ağır olaylar unutulmasın: sahnedeki karakterlerin yaşadıkları, tepkileri buna göre olsun
        son_durumlar = istem.karakter_son_durumlari(dunya, durum, son.karakterler)
        if son_durumlar:
            bolumler.append("[KARAKTERLERİN YAŞADIKLARI — tepkileri bunlarla orantılı ve tutarlı olsun]\n"
                            + son_durumlar)

        son_celiskiler = [c for c in durum.celiskiler if c.sahne_no == simdiki]
        if son_celiskiler:
            olgular = {o.id: o.metin for o in dunya.sabit_olgular} | {o.id: o.metin for o in durum.olgular}
            bolumler.append(
                "[DİKKAT — son sahne şu olgularla çelişti; bundan sonra olgulara uy]\n"
                + "\n".join(f'- Yazılan: "{c.iddia}" · Doğrusu: {olgular.get(c.olgu_id, c.olgu_id)}'
                            for c in son_celiskiler)
            )

        son_sapmalar = [s for s in durum.karakter_sapmalari if s.sahne_no == simdiki]
        if son_sapmalar:
            satirlar = []
            for s in son_sapmalar:
                if s.karakter == "oyuncu":
                    satirlar.append(f"- Anlatım oyuncuya bilemeyeceği bir şeyi bildirdi: {s.gerekce}")
                    continue
                k = dunya.karakterler[s.karakter]
                hatirlatma = {"kisilik": f"Kişiliği: {k.kisilik}", "konusma": f"Konuşması: {k.konusma}",
                              "bilgi": "Yalnızca bilebileceğini bilsin."}[s.tur]
                satirlar.append(f"- {k.ad} ({_TUR_ADLARI[s.tur]}): {s.gerekce} → {hatirlatma}")
            bolumler.append("[KARAKTER UYARISI — son sahnede kartından saptı]\n" + "\n".join(satirlar))

        # Modele sorulmadan, doğrudan kodla bulunan sorunlar
        # Reddedilen karakter durumu bildirimleri editörün hatasıdır; yazarı yönlendirmez
        kod_uyarilari = [u for u in son.uyarilar if "düzeltildi" not in u
                         and not u.startswith("karakter durumu reddedildi")]
        konusanlar = {r.karakter for r in son.replikler}
        if son.karakterler and not konusanlar:
            susanlar = ", ".join(dunya.karakterler[k].ad for k in son.karakterler)
            kod_uyarilari.append(f"{susanlar} hiç konuşmadı; bu sahnede sahnedeki karakterler "
                                 "konuşsun ve oyuncuya cevap versin")
        if kod_uyarilari:
            bolumler.append("[DİKKAT — önceki sahnede kodla bulunan sorunlar]\n"
                            + "\n".join(f"- {u}" for u in kod_uyarilari))

        tekrarlar = tekrarlanan_anlatim(dunya, durum)
        if tekrarlar:
            bolumler.append("[TEKRARLANAN SÖZCÜKLER — son sahnelerin anlatımında çok kullanıldı; bu sahnede "
                            "kullanma, yerine yeni imgeler bul]\n"
                            + ", ".join(f"{s} ({n} kez)" for s, n in tekrarlar))

        if self.zanaat_acik:
            tekrarlayan = _tekrarlayan_zayiflar(durum.zanaat_gecmisi)
            if tekrarlayan:
                ilke_metni = {i["id"]: i["ilke"] for i in self.ilkeler}
                bolumler.append(
                    "[TEKRARLAYAN SORUN — son iki sahnede de zayıftı; bu sahnede mutlaka düzelt]\n"
                    + "\n".join(f"- {i}: {ilke_metni.get(i, '')}" for i in tekrarlayan)
                )
            if durum.editor_notu:
                bolumler.append(f"[EDİTÖR NOTU]\n{durum.editor_notu}")
        return bolumler


def tekrarlanan_anlatim(dunya: Dunya, durum: Durum) -> list[tuple[str, int]]:
    """Son sahnelerin ANLATIMINDA (replikler hariç: "evlat" gibi konuşma imzaları tekrar
    etmeli) çok geçen sözcükler. Karakter adları ve görünüş etiketleri sayılmaz."""
    satirlar = [satir for s in durum.sahneler[-TEKRAR_SAHNE_SAYISI:] for satir in s.metin.split("\n")
                if satir.strip() and not _ETIKETLI_SATIR.match(satir.strip())]
    haric = set()
    for k in dunya.karakterler.values():
        for ad in [k.ad, k.gorunen_ad] + k.adlar:
            haric.update(belirtecle(ad))
    return tekrarlanan_sozcukler(satirlar, haric=haric)


def _ilgili_oyun_olgulari(durum: Durum, sahne_metni: str) -> list:
    """Uzun oyunlarda editöre tüm oyun olgularını değil, sahneyle en ilgilileri gönder."""
    if len(durum.olgular) <= EDITOR_OLGU_SINIRI:
        return durum.olgular
    getirici = BM25([o.metin for o in durum.olgular])
    secilen = set(getirici.en_iyiler(sahne_metni, EDITOR_OLGU_SINIRI))
    return [o for i, o in enumerate(durum.olgular) if i in secilen]


def _tekrarlayan_zayiflar(gecmis: list[list[str]]) -> list[str]:
    if len(gecmis) < 2:
        return []
    return [i for i in gecmis[-1] if i in gecmis[-2]]
