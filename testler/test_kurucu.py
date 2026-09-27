"""Dünya kurucu: oyuncunun cevaplarından oynanabilir dünya dosyası."""
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import web
from hikaye.bellek import Bellek
from hikaye.dunya import dunya_yukle
from hikaye.dunya_kurucu import (KurucuHatasi, cevaplardan_dunya, dunya_kaydet, ipuclari,
                                 karakter_ozel_adlari, kimlik_uret, mekan_kaliplari)
from hikaye.editor import Editor
from hikaye.llm import SahteLLM
from hikaye.motor import Motor, eylem_denetimi

KOK = Path(__file__).parent.parent


def ornek_cevaplar(**degisen) -> dict:
    """Bilimkurgu bir dünya: Tuzhan'dan bilerek farklı (para birimi, tür, adsız karakter)."""
    c = {
        "ad": "Yedinci Koloni",
        "tur": "Bilimkurgu",
        "ton": "Soğuk, gergin, yalnız",
        "donem": "Uzak gelecek; yapay çekim var ama ışıktan hızlı yolculuk yok",
        "yoklar": "Işınlanma yok\nUzaylılar yok",
        "para_birimi": "kredi",
        "oyuncu": {"kim": "Koloniye yeni atanan bir bakım teknisyeni", "neden": "Kaybolan ikmal gemisini araştırmak",
                   "esyalar": "el feneri, tamir çantası", "para": 40},
        "sir": "İkmal gemisi Aster'e ne oldu?\nKuzey kubbesindeki sinyal kimden geliyor?",
        "mekanlar": [
            {"ad": "Merkez Kubbe", "tanim": "Koloninin ortak yaşam alanı; yirmi iki ranza var."},
            {"ad": "Kuzey Kubbesi", "tanim": "Üç yıldır kapalı araştırma bölümü; kapısı mühürlü."},
        ],
        "karakterler": [
            {"ad": "Doktor Leyla Aras", "gorunus": "Kısa saçlı, gözlüklü, kırk yaşlarında bir kadın",
             "kisilik": "Soğukkanlı, her şeyi kayda geçirir", "konusma": "Kesin, teknik, kısa cümleler",
             "imza": "kayda geçtim", "sir": "Aster'in son mesajını gizliyor.", "yer": "Merkez Kubbe"},
            {"ad": "Gri Tulumlu", "adsiz": True, "gorunus": "Yüzü kasklı, hiç konuşmayan biri",
             "kisilik": "Sessiz", "konusma": "Neredeyse hiç konuşmaz", "yer": "Kuzey Kubbesi"},
        ],
        "gercekler": "Kuzey Kubbesi'nin kapısı üç yıldır mühürlü; şifreyi yalnızca Leyla biliyor.\n"
                     "Kolonide on dokuz kişi yaşıyor.",
        "acilis": {"mekan": "Merkez Kubbe", "zaman": "1. gün, vardiya başı",
                   "metin": "Hava kilidinden geçip Merkez Kubbe'ye adım atıyorsun."},
    }
    c.update(degisen)
    return c


class KurucuYardimcilariTesti(unittest.TestCase):
    def test_kimlik_turkce_ve_benzersiz(self):
        kullanilan = set()
        self.assertEqual(kimlik_uret("Kâtip Selvi", kullanilan), "katip_selvi")
        self.assertEqual(kimlik_uret("Kâtip Selvi", kullanilan), "katip_selvi_2")
        self.assertEqual(kimlik_uret("Işık Öğüt", set()), "isik_ogut")

    def test_ozel_ad_unvansiz(self):
        self.assertEqual(karakter_ozel_adlari("Nehir Hanım"), ["nehir"])
        self.assertEqual(karakter_ozel_adlari("Doktor Leyla Aras"), ["leyla", "aras"])
        self.assertEqual(karakter_ozel_adlari("Nehir Hanım", "Nehir'cik"), ["nehir'cik"])

    def test_mekan_kaliplari(self):
        self.assertIn("kule*", mekan_kaliplari("Yıkık Gözetleme Kulesi"))
        gol = mekan_kaliplari("Kuru Tuz Gölü")
        self.assertIn("göle", gol)
        self.assertNotIn("göl*", gol)                     # "gölge"yi yakalamasın
        # Paylaşılan kök yalnızca tam ad kalıbıyla eşleşir
        self.assertEqual(mekan_kaliplari("Merkez Kubbe", {"kubbe"}), ["merkez kubbe", "merkez*"])


