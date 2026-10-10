"""Manga: panel planı, görünüm etiketleri, görsel servisi istemcisi, sayfa dizme ve web akışı.
Ağ yok: sahte model, sahte görsel ve 127.0.0.1'de sahte görsel servisi."""
import io
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

import web
from hikaye import manga
from hikaye.dunya import dunya_yukle
from hikaye.durum import Replik, Sahne
from hikaye.llm import LLMYanit, SahteLLM

KOK = Path(__file__).resolve().parent.parent
TUZHAN = dunya_yukle(KOK / "dunyalar" / "tuzhan.yaml")
GORUNUM = {"dunya": "desert town", "karakterler": {"nehir": "1woman, braid", "tekin": "1boy, barefoot"},
           "mekanlar": {"han": "caravanserai"}}


def sahne(no=1):
    metin = ('Fırın soğuk.\nYalınayak çocuk: "Abi, körük kırıldı!"\n'
             'Yaşlı demirci: "Demir tavında dövülür."\nİri yapılı kadın: "Otur, evlat."')
    return Sahne(no=no, eylem="Demirhaneye gir", mekan="han", metin=metin, karakterler=["tekin", "oruc"],
                 replikler=[Replik("tekin", "Abi, körük kırıldı!"), Replik("oruc", "Demir tavında dövülür."),
                            Replik("nehir", "Otur, evlat.")], secenekler=[])


class SayacliLLM:
    def __init__(self, yanit: dict):
        self.ad = "sahte:sayacli"
        self.yanit = yanit
        self.cagri = 0

    def uret(self, sistem, kullanici, json_mod=True, sicaklik=0.8):
        self.cagri += 1
        return LLMYanit(metin=json.dumps(self.yanit), sure=0.0, girdi_token=100, cikti_token=20)


class PlanTesti(unittest.TestCase):
    def test_parcalar(self):
        p = manga.sahne_parcalari(sahne().metin)
        self.assertEqual([x["tur"] for x in p], ["anlatim", "replik", "replik", "replik"])
        self.assertEqual(p[1], {"tur": "replik", "konusan": "Yalınayak çocuk", "metin": "Abi, körük kırıldı!"})

    def test_plan_dogrulanir(self):
        s = sahne()
        ham = {"paneller": [
            {"kamera": "uzak", "karakterler": ["tekin", "olmayan"], "eylem_en": "shouting, sparks",
             "replikler": [0, 0, 9], "anlatim": "Fırın soğuk."},
            {"kamera": "yakin", "karakterler": [], "eylem_en": "Çocuk bağırıyor", "replikler": [1, 0]},
            {"kamera": "genis"}, {"kamera": "genis"}, {"kamera": "genis"},
        ]}
        paneller = manga.plani_coz(ham, s, TUZHAN, manga.sahne_parcalari(s.metin), GORUNUM)
        self.assertEqual(len(paneller), manga.EN_FAZLA_PANEL)                  # fazlası atılır
        a, b = paneller[0], paneller[1]
        self.assertEqual(a["kamera"], "orta")                                   # bilinmeyen kamera
        self.assertEqual(a["karakterler"], ["tekin"])                           # bilinmeyen karakter atılır
        self.assertEqual([r["metin"] for r in a["replikler"]], ["Abi, körük kırıldı!"])   # tekrar ve sınır dışı atılır
        self.assertIn("1boy, barefoot", a["prompt_en"])
        self.assertTrue(a["prompt_en"].endswith("medium shot"))
        self.assertEqual(b["karakterler"], ["oruc"])                            # konuşan panelde görünmeli
        self.assertNotIn("bağırıyor", b["prompt_en"])                           # Türkçe eylem atılır
        self.assertEqual(len(b["replikler"]), 1)                                # 0 zaten kullanıldı
        self.assertEqual((paneller[2]["genislik"], paneller[2]["yukseklik"]), manga.BOYUTLAR["genis"])
        self.assertIn("no humans", paneller[2]["prompt_en"])
        with self.assertRaises(ValueError):
            manga.plani_coz({"paneller": []}, s, TUZHAN, [], GORUNUM)

    def test_model_yoksa_ya_da_bozuksa_basit_plan(self):
        s = sahne()
        paneller, yanit = manga.sahne_plani(s, TUZHAN, GORUNUM, llm=None)
        self.assertIsNone(yanit)
        self.assertEqual(paneller[0]["kamera"], "genis")
        self.assertEqual([p["karakterler"] for p in paneller[1:]], [["tekin"], ["oruc"], ["nehir"]])
        bozuk = SayacliLLM({"yok": 1})
        self.assertEqual(len(manga.sahne_plani(s, TUZHAN, GORUNUM, llm=bozuk)[0]), 4)


