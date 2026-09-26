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
import json
import os
import threading
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from hikaye.bellek import STRATEJILER, Bellek
from hikaye.dunya import dunya_yukle
from hikaye.editor import MODLAR, Editor
from hikaye.kayit import Kayitci
from hikaye.llm import env_yukle, llm_olustur
from hikaye.motor import ETIKETLI_SATIR, Motor, YanitHatasi

KOK = Path(__file__).parent
WEB_KLASORU = KOK / "web"
DUNYA_KLASORU = KOK / "dunyalar"
EN_UZUN_EYLEM = 300

# Ücretli katman, metin, 1M token başına dolar (girdi, çıktı). Kaynak: ai.google.dev/gemini-api/docs/pricing
FIYATLAR = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-3.1-flash-lite": (0.25, 1.50),
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


class Oturum:
    """Sunucudaki tek oyun. Motor çağrıları saniyeler sürdüğü için kilitle korunur."""

    def __init__(self, llm_turu: str, model: str | None, kayit_klasoru: Path = KOK / "oturumlar"):
        self.llm_turu = llm_turu
        self.model = model
        self.kayit_klasoru = kayit_klasoru
        self.motor: Motor | None = None
        self.kilit = threading.Lock()
        self.harcama = {"girdi": 0, "cikti": 0, "dolar": 0.0, "bilinmiyor": False}

    def ayarlar(self) -> dict:
        return {
            "dunyalar": sorted(p.stem for p in DUNYA_KLASORU.glob("*.yaml")),
            "bellekler": list(STRATEJILER),
            "editorler": list(MODLAR),
            "varsayilan": {"dunya": "tuzhan", "bellek": "tam", "editor": "tam"},
            "llm": self.llm_turu,
            "oyun_var": self.motor is not None,
        }

    def yeni(self, dunya: str, bellek: str, editor: str) -> dict:
        if dunya not in self.ayarlar()["dunyalar"]:
            raise ValueError(f"Bilinmeyen dünya: {dunya}")
        if bellek not in STRATEJILER or editor not in MODLAR:
            raise ValueError("Geçersiz bellek ya da editör seçimi.")
        with self.kilit:
            d = dunya_yukle(DUNYA_KLASORU / f"{dunya}.yaml")
            llm = llm_olustur(self.llm_turu, dunya=d, model=self.model)
            editor_modeli, ozet_modeli = os.environ.get("EDITOR_MODEL"), os.environ.get("OZET_MODEL")
            editor_llm = llm_olustur(self.llm_turu, dunya=d, model=editor_modeli) if editor_modeli else llm
            ozet_llm = llm_olustur(self.llm_turu, dunya=d, model=ozet_modeli) if ozet_modeli else llm
            kayitci = Kayitci(self.kayit_klasoru, meta={
                "dunya": d.ad, "llm": llm.ad, "editor_llm": editor_llm.ad, "ozet_llm": ozet_llm.ad,
                "bellek": bellek, "editor": editor, "arayuz": "web",
            })
            self.motor = Motor(d, llm, Bellek(bellek), kayitci, editor=Editor(editor),
                               editor_llm=editor_llm, ozet_llm=ozet_llm)
            self.harcama = {"girdi": 0, "cikti": 0, "dolar": 0.0, "bilinmiyor": False}
            sahne = self.motor.basla()
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
                     "model": m.llm.ad},
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
            if self.path in ("/", "/index.html"):
                self._gonder(200, (WEB_KLASORU / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/ayarlar":
                self._json(200, oturum.ayarlar())
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
                                                govde.get("editor", "tam")))
                elif self.path == "/api/oyna":
                    self._json(200, oturum.oyna(govde.get("eylem", "")))
                else:
                    self._json(404, {"hata": "Bulunamadı."})
            except (ValueError, json.JSONDecodeError) as e:
                self._json(400, {"hata": str(e)})
            except YanitHatasi as e:
                self._json(502, {"hata": f"Model geçerli bir sahne üretemedi, tekrar dene. ({e})"})
            except Exception as e:                 # ağ hatası, API anahtarı vb.
                self._json(500, {"hata": f"{type(e).__name__}: {e}"})

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
