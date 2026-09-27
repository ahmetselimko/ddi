"""Web arayüzünün sunucu tarafı. Ağ yerine sahte model; HTTP testi yalnızca 127.0.0.1'de."""
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import web

_GECICI = tempfile.TemporaryDirectory()      # testlerin oyun kayıtları gerçek oturumlar/'a yazılmasın
KAYIT = Path(_GECICI.name)


def tearDownModule():
    _GECICI.cleanup()


class ParcalaraBolTesti(unittest.TestCase):
    def test_anlatim_ve_replik_ayrilir(self):
        parcalar = web.parcalara_bol('Fener titriyor.\nİri yapılı kadın: "Otur, evlat."\n')
        self.assertEqual(parcalar, [
            {"tur": "anlatim", "metin": "Fener titriyor."},
            {"tur": "replik", "ad": "İri yapılı kadın", "metin": "Otur, evlat."},
        ])


class OturumTesti(unittest.TestCase):
    def setUp(self):
        self.oturum = web.Oturum("sahte", None, KAYIT, oyun_klasoru=KAYIT / "kayitlar")

    def test_yeni_oyun_ve_tur(self):
        ilk = self.oturum.yeni("tuzhan", "tam", "tam")
        self.assertEqual(ilk["sahne"]["no"], 1)
        self.assertTrue(ilk["sahne"]["secenekler"])
        self.assertIsNotNone(ilk["editor"])
        ikinci = self.oturum.oyna(ilk["sahne"]["secenekler"][0])
        self.assertEqual(ikinci["sahne"]["no"], 2)
        self.assertEqual(ikinci["sahne"]["eylem"], ilk["sahne"]["secenekler"][0])
        self.assertEqual(ikinci["sayac"]["sahne"], 2)
        self.assertEqual(len(self.oturum.durum()["sahneler"]), 2)

    def test_gecersiz_istekler(self):
        with self.assertRaises(ValueError):
            self.oturum.oyna("bir şey")                 # oyun başlamadı
        with self.assertRaises(ValueError):
            self.oturum.yeni("olmayan", "tam", "tam")
        self.oturum.yeni("tuzhan", "son", "yok")
        with self.assertRaises(ValueError):
            self.oturum.oyna("   ")
        with self.assertRaises(ValueError):
            self.oturum.oyna("x" * (web.EN_UZUN_EYLEM + 1))


class HttpTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sunucu = ThreadingHTTPServer(("127.0.0.1", 0), web.isleyici_olustur(web.Oturum("sahte", None, KAYIT, oyun_klasoru=KAYIT / "kayitlar")))
        cls.adres = f"http://127.0.0.1:{cls.sunucu.server_address[1]}"
        threading.Thread(target=cls.sunucu.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.shutdown()
        cls.sunucu.server_close()

    def _istek(self, yol, govde=None):
        veri = None if govde is None else json.dumps(govde).encode()
        istek = urllib.request.Request(self.adres + yol, data=veri, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(istek, timeout=10) as y:
                return y.status, y.read()
        except urllib.error.HTTPError as h:
            return h.code, h.read()

    def test_calisan_sunucu_algilanir(self):
        self.assertTrue(web.calisiyor_mu(self.adres))
        self.assertFalse(web.calisiyor_mu("http://127.0.0.1:1"))

    def test_sayfa_ve_api(self):
        kod, govde = self._istek("/")
        self.assertEqual(kod, 200)
        self.assertIn(b"<title>Tuzhan</title>", govde)

        kod, govde = self._istek("/api/ayarlar")
        self.assertEqual(kod, 200)
        self.assertIn("tuzhan", json.loads(govde)["dunyalar"])

        kod, govde = self._istek("/api/yeni", {"dunya": "tuzhan", "bellek": "tam", "editor": "denetim"})
        self.assertEqual(kod, 200)
        secenek = json.loads(govde)["sahne"]["secenekler"][0]

        kod, govde = self._istek("/api/oyna", {"eylem": secenek})
        self.assertEqual(kod, 200)
        self.assertEqual(json.loads(govde)["sahne"]["no"], 2)

        kod, govde = self._istek("/api/oyna", {"eylem": ""})
        self.assertEqual(kod, 400)
        self.assertIn("hata", json.loads(govde))

        kod, govde = self._istek("/api/yeniden", {})
        self.assertEqual(kod, 200)
        self.assertEqual(json.loads(govde)["sahne"]["no"], 2)          # 2. sahne yeniden yazıldı

        kod, govde = self._istek("/api/yeni", {"dunya": "tuzhan", "yazar": "olmayan"})
        self.assertEqual(kod, 400)


if __name__ == "__main__":
    unittest.main()


class KayitliOyunTesti(unittest.TestCase):
    """Her turdan sonra otomatik kayıt; sunucu yeniden açılsa da kaldığı yerden devam."""

    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.kok = Path(self.gecici.name)

    def tearDown(self):
        self.gecici.cleanup()

    def _oturum(self):
        return web.Oturum("sahte", None, self.kok / "oturumlar", oyun_klasoru=self.kok / "kayitlar")

    def test_kaydet_kapat_devam_et(self):
        birinci = self._oturum()
        ilk = birinci.yeni("tuzhan", "tam", "tam")
        ikinci = birinci.oyna(ilk["sahne"]["secenekler"][0])
        kimlik = birinci.kimlik

        # Sunucu kapandı, yenisi açıldı: kayıt listede
        yeni = self._oturum()
        liste = yeni.kayitli_oyunlar()["kayitlar"]
        self.assertEqual([(k["kimlik"], k["sahne"], k["dunya_ad"]) for k in liste], [(kimlik, 2, "Tuzhan")])

        devam = yeni.devam(kimlik)
        self.assertEqual(len(devam["sahneler"]), 2)
        self.assertEqual(devam["sahneler"][-1]["secenekler"], ikinci["sahne"]["secenekler"])
        self.assertEqual(devam["sayac"], ikinci["sayac"])                   # olgular, vaatler... aynı
        self.assertEqual(devam["harcama"], ikinci["harcama"])
        self.assertIsNotNone(devam["editor"])                               # son sahnenin bulguları da geri geldi

        ucuncu = yeni.oyna(devam["sahneler"][-1]["secenekler"][0])
        self.assertEqual(ucuncu["sahne"]["no"], 3)
        self.assertEqual(yeni.yeniden()["sahne"]["no"], 3)                 # yeniden yaz da çalışıyor
        # Tur kayıtları aynı dosyaya eklenmeye sürdü
        satirlar = [json.loads(s) for s in (self.kok / "oturumlar" / f"{kimlik}.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([s["tip"] for s in satirlar].count("devam"), 1)
        self.assertEqual(len(yeni.kayitli_oyunlar()["kayitlar"]), 1)

    def test_silme_ve_guvenlik(self):
        o = self._oturum()
        o.yeni("tuzhan", "son", "yok")
        eski = o.kimlik
        o.yeni("tuzhan", "son", "yok")
        with self.assertRaises(ValueError):
            o.kayit_sil(o.kimlik)                                          # oynanan silinemez
        self.assertEqual(len(o.kayit_sil(eski)["kayitlar"]), 1)
        with self.assertRaises(ValueError):
            o.devam("../../gizli")                                         # yol oyunu yok
        with self.assertRaises(ValueError):
            o.devam("olmayan_kayit")