class GorunumTesti(unittest.TestCase):
    def test_dosya_once_sonra_onbellek_sonra_model(self):
        with tempfile.TemporaryDirectory() as k:
            onbellek = Path(k) / "g.json"
            d = dunya_yukle(KOK / "dunyalar" / "tuzhan.yaml")
            d.karakterler["tekin"].gorunum = {}              # biri eksik
            llm = SayacliLLM({"dunya": "ignored", "karakterler": {"tekin": "1boy, sling", "nehir": "x"},
                              "mekanlar": {}})
            g = manga.gorunumleri_hazirla(d, llm, onbellek)
            self.assertEqual(g["karakterler"]["tekin"], "1boy, sling")
            self.assertEqual(g["karakterler"]["nehir"], d.karakterler["nehir"].gorunum["prompt_en"])   # dosya kazanır
            self.assertEqual(g["dunya"], d.gorsel_en)
            self.assertEqual(llm.cagri, 1)
            manga.gorunumleri_hazirla(d, llm, onbellek)       # önbellekten: yeniden sorulmaz
            self.assertEqual(llm.cagri, 1)

    def test_turkce_ya_da_cumle_reddedilir(self):
        self.assertTrue(manga._etiket_mi("1girl, short black hair, (smile:1.2)"))
        self.assertFalse(manga._etiket_mi("kısa saçlı kız"))
        self.assertFalse(manga._etiket_mi(""))

    def test_sahte_model_tum_dunyayi_tamamlar(self):
        d = dunya_yukle(KOK / "dunyalar" / "karinca_yolu.yaml")
        g = manga.gorunumleri_hazirla(d, SahteLLM(d), None)
        self.assertEqual(set(g["karakterler"]), set(d.karakterler))
        self.assertEqual(set(g["mekanlar"]), set(d.mekanlar))


def _png(w, h):
    t = io.BytesIO()
    Image.new("RGB", (w, h), "gray").save(t, "PNG")
    return t.getvalue()


class SayfaTesti(unittest.TestCase):
    def test_satirlar_okuma_sirasini_korur(self):
        k = lambda *x: [{"kamera": c, "i": i} for i, c in enumerate(x)]   # noqa: E731
        satirlar = manga._satirlar(k("genis", "orta", "genis", "orta", "orta", "yakin"))
        self.assertEqual([[p["i"] for p in s] for s in satirlar], [[0, 1], [2], [3, 4], [5]])

    def test_sayfa_ve_balonlar(self):
        paneller = [{"kamera": c, "replikler": [{"konusan": "x", "metin": "Iğdır'dan geldim, şükür! İyi akşamlar."}],
                     "anlatim": "Gün batıyor."} for c in ("genis", "orta", "yakin", "genis", "orta", "orta")]
        sayfalar = manga.sayfalari_diz(paneller, lambda p: Image.new("RGB", manga.BOYUTLAR[p["kamera"]], "gray"))
        self.assertGreaterEqual(len(sayfalar), 2)
        self.assertTrue(all(s.size == manga.SAYFA for s in sayfalar))
        self.assertTrue(all(p["sigmayan_balon"] == 0 for p in paneller))
        # balon beyaz, panel gri: balonun olduğu sol üst bölgede beyaz piksel var
        self.assertIn((255, 255, 255), [c for _, c in sayfalar[0].crop((80, 80, 500, 300)).getcolors(100000)])

    def test_uzun_metin_satirlara_bolunur(self):
        font = manga.yazi_tipi(30)
        satirlar = manga.satirlara_bol("bir iki üç dört beş altı yedi sekiz dokuz on " * 3, font, 200)
        self.assertGreater(len(satirlar), 3)
        self.assertTrue(all(font.getlength(s) <= 200 or " " not in s for s in satirlar))


