"""Oyun saati (kod tutar), eylemin karşılanma denetimi ve konuşmasız sahne ölçümü. Ağ yok."""
import json
import tempfile
import unittest
from pathlib import Path

from hikaye.bellek import Bellek
from hikaye.dunya import dunya_yukle
from hikaye.editor import Editor, editor_yanit_coz
from hikaye.kayit import Kayitci
from hikaye.llm import LLMYanit, SahteLLM
from hikaye.motor import Motor
from hikaye.olcum import rapor
from hikaye.zaman import (EN_AZ_YOL, EN_UZUN_SAHNE, VARSAYILAN_SURE, etiket_dakika, sure_belirle,
                          sure_oku, vakit_adi, vakte_ilerlet)

KOK = Path(__file__).resolve().parent.parent
TUZHAN = dunya_yukle(KOK / "dunyalar" / "tuzhan.yaml")


class SaatTesti(unittest.TestCase):
    def test_vakitler_ve_gun_gecisi(self):
        saat = lambda g, s, d=0: (g - 1) * 1440 + s * 60 + d   # noqa: E731
        self.assertEqual(vakit_adi(saat(1, 4, 59)), "1. gün, gece")
        self.assertEqual(vakit_adi(saat(1, 5)), "1. gün, şafak")
        self.assertEqual(vakit_adi(saat(1, 18)), "1. gün, gün batımı")
        self.assertEqual(vakit_adi(saat(1, 23, 59)), "1. gün, gece")
        self.assertEqual(vakit_adi(saat(2, 0)), "2. gün, gece")           # gece yarısı gün geçer
        self.assertEqual(vakit_adi(saat(2, 8)), "2. gün, sabah")

    def test_etiket_cevirme(self):
        self.assertEqual(vakit_adi(etiket_dakika("1. gün, gün batımı")), "1. gün, gün batımı")
        self.assertEqual(vakit_adi(etiket_dakika("3. gün, öğleden sonra")), "3. gün, ikindi")
        self.assertEqual(vakit_adi(etiket_dakika("1. gün, vardiya başı")), "1. gün, sabah")   # tanınmayan
        self.assertEqual(vakit_adi(etiket_dakika("")), "1. gün, sabah")

    def test_anlatimdaki_vakte_ileri_sarma(self):
        gece = etiket_dakika("1. gün, akşam") + 500          # 2. gün 04.20: gece
        self.assertEqual(vakit_adi(gece), "2. gün, gece")
        self.assertEqual(vakit_adi(vakte_ilerlet(gece, "sabah")), "2. gün, sabah")   # "sabahın ilk ışıkları"
        self.assertEqual(vakte_ilerlet(gece, "gece"), gece)                         # zaten gece
        self.assertEqual(vakte_ilerlet(gece, "bilinmez"), gece)
        aksam = etiket_dakika("1. gün, akşam")
        self.assertEqual(vakit_adi(vakte_ilerlet(aksam, "sabah")), "2. gün, sabah")  # geri değil ileri

    def test_sure_kurallari(self):
        self.assertEqual(sure_oku("30"), 30)
        self.assertIsNone(sure_oku("bilinmiyor"))
        self.assertIsNone(sure_oku(-5))
        self.assertEqual(sure_belirle(None, False), VARSAYILAN_SURE)
        self.assertEqual(sure_belirle(2, True), EN_AZ_YOL)                   # yer değişti: en az yol
        self.assertEqual(sure_belirle(5000, False), EN_UZUN_SAHNE)
        self.assertEqual(sure_belirle(0, False), 1)                          # zaman hep ileri akar


def _motor(sure, eylem=None, editor="denetim", kayitci=None, karakterler=None):
    """Editör her sahnede verilen süreyi ve eylem değerlendirmesini bildirir."""
    sahte = SahteLLM(TUZHAN)

    class Model:
        ad = "sahte"

        def uret(self, sistem, kullanici, json_mod=True, sicaklik=0.8):
            yanit = sahte.uret(sistem, kullanici, json_mod, sicaklik)
            if "editörüsün" not in sistem:
                return yanit
            veri = json.loads(yanit.metin)
            veri["sahne_bilgisi"] = {"gecen_dakika": sure, "karakterler": karakterler or []}
            if eylem:
                veri["eylem"] = eylem
            return LLMYanit(metin=json.dumps(veri, ensure_ascii=False), sure=0.0)

    return Motor(TUZHAN, Model(), Bellek("son"), kayitci, editor=Editor(editor))


class MotorSaatiTesti(unittest.TestCase):
    def test_saat_ilerler_ve_gun_gecer(self):
        motor = _motor(240)                                   # her sahne 4 saat
        self.assertEqual(motor.durum.zaman, "1. gün, gün batımı")
        zamanlar = [motor.basla().zaman] + [motor.oyna("Bekle").zaman for _ in range(2)]
        self.assertEqual(zamanlar, ["1. gün, gece", "2. gün, gece", "2. gün, şafak"])

    def test_yeniden_yaz_saati_geri_alir(self):
        motor = _motor(60)
        motor.basla()
        motor.oyna("Bekle")
        once = motor.durum.dakika
        motor.yeniden_yaz()
        self.assertEqual(motor.durum.dakika, once)            # aynı süre: aynı yere gelir, iki kez eklenmez

    def test_eski_kayit_etiketten_baslar(self):
        motor = _motor(30)
        motor.basla()
        veri = json.loads(json.dumps(motor.kaydedilecek()))
        veri["durum"]["dakika"] = None
        veri["durum"]["zaman"] = "3. gün, sabah"
        yeni = _motor(30)
        yeni.yukle(veri)
        self.assertEqual(vakit_adi(yeni.durum.dakika), "3. gün, sabah")


