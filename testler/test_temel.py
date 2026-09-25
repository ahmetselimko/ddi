"""Çalıştırmak için proje kökünden:  python -m unittest discover testler -v"""
import json
import tempfile
import unittest
from pathlib import Path

from hikaye.bellek import STRATEJILER, Bellek
from hikaye.dunya import DunyaHatasi, dunya_yukle
from hikaye.editor import Editor, editor_yanit_coz, ilkeleri_yukle
from hikaye.getirim import BM25, belirtecle, kucult
from hikaye.istem import sistem_istemi
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


class IstemTesti(unittest.TestCase):
    def test_sistem_isteminde_tum_karakterlerin_tanimi_var(self):
        dunya = dunya_yukle(DUNYA_YOLU)
        sistem = sistem_istemi(dunya)
        for k in dunya.karakterler.values():
            self.assertIn(k.tanim, sistem)          # "iri yapılı" kart gelmese de bilinsin


class EditorTesti(unittest.TestCase):
    def setUp(self):
        self.dunya = dunya_yukle(DUNYA_YOLU)
        self.motor = Motor(self.dunya, SahteLLM(self.dunya), Bellek("son"))
        self.motor.basla()
        self.durum = self.motor.durum

    def test_ilke_dosyasi_gecerli(self):
        ilkeler = ilkeleri_yukle()
        self.assertTrue(all(i["kapsam"] in ("sahne", "hikaye") for i in ilkeler))
        self.assertTrue(all("soru" in i for i in ilkeler if i["kapsam"] == "sahne"))
        self.assertEqual(len({i["id"] for i in ilkeler}), len(ilkeler))

    def test_gecersiz_kayitlar_ayiklanir(self):
        self.durum.vaat_ac("Yedi numaralı odada ne var?", 1)
        metin = json.dumps({
            "iddialar": [
                {"metin": "Nehir zarif", "durum": "celisiyor", "olgu": "o99"},   # olgu yok → atılır
                {"metin": "Nehir iri", "durum": "biliniyor", "olgu": "o2"},
                {"metin": "?", "durum": "belki"},                                # geçersiz durum
            ],
            "vaatler": {"acilan": ["a", "b", "c"], "ilerleyen": ["v1", "v9"], "cozulen": []},
            "karakter_degisimleri": [{"karakter": "vezir", "degisim": "x"}],
        })
        b = editor_yanit_coz(metin, self.dunya, self.durum)
        self.assertEqual([i["metin"] for i in b["iddialar"]], ["Nehir iri"])
        self.assertEqual(b["vaatler"]["acilan"], ["a", "b"])                     # en fazla 2
        self.assertEqual(b["vaatler"]["ilerleyen"], ["v1"])
        self.assertEqual(b["karakter_degisimleri"], [])

    def test_bulgular_duruma_islenir(self):
        self.durum.vaat_ac("Yedi numaralı odada ne var?", 1)
        editor = Editor("tam", ilkeler=[])
        editor._uygula({
            "iddialar": [
                {"metin": "Selvi'nin gözleri ela", "durum": "yeni", "olgu": None, "ilgili": ["selvi"]},
                {"metin": "Nehir zarif", "durum": "celisiyor", "olgu": "o2", "ilgili": []},
            ],
            "vaatler": {"acilan": ["Yabancı kim?"], "ilerleyen": [], "cozulen": ["v1"]},
            "karakter_degisimleri": [{"karakter": "nehir", "degisim": "oyuncuya ısındı"}],
            "zanaat": [],
            "yazar_notu": "Tekin'i konuştur.",
        }, self.durum, 2)
        self.assertEqual(self.durum.olgular[-1].metin, "Selvi'nin gözleri ela")
        self.assertEqual(self.durum.celiskiler[0].olgu_id, "o2")
        self.assertEqual([v.metin for v in self.durum.acik_vaatler], ["Yabancı kim?"])
        self.assertEqual(self.durum.vaatler[0].cozuldugu_sahne, 2)
        self.assertEqual(self.durum.editor_notu, "Tekin'i konuştur.")

    def test_yazara_giden_bolumler(self):
        self.durum.vaat_ac("Yabancı kim?", 1)
        from hikaye.durum import Celiski
        self.durum.celiskiler.append(Celiski(sahne_no=1, iddia="Nehir zarif", olgu_id="o2"))
        self.durum.editor_notu = "Tekin'i konuştur."

        metin = "\n".join(Editor("tam", ilkeler=[]).yazara_bolumler(self.dunya, self.durum))
        self.assertIn("Yabancı kim?", metin)
        self.assertIn("üç parmak eksik", metin)         # çelişilen olgunun doğrusu
        self.assertIn("Tekin'i konuştur.", metin)

        denetim = "\n".join(Editor("denetim").yazara_bolumler(self.dunya, self.durum))
        self.assertNotIn("EDİTÖR NOTU", denetim)         # zanaat notu yalnızca tam modda


class EditorluMotorTesti(unittest.TestCase):
    def test_tam_editorle_uctan_uca(self):
        dunya = dunya_yukle(DUNYA_YOLU)
        with tempfile.TemporaryDirectory() as klasor:
            kayitci = Kayitci(Path(klasor), meta={"bellek": "ozet+kanon"})
            motor = Motor(dunya, SahteLLM(dunya), Bellek("ozet+kanon"), kayitci, editor=Editor("tam"))
            sahne = motor.basla()
            for _ in range(3):
                sahne = motor.oyna(sahne.secenekler[0])

            durum = motor.durum
            # Olgular editörden gelir (tur başına 1), yazarınkiler yok sayılır
            self.assertEqual([o.metin for o in durum.olgular],
                             [f"Sahte iddia {n}" for n in (2, 5, 8, 11)])
            self.assertEqual(len(durum.celiskiler), 4)
            self.assertEqual(len(durum.vaatler), 4)
            self.assertTrue(any(v.cozuldugu_sahne for v in durum.vaatler))
            self.assertTrue(durum.editor_notu)

            son = json.loads(kayitci.yol.read_text(encoding="utf-8").splitlines()[-1])
            self.assertGreater(son["baglam"]["editor_bolumleri"], 0)
            self.assertFalse(son["editor_basarisiz"])

    def test_editor_bozulursa_oyun_surer(self):
        dunya = dunya_yukle(DUNYA_YOLU)

        class EditoruBozukLLM(SahteLLM):
            def uret(self, sistem, kullanici, json_mod=True, sicaklik=0.8):
                if "editörüsün" in sistem:
                    return LLMYanit(metin="bozuk", sure=0.0)
                return super().uret(sistem, kullanici, json_mod, sicaklik)

        motor = Motor(dunya, EditoruBozukLLM(dunya), Bellek("son"), editor=Editor("denetim"))
        motor.basla()
        self.assertIsNone(motor.son_bulgular)
        self.assertEqual(len(motor.durum.olgular), 1)       # yazarın olgusuna geri düşer


if __name__ == "__main__":
    unittest.main()