class CevaplardanDunyaTesti(unittest.TestCase):
    def test_eksik_cevaplar_listelenir(self):
        with self.assertRaises(KurucuHatasi) as h:
            cevaplardan_dunya({"ad": "", "mekanlar": [], "karakterler": []})
        self.assertEqual(len(h.exception.hatalar), 5)

    def test_kurulan_dunya_oynanabilir(self):
        sozluk = cevaplardan_dunya(ornek_cevaplar())
        self.assertEqual(sozluk["kurucu"], "oyuncu")
        self.assertEqual(sozluk["baslangic_mekan"], "merkez_kubbe")
        leyla = next(k for k in sozluk["karakterler"] if k["id"] == "doktor_leyla_aras")
        self.assertEqual((leyla["yer"], leyla["imza"], leyla["gorunen_ad"]),
                         ("merkez_kubbe", ["kayda geçtim"], "Kısa saçlı"))
        gri = next(k for k in sozluk["karakterler"] if k["id"] == "gri_tulumlu")
        self.assertEqual(gri["adlar"], [])
        # Gerçeklerin ilgili bağlantıları metinden çıkarıldı; sır kanona girdi
        mühür = sozluk["olgular"][0]
        self.assertEqual(set(mühür["ilgili"]), {"kuzey_kubbesi", "doktor_leyla_aras"})
        self.assertTrue(any("Aster'in son mesajını" in o["metin"] and o["ilgili"] == ["doktor_leyla_aras"]
                            for o in sozluk["olgular"]))
        self.assertTrue(sozluk["kurallar"][0].startswith("Dönem ve teknoloji:"))

        with tempfile.TemporaryDirectory() as klasor:
            ad = dunya_kaydet(sozluk, Path(klasor))
            self.assertEqual(ad, "yedinci_koloni")
            dunya = dunya_yukle(Path(klasor) / f"{ad}.yaml")
            self.assertEqual(dunya.para_birimi, "kredi")
            motor = Motor(dunya, SahteLLM(dunya), Bellek("tam"), editor=Editor("denetim"))
            self.assertEqual([v.metin for v in motor.durum.acik_vaatler],
                             ["İkmal gemisi Aster'e ne oldu?", "Kuzey kubbesindeki sinyal kimden geliyor?"])
            motor.basla()
            self.assertEqual(len(motor.durum.sahneler), 1)
            # Para birimi dünyadan gelir
            notlar = eylem_denetimi("Ona 100 kredi veriyorum", motor.durum, dunya.para_birimi)
            self.assertTrue(any("40 kredi" in n for n in notlar))
            # Aynı ad ikinci kez kaydedilirse üzerine yazılmaz
            self.assertEqual(dunya_kaydet(sozluk, Path(klasor)), "yedinci_koloni_2")

    def test_ipuclari(self):
        sozluk = cevaplardan_dunya(ornek_cevaplar(gercekler="", yoklar="", donem="", sir=""))
        self.assertGreaterEqual(len(ipuclari(sozluk)), 3)