class EylemDenetimiTesti(unittest.TestCase):
    def test_ayristirma(self):
        motor = _motor(5)
        motor.basla()
        oku = lambda e: editor_yanit_coz(json.dumps({"eylem": e}), TUZHAN, motor.durum)["eylem"]   # noqa: E731
        self.assertEqual(oku({"karsilandi": "kismen", "eksik": "Pusula sorusu cevapsız"}),
                         {"karsilandi": "kismen", "eksik": "Pusula sorusu cevapsız"})
        self.assertEqual(oku({"karsilandi": "evet", "eksik": "x"}), {"karsilandi": "evet", "eksik": ""})
        self.assertEqual(oku({"karsilandi": "belki"}), {"karsilandi": "evet", "eksik": ""})
        self.assertEqual(oku(None), {"karsilandi": "evet", "eksik": ""})

    def test_kismen_yalnizca_olcumde(self):
        motor = _motor(5, eylem={"karsilandi": "kismen", "eksik": "alakasız gerekçe"})
        motor.basla()
        motor.oyna("Pusulayı saklıyor musun?")
        self.assertNotIn("cevapsız kaldı", "\n".join(motor.editor.yazara_bolumler(TUZHAN, motor.durum)))
        self.assertEqual(motor.son_bulgular["eylem"]["karsilandi"], "kismen")

    def test_cevapsiz_eylem_yazara_bir_kez_not_olur(self):
        motor = _motor(5, eylem={"karsilandi": "hayir", "eksik": "Pusula sorusu cevapsız kaldı"})
        motor.basla()
        motor.oyna("Pusulayı saklıyor musun?")
        notlar = "\n".join(motor.editor.yazara_bolumler(TUZHAN, motor.durum))
        self.assertIn("cevapsız kaldı", notlar)
        self.assertIn("Pusulayı saklıyor musun?: Pusula sorusu cevapsız kaldı", notlar)

        tamam = _motor(5, eylem={"karsilandi": "evet"})
        tamam.basla()
        tamam.oyna("Selam ver")
        self.assertNotIn("cevapsız kaldı", "\n".join(tamam.editor.yazara_bolumler(TUZHAN, tamam.durum)))

    def test_yazara_eylem_hatirlatmasi_gider(self):
        istekler = []
        motor = _motor(5)
        asil = motor.llm.uret
        motor.llm.uret = lambda s, k, *a, **kw: (istekler.append(k), asil(s, k, *a, **kw))[1]
        motor.basla()
        motor.oyna("Kadına kervanı sor")
        yazar = next(k for k in istekler if "[OYUNCUNUN EYLEMİ]" in k)
        self.assertTrue(yazar.rstrip().endswith("vakit değişiyorsa ışığı ve sesleri buna göre anlat."))
        self.assertIn("eylem bir soruysa karşısındaki bu sahnede cevap versin", yazar)


class OlcumTesti(unittest.TestCase):
    def test_konusmasiz_sahne_ve_eylem_raporda(self):
        with tempfile.TemporaryDirectory() as g:
            kayitci = Kayitci(Path(g), meta={"dunya": TUZHAN.ad, "llm": "gemini:gemini-2.5-flash", "editor": "denetim"})
            motor = _motor(5, eylem={"karsilandi": "kismen", "eksik": "yarım"}, kayitci=kayitci,
                           karakterler=["oruc"])
            motor.basla()
            # Sahnede karakter var ama replik yok: ölçüm için uyarı (yazara ayrı not gider, uyarı gitmez)
            motor.llm_asil = motor.llm.uret
            motor.llm.uret = lambda s, k, *a, **kw: (
                LLMYanit(metin=json.dumps({"akis": [{"anlatim": "İkisi de sana dönüyor."}],
                                           "secenekler": ["Selam ver"]}, ensure_ascii=False), sure=0.0)
                if "editörüsün" not in s else motor.llm_asil(s, k, *a, **kw))
            motor.editor_llm = motor.llm
            sahne = motor.oyna("Demirhaneye gir")
            self.assertEqual(sahne.karakterler, ["oruc"])
            self.assertIn("sahnede karakter var ama kimse konuşmadı", sahne.uyarilar)
            notlar = "\n".join(motor.editor.yazara_bolumler(TUZHAN, motor.durum))
            self.assertNotIn("sahnede karakter var ama", notlar)      # ölçüm uyarısı yazara gitmez
            self.assertIn("hiç konuşmadı", notlar)                    # yazara giden eski not duruyor
            metin = rapor([kayitci.yol])
            self.assertIn("Oyuncunun eylemi karşılandı mı (editöre göre): kismen 1", metin)


if __name__ == "__main__":
    unittest.main()
