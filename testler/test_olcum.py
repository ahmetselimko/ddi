"""Ölçüm araçları: kayıttan durum kurma, rapor, enjeksiyon deneyi. Oyunun davranışını
değiştirmezler. Ağ yok: sahte model ve geçici klasörler."""
import tempfile
import unittest
from pathlib import Path

from hikaye.bellek import Bellek
from hikaye.dunya import dunya_yukle
from hikaye.editor import Editor
from hikaye.kayit import Kayitci
from hikaye.llm import SahteLLM, dolar
from hikaye.motor import Motor
from hikaye.olcum import (cumle_ekle, durumlari_kur, enjeksiyon, enjeksiyon_ozeti, gecerli_turlar,
                          kayit_oku, ornek_havuzu, rapor, uyari_turu)

KOK = Path(__file__).resolve().parent.parent
DUNYA_KLASORU = KOK / "dunyalar"
TUZHAN = dunya_yukle(DUNYA_KLASORU / "tuzhan.yaml")


class KayittanTesti(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.klasor = Path(self.gecici.name)
        llm = SahteLLM(TUZHAN)
        llm.ad = "gemini:gemini-2.5-flash"         # ölçüm sahte modelle yapılan denemeleri dışarıda bırakır
        kayitci = Kayitci(self.klasor, meta={"dunya": TUZHAN.ad, "llm": llm.ad, "editor": "tam", "bellek": "tam"})
        self.motor = Motor(TUZHAN, llm, Bellek("tam"), kayitci, editor=Editor("tam"))
        self.motor.basla()
        for _ in range(3):
            self.motor.oyna(self.motor.durum.sahneler[-1].secenekler[0])
        self.motor.yeniden_yaz()                                   # 4. sahne yeniden yazıldı
        self.yol = kayitci.yol

    def tearDown(self):
        self.gecici.cleanup()

    def test_geri_alinan_tur_atilir(self):
        turlar = gecerli_turlar(kayit_oku(self.yol))
        self.assertEqual([t["no"] for t in turlar], [1, 2, 3, 4])
        self.assertEqual(turlar[-1]["sahne"]["metin"], self.motor.durum.sahneler[-1].metin)

    def test_durumlar_editorun_gordugu_gibi_kurulur(self):
        kurulan = durumlari_kur(kayit_oku(self.yol), TUZHAN)
        self.assertEqual(len(kurulan), 4)
        _, d = kurulan[2]                                           # 3. sahnenin denetimi
        self.assertEqual([s.no for s in d.sahneler], [1, 2, 3])
        gercek = self.motor.durum
        self.assertEqual([o.id for o in d.olgular], [o.id for o in gercek.olgular if o.sahne_no < 3])
        self.assertEqual([v.id for v in d.vaatler], [v.id for v in gercek.vaatler if v.acildigi_sahne < 3])
        self.assertEqual(d.mekan, gercek.sahneler[1].mekan)        # sahneden önceki yer

    def test_rapor(self):
        metin = rapor([self.yol])
        self.assertIn("CED (10 bin sözcük başına)", metin)
        self.assertIn("| 1–10 |", metin)
        sahte = self.klasor / "sahte.jsonl"
        sahte.write_text(self.yol.read_text(encoding="utf-8").replace("gemini:gemini-2.5-flash", "sahte"),
                         encoding="utf-8")
        self.assertIn("bulunamadı", rapor([sahte]))

    def test_enjeksiyon_ve_onceki_cumleler(self):
        havuz = ornek_havuzu([self.yol], DUNYA_KLASORU)
        self.assertTrue(havuz)
        ilk = enjeksiyon(havuz, SahteLLM(TUZHAN), ornek=3, tohum=1)
        self.assertEqual(enjeksiyon_ozeti(ilk)["ornek"], len(ilk["ornekler"]))
        self.assertTrue(ilk["ornekler"][0].gevsek)                 # sahte editör her sahnede çelişki bulur
        # Aynı sahneler ve aynı cümlelerle tekrar (önce/sonra ya da koşudan koşuya oynama)
        hazir = {(o.oturum, o.sahne_no): (o.olgu, o.cumle) for o in ilk["ornekler"]}
        ikinci = enjeksiyon(havuz, SahteLLM(TUZHAN), ornek=3, tohum=1, hazir=hazir, editor_modu="denetim")
        self.assertEqual([(o.sahne_no, o.olgu, o.cumle) for o in ikinci["ornekler"]],
                         [(o.sahne_no, o.olgu, o.cumle) for o in ilk["ornekler"]])

    def test_uyari_turleri(self):
        self.assertEqual(uyari_turu("oyuncu adına replik yazıldı (atıldı): 'x'"), "oyuncu adına konuşma")
        self.assertEqual(uyari_turu("oyuncunun 3 parası var, 5 ödeyemez"), "eşya ve para")
        self.assertEqual(uyari_turu("bambaşka"), "diğer")


class YardimciTesti(unittest.TestCase):
    def test_cumle_ortadaki_anlatima_eklenir(self):
        metin = 'Bir.\nKadın: "Selam."\nİki.\nÜç.'
        self.assertEqual(cumle_ekle(metin, "EK."), 'Bir.\nKadın: "Selam."\nİki. EK.\nÜç.')

    def test_dolar(self):
        self.assertAlmostEqual(dolar("gemini:gemini-2.5-flash", 1_000_000, 0), 0.30)
        self.assertIsNone(dolar("sahte", 10, 10))


if __name__ == "__main__":
    unittest.main()
