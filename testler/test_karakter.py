"""Karakter özellikleri: sabit alanlar (kart, doğrulama, dünya kurucu) ve oyun içinde değişen
durum (konum kodla, eşya/beden editörden ve kodla doğrulanmış). Ağ yok: sahte model."""
import json
import tempfile
import unittest
from pathlib import Path

import web
from hikaye.bellek import Bellek
from hikaye.dunya import DunyaHatasi, dunya_yukle
from hikaye.dunya_kurucu import cevaplardan_dunya
from hikaye.durum import KarakterDurumu, durum_yukle, karakter_degisimi_uygula
from hikaye.editor import Editor, editor_yanit_coz
from hikaye.llm import LLMYanit, SahteLLM
from hikaye.motor import Motor

KOK = Path(__file__).resolve().parent.parent
TUZHAN_YOLU = KOK / "dunyalar" / "tuzhan.yaml"
TUZHAN = dunya_yukle(TUZHAN_YOLU)


class SabitOzellikTesti(unittest.TestCase):
    def test_kart(self):
        kart = TUZHAN.karakterler["oruc"].kart(adlar=TUZHAN.karakter_adlari)
        self.assertIn("Görünüş: Kel, kısa beyaz sakal", kart)
        self.assertIn("Hedefi: Körüğü onarıp", kart)
        self.assertIn("Yapamadıkları", kart)
        self.assertIn("okuma yazma bilmez", kart)
        self.assertIn("İlişkileri: Tekin — Yeğeni", kart)          # id değil ad
        self.assertNotIn("prompt_en", kart)                         # İngilizce görsel etiket yazara gitmez

    def test_alanlarsiz_dunya_calisir(self):
        karinca = dunya_yukle(KOK / "dunyalar" / "karinca_yolu.yaml")
        k = next(iter(karinca.karakterler.values()))
        self.assertEqual((k.hedef, k.yapabilir, k.esyalar, k.iliskiler), ("", [], [], {}))
        self.assertNotIn("Hedefi", k.kart())

    def test_iliski_dogrulama(self):
        with tempfile.TemporaryDirectory() as g:
            yol = Path(g) / "bozuk.yaml"
            yol.write_text(TUZHAN_YOLU.read_text(encoding="utf-8").replace(
                "      tekin: Yaramaz ama iyi çocuk", "      hayalet: Yaramaz ama iyi çocuk", 1), encoding="utf-8")
            with self.assertRaisesRegex(DunyaHatasi, "hayalet"):
                dunya_yukle(yol)

    def test_kurucu_yeni_alanlari_esler(self):
        cevaplar = {
            "ad": "Sisli Liman", "tur": "Gizem", "ton": "Kasvetli",
            "oyuncu": {"kim": "Müfettiş", "neden": "Batan gemi", "esyalar": "defter", "para": 5},
            "sir": "Gemi neden battı?",
            "mekanlar": [{"ad": "Meyhane", "tanim": "Alçak tavanlı."}],
            "karakterler": [
                {"ad": "Meyhaneci Duru", "kisa_ad": "Duru", "kisilik": "Neşeli", "konusma": "Hızlı",
                 "hedef": "Borcu kapatmak", "yapabildikleri": "kavga ayırır, rom yapar",
                 "yapamadiklari": "yüzme bilmez", "esyalar": "depo anahtarı",
                 "iliskiler": "Kaptan Rıza: eski sevgilisi\nOlmayan Kişi: kimse"},
                {"ad": "Kaptan Rıza", "kisilik": "Sert", "konusma": "Kısa",
                 "iliskiler": "Duru: hâlâ borçlu olduğu kadın"},
            ],
            "gercekler": ["Gemi on iki gün önce battı."],
            "acilis": {"mekan": "Meyhane", "metin": "Kapıyı itiyorsun."},
        }
        sozluk = cevaplardan_dunya(cevaplar)
        duru, riza = sozluk["karakterler"]
        self.assertEqual(duru["hedef"], "Borcu kapatmak")
        self.assertEqual(duru["yapabilir"], ["kavga ayırır", "rom yapar"])
        self.assertEqual(duru["esyalar"], ["depo anahtarı"])
        self.assertEqual(duru["iliskiler"], {riza["id"]: "eski sevgilisi"})      # bulunamayan ad atıldı
        self.assertEqual(riza["iliskiler"], {duru["id"]: "hâlâ borçlu olduğu kadın"})   # kısa adla da bulunur
        self.assertNotIn("hedef", riza)
        self.assertEqual(sozluk["para_birimi"], "akçe")


