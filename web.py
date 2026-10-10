"""
Türkçe interaktif hikâye oyunu — web arayüzü (yerel sunucu).

  python web.py                  # http://127.0.0.1:8000 tarayıcıda açılır
  python web.py --port 8080
  python web.py --llm sahte      # API'siz deneme

Sunucu varsayılan olarak yalnızca bu bilgisayardan erişilir. --host 0.0.0.0 ile
aynı ağdaki bir telefondan da açılabilir; ama o zaman ağdaki herkes senin API
anahtarınla (ve senin hesabına) oynayabilir.

Ek paket gerekmez: Python'un kendi http.server'ı kullanılır. Tek oyuncu içindir;
aynı anda tek oyun yürür.
"""
import argparse
import copy
import json
import os
import queue
import re
import threading
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from hikaye.bellek import STRATEJILER, Bellek
from hikaye.dunya import dunya_yukle
from hikaye.durum import durum_yukle
from hikaye.dunya_kurucu import KurucuHatasi, cevaplardan_dunya, dunya_kaydet, ipuclari, taslak_uret
from hikaye.editor import MODLAR, Editor
from hikaye.kayit import KAYIT_KIMLIGI, Kayitci, oyun_kaydet, oyun_oku, oyun_sil, oyunlari_listele
from hikaye.llm import YAZAR_SECENEKLERI, env_yukle, llm_olustur
from hikaye.manga import STILLER as MANGA_STILLERI
from hikaye.manga import MangaUretici, hazir_kaynaklar, servis_olustur
from hikaye.motor import ETIKETLI_SATIR, Motor, YanitHatasi

KOK = Path(__file__).parent
WEB_KLASORU = KOK / "web"
DUNYA_KLASORU = KOK / "dunyalar"
EN_UZUN_EYLEM = 300
MANGA_DOSYASI = re.compile(r"^[\w-]{1,40}\.png$")
MANGA_KAPALI = {"acik": False, "kaynak": "yerel", "stil": "siyahbeyaz"}

# Ücretli katman, metin, 1M token başına dolar (girdi, çıktı). Kaynak: ai.google.dev/gemini-api/docs/pricing
FIYATLAR = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.8-flash": (0.75, 3.75),     # 31.12.2026'ya kadar geçerli fiyat
}


def parcalara_bol(metin: str) -> list[dict]:
    """Motorun kurduğu sahne metnini arayüz için anlatım/replik parçalarına ayırır."""
    parcalar = []
    for satir in metin.split("\n"):
        satir = satir.strip()
        if not satir:
            continue
        eslesme = ETIKETLI_SATIR.match(satir)
        if eslesme:
            parcalar.append({"tur": "replik", "ad": satir.split(":", 1)[0], "metin": eslesme.group(1)})
        else:
            parcalar.append({"tur": "anlatim", "metin": satir})
    return parcalar


def _model_adi(llm) -> str:
    return llm.ad.split(":", 1)[-1]


