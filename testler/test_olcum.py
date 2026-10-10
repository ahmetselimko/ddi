"""Ölçüm (kayıttan durum kurma, rapor, enjeksiyon) ve araştırma önerileri: envanter önceliği,
bilen alanı, dünya kurucuda sırlar. Ağ yok: sahte model ve geçici klasörler."""
import json
import tempfile
import unittest
from pathlib import Path

from hikaye.bellek import Bellek
from hikaye.dunya import DunyaHatasi, dunya_yukle
from hikaye.dunya_kurucu import cevaplardan_dunya
from hikaye.durum import Durum, envanter_dogrula, envanter_esit, envanter_oku
from hikaye.editor import Editor, alinti_sahnede
from hikaye.kayit import Kayitci
from hikaye.llm import LLMYanit, SahteLLM
from hikaye.motor import Motor
from hikaye.olcum import (cumle_ekle, durumlari_kur, enjeksiyon, enjeksiyon_ozeti, gecerli_turlar,
                          kayit_oku, ornek_havuzu, rapor, uyari_turu)

KOK = Path(__file__).resolve().parent.parent
DUNYA_KLASORU = KOK / "dunyalar"
TUZHAN = dunya_yukle(DUNYA_KLASORU / "tuzhan.yaml")


def _gemini_gibi(llm):
    """Sahte model kayıtta gemini gibi görünsün: ölçüm sahte denemeleri dışarıda bırakır."""
    llm.ad = "gemini:gemini-2.5-flash"
    return llm