class DegisenDurumTesti(unittest.TestCase):
    def test_baslangic_ve_eski_kayit(self):
        motor = Motor(TUZHAN, SahteLLM(TUZHAN), Bellek("son"))
        kd = motor.durum.karakter_durumlari["selvi"]
        self.assertEqual((kd.konum, kd.esyalar, kd.goruldugu_sahne), ("katiplik", ["boynunda sandık anahtarı", "kalem ve hokka"], 0))
        motor.basla()
        eski = json.loads(json.dumps(motor.kaydedilecek(), default=str))
        del eski["durum"]["karakter_durumlari"]                     # alan eklenmeden önceki kayıt
        yeni = Motor(TUZHAN, SahteLLM(TUZHAN), Bellek("son"))
        yeni.yukle(eski)
        self.assertEqual(set(yeni.durum.karakter_durumlari), set(TUZHAN.karakterler))

    def test_degisim_dogrulanir(self):
        motor = Motor(TUZHAN, SahteLLM(TUZHAN), Bellek("son"))
        d = motor.durum
        uyarilar = karakter_degisimi_uygula(d, [
            {"karakter": "oruc", "eklenen": ["pusula"], "cikan": ["maşa", "kılıç"], "beden": "sol eli yanık"},
        ], 3)
        kd = d.karakter_durumlari["oruc"]
        self.assertEqual(kd.esyalar, ["çekiç", "pusula"])
        self.assertEqual((kd.beden, kd.beden_sahnesi), ("sol eli yanık", 3))
        self.assertEqual(len(uyarilar), 1)
        self.assertTrue(uyarilar[0].startswith("karakter durumu reddedildi"))
        karakter_degisimi_uygula(d, [{"karakter": "oruc", "eklenen": [], "cikan": [], "beden": "iyi"}], 5)
        self.assertEqual(kd.beden, "")

    def test_oyuncu_ile_karakter_arasinda_devir(self):
        from hikaye.durum import devir_uygula, envanter_devirleri, envanter_oku, envanter_uygula
        motor = Motor(TUZHAN, SahteLLM(TUZHAN), Bellek("son"))
        d = motor.durum
        ham = {"cikan": [{"esya": "pusula", "kime": "nehir"}, {"esya": "kılıç", "kime": "nehir"}],
               "eklenen": [{"esya": "tuz taşı", "kimden": "tekin"}, {"esya": "x", "kimden": "hayalet"}]}
        self.assertEqual(envanter_oku(ham), {"eklenen": ["tuz taşı", "x"], "cikan": ["pusula", "kılıç"], "akce": 0})
        devirler = envanter_devirleri(ham, TUZHAN.karakterler)
        self.assertEqual(len(devirler), 3)                          # bilinmeyen karakter atıldı
        onceki = list(d.esyalar)
        envanter_uygula(d, envanter_oku(ham))                        # kılıç oyuncuda yok: çıkmaz
        uyarilar = devir_uygula(d, devirler, onceki)
        self.assertIn("pusula", d.karakter_durumlari["nehir"].esyalar)
        self.assertNotIn("kılıç", d.karakter_durumlari["nehir"].esyalar)
        self.assertEqual(len(uyarilar), 1)                           # oyuncudan çıkmayan kılıç reddedildi
        self.assertEqual(d.karakter_durumlari["tekin"].esyalar, [])  # tuz taşı oyuncuya geçti
        self.assertIn("tuz taşı", d.esyalar)

    def test_reddedilen_hediye_oyuncuda_kalir(self):
        from hikaye.durum import devir_uygula, envanter_devirleri
        motor = Motor(TUZHAN, SahteLLM(TUZHAN), Bellek("son"))
        d = motor.durum
        # editör yalnızca devri yazdı ama envanterden çıkarmadı (ör. kadın almayı reddetti)
        uyarilar = devir_uygula(d, envanter_devirleri({"cikan": [{"esya": "pusula", "kime": "nehir"}]},
                                                      TUZHAN.karakterler), list(d.esyalar))
        self.assertIn("pusula", d.esyalar)
        self.assertNotIn("pusula", d.karakter_durumlari["nehir"].esyalar)
        self.assertTrue(uyarilar)

    def test_editor_bildirimi_ayristirilir(self):
        motor = Motor(TUZHAN, SahteLLM(TUZHAN), Bellek("son"))
        motor.basla()
        b = editor_yanit_coz(json.dumps({"sahne_bilgisi": {"karakterler_degisen": [
            {"karakter": "nehir", "eklenen": ["pusula"], "beden": ""},
            {"karakter": "hayalet", "eklenen": ["x"]},
            {"karakter": "selvi"},                                 # boş bildirim
        ]}}), TUZHAN, motor.durum)
        self.assertEqual(b["sahne_bilgisi"]["karakterler_degisen"],
                         [{"karakter": "nehir", "eklenen": ["pusula"], "cikan": [], "beden": ""}])

    def _motor(self, degisen):
        """Sahte yazar + editör; editör her sahnede verilen karakter değişimini bildirir."""
        sahte = SahteLLM(TUZHAN)

        class Model:
            ad = "sahte"

            def uret(self, sistem, kullanici, json_mod=True, sicaklik=0.8):
                yanit = sahte.uret(sistem, kullanici, json_mod, sicaklik)
                if "editörüsün" not in sistem:
                    return yanit
                veri = json.loads(yanit.metin)
                veri["sahne_bilgisi"] = {"mekan": "demirhane", "karakterler": ["oruc"],
                                         "karakterler_degisen": degisen}
                return LLMYanit(metin=json.dumps(veri, ensure_ascii=False), sure=0.0)

        return Motor(TUZHAN, Model(), Bellek("son"), editor=Editor("denetim"))

    def test_turda_konum_kodla_esya_editorden(self):
        motor = self._motor([{"karakter": "oruc", "eklenen": ["yeni körük"], "cikan": ["kılıç"]}])
        sahne = motor.basla()
        kd = motor.durum.karakter_durumlari
        self.assertEqual((kd["oruc"].konum, kd["oruc"].goruldugu_sahne), ("demirhane", 1))
        gorulmeyen = next(k for k in TUZHAN.karakterler if k not in sahne.karakterler)
        self.assertEqual((kd[gorulmeyen].konum, kd[gorulmeyen].goruldugu_sahne),
                         (TUZHAN.karakterler[gorulmeyen].yer, 0))   # sahnede yoktu: yeri değişmez
        self.assertIn("yeni körük", kd["oruc"].esyalar)
        self.assertTrue(any(u.startswith("karakter durumu reddedildi") for u in sahne.uyarilar))
        # reddedilen bildirim yazara gitmez
        self.assertNotIn("reddedildi", "\n".join(motor.editor.yazara_bolumler(TUZHAN, motor.durum)))

    def test_yazara_su_an_satiri_gider_ve_yeniden_yaz_geri_alir(self):
        motor = self._motor([{"karakter": "oruc", "eklenen": [], "cikan": [], "beden": "elinde yanık"}])
        motor.basla()
        istekler = []
        asil = motor.llm.uret
        motor.llm.uret = lambda s, k, *a, **kw: (istekler.append(k), asil(s, k, *a, **kw))[1]
        motor.oyna("Demirhaneye git")
        yazar_istegi = next(k for k in istekler if "OYUNCUNUN EYLEMİ" in k)
        self.assertIn("[KARAKTERLERİN SON BİLİNEN DURUMU", yazar_istegi)
        self.assertIn("bedeni: elinde yanık (sahne 1)", yazar_istegi)
        self.assertEqual(motor.durum.karakter_durumlari["oruc"].goruldugu_sahne, 2)
        motor.yeniden_yaz()                                          # 2. sahne yeniden: durum geri alınıp tekrar
        self.assertEqual(motor.durum.karakter_durumlari["oruc"].goruldugu_sahne, 2)
        self.assertEqual(len(motor.durum.sahneler), 2)

    def test_kayit_dongusu(self):
        motor = self._motor([{"karakter": "oruc", "eklenen": ["yeni körük"], "cikan": []}])
        motor.basla()
        geri = durum_yukle(json.loads(json.dumps(motor.kaydedilecek()["durum"])))
        self.assertIsInstance(geri.karakter_durumlari["oruc"], KarakterDurumu)
        self.assertIn("yeni körük", geri.karakter_durumlari["oruc"].esyalar)


class PanelTesti(unittest.TestCase):
    def test_panelde_yalnizca_gorulenler_ve_spoiler_yok(self):
        with tempfile.TemporaryDirectory() as g:
            o = web.Oturum("sahte", None, Path(g), oyun_klasoru=Path(g) / "k", manga_klasoru=Path(g) / "m")
            ilk = o.yeni("tuzhan", "son", "yok")
            karakterler = ilk["karakterler"]
            gorulen = {k for s in o.motor.durum.sahneler for k in s.karakterler}
            self.assertEqual(len(karakterler), len(gorulen))
            for k in karakterler:
                self.assertEqual(set(k), {"ad", "konum", "goruldugu_sahne", "edindikleri", "beden", "tutum"})
                self.assertEqual(k["edindikleri"], [])               # başlangıç eşyaları gösterilmez
            metin = json.dumps(karakterler, ensure_ascii=False)
            for gizli in ("Hedefi", "sandık anahtarı", "mühürlü"):
                self.assertNotIn(gizli, metin)


if __name__ == "__main__":
    unittest.main()