class TaslakUretTesti(unittest.TestCase):
    """Oyuncunun kısa fikrinden modelin kurduğu taslak."""

    def test_fikirden_taslak(self):
        from hikaye.dunya_kurucu import taslak_uret
        sonuc = taslak_uret({"tur": "Gizem", "fikir": "Sisli bir liman kasabası, batan bir gemi."}, SahteLLM())
        t = sonuc["taslak"]
        # Model listeleri döndürdü; sihirbazın metin kutuları için dizeye çevrildi
        self.assertEqual(t["yoklar"], "Büyü yok\nAteşli silah çok nadir ve pahalı")
        self.assertEqual(t["oyuncu"]["esyalar"], "not defteri, mühürlü mektup")
        self.assertEqual(t["karakterler"][0]["imza"], "tatlım")
        self.assertEqual(t["para_birimi"], "gümüş")               # para birimini model belirledi
        sozluk = cevaplardan_dunya(t)                              # kaydedilebilir
        self.assertEqual(sozluk["para_birimi"], "gümüş")

    def test_bos_fikir_ve_bozuk_yanit(self):
        from hikaye.dunya_kurucu import taslak_uret
        from hikaye.llm import LLMYanit
        with self.assertRaises(KurucuHatasi):
            taslak_uret({"fikir": "  "}, SahteLLM())

        class BirKezBozuk(SahteLLM):
            cagri = 0

            def uret(self, sistem, kullanici, json_mod=True, sicaklik=0.8):
                self.cagri += 1
                if self.cagri == 1:
                    return LLMYanit(metin='{"ad": "Yarım"}', sure=0.0)   # geçerli JSON, eksik dünya
                return super().uret(sistem, kullanici, json_mod, sicaklik)

        llm = BirKezBozuk()
        self.assertEqual(taslak_uret({"fikir": "Liman"}, llm)["taslak"]["ad"], "Sisli Liman")
        self.assertEqual(llm.cagri, 2)


class KurucuHttpTesti(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        klasor = Path(self.gecici.name)
        (klasor / "dunyalar").mkdir()
        (klasor / "dunyalar" / "tuzhan.yaml").write_text(
            (KOK / "dunyalar" / "tuzhan.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        oturum = web.Oturum("sahte", None, klasor / "oturumlar", klasor / "dunyalar")
        self.sunucu = ThreadingHTTPServer(("127.0.0.1", 0), web.isleyici_olustur(oturum))
        self.adres = f"http://127.0.0.1:{self.sunucu.server_address[1]}"
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()

    def tearDown(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()
        self.gecici.cleanup()

    def _istek(self, yol, govde=None):
        veri = None if govde is None else json.dumps(govde).encode()
        istek = urllib.request.Request(self.adres + yol, data=veri, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(istek, timeout=10) as y:
                return y.status, json.loads(y.read())
        except urllib.error.HTTPError as h:
            return h.code, json.loads(h.read())

    def test_dunya_kurup_oynamak(self):
        kod, v = self._istek("/api/dunya", ornek_cevaplar())
        self.assertEqual(kod, 200)
        self.assertEqual(v["dunya"], "yedinci_koloni")
        kod, ayarlar = self._istek("/api/ayarlar")
        self.assertEqual(ayarlar["dunya_adlari"]["yedinci_koloni"], "Yedinci Koloni")
        kod, oyun = self._istek("/api/yeni", {"dunya": "yedinci_koloni", "bellek": "tam", "editor": "tam"})
        self.assertEqual(kod, 200)
        self.assertEqual(oyun["para_birimi"], "kredi")
        # 2 başlangıç sorusu + sahte editörün açtığı 1 (sahte editör ayrıca birini çözer)
        self.assertEqual(oyun["sayac"]["vaat"], 3)
        self.assertEqual(len(oyun["acik_vaatler"]) + len(oyun["cozulen_vaatler"]), 3)

    def test_fikirden_taslak_sonra_kaydet(self):
        kod, v = self._istek("/api/dunya/taslak", {"tur": "Gizem", "fikir": "Sisli bir liman."})
        self.assertEqual(kod, 200)
        self.assertEqual(v["taslak"]["ad"], "Sisli Liman")
        kod, kayit = self._istek("/api/dunya", v["taslak"])
        self.assertEqual((kod, kayit["dunya"]), (200, "sisli_liman"))

    def test_eksik_cevap_400_ve_liste(self):
        kod, v = self._istek("/api/dunya", {"ad": "Yarım"})
        self.assertEqual(kod, 400)
        self.assertGreaterEqual(len(v["hatalar"]), 3)


if __name__ == "__main__":
    unittest.main()