class KayittanTesti(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.klasor = Path(self.gecici.name)
        llm = _gemini_gibi(SahteLLM(TUZHAN))
        kayitci = Kayitci(self.klasor, meta={"dunya": TUZHAN.ad, "llm": llm.ad, "editor": "denetim", "bellek": "tam"})
        self.motor = Motor(TUZHAN, llm, Bellek("tam"), kayitci, editor=Editor("denetim"))
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
        t, d = kurulan[2]                                           # 3. sahnenin denetimi
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
        self.assertIn("bulunamadı", rapor([sahte]))                 # sahte denemeler ölçüme girmez

    def test_enjeksiyon_sahte_modelle(self):
        havuz = ornek_havuzu([self.yol], DUNYA_KLASORU)
        self.assertTrue(havuz)
        sonuc = enjeksiyon(havuz, SahteLLM(TUZHAN), ornek=3, tohum=1)
        ozet = enjeksiyon_ozeti(sonuc)
        self.assertEqual(ozet["ornek"], len(sonuc["ornekler"]))
        o = sonuc["ornekler"][0]
        self.assertTrue(o.cumle.startswith("Kervanda yalnızca iki deve"))
        self.assertTrue(o.gevsek)                                   # sahte editör her sahnede çelişki bulur

    def test_uyari_turleri(self):
        self.assertEqual(uyari_turu("oyuncu adına replik yazıldı (atıldı): 'x'"), "oyuncu adına konuşma")
        self.assertEqual(uyari_turu("oyuncunun 3 parası var, 5 ödeyemez"), "eşya ve para")
        self.assertEqual(uyari_turu("envanter uyuşmazlığı: yazar x / editör y"), "envanter uyuşmazlığı")
        self.assertEqual(uyari_turu("bambaşka"), "diğer")


class YardimciTesti(unittest.TestCase):
    def test_cumle_ortadaki_anlatima_eklenir(self):
        metin = 'Bir.\nKadın: "Selam."\nİki.\nÜç.'
        self.assertEqual(cumle_ekle(metin, "EK."), 'Bir.\nKadın: "Selam."\nİki. EK.\nÜç.')

    def test_alinti_sahnede(self):
        sahne = "Kapıyı itiyorsun. Yedi numaralı oda ardına kadar açık duruyor!\nKadın: \"Otur.\""
        self.assertTrue(alinti_sahnede("yedi numaralı oda ardına kadar açık duruyor", sahne))
        self.assertTrue(alinti_sahnede("Yedi numaralı oda ardına kadar açık duruyordu.", sahne))   # küçük fark
        self.assertFalse(alinti_sahnede("Yabancı kılıcını çekiyor.", sahne))
        self.assertFalse(alinti_sahnede("açık", sahne))                                          # çok kısa


class EnvanterTesti(unittest.TestCase):
    def test_dogrula_ve_esit(self):
        d = Durum(mekan="han", esyalar=["pusula", "boş harita defteri"], akce=5)
        self.assertEqual(envanter_dogrula(d, envanter_oku({"cikan": ["pusula"], "akce": -5})), [])
        hatalar = envanter_dogrula(d, envanter_oku({"cikan": ["kılıç"], "akce": -6}))
        self.assertEqual(len(hatalar), 2)
        self.assertEqual(d.esyalar, ["pusula", "boş harita defteri"])              # durum değişmedi
        self.assertTrue(envanter_esit(envanter_oku({"cikan": ["harita defteri"]}),
                                      envanter_oku({"cikan": ["boş harita defteri"]})))
        self.assertFalse(envanter_esit(envanter_oku({"akce": -1}), envanter_oku({})))

    def _motor(self, yanitlar_yazar, editor_envanteri):
        """Yazar sırayla verilen envanterleri bildirir; editör hep editor_envanteri'ni."""
        sahte = SahteLLM(TUZHAN)

        class Model:
            ad = "sahte"
            cagri = 0

            def uret(self, sistem, kullanici, json_mod=True, sicaklik=0.8):
                yanit = sahte.uret(sistem, kullanici, json_mod, sicaklik)
                veri = json.loads(yanit.metin)
                if "editörüsün" in sistem:
                    veri["sahne_bilgisi"] = {"envanter": editor_envanteri}
                elif "akis" in veri:
                    veri["envanter"] = yanitlar_yazar[min(Model.cagri, len(yanitlar_yazar) - 1)]
                    Model.cagri += 1
                return LLMYanit(metin=json.dumps(veri, ensure_ascii=False), sure=0.0)

        motor = Motor(TUZHAN, Model(), Bellek("son"), editor=Editor("denetim"))
        return motor, Model

    def test_yazar_once_gecersizse_yeniden_istenir(self):
        motor, model = self._motor([{"cikan": ["kılıç"]}, {"eklenen": ["ip"]}], {"eklenen": ["ip"]})
        motor.basla()
        self.assertEqual(model.cagri, 2)                                  # bir kez düzelttirildi
        self.assertIn("ip", motor.durum.esyalar)
        self.assertFalse(any("uyuşmazlığı" in u for u in motor.durum.sahneler[-1].uyarilar))

    def test_yazar_bildirmezse_editorunku_ve_uyusmazlik_kaydi(self):
        motor, _ = self._motor([{}], {"eklenen": ["anahtar"], "akce": -2})
        sahne = motor.basla()
        self.assertIn("anahtar", motor.durum.esyalar)
        self.assertEqual(motor.durum.akce, TUZHAN.oyuncu_akce - 2)
        self.assertTrue(any(u.startswith("envanter uyuşmazlığı") for u in sahne.uyarilar))
        # yazara gitmez (yalnızca ölçüm için)
        bolumler = "\n".join(motor.editor.yazara_bolumler(TUZHAN, motor.durum))
        self.assertNotIn("uyuşmazlığı", bolumler)

    def test_ikisi_farkliysa_yazarinki(self):
        motor, _ = self._motor([{"eklenen": ["ekmek"]}], {"eklenen": ["anahtar"]})
        motor.basla()
        self.assertIn("ekmek", motor.durum.esyalar)
        self.assertNotIn("anahtar", motor.durum.esyalar)


class BilenTesti(unittest.TestCase):
    def test_dogrulama(self):
        with tempfile.TemporaryDirectory() as k:
            metin = (DUNYA_KLASORU / "tuzhan.yaml").read_text(encoding="utf-8").replace(
                "bilen: [selvi]", "bilen: [selvi, hayalet]", 1)
            yol = Path(k) / "bozuk.yaml"
            yol.write_text(metin, encoding="utf-8")
            with self.assertRaisesRegex(DunyaHatasi, "hayalet"):
                dunya_yukle(yol)

    def test_baslangicta_oyuncunun_bildikleri(self):
        motor = Motor(TUZHAN, SahteLLM(TUZHAN), Bellek("son"))
        self.assertEqual(motor.durum.ogrenilen, ["o3"])

    def test_kurucuda_sirlari_yalniz_sahibi_bilir(self):
        cevaplar = {
            "ad": "Sisli Liman", "tur": "Gizem", "ton": "Kasvetli",
            "oyuncu": {"kim": "Müfettiş", "neden": "Batan gemi", "esyalar": "defter", "para": 5},
            "sir": "Gemi neden battı?",
            "mekanlar": [{"ad": "Meyhane", "tanim": "Alçak tavanlı."}],
            "karakterler": [{"ad": "Meyhaneci Duru", "kisa_ad": "Duru", "kisilik": "Neşeli",
                             "konusma": "Hızlı", "sir": "Kaptanı son gören o."}],
            "gercekler": ["Gemi on iki gün önce battı."],
            "acilis": {"mekan": "Meyhane", "metin": "Kapıyı itiyorsun."},
        }
        olgular = cevaplardan_dunya(cevaplar)["olgular"]
        self.assertNotIn("bilen", olgular[0])                      # gerçek: varsayılan herkes
        self.assertEqual(olgular[1]["bilen"], [olgular[1]["ilgili"][0]])


if __name__ == "__main__":
    unittest.main()
