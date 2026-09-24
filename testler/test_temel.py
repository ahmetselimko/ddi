"""Çalıştırmak için proje kökünden:  python -m unittest discover testler -v"""
import json
import tempfile
import unittest
from pathlib import Path

from hikaye.bellek import STRATEJILER, Bellek
from hikaye.dunya import DunyaHatasi, dunya_yukle
from hikaye.getirim import BM25, belirtecle, kucult
from hikaye.kayit import Kayitci
from hikaye.llm import LLMYanit, SahteLLM
from hikaye.motor import Motor, YanitHatasi, yanit_coz

KOK = Path(__file__).parent.parent
DUNYA_YOLU = KOK / "dunyalar" / "tuzhan.yaml"


def gecerli_yanit(**degisen) -> str:
    veri = {
        "sahne": "Nehir Hanım feneri kaldırıyor.",
        "mekan": "han",
        "karakterler": ["nehir"],
        "replikler": [{"karakter": "nehir", "metin": "Otur, evlat."}],
        "yeni_olgular": [],
        "secenekler": ["Otur", "Kervanı sor", "Odaya çık"],
    }
    veri.update(degisen)
    return json.dumps(veri, ensure_ascii=False)


class DunyaTesti(unittest.TestCase):
    def test_demo_dunya_yuklenir(self):
        dunya = dunya_yukle(DUNYA_YOLU)
        self.assertIn(dunya.baslangic_mekan, dunya.mekanlar)
        self.assertGreaterEqual(len(dunya.karakterler), 4)
        self.assertGreaterEqual(len(dunya.olgular), 10)

    def test_tanimsiz_id_reddedilir(self):
        bozuk = DUNYA_YOLU.read_text(encoding="utf-8").replace("ilgili: [kule]", "ilgili: [ejderha]")
        with tempfile.TemporaryDirectory() as klasor:
            yol = Path(klasor) / "bozuk.yaml"
            yol.write_text(bozuk, encoding="utf-8")
            with self.assertRaises(DunyaHatasi):
                dunya_yukle(yol)


class GetirimTesti(unittest.TestCase):
    def test_turkce_kucultme(self):
        self.assertEqual(kucult("IŞIK İzmir"), "ışık izmir")

    def test_kesme_eki_ve_f5_kok(self):
        self.assertEqual(belirtecle("Oruç'un demirhanesindeki körük"), ["oruç", "demir", "körük"])

    def test_bm25_ilgili_olguyu_bulur(self):
        dunya = dunya_yukle(DUNYA_YOLU)
        getirici = BM25([o.metin for o in dunya.olgular])
        en_iyi = getirici.en_iyiler("Yedi numaralı odanın anahtarı kimde?", k=1)
        self.assertEqual(dunya.olgular[en_iyi[0]].id, "o1")


class YanitCozmeTesti(unittest.TestCase):
    def setUp(self):
        self.dunya = dunya_yukle(DUNYA_YOLU)

    def test_kod_blogu_sarmali_acilir(self):
        cozum, uyarilar = yanit_coz("```json\n" + gecerli_yanit() + "\n```", self.dunya, "han")
        self.assertEqual(cozum["mekan"], "han")
        self.assertEqual(uyarilar, [])

    def test_bilinmeyen_idler_uyari_olur(self):
        metin = gecerli_yanit(mekan="saray", karakterler=["nehir", "vezir"])
        cozum, uyarilar = yanit_coz(metin, self.dunya, "demirhane")
        self.assertEqual(cozum["mekan"], "demirhane")       # önceki mekânda kalır
        self.assertEqual(cozum["karakterler"], ["nehir"])
        self.assertEqual(len(uyarilar), 2)

    def test_bos_sahne_hata(self):
        with self.assertRaises(YanitHatasi):
            yanit_coz(gecerli_yanit(sahne=""), self.dunya, "han")


class BellekTesti(unittest.TestCase):
    def test_eylemde_adi_gecen_karakter_kartla_gelir(self):
        dunya = dunya_yukle(DUNYA_YOLU)
        motor = Motor(dunya, SahteLLM(dunya), Bellek("son"))
        motor.basla()
        baglam = Bellek("son").baglam(dunya, motor.durum, "Oruç'a körüğü sor")
        self.assertIn("oruc", baglam.karakter_idleri)

    def test_taban_cizgisi_olgu_getirmez(self):
        dunya = dunya_yukle(DUNYA_YOLU)
        motor = Motor(dunya, SahteLLM(dunya), Bellek("son"))
        motor.basla()
        self.assertEqual(Bellek("son").baglam(dunya, motor.durum, "yedi numaralı oda").olgular, [])
        self.assertTrue(Bellek("kanon").baglam(dunya, motor.durum, "yedi numaralı oda").olgular)


class MotorTesti(unittest.TestCase):
    def test_her_strateji_uctan_uca_calisir(self):
        dunya = dunya_yukle(DUNYA_YOLU)
        for strateji in STRATEJILER:
            with self.subTest(strateji=strateji), tempfile.TemporaryDirectory() as klasor:
                kayitci = Kayitci(Path(klasor), meta={"bellek": strateji})
                motor = Motor(dunya, SahteLLM(dunya), Bellek(strateji), kayitci)
                sahne = motor.basla()
                for _ in range(4):
                    sahne = motor.oyna(sahne.secenekler[0])

                self.assertEqual(len(motor.durum.sahneler), 5)
                self.assertEqual(len(motor.durum.olgular), 5)
                self.assertEqual(bool(motor.durum.ozet), "ozet" in strateji)

                satirlar = kayitci.yol.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(satirlar), 1 + 5)      # meta + 5 tur
                son_tur = json.loads(satirlar[-1])
                self.assertEqual(son_tur["sahne"]["no"], 5)
                if "kanon" in strateji:
                    self.assertTrue(son_tur["baglam"]["olgu_idleri"])

    def test_gecersiz_yanitta_bir_kez_daha_dener(self):
        dunya = dunya_yukle(DUNYA_YOLU)

        class BirKezBozukLLM:
            ad = "bozuk"
            cagri = 0

            def uret(self, sistem, kullanici, json_mod=True, sicaklik=0.8):
                self.cagri += 1
                metin = "bu JSON değil" if self.cagri == 1 else gecerli_yanit()
                return LLMYanit(metin=metin, sure=0.0)

        llm = BirKezBozukLLM()
        sahne = Motor(dunya, llm, Bellek("son")).basla()
        self.assertEqual(sahne.no, 1)
        self.assertEqual(llm.cagri, 2)


if __name__ == "__main__":
    unittest.main()
