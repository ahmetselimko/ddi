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
        self.oturum = web.Oturum("sahte", None, KAYIT)

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
        cls.sunucu = ThreadingHTTPServer(("127.0.0.1", 0), web.isleyici_olustur(web.Oturum("sahte", None, KAYIT)))
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


if __name__ == "__main__":
    unittest.main()