class SahteServis(BaseHTTPRequestHandler):
    gelen: list = []

    def do_GET(self):
        self._yaz(200, json.dumps({"ok": True, "model": "x", "cihaz": "cuda"}).encode(), "application/json")

    def do_POST(self):
        govde = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SahteServis.gelen.append({"yetki": self.headers.get("Authorization"), **govde})
        if govde["prompt"] == "bozuk":
            return self._yaz(200, b"not a png", "image/png")
        if govde["prompt"] == "hata":
            return self._yaz(503, b"GPU yok", "text/plain")
        self._yaz(200, _png(govde["genislik"], govde["yukseklik"]), "image/png", seed="1234")

    def _yaz(self, kod, govde, tur, seed=None):
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        if seed:
            self.send_header("X-Seed", seed)
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def log_message(self, *a):
        pass


class ServisTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sunucu = ThreadingHTTPServer(("127.0.0.1", 0), SahteServis)
        cls.adres = f"http://127.0.0.1:{cls.sunucu.server_address[1]}"
        threading.Thread(target=cls.sunucu.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.shutdown()
        cls.sunucu.server_close()

    def test_istek_bicimi(self):
        s = manga.GorselServisi(self.adres, token="gizli", stil="renkli")
        self.assertTrue(s.saglik()["ok"])
        png, seed = s.ciz("1girl, smile", 832, 1216)
        self.assertEqual(seed, 1234)
        self.assertEqual(Image.open(io.BytesIO(png)).size, (832, 1216))
        g = SahteServis.gelen[-1]
        self.assertEqual(g["yetki"], "Bearer gizli")
        self.assertEqual((g["prompt"], g["stil"], g["genislik"], g["yukseklik"]), ("1girl, smile", "renkli", 832, 1216))

    def test_hatalar(self):
        s = manga.GorselServisi(self.adres)
        with self.assertRaises(manga.GorselHatasi):
            s.ciz("bozuk", 64, 64)
        with self.assertRaisesRegex(manga.GorselHatasi, "503"):
            s.ciz("hata", 64, 64)
        with self.assertRaises(manga.GorselHatasi):
            manga.GorselServisi("http://127.0.0.1:1").ciz("x", 64, 64)
        with self.assertRaises(ValueError):
            manga.GorselServisi(self.adres, stil="pastel")

    def test_adres_yoksa_anlasilir_hata(self):
        with self.assertRaisesRegex(ValueError, "MANGA_RUNPOD_ADRES"):
            manga.servis_olustur("runpod", "siyahbeyaz")


class WebMangaTesti(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        k = Path(self.gecici.name)
        self.oturum = web.Oturum("sahte", None, k / "oturumlar", oyun_klasoru=k / "kayitlar",
                                 manga_klasoru=k / "manga")

    def tearDown(self):
        self.oturum.manga.bekle()
        self.gecici.cleanup()

    def test_varsayilan_kapali(self):
        ilk = self.oturum.yeni("tuzhan", "son", "yok")
        self.assertFalse(ilk["manga"]["acik"])
        self.oturum.oyna(ilk["sahne"]["secenekler"][0])
        self.oturum.manga.bekle()
        self.assertEqual(self.oturum.manga_durumu()["sahneler"], {})
        self.assertFalse((Path(self.gecici.name) / "manga").exists())

    def test_oyun_sirasinda_cizer_ve_yeniden_yazinca_yeniler(self):
        ilk = self.oturum.yeni("tuzhan", "son", "yok", manga={"acik": True, "kaynak": "sahte", "stil": "renkli"})
        self.oturum.oyna(ilk["sahne"]["secenekler"][0])
        self.oturum.manga.bekle()
        m = self.oturum.manga_durumu()
        self.assertEqual(set(m["sahneler"]), {"1", "2"})
        self.assertTrue(all(d["durum"] == "hazir" and d["paneller"] for d in m["sahneler"].values()))
        self.assertEqual(m["harcama"]["gorsel"], sum(len(d["paneller"]) for d in m["sahneler"].values()))
        self.oturum.yeniden()
        self.oturum.manga.bekle()
        self.assertEqual(set(self.oturum.manga_durumu()["sahneler"]), {"1", "2"})
        sayfalar = self.oturum.manga_sayfalari(self.oturum.kimlik)["sayfalar"]
        self.assertTrue(sayfalar)

    def test_ayar_dogrulama_ve_sonradan_acma(self):
        with self.assertRaises(ValueError):
            self.oturum.yeni("tuzhan", "son", "yok", manga={"acik": True, "kaynak": "runpod"})   # adres yok
        with self.assertRaises(ValueError):
            self.oturum.yeni("tuzhan", "son", "yok", manga={"acik": True, "kaynak": "sahte", "stil": "pastel"})
        self.oturum.yeni("tuzhan", "son", "yok")
        m = self.oturum.manga_ayarla({"acik": True, "kaynak": "sahte"})
        self.assertTrue(m["manga"]["acik"])
        self.oturum.manga.bekle()
        self.assertEqual(self.oturum.manga_durumu()["sahneler"]["1"]["durum"], "hazir")   # son sahne çizildi

    def test_kayittan_manga_ve_devam(self):
        ilk = self.oturum.yeni("tuzhan", "son", "yok", manga={"acik": False, "kaynak": "sahte", "stil": "renkli"})
        self.oturum.oyna(ilk["sahne"]["secenekler"][0])
        kimlik = self.oturum.kimlik
        self.oturum.yeni("tuzhan", "son", "yok")                 # başka oyuna geç
        m = self.oturum.manga_kayittan(kimlik, {"kaynak": "sahte", "stil": "siyahbeyaz"})
        self.assertEqual(m["is"]["toplam"], 2)
        self.oturum.manga.bekle()
        m = self.oturum.manga_durumu(kimlik)
        self.assertEqual((m["is"]["durum"], m["is"]["biten"]), ("bitti", 2))
        self.assertTrue(m["sayfalar"])
        # ikinci kez: çizilmiş sahneler yeniden çizilmez
        self.assertEqual(self.oturum.manga_kayittan(kimlik, {"kaynak": "sahte"})["is"]["toplam"], 0)
        self.oturum.manga.bekle()
        # devam: oyunun manga ayarı geri gelir
        self.assertEqual(self.oturum.devam(kimlik)["manga"]["stil"], "renkli")

    def test_http_dosya_ve_galeri(self):
        self.oturum.yeni("tuzhan", "son", "yok", manga={"acik": True, "kaynak": "sahte"})
        self.oturum.manga.bekle()
        kimlik = self.oturum.kimlik
        self.oturum.manga_sayfalari(kimlik)
        sunucu = ThreadingHTTPServer(("127.0.0.1", 0), web.isleyici_olustur(self.oturum))
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        adres = f"http://127.0.0.1:{sunucu.server_address[1]}"
        try:
            def al(yol):
                try:
                    with urllib.request.urlopen(adres + yol, timeout=10) as y:
                        return y.status, y.headers.get("Content-Type"), y.read()
                except urllib.error.HTTPError as h:
                    return h.code, None, b""
            kod, tur, govde = al(f"/manga/{kimlik}/sayfa_01.png")
            self.assertEqual((kod, tur), (200, "image/png"))
            kod, tur, govde = al(f"/manga/{kimlik}/")
            self.assertEqual(kod, 200)
            self.assertIn(b'<img src="sayfa_01.png"', govde)
            kod, _, govde = al(f"/api/manga?kimlik={kimlik}")
            self.assertEqual(json.loads(govde)["sahneler"]["1"]["durum"], "hazir")
            for kotu in (f"/manga/{kimlik}/../../web.py", f"/manga/{kimlik}/paneller.json",
                         "/manga/..%2F..%2Fweb.py/x.png", f"/manga/{kimlik}/a/b.png", "/api/manga?kimlik=../x"):
                self.assertIn(al(kotu)[0], (400, 404), kotu)
        finally:
            sunucu.shutdown()
            sunucu.server_close()


if __name__ == "__main__":
    unittest.main()
