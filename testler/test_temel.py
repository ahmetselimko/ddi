"""Çalıştırmak için proje kökünden:  python -m unittest discover testler -v"""
import json
import tempfile
import unittest
from pathlib import Path

from hikaye.bellek import STRATEJILER, Bellek
from hikaye.dunya import DunyaHatasi, dunya_yukle
from hikaye.editor import Editor, editor_yanit_coz, ilkeleri_yukle
from hikaye.getirim import BM25, belirtecle, kucult, ortusme
from hikaye.istem import sistem_istemi
from hikaye.kayit import Kayitci
from hikaye.llm import LLMYanit, SahteLLM
from hikaye.motor import Motor, YanitHatasi, tekrar_secenekleri_ayikla, yanit_coz

KOK = Path(__file__).parent.parent
DUNYA_YOLU = KOK / "dunyalar" / "tuzhan.yaml"


def gecerli_yanit(**degisen) -> str:
    veri = {
        "akis": [
            {"anlatim": "Kadın feneri kaldırıyor."},
            {"konusan": "nehir", "replik": "Otur, evlat."},
        ],
        "mekan": "han",
        "karakterler": ["nehir"],
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

    def test_tekrarlanan_sozcukler_kok_duzeyinde(self):
        from hikaye.getirim import tekrarlanan_sozcukler
        metinler = ["Fenerin ışığı titriyor.", "Feneri kaldırıyor.", "Fener sönüyor.",
                    "Elindeki feneri bırakıyor.", "Kadın seni süzüyor."]
        self.assertEqual(tekrarlanan_sozcukler(metinler, esik=4), [("feneri", 4)])
        self.assertEqual(tekrarlanan_sozcukler(metinler, esik=4, haric={"fener"}), [])

    def test_ortusme_ayni_bilgiyi_farkli_sozle_yakalar(self):
        kanon = "Kervanlar normalde her on günde bir Tuzhan'a uğrar; kırk gündür tek bir kervan gelmedi."
        self.assertGreaterEqual(ortusme("Kırk gündür Tuzhan'a hiç kervan uğramadı.", kanon), 0.6)
        self.assertLess(ortusme("Selvi'nin gözleri ela.", kanon), 0.2)

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

    def test_bos_akis_hata(self):
        with self.assertRaises(YanitHatasi):
            yanit_coz(gecerli_yanit(akis=[]), self.dunya, "han")

    def test_replikler_sahneye_girer_oyuncu_replikleri_atilir(self):
        metin = gecerli_yanit(akis=[
            {"anlatim": "Fener titriyor."},
            {"konusan": "oyuncu", "replik": "Kervanı arıyorum."},
            {"konusan": "nehir", "replik": "\"Otur, evlat.\""},
        ])
        cozum, uyarilar = yanit_coz(metin, self.dunya, "han", taninan=["nehir"])
        self.assertEqual(cozum["sahne"], 'Fener titriyor.\nNehir Hanım: "Otur, evlat."')
        self.assertEqual([(r.karakter, r.metin) for r in cozum["replikler"]], [("nehir", "Otur, evlat.")])
        self.assertTrue(uyarilar[0].startswith("oyuncu adına replik"))

    def test_tanismadan_once_gorunus_sonra_ad(self):
        metin = gecerli_yanit(akis=[
            {"konusan": "nehir", "replik": "Ben Nehir, bu hanın sahibiyim."},
            {"anlatim": "Bir yabancı daha geldi mi diye kapıya bakıyor."},   # sıradan kelime, Yabancı değil
            {"konusan": "nehir", "replik": "Otur."},
        ])
        cozum, _ = yanit_coz(metin, self.dunya, "han")
        self.assertTrue(cozum["sahne"].startswith('İri yapılı kadın: "Ben Nehir'))
        self.assertTrue(cozum["sahne"].endswith('Nehir Hanım: "Otur."'))
        self.assertEqual(cozum["taninan"], ["nehir"])

    def test_anlatimda_ad_tanisma_sayilmaz_uyari_uretir(self):
        metin = gecerli_yanit(akis=[{"anlatim": "Nehir Hanım feneri kaldırıyor."},
                                    {"konusan": "nehir", "replik": "Otur."}],
                              secenekler=["Selvi'yi bul", "Otur"])
        cozum, uyarilar = yanit_coz(metin, self.dunya, "han")
        self.assertEqual(cozum["taninan"], [])
        self.assertIn('İri yapılı kadın: "Otur."', cozum["sahne"])
        self.assertEqual(len([u for u in uyarilar if "adıyla andı" in u]), 2)   # anlatım + seçenek

    def test_anlatimda_tanitma_tanisma_sayilir(self):
        metin = gecerli_yanit(akis=[{"anlatim": "Kadın, adını Nehir olarak tanıtıyor."},
                                    {"konusan": "nehir", "replik": "Otur."},
                                    {"anlatim": "Nehir Hanım feneri bırakıyor."}])
        cozum, uyarilar = yanit_coz(metin, self.dunya, "han")
        self.assertEqual(cozum["taninan"], ["nehir"])
        self.assertIn('Nehir Hanım: "Otur."', cozum["sahne"])
        self.assertEqual([u for u in uyarilar if "adıyla andı" in u], [])

    def test_yazarin_bildirdigi_tanisma(self):
        metin = gecerli_yanit(akis=[{"anlatim": "Nehir Hanım başını sallıyor."},
                                    {"konusan": "nehir", "replik": "Otur."}],
                              tanisilan=["nehir", "vezir"])
        cozum, uyarilar = yanit_coz(metin, self.dunya, "han")
        self.assertEqual(cozum["taninan"], ["nehir"])
        self.assertEqual([u for u in uyarilar if "adıyla andı" in u], [])

    def test_yazarin_bildirimi_ad_gecmeden_yetmez(self):
        metin = gecerli_yanit(akis=[{"anlatim": "Kadın başını sallıyor."},
                                    {"konusan": "nehir", "replik": "Otur."}], tanisilan=["nehir"])
        cozum, _ = yanit_coz(metin, self.dunya, "han")
        self.assertEqual(cozum["taninan"], [])
        self.assertIn('İri yapılı kadın: "Otur."', cozum["sahne"])

    def test_envanter_okunur(self):
        cozum, _ = yanit_coz(gecerli_yanit(envanter={"eklenen": ["anahtar"], "cikan": [], "akce": "-5"}),
                             self.dunya, "han")
        self.assertEqual(cozum["envanter"], {"eklenen": ["anahtar"], "cikan": [], "akce": -5})
        cozum, _ = yanit_coz(gecerli_yanit(), self.dunya, "han")
        self.assertEqual(cozum["envanter"], {"eklenen": [], "cikan": [], "akce": 0})

    def test_ayni_uyari_bir_kez(self):
        metin = gecerli_yanit(akis=[{"anlatim": "Selvi'yi düşünüyorsun."}, {"anlatim": "Selvi uzakta."},
                                    {"konusan": "nehir", "replik": "Otur."}])
        _, uyarilar = yanit_coz(metin, self.dunya, "han")
        self.assertEqual(len([u for u in uyarilar if "Kâtip Selvi" in u]), 1)

    def test_onceki_sahneden_tekrar_atilir(self):
        onceki = 'Kadın bardağını masaya bırakıyor, ses avluda yankılanıyor.\nİri yapılı kadın: "Adını bile söylemedi, evlat."'
        metin = gecerli_yanit(akis=[
            {"anlatim": "Kadın bardağını masaya bırakıyor, ses avluda yankılanıyor."},
            {"konusan": "nehir", "replik": "Adını bile söylemedi, evlat."},
            {"anlatim": "Sonra sesini alçaltıyor."},
            {"konusan": "nehir", "replik": "Yedi numaralı odaya takıldı."},
        ])
        cozum, uyarilar = yanit_coz(metin, self.dunya, "han", onceki_metin=onceki)
        self.assertEqual(cozum["sahne"], 'Sonra sesini alçaltıyor.\nİri yapılı kadın: "Yedi numaralı odaya takıldı."')
        self.assertEqual(len([u for u in uyarilar if "tekrarlanan" in u]), 2)

    def test_ornek_replik_kopyasi_yakalanir(self):
        metin = gecerli_yanit(akis=[{"konusan": "selvi",
                                     "replik": "Usulen önce adınızı yazmam gerekiyor; kuraldır, kusura bakmayın."}])
        _, uyarilar = yanit_coz(metin, self.dunya, "katiplik")
        self.assertIn("örnek replik aynen kullanıldı: selvi", uyarilar)

    def test_tekrar_eden_secenek_ayiklanir(self):
        gecmis = ["Kervan aradığını söyle", "Çevreyi incele"]
        secenekler, uyarilar = tekrar_secenekleri_ayikla(
            ["Kervan aradığını söyle", "Selvi'yi bulmaya git", "Ahıra bak"], gecmis)
        self.assertEqual(secenekler, ["Selvi'yi bulmaya git", "Ahıra bak"])
        self.assertEqual(len(uyarilar), 1)
        # ikiden az seçenek kalacaksa dokunma, ama uyar
        secenekler, uyarilar = tekrar_secenekleri_ayikla(["Kervan aradığını söyle", "Ahıra bak"], gecmis)
        self.assertEqual(len(secenekler), 2)
        self.assertEqual(len(uyarilar), 1)

    def test_zaman_okunur(self):
        cozum, _ = yanit_coz(gecerli_yanit(zaman="1. gün, gece"), self.dunya, "han")
        self.assertEqual(cozum["zaman"], "1. gün, gece")

    def test_bilinmeyen_konusan_uyari(self):
        metin = gecerli_yanit(akis=[{"konusan": "vezir", "replik": "Selam."}])
        cozum, uyarilar = yanit_coz(metin, self.dunya, "han")
        self.assertIn('vezir: "Selam."', cozum["sahne"])
        self.assertEqual(cozum["replikler"], [])
        self.assertEqual(len(uyarilar), 1)

    def test_konusan_yazim_kaymasi_duzeltilir(self):
        metin = gecerli_yanit(akis=[{"konusan": "tekine", "replik": "Abi!"},
                                    {"konusan": "Nehir Hanım", "replik": "Otur."}])
        cozum, uyarilar = yanit_coz(metin, self.dunya, "han", taninan=["tekin", "nehir"])
        self.assertEqual([r.karakter for r in cozum["replikler"]], ["tekin", "nehir"])
        self.assertIn('Tekin: "Abi!"', cozum["sahne"])
        self.assertEqual(len(uyarilar), 2)              # düzeltmeler yine de kayda geçer

    def test_eski_duz_metin_bicimi_kabul_edilir(self):
        veri = json.loads(gecerli_yanit())
        del veri["akis"]
        veri["sahne"] = "Düz metin."
        cozum, uyarilar = yanit_coz(json.dumps(veri), self.dunya, "han")
        self.assertEqual(cozum["sahne"], "Düz metin.")
        self.assertEqual(len(uyarilar), 1)


class BellekTesti(unittest.TestCase):
    def test_eylemde_adi_gecen_karakter_kartla_gelir(self):
        dunya = dunya_yukle(DUNYA_YOLU)
        motor = Motor(dunya, SahteLLM(dunya), Bellek("son"))
        motor.basla()
        baglam = Bellek("son").baglam(dunya, motor.durum, "Oruç'a körüğü sor")
        self.assertIn("oruc", baglam.karakter_idleri)

    def test_tam_bellek_tum_sahneleri_verir(self):
        dunya = dunya_yukle(DUNYA_YOLU)
        motor = Motor(dunya, SahteLLM(dunya), Bellek("tam"))
        sahne = motor.basla()
        for _ in range(4):
            sahne = motor.oyna(sahne.secenekler[0])
        baglam = Bellek("tam").baglam(dunya, motor.durum, "yedi numaralı oda")
        self.assertEqual(len(baglam.son_sahneler), 5)
        self.assertTrue(baglam.olgular)
        self.assertEqual(len(Bellek("son").baglam(dunya, motor.durum, "x").son_sahneler), 2)

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

    def test_dunya_kurallari_ve_uzerindekiler(self):
        dunya = dunya_yukle(DUNYA_YOLU)
        self.assertEqual(dunya.kurallar[0].id, "k1")
        self.assertIn("ateşli silah", sistem_istemi(dunya))
        motor = Motor(dunya, SahteLLM(dunya), Bellek("tam"))
        motor.basla()
        from hikaye.istem import sahne_istemi
        baglam = Bellek("tam").baglam(dunya, motor.durum, "silahını çek")
        metin = sahne_istemi(dunya, baglam, "silahını çek", ek=["[EDİTÖR NOTU]\nnot"],
                             esyalar=motor.durum.esyalar, akce=motor.durum.akce)
        self.assertIn("[OYUNCUNUN ÜZERİNDEKİLER] pusula, boş harita defteri · 15 akçe", metin)
        # Editör notu geçmiş sahnelerden SONRA, eylemin hemen önünde (yazarın en son okuduğu yer)
        self.assertLess(metin.index("[ÖNCEKİ SAHNELER]"), metin.index("[EDİTÖR NOTU]"))
        self.assertLess(metin.index("[EDİTÖR NOTU]"), metin.index("[OYUNCUNUN EYLEMİ]"))


class EnvanterTesti(unittest.TestCase):
    def test_esya_ve_akce_islenir(self):
        from hikaye.durum import Durum
        from hikaye.motor import envanter_uygula
        durum = Durum(mekan="han", esyalar=["pusula", "boş harita defteri"], akce=15)
        uyarilar = envanter_uygula(durum, {"eklenen": ["yedi numaranın anahtarı"],
                                           "cikan": ["pusulanı"], "akce": -5})
        self.assertEqual(uyarilar, [])
        self.assertEqual(durum.esyalar, ["boş harita defteri", "yedi numaranın anahtarı"])
        self.assertEqual(durum.akce, 10)

    def test_olmayan_esya_ve_yetmeyen_akce(self):
        from hikaye.durum import Durum
        from hikaye.motor import envanter_uygula
        durum = Durum(mekan="han", esyalar=["pusula"], akce=3)
        uyarilar = envanter_uygula(durum, {"eklenen": [], "cikan": ["tabanca"], "akce": -5})
        self.assertEqual(len(uyarilar), 2)
        self.assertEqual((durum.esyalar, durum.akce), (["pusula"], 3))   # hiçbiri uygulanmadı

    def test_motor_baslangic_envanteri(self):
        dunya = dunya_yukle(DUNYA_YOLU)
        motor = Motor(dunya, SahteLLM(dunya), Bellek("son"))
        self.assertEqual((motor.durum.esyalar, motor.durum.akce), (["pusula", "boş harita defteri"], 15))
        self.assertIsNot(motor.durum.esyalar, dunya.oyuncu_esyalar)      # dünya dosyası değişmesin


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
            "vaatler": {"acilan": ["a", "b", "c"],
                        "ilerleyen": [{"id": "v1", "kanit": "Anahtarı gösterdi."},
                                      {"id": "v9", "kanit": "x"},                # açık değil
                                      "v1"]},                                    # kanıtsız
            "karakter_denetimi": [{"karakter": "vezir", "kisilik": "sapma"},
                                  {"karakter": "nehir", "kisilik": "sapma", "bilgi": "sizinti",
                                   "gerekce": "Sırrını hemen döktü."}],
            "karakter_degisimleri": [{"karakter": "vezir", "degisim": "x"}],
        })
        b = editor_yanit_coz(metin, self.dunya, self.durum)
        self.assertEqual([i["metin"] for i in b["iddialar"]], ["Nehir iri"])
        self.assertEqual(b["vaatler"]["acilan"], ["a", "b"])                     # en fazla 2
        self.assertEqual(b["vaatler"]["ilerleyen"], [{"id": "v1", "kanit": "Anahtarı gösterdi."}])
        self.assertEqual(b["otomatik"]["kanitsiz_vaat"], ["v9", "v1"])
        self.assertEqual(b["karakter_denetimi"], [{"karakter": "nehir", "gerekce": "Sırrını hemen döktü.",
                                                   "kisilik": "sapma", "konusma": "uygun", "bilgi": "sizinti"}])
        self.assertEqual(b["karakter_degisimleri"], [])

    def test_kod_suzgeci(self):
        self.durum.vaat_ac("Yedi numaralı odada ne var?", 1)
        metin = json.dumps({
            "iddialar": [
                {"metin": "Selvi yorgun görünüyor.", "durum": "yeni"},
                {"metin": "Nehir Hanım konuşmaya istekli hale geldi.", "durum": "yeni"},
                {"metin": "Nehir Hanım hâlâ mutfakta.", "durum": "yeni"},
                {"metin": "Nehir Hanım'ın sol elinde üç parmak eksik.", "durum": "yeni"},
                {"metin": "Selvi'nin gözleri ela.", "durum": "yeni"},
            ],
            "vaatler": {"acilan": ["Yedi numaralı odada neler var?", "Yabancı kimi arıyor?"]},
        })
        b = editor_yanit_coz(metin, self.dunya, self.durum)
        self.assertEqual(b["otomatik"]["atilan_tahmin"],
                         ["Selvi yorgun görünüyor.", "Nehir Hanım konuşmaya istekli hale geldi.",
                          "Nehir Hanım hâlâ mutfakta."])
        self.assertEqual(b["otomatik"]["yeniden_siniflanan"], ["Nehir Hanım'ın sol elinde üç parmak eksik."])
        self.assertEqual([(i["durum"], i["olgu"]) for i in b["iddialar"]], [("biliniyor", "o2"), ("yeni", None)])
        self.assertEqual(b["vaatler"]["acilan"], ["Yabancı kimi arıyor?"])
        self.assertEqual(b["otomatik"]["tekrar_vaat"], ["Yedi numaralı odada neler var?"])

    def test_tur_suzgeci_ilerleme_siniri_ve_kural_celiskisi(self):
        for m in ("Kervan nerede?", "Yabancı kim?", "Kule neden yıkık?"):
            self.durum.vaat_ac(m, 1)
        metin = json.dumps({
            "iddialar": [
                {"metin": "Nehir Hanım sabırsız biridir.", "tur": "kisilik", "durum": "yeni"},
                {"metin": "Oyuncunun elinde bir tabanca var.", "tur": "sahiplik", "durum": "celisiyor", "olgu": "k1"},
            ],
            "vaatler": {"ilerleyen": [{"id": v, "kanit": "x"} for v in ("v1", "v2", "v3")]},
        })
        b = editor_yanit_coz(metin, self.dunya, self.durum)
        self.assertEqual(b["otomatik"]["atilan_tur"], ["Nehir Hanım sabırsız biridir."])
        self.assertEqual([(i["durum"], i["olgu"]) for i in b["iddialar"]], [("celisiyor", "k1")])
        self.assertEqual([x["id"] for x in b["vaatler"]["ilerleyen"]], ["v1", "v2"])
        self.assertEqual(b["otomatik"]["fazla_ilerleme"], ["v3"])

    def test_yazara_yasananlar_ve_tekrarlar_gider(self):
        from hikaye.durum import KarakterDegisimi
        son = self.durum.sahneler[-1]
        son.karakterler = ["nehir"]
        son.metin = "\n".join(["Feneri kaldırıyor.", "Fenerin ışığı titriyor.", "Fener sönüyor.",
                               "Feneri bırakıyor.", 'İri yapılı kadın: "Fener fener fener."'])
        self.durum.karakter_degisimleri.append(
            KarakterDegisimi(sahne_no=1, karakter="nehir", degisim="Oyuncu onu omzundan vurdu; öfkeli."))
        metin = "\n".join(Editor("denetim").yazara_bolumler(self.dunya, self.durum))
        self.assertIn("omzundan vurdu", metin)
        self.assertIn("TEKRARLANAN SÖZCÜKLER", metin)
        self.assertIn("(4 kez)", metin)                  # replikteki "fener"ler sayılmaz

    def test_editor_adi_gecen_karakterin_kartini_gorur(self):
        from hikaye.istem import editor_istemi
        sahne = self.durum.sahneler[-1]
        sahne.karakterler, sahne.metin = ["nehir"], 'İri yapılı kadın: "Kâtip Selvi ağzı sıkıdır."'
        _, kullanici = editor_istemi(self.dunya, self.durum, sahne, [], zanaat_acik=False)
        self.assertIn(self.dunya.karakterler["selvi"].kisilik, kullanici)

    def test_acilis_metni_ve_olgu_siniri(self):
        yeni = ["Kuyunun ipi yepyeni.", "Ahırın kapısı mavi boyalı.", "Demirhanenin çatısı akıyor.",
                "Pazarcı kadın incir satıyor."]
        metin = json.dumps({"iddialar": (
            [{"metin": "Güneş batarken tuz çölünü aşıp Tuzhan'a varıyorsun.", "durum": "yeni"}]
            + [{"metin": m, "durum": "yeni"} for m in yeni])})
        b = editor_yanit_coz(metin, self.dunya, self.durum)
        self.assertEqual(b["otomatik"]["yeniden_siniflanan"], ["Güneş batarken tuz çölünü aşıp Tuzhan'a varıyorsun."])
        self.assertEqual([i["metin"] for i in b["iddialar"] if i["durum"] == "yeni"], yeni[:3])
        self.assertEqual(b["otomatik"]["fazla_olgu"], yeni[3:])

    def test_bulgular_duruma_islenir(self):
        self.durum.vaat_ac("Yedi numaralı odada ne var?", 1)
        editor = Editor("tam", ilkeler=[])
        editor._uygula({
            "iddialar": [
                {"metin": "Selvi'nin gözleri ela", "durum": "yeni", "olgu": None, "ilgili": ["selvi"]},
                {"metin": "Nehir zarif", "durum": "celisiyor", "olgu": "o2", "ilgili": []},
            ],
            "vaatler": {"acilan": ["Yabancı kim?"], "ilerleyen": [],
                        "cozulen": [{"id": "v1", "kanit": "Oda boş çıktı."}]},
            "karakter_denetimi": [{"karakter": "nehir", "kisilik": "sapma", "konusma": "uygun",
                                   "bilgi": "uygun", "gerekce": "Sırrını hemen döktü."}],
            "oyuncu_bilgi_sizintisi": "Oyuncu kervandaki deve sayısını biliyor.",
            "karakter_degisimleri": [{"karakter": "nehir", "degisim": "oyuncuya ısındı"}],
            "zanaat": [],
            "yazar_notu": "Tekin'i konuştur.",
        }, self.durum, 2)
        self.assertEqual(self.durum.olgular[-1].metin, "Selvi'nin gözleri ela")
        self.assertEqual(self.durum.celiskiler[0].olgu_id, "o2")
        self.assertEqual([v.metin for v in self.durum.acik_vaatler], ["Yabancı kim?"])
        self.assertEqual(self.durum.vaatler[0].cozuldugu_sahne, 2)
        self.assertEqual([(s.karakter, s.tur) for s in self.durum.karakter_sapmalari],
                         [("nehir", "kisilik"), ("oyuncu", "bilgi")])
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

    def test_karakter_uyarisi_kartla_doner(self):
        from hikaye.durum import KarakterSapmasi
        self.durum.karakter_sapmalari.append(
            KarakterSapmasi(sahne_no=1, karakter="nehir", tur="kisilik", gerekce="Sırrını hemen döktü."))
        metin = "\n".join(Editor("denetim").yazara_bolumler(self.dunya, self.durum))
        self.assertIn("KARAKTER UYARISI", metin)
        self.assertIn(self.dunya.karakterler["nehir"].kisilik, metin)

    def test_kod_uyarilari_yazara_doner(self):
        self.durum.sahneler[-1].uyarilar = ["oyuncu adına replik yazıldı (atıldı): 'x'",
                                           "konuşan id'si düzeltildi: 'tekine' → tekin"]
        metin = "\n".join(Editor("denetim").yazara_bolumler(self.dunya, self.durum))
        self.assertIn("oyuncu adına replik", metin)
        self.assertNotIn("düzeltildi", metin)           # zararsız düzeltmeler yazarı meşgul etmez

    def test_konusmayan_karakter_uyarisi(self):
        editor = Editor("denetim")
        self.assertNotIn("hiç konuşmadı", "\n".join(editor.yazara_bolumler(self.dunya, self.durum)))
        self.durum.sahneler[-1].replikler = []
        uyari = "\n".join(editor.yazara_bolumler(self.dunya, self.durum))
        self.assertIn("hiç konuşmadı", uyari)

    def test_tekrarlayan_zayif_olcut_uyarisi(self):
        editor = Editor("tam")
        self.durum.zanaat_gecmisi = [["sahne_donusu", "fikir"], ["sahne_donusu"]]
        metin = "\n".join(editor.yazara_bolumler(self.dunya, self.durum))
        self.assertIn("TEKRARLAYAN SORUN", metin)
        self.assertIn("sahne_donusu", metin)
        self.assertNotIn("- fikir", metin)               # yalnızca son sahnede zayıf değil


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
            self.assertEqual([o.metin for o in durum.olgular], SahteLLM.YENI_OLGULAR[:4])
            self.assertEqual(len(durum.celiskiler), 4)
            self.assertEqual(len(durum.vaatler), 4)
            self.assertEqual(len(durum.karakter_sapmalari), 4)
            self.assertTrue(any(v.cozuldugu_sahne for v in durum.vaatler))
            self.assertTrue(durum.editor_notu)
            self.assertNotEqual(durum.zaman, dunya.baslangic_zamani)    # zaman ilerledi

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

    def test_rollere_ayri_model(self):
        dunya = dunya_yukle(DUNYA_YOLU)
        yazar, editor_llm, ozet_llm = SahteLLM(dunya), SahteLLM(dunya), SahteLLM(dunya)
        motor = Motor(dunya, yazar, Bellek("ozet"), editor=Editor("denetim"),
                      editor_llm=editor_llm, ozet_llm=ozet_llm)
        sahne = motor.basla()
        motor.oyna(sahne.secenekler[0])
        self.assertEqual((yazar.cagri_sayisi, editor_llm.cagri_sayisi, ozet_llm.cagri_sayisi), (2, 2, 2))
        self.assertEqual(yazar.editor_cagrisi, 0)


if __name__ == "__main__":
    unittest.main()