class MangaIsci:
    """Manga panellerini arka planda, sırayla çizer (görsel servisi tek GPU). Oyun beklemez:
    sahne kuyruğa girer, arayüz durumu /api/manga ile sorar."""

    def __init__(self, klasor: Path, llm_turu: str):
        self.klasor = klasor
        self.llm_turu = llm_turu
        self.kuyruk: queue.Queue = queue.Queue()
        self.kilit = threading.Lock()
        self.durumlar: dict = {}          # kimlik → {"sahneler": {no: {...}}, "is": {...}|None, "harcama": {...}}
        self._ureticiler: dict = {}       # (kimlik, kaynak, stil) → MangaUretici
        threading.Thread(target=self._calis, daemon=True, name="manga").start()

    def _kayit(self, kimlik: str) -> dict:
        return self.durumlar.setdefault(kimlik, {"sahneler": {}, "is": None,
                                                 "harcama": {"girdi": 0, "cikti": 0, "gorsel": 0, "dolar": 0.0}})

    def sahne_ekle(self, kimlik, dunya_kimligi, dunya, sahne, kaynak, stil, toplu=False) -> None:
        with self.kilit:
            self._kayit(kimlik)["sahneler"][sahne.no] = {"durum": "bekliyor", "hata": ""}
        self.kuyruk.put(("sahne", kimlik, dunya_kimligi, dunya, copy.deepcopy(sahne), kaynak, stil, toplu))

    def kayit_ekle(self, kimlik, dunya_kimligi, dunya, sahneler, kaynak, stil) -> int:
        """Kayıtlı bir oyunun henüz çizilmemiş sahneleri, sonra sayfalar. Kuyruğa giren sahne sayısı."""
        cizilmis = {p["sahne_no"] for p in self.paneller(kimlik)}
        eksik = [s for s in sahneler if s.no not in cizilmis]
        with self.kilit:
            self._kayit(kimlik)["is"] = {"durum": "calisiyor", "toplam": len(eksik), "biten": 0, "hata": ""}
        for s in eksik:
            self.sahne_ekle(kimlik, dunya_kimligi, dunya, s, kaynak, stil, toplu=True)
        self.kuyruk.put(("sayfa", kimlik, dunya_kimligi, dunya, None, kaynak, stil, True))
        return len(eksik)

    def bekle(self) -> None:
        """Kuyruktaki her iş bitene kadar bekler (testler için)."""
        self.kuyruk.join()

    def _uretici(self, kimlik, dunya_kimligi, dunya, kaynak, stil) -> MangaUretici:
        anahtar = (kimlik, kaynak, stil)
        if anahtar not in self._ureticiler:
            self._ureticiler[anahtar] = MangaUretici(
                dunya, servis_olustur(kaynak, stil), self.klasor / kimlik,
                llm=llm_olustur(self.llm_turu, dunya=dunya, yazar="hizli"),
                gorunum_onbellegi=self.klasor / "_gorunum" / f"{dunya_kimligi}.json")
        return self._ureticiler[anahtar]

    def _calis(self) -> None:
        while True:
            is_ = self.kuyruk.get()
            try:
                self._is(*is_)
            except Exception as e:                 # işçi asla durmasın
                print(f"Manga işçisi: {type(e).__name__}: {e}")
            finally:
                self.kuyruk.task_done()

    def _is(self, tur, kimlik, dunya_kimligi, dunya, sahne, kaynak, stil, toplu) -> None:
        kayit = self._kayit(kimlik)
        if tur == "sayfa":
            try:
                self.sayfalari_kur(kimlik, dunya)
                durum, hata = "bitti", ""
            except Exception as e:
                durum, hata = "hata", f"{type(e).__name__}: {e}"
            with self.kilit:
                if kayit["is"]:
                    kayit["is"].update(durum=durum, hata=hata or kayit["is"]["hata"])
            return
        with self.kilit:
            kayit["sahneler"][sahne.no] = {"durum": "ciziliyor", "hata": ""}
        try:
            uretici = self._uretici(kimlik, dunya_kimligi, dunya, kaynak, stil)
            once = (uretici.kullanim.girdi, uretici.kullanim.cikti, uretici.kullanim.gorsel)
            uretici.sahne_ciz(sahne)
            sonuc = {"durum": "hazir", "hata": ""}
            girdi = uretici.kullanim.girdi - once[0]
            cikti = uretici.kullanim.cikti - once[1]
            fiyat = FIYATLAR.get(_model_adi(uretici.llm)) if uretici.llm else None
            with self.kilit:
                h = kayit["harcama"]
                h["girdi"] += girdi
                h["cikti"] += cikti
                h["gorsel"] += uretici.kullanim.gorsel - once[2]
                if fiyat:
                    h["dolar"] += girdi * fiyat[0] / 1e6 + cikti * fiyat[1] / 1e6
        except Exception as e:                     # servis kapalı, ağ, bozuk yanıt
            sonuc = {"durum": "hata", "hata": f"{type(e).__name__}: {e}"}
        with self.kilit:
            kayit["sahneler"][sahne.no] = sonuc
            if toplu and kayit["is"]:
                kayit["is"]["biten"] += 1
                if sonuc["hata"]:
                    kayit["is"]["hata"] = sonuc["hata"]

    def paneller(self, kimlik: str) -> list[dict]:
        try:
            return json.loads((self.klasor / kimlik / "paneller.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def durum(self, kimlik: str) -> dict:
        paneller: dict = {}
        for p in self.paneller(kimlik):
            paneller.setdefault(p["sahne_no"], []).append(f"/manga/{kimlik}/{p['dosya']}?s={p.get('seed') or 0}")
        with self.kilit:
            kayit = copy.deepcopy(self._kayit(kimlik))
        sahneler = {no: {"durum": "hazir", "hata": "", "paneller": liste} for no, liste in paneller.items()}
        for no, d in kayit["sahneler"].items():
            sahneler[no] = {**d, "paneller": paneller.get(no, []) if d["durum"] == "hazir" else []}
        kayit["harcama"]["dolar"] = round(kayit["harcama"]["dolar"], 4)
        return {"kimlik": kimlik, "sahneler": {str(k): v for k, v in sorted(sahneler.items())},
                "is": kayit["is"], "harcama": kayit["harcama"],
                "sayfalar": sorted(p.name for p in (self.klasor / kimlik).glob("sayfa_*.png"))}

    def sayfalari_kur(self, kimlik: str, dunya) -> list[str]:
        """Sayfaları şimdi dizer (görsel servisi gerekmez: paneller zaten çizildi)."""
        return MangaUretici(dunya, None, self.klasor / kimlik).sayfalari_kaydet()


class Oturum:
    """Sunucudaki tek oyun. Motor çağrıları saniyeler sürdüğü için kilitle korunur."""

    def __init__(self, llm_turu: str, model: str | None, kayit_klasoru: Path = KOK / "oturumlar",
                 dunya_klasoru: Path = DUNYA_KLASORU, oyun_klasoru: Path = KOK / "kayitlar",
                 manga_klasoru: Path = KOK / "manga"):
        self.llm_turu = llm_turu
        self.model = model
        self.kayit_klasoru = kayit_klasoru
        self.dunya_klasoru = dunya_klasoru
        self.oyun_klasoru = oyun_klasoru     # devam edilebilir oyun kayıtları
        self.yazar = "hizli"
        self.ayar: dict = {}
        self.kimlik: str | None = None       # oynanan oyunun kayıt kimliği
        self.motor: Motor | None = None
        self.kilit = threading.Lock()
        self.harcama = {"girdi": 0, "cikti": 0, "dolar": 0.0, "bilinmiyor": False}
        self.manga_klasoru = manga_klasoru
        self.manga = MangaIsci(manga_klasoru, llm_turu)

    def ayarlar(self) -> dict:
        return {
            "dunyalar": sorted(p.stem for p in self.dunya_klasoru.glob("*.yaml")),
            "dunya_adlari": self._dunya_adlari(),
            "bellekler": list(STRATEJILER),
            "editorler": list(MODLAR),
            "yazarlar": {ad: s["aciklama"] for ad, s in YAZAR_SECENEKLERI.items()},
            "varsayilan": {"dunya": "tuzhan", "bellek": "tam", "editor": "tam", "yazar": "hizli"},
            "llm": self.llm_turu,
            "oyun_var": self.motor is not None,
            "manga": {"kaynaklar": self._manga_kaynaklari(), "stiller": list(MANGA_STILLERI),
                      "varsayilan": MANGA_KAPALI},
        }

    # ── Manga ────────────────────────────────────────────────────────────────

    def _manga_kaynaklari(self) -> dict[str, bool]:
        """Kaynak → .env'de adresi tanımlı mı. API'siz denemede ağsız 'sahte' kaynak da var."""
        kaynaklar = hazir_kaynaklar()
        if self.llm_turu == "sahte":
            kaynaklar["sahte"] = True
        return kaynaklar

    def _manga_ayari(self, m: dict | None) -> dict:
        m = m or {}
        ayar = {"acik": bool(m.get("acik")), "kaynak": m.get("kaynak") or "yerel",
                "stil": m.get("stil") or "siyahbeyaz"}
        if ayar["stil"] not in MANGA_STILLERI:
            raise ValueError(f"Bilinmeyen manga stili: {ayar['stil']}")
        if ayar["kaynak"] not in self._manga_kaynaklari():
            raise ValueError(f"Bilinmeyen görsel kaynağı: {ayar['kaynak']}")
        if ayar["acik"]:
            servis_olustur(ayar["kaynak"], ayar["stil"])     # adres yoksa burada anlaşılır hata
        return ayar

    def _manga_sahne(self, sahne) -> None:
        m = self.ayar.get("manga") or MANGA_KAPALI
        if m["acik"]:
            self.manga.sahne_ekle(self.kimlik, self.ayar["dunya"], self.motor.dunya, sahne, m["kaynak"], m["stil"])

    def manga_ayarla(self, m: dict) -> dict:
        """Oynanan oyunda mangayı aç/kapa ya da kaynağı/stili değiştir. Açılınca son sahne çizilir."""
        with self.kilit:
            if self.motor is None:
                raise ValueError("Önce bir oyun başlat.")
            eski = self.ayar.get("manga") or MANGA_KAPALI
            self.ayar["manga"] = self._manga_ayari(m)
            self._kaydet()
            if self.ayar["manga"]["acik"] and not eski["acik"] and self.motor.durum.sahneler:
                self._manga_sahne(self.motor.durum.sahneler[-1])
            return {"manga": self.ayar["manga"], **self.manga.durum(self.kimlik)}

    def manga_durumu(self, kimlik: str | None = None) -> dict:
        kimlik = kimlik or self.kimlik
        if not kimlik or not KAYIT_KIMLIGI.match(kimlik):
            raise ValueError("Geçersiz oyun kimliği.")
        return self.manga.durum(kimlik)

    def _kayitli_oyun(self, kimlik: str):
        veri = oyun_oku(self.oyun_klasoru, kimlik)
        dunya_kimligi = veri["ayar"]["dunya"]
        if not (self.dunya_klasoru / f"{dunya_kimligi}.yaml").exists():
            raise ValueError(f"Bu oyunun dünya dosyası artık yok: {dunya_kimligi}")
        dunya = dunya_yukle(self.dunya_klasoru / f"{dunya_kimligi}.yaml")
        return dunya_kimligi, dunya, durum_yukle(veri["oyun"]["durum"]).sahneler

    def manga_kayittan(self, kimlik: str, m: dict | None) -> dict:
        """Kayıtlı bir oyunun tamamından manga: çizilmemiş sahneler + sayfalar, arka planda."""
        ayar = self._manga_ayari({**(m or {}), "acik": True})
        dunya_kimligi, dunya, sahneler = self._kayitli_oyun(kimlik)
        if not sahneler:
            raise ValueError("Bu oyunda henüz sahne yok.")
        self.manga.kayit_ekle(kimlik, dunya_kimligi, dunya, sahneler, ayar["kaynak"], ayar["stil"])
        return self.manga.durum(kimlik)

    def manga_sayfalari(self, kimlik: str) -> dict:
        """Çizilmiş panellerden sayfaları şimdi dizer."""
        if not KAYIT_KIMLIGI.match(kimlik or ""):
            raise ValueError("Geçersiz oyun kimliği.")
        if kimlik == self.kimlik and self.motor is not None:
            dunya = self.motor.dunya
        else:
            dunya = self._kayitli_oyun(kimlik)[1]
        self.manga.sayfalari_kur(kimlik, dunya)
        return self.manga.durum(kimlik)

    def _motor_kur(self, dunya: str, bellek: str, editor: str, yazar: str,
                   kayit_yolu: Path | None = None) -> Motor:
        """Yeni oyun ve kayıttan devam için ortak kurulum. kayit_yolu: devam edilen oyunun
        tur kayıtları aynı .jsonl dosyasına eklenmeye sürsün diye."""
        if not (self.dunya_klasoru / f"{dunya}.yaml").exists():
            raise ValueError(f"Dünya dosyası bulunamadı: {dunya}")
        if bellek not in STRATEJILER or editor not in MODLAR or yazar not in YAZAR_SECENEKLERI:
            raise ValueError("Geçersiz bellek, editör ya da yazar seçimi.")
        d = dunya_yukle(self.dunya_klasoru / f"{dunya}.yaml")
        llm = llm_olustur(self.llm_turu, dunya=d, model=self.model, yazar=yazar)
        # Güçlü/düşünen seçenek yalnızca yazarı etkiler; editör ve özet temel modelde kalır
        temel = llm if yazar == "hizli" else llm_olustur(self.llm_turu, dunya=d, yazar="hizli")
        editor_modeli, ozet_modeli = os.environ.get("EDITOR_MODEL"), os.environ.get("OZET_MODEL")
        editor_llm = llm_olustur(self.llm_turu, dunya=d, model=editor_modeli) if editor_modeli else temel
        ozet_llm = llm_olustur(self.llm_turu, dunya=d, model=ozet_modeli) if ozet_modeli else temel
        kayitci = Kayitci(self.kayit_klasoru, meta={
            "dunya": d.ad, "llm": llm.ad, "yazar": yazar, "editor_llm": editor_llm.ad,
            "ozet_llm": ozet_llm.ad, "bellek": bellek, "editor": editor, "arayuz": "web",
        }, yol=kayit_yolu)
        self.yazar = yazar
        self.ayar = {"dunya": dunya, "bellek": bellek, "editor": editor, "yazar": yazar}
        return Motor(d, llm, Bellek(bellek), kayitci, editor=Editor(editor),
                     editor_llm=editor_llm, ozet_llm=ozet_llm)

    def yeni(self, dunya: str, bellek: str, editor: str, yazar: str = "hizli", manga: dict | None = None) -> dict:
        if dunya not in self.ayarlar()["dunyalar"]:
            raise ValueError(f"Bilinmeyen dünya: {dunya}")
        manga_ayari = self._manga_ayari(manga)
        with self.kilit:
            self.motor = self._motor_kur(dunya, bellek, editor, yazar)
            self.ayar["manga"] = manga_ayari
            self.kimlik = self.motor.kayitci.kimlik
            self.harcama = {"girdi": 0, "cikti": 0, "dolar": 0.0, "bilinmiyor": False}
            sahne = self.motor.basla()
            self._kaydet()
            self._manga_sahne(sahne)
            return self._yanit(sahne)

    def oyna(self, eylem: str) -> dict:
        eylem = (eylem or "").strip()
        if not eylem:
            raise ValueError("Boş eylem.")
        if len(eylem) > EN_UZUN_EYLEM:
            raise ValueError(f"Eylem en fazla {EN_UZUN_EYLEM} karakter olabilir.")
        with self.kilit:
            if self.motor is None:
                raise ValueError("Önce yeni bir oyun başlat.")
            sahne = self.motor.oyna(eylem)
            self._kaydet()
            self._manga_sahne(sahne)
            return self._yanit(sahne)

    # ── Kayıtlı oyunlar ──────────────────────────────────────────────────────

    def _kaydet(self) -> None:
        """Her turdan sonra otomatik: oyun kapansa da kaldığı yerden sürdürülebilir."""
        oyun_kaydet(self.oyun_klasoru, self.kimlik, {
            "surum": 1,
            "kaydedildi": datetime.now().isoformat(timespec="seconds"),
            "dunya_ad": self.motor.dunya.ad,
            "ayar": self.ayar,
            "kayit": self.motor.kayitci.kimlik,
            "harcama": self.harcama,
            "oyun": self.motor.kaydedilecek(),
        })

    def kayitli_oyunlar(self) -> dict:
        return {"kayitlar": oyunlari_listele(self.oyun_klasoru), "oynanan": self.kimlik}

    def devam(self, kimlik: str) -> dict:
        """Kayıtlı bir oyunu yükleyip kaldığı sahneden sürdürür."""
        with self.kilit:
            veri = oyun_oku(self.oyun_klasoru, kimlik)
            a = veri["ayar"]
            motor = self._motor_kur(a["dunya"], a["bellek"], a["editor"], a["yazar"],
                                    kayit_yolu=self.kayit_klasoru / f"{veri['kayit']}.jsonl")
            motor.yukle(veri["oyun"])
            self.ayar["manga"] = {**MANGA_KAPALI, **(a.get("manga") or {})}
            self.motor, self.kimlik = motor, kimlik
            self.harcama = veri.get("harcama") or {"girdi": 0, "cikti": 0, "dolar": 0.0, "bilinmiyor": False}
            return {"oyun_var": True, "sahneler": [self._sahne(s) for s in motor.durum.sahneler],
                    "editor": self._editor_ozeti(), "uyarilar": [], **self._durum_ozeti()}

    def kayit_sil(self, kimlik: str) -> dict:
        if kimlik == self.kimlik:
            raise ValueError("Şu an oynanan oyun silinemez; önce başka bir oyun başlat.")
        oyun_sil(self.oyun_klasoru, kimlik)
        return self.kayitli_oyunlar()

    def dunya_taslagi(self, istek: dict) -> dict:
        """Oyuncunun kısa fikrinden model tam bir dünya taslağı kurar (kaydedilmez, önizlenir)."""
        llm = llm_olustur(self.llm_turu, model=self.model, yazar="hizli")
        sonuc = taslak_uret(istek, llm)
        fiyat = FIYATLAR.get(_model_adi(llm))
        dolar = sum((y.girdi_token or 0) * fiyat[0] / 1e6 + (y.cikti_token or 0) * fiyat[1] / 1e6
                    for y in sonuc["yanitlar"]) if fiyat else None
        return {"taslak": sonuc["taslak"], "ipuclari": sonuc["ipuclari"],
                "maliyet": round(dolar, 4) if dolar is not None else None}

    def dunya_kur(self, cevaplar: dict) -> dict:
        """Oyuncunun sihirbazdaki cevaplarından yeni bir dünya dosyası kurar."""
        sozluk = cevaplardan_dunya(cevaplar)
        ad = dunya_kaydet(sozluk, self.dunya_klasoru)
        return {"dunya": ad, "ad": sozluk["ad"], "ipuclari": ipuclari(sozluk)}

    def _dunya_adlari(self) -> dict:
        adlar = {}
        for p in self.dunya_klasoru.glob("*.yaml"):
            try:
                adlar[p.stem] = dunya_yukle(p).ad
            except Exception:
                adlar[p.stem] = f"{p.stem} (bozuk dosya)"
        return adlar

    def yeniden(self) -> dict:
        """Son sahneyi geri alıp aynı eylemle yeniden yazdırır."""
        with self.kilit:
            if self.motor is None or not self.motor.durum.sahneler:
                raise ValueError("Yeniden yazılacak sahne yok.")
            sahne = self.motor.yeniden_yaz()
            self._kaydet()
            self._manga_sahne(sahne)          # yeniden yazılan sahnenin panelleri de yenilenir
            return self._yanit(sahne)

    def durum(self) -> dict:
        """Sayfa yenilendiğinde oyunu kaldığı yerden göstermek için: tüm sahneler + özet."""
        with self.kilit:
            if self.motor is None:
                return {"oyun_var": False}
            return {"oyun_var": True, "sahneler": [self._sahne(s) for s in self.motor.durum.sahneler],
                    **self._durum_ozeti()}

    # ── Yanıt kurucular ──────────────────────────────────────────────────────

    def _harcamayi_guncelle(self) -> None:
        m = self.motor
        modeller = {"yazar": m.llm, "editor": m.editor_llm, "ozet": m.ozet_llm}
        for rol, (girdi, cikti) in m.son_kullanim.items():
            self.harcama["girdi"] += girdi
            self.harcama["cikti"] += cikti
            fiyat = FIYATLAR.get(_model_adi(modeller[rol]))
            if fiyat:
                self.harcama["dolar"] += girdi * fiyat[0] / 1e6 + cikti * fiyat[1] / 1e6
            elif girdi or cikti:
                self.harcama["bilinmiyor"] = True

    def _sahne(self, sahne) -> dict:
        return {
            "no": sahne.no,
            "mekan": self.motor.dunya.mekanlar[sahne.mekan].ad,
            "zaman": sahne.zaman,
            "eylem": sahne.eylem,
            "parcalar": parcalara_bol(sahne.metin),
            "secenekler": sahne.secenekler,
        }

    def _yanit(self, sahne) -> dict:
        self._harcamayi_guncelle()
        return {
            "sahne": self._sahne(sahne),
            "editor": self._editor_ozeti(),
            "uyarilar": [u for u in sahne.uyarilar if "düzeltildi" not in u],
            **self._durum_ozeti(),
        }

    def _durum_ozeti(self) -> dict:
        m = self.motor
        d, dunya = m.durum, m.dunya
        son_no = d.sahneler[-1].no if d.sahneler else 0
        return {
            "dunya": dunya.ad,
            "zaman": d.zaman,
            "mekan": dunya.mekanlar[d.mekan].ad,
            "taninan": [dunya.karakterler[k].ad for k in d.taninan if k in dunya.karakterler],
            "esyalar": d.esyalar,
            "akce": d.akce,
            "para_birimi": dunya.para_birimi,
            "acik_vaatler": [{"id": v.id, "metin": v.metin, "yas": son_no - v.acildigi_sahne + 1,
                              "ilerleme": len(v.ilerledigi_sahneler)} for v in d.acik_vaatler],
            "cozulen_vaatler": [{"id": v.id, "metin": v.metin, "sahne": v.cozuldugu_sahne}
                                for v in d.vaatler if not v.acik],
            "olgular": [o.metin for o in d.olgular[-12:]],
            "degisimler": [f"{dunya.karakterler[x.karakter].ad}: {x.degisim}"
                           for x in d.karakter_degisimleri[-6:] if x.karakter in dunya.karakterler],
            "sayac": {"sahne": son_no, "olgu": len(d.olgular), "celiski": len(d.celiskiler),
                      "sapma": len(d.karakter_sapmalari), "vaat": len(d.vaatler)},
            "harcama": {"girdi": self.harcama["girdi"], "cikti": self.harcama["cikti"],
                        "dolar": round(self.harcama["dolar"], 4),
                        "tam_degil": self.harcama["bilinmiyor"]},
            "ayar": {"bellek": m.bellek.strateji, "editor": m.editor.mod if m.editor else "yok",
                     "yazar": self.yazar, "model": m.llm.ad},
            "kimlik": self.kimlik,
            "manga": self.ayar.get("manga") or MANGA_KAPALI,
        }

    def _editor_ozeti(self) -> dict | None:
        b = self.motor.son_bulgular
        if b is None:
            return None
        dunya, d = self.motor.dunya, self.motor.durum
        olgu_metni = {o.id: o.metin for o in dunya.sabit_olgular} | {o.id: o.metin for o in d.olgular}
        ad = lambda k: "Oyuncu" if k == "oyuncu" else dunya.karakterler[k].ad   # noqa: E731
        karakter = [f"{ad(x['karakter'])} · {tur}: {x['gerekce']}"
                    for x in b["karakter_denetimi"]
                    for alan, tur in (("kisilik", "kişilik"), ("konusma", "konuşma"), ("bilgi", "bilgi sızıntısı"))
                    if x[alan] != "uygun"]
        if b["oyuncu_bilgi_sizintisi"]:
            karakter.append(f"Oyuncu · bilgi sızıntısı: {b['oyuncu_bilgi_sizintisi']}")
        return {
            "yeni_olgular": [i["metin"] for i in b["iddialar"] if i["durum"] == "yeni"],
            "celiskiler": [{"yazilan": i["metin"], "dogrusu": olgu_metni.get(i["olgu"], i["olgu"])}
                           for i in b["iddialar"] if i["durum"] == "celisiyor"],
            "karakter": karakter,
            "vaat_acilan": b["vaatler"]["acilan"],
            "vaat_ilerleyen": [f"{x['id']}: {x['kanit']}" for x in b["vaatler"]["ilerleyen"]],
            "vaat_cozulen": [f"{x['id']}: {x['kanit']}" for x in b["vaatler"]["cozulen"]],
            "zanaat_iyi": sum(z["sonuc"] == "iyi" for z in b["zanaat"]),
            "zanaat_toplam": len(b["zanaat"]),
            "zanaat_zayif": [z["ilke"] for z in b["zanaat"] if z["sonuc"] == "zayif"],
            "yazar_notu": b["yazar_notu"],
            "otomatik": {k: len(v) for k, v in b["otomatik"].items() if v},
        }


def isleyici_olustur(oturum: Oturum):
    class Isleyici(BaseHTTPRequestHandler):
        def do_GET(self):
            yol = urlsplit(self.path)
            if yol.path.startswith("/manga/"):
                return self._manga_dosyasi(yol.path)
            if yol.path == "/api/manga":
                try:
                    return self._json(200, oturum.manga_durumu(parse_qs(yol.query).get("kimlik", [None])[0]))
                except ValueError as e:
                    return self._json(400, {"hata": str(e)})
            if self.path in ("/", "/index.html"):
                self._gonder(200, (WEB_KLASORU / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/ayarlar":
                self._json(200, oturum.ayarlar())
            elif self.path == "/api/kayitlar":
                self._json(200, oturum.kayitli_oyunlar())
            elif self.path == "/api/durum":
                self._json(200, oturum.durum())
            else:
                self._json(404, {"hata": "Bulunamadı."})

        def do_POST(self):
            try:
                uzunluk = int(self.headers.get("Content-Length") or 0)
                govde = json.loads(self.rfile.read(uzunluk) or b"{}") if uzunluk else {}
                if self.path == "/api/yeni":
                    self._json(200, oturum.yeni(govde.get("dunya", "tuzhan"), govde.get("bellek", "tam"),
                                                govde.get("editor", "tam"), govde.get("yazar", "hizli"),
                                                govde.get("manga")))
                elif self.path == "/api/oyna":
                    self._json(200, oturum.oyna(govde.get("eylem", "")))
                elif self.path == "/api/yeniden":
                    self._json(200, oturum.yeniden())
                elif self.path == "/api/dunya":
                    self._json(200, oturum.dunya_kur(govde))
                elif self.path == "/api/devam":
                    self._json(200, oturum.devam(govde.get("kimlik", "")))
                elif self.path == "/api/kayit/sil":
                    self._json(200, oturum.kayit_sil(govde.get("kimlik", "")))
                elif self.path == "/api/dunya/taslak":
                    self._json(200, oturum.dunya_taslagi(govde))
                elif self.path == "/api/manga/ayar":
                    self._json(200, oturum.manga_ayarla(govde))
                elif self.path == "/api/manga/kayit":
                    self._json(200, oturum.manga_kayittan(govde.get("kimlik", ""), govde))
                elif self.path == "/api/manga/sayfalar":
                    self._json(200, oturum.manga_sayfalari(govde.get("kimlik", "")))
                else:
                    self._json(404, {"hata": "Bulunamadı."})
            except KurucuHatasi as e:
                self._json(400, {"hata": " ".join(e.hatalar), "hatalar": e.hatalar})
            except (ValueError, json.JSONDecodeError) as e:
                self._json(400, {"hata": str(e)})
            except YanitHatasi as e:
                self._json(502, {"hata": f"Model geçerli bir sahne üretemedi, tekrar dene. ({e})"})
            except Exception as e:                 # ağ hatası, API anahtarı vb.
                self._json(500, {"hata": f"{type(e).__name__}: {e}"})

        def _manga_dosyasi(self, yol: str) -> None:
            """/manga/<kimlik>/<dosya>.png ya da /manga/<kimlik>/ (sayfaların galerisi)."""
            parcalar = yol.split("/")[2:]
            kimlik = parcalar[0] if parcalar else ""
            dosya = parcalar[1] if len(parcalar) > 1 else ""
            if len(parcalar) > 2 or not KAYIT_KIMLIGI.match(kimlik) or (dosya and not MANGA_DOSYASI.match(dosya)):
                return self._json(404, {"hata": "Bulunamadı."})
            klasor = oturum.manga_klasoru / kimlik
            if dosya:
                if not (klasor / dosya).is_file():
                    return self._json(404, {"hata": "Bulunamadı."})
                return self._gonder(200, (klasor / dosya).read_bytes(), "image/png")
            sayfalar = sorted(klasor.glob("sayfa_*.png"))
            govde = "".join(f'<img src="{p.name}" alt="Sayfa {i}">' for i, p in enumerate(sayfalar, 1)) \
                or "<p>Henüz sayfa yok. Oyunlar penceresinden mangayı oluştur.</p>"
            self._gonder(200, ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                               "<title>Manga</title><style>body{margin:0;background:#2b2b2b;color:#eee;"
                               "font-family:sans-serif;text-align:center}img{display:block;max-width:min(100%,900px);"
                               "margin:16px auto;box-shadow:0 2px 12px #000}</style>" + govde).encode("utf-8"),
                       "text/html; charset=utf-8")

        def _json(self, kod: int, veri: dict) -> None:
            self._gonder(kod, json.dumps(veri, ensure_ascii=False).encode("utf-8"),
                         "application/json; charset=utf-8")

        def _gonder(self, kod: int, govde: bytes, tur: str) -> None:
            self.send_response(kod)
            self.send_header("Content-Type", tur)
            self.send_header("Content-Length", str(len(govde)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(govde)

        def log_message(self, *args):          # her isteği terminale basma
            pass

    return Isleyici


def calisiyor_mu(adres: str) -> bool:
    """Bu adreste Tuzhan sunucusu zaten yanıt veriyor mu?"""
    try:
        with urllib.request.urlopen(f"{adres}/api/ayarlar", timeout=1.5) as yanit:
            return "dunyalar" in json.loads(yanit.read())
    except (OSError, ValueError):
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Türkçe interaktif hikâye oyunu — web arayüzü")
    ap.add_argument("--host", default="127.0.0.1", help="Dinlenecek adres (varsayılan: yalnızca bu bilgisayar)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--llm", choices=["gemini", "yerel", "sahte"], default="gemini")
    ap.add_argument("--model", help="Yazar modelin adı")
    ap.add_argument("--tarayici-acma", action="store_true", help="Tarayıcıyı otomatik açma")
    args = ap.parse_args()

    adres = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    if calisiyor_mu(adres):
        # Windows aynı porta ikinci bir sunucunun bağlanmasına izin verebiliyor; o zaman
        # istekler rastgele birine gider. Zaten açıksa yenisini başlatma, sayfayı aç.
        print(f"Tuzhan zaten çalışıyor: {adres} — tarayıcıda açılıyor.")
        if not args.tarayici_acma:
            webbrowser.open(adres)
        return

    env_yukle(KOK / ".env")
    try:
        sunucu = ThreadingHTTPServer((args.host, args.port), isleyici_olustur(Oturum(args.llm, args.model)))
    except OSError as e:
        raise SystemExit(f"{args.port} portu açılamadı ({e}). Başka bir port dene: python web.py --port 8080")
    print(f"Tuzhan çalışıyor: {adres}   (durdurmak için Ctrl+C)")
    if args.host == "0.0.0.0":
        print("UYARI: aynı ağdaki herkes bu oyuna erişebilir ve senin API anahtarını kullanır.")
    if not args.tarayici_acma:
        webbrowser.open(adres)
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        print("\nKapatıldı.")


if __name__ == "__main__":
    main()
