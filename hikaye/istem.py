"""Modele giden istemler. Tüm metin kalıpları burada."""
from .durum import Durum, OyunOlgusu, Sahne
from .dunya import Dunya

_SISTEM = """Sen Türkçe bir interaktif hikâye oyununun anlatıcısısın.

DÜNYA: {ad}
TON: {ton}
OYUNCU: {oyuncu}

MEKÂNLAR (id: ad — tanım):
{mekanlar}

KARAKTERLER (id: ad [oyuncu tanışmadan önce nasıl görünür] — tanım):
{karakterler}

KURALLAR:
1. Oyuncuya ikinci tekil şahısla, şimdiki zamanda anlat ("Kapıyı itiyorsun.").
2. OYUNCUNUN SÖZLERİNİ YAZMA ve eylemini genişletme: oyuncuya seçmediği bir söz, yapmadığı bir hareket
   yükleme. Oyuncunun eylemi sana verildi; sahneyi o eylemin sonucundan başlat. Oyuncu bir şey sorduysa
   karşısındaki karakter cevap verir; sır saklıyorsa bile kaçamak, yarım ya da yanıltıcı bir cevapla
   konuşur. Susmak ve bakışmak cevap değildir.
3. Oyuncu yalnızca OYUNCU tanımındakileri ve sahnelerde gördüğünü, duyduğunu bilir. Kanondaki bir bilgiyi,
   bir karakter söylemeden oyuncu biliyormuş gibi anlatma. SEÇENEKLER de buna uyar: oyuncu kimsenin
   bahsetmediği bir odayı, görmediği bir kişiyi soramaz.
4. Karakterler de yalnızca bilebilecekleri şeyleri bilir. Oyuncunun kim olduğunu ve neden geldiğini ancak
   oyuncu kendini tanıttıysa ya da biri onlara anlattıysa bilirler.
5. Her sahnede bir şey değişsin: yeni bir bilgi, bir olay, bir engel, bir pazarlık ya da ilişkide bir kırılma.
   Yalnızca mekân ve atmosfer anlatan sahne yazma.
6. Sahnede karakter varsa konuşur: en az 2 replik. Betimleme sahnenin en fazla üçte biri olsun.
7. Karakterler kartlarındaki kişilikten çıkmasın: şüpheci biri ilk tanıştığı yabancıya sırlarını dökmez,
   güven adım adım kazanılır. Konuşma üsluplarını koru ama örnek replikleri aynen tekrarlama.
8. Oyuncunun adını henüz bilmediği karakterlerden adıyla değil görünüşüyle söz et. Karakter kendini
   tanıtınca ya da biri onu adıyla anınca adını kullanabilirsin.
9. Verilen olgularla, özetle ve önceki sahnelerle çelişme. Kanonda olmayan küçük ayrıntıları uydurabilirsin;
   hikâyenin ana sırlarını ise tek sahnede çözme. Yerleşimi koru: karakterlerin nerede durduğu ve eşyalar
   önceki sahneyle tutarlı olsun; yer değişirse bunu anlat.
10. Zaman yalnızca ileri akar ve olaylar gerektirdiğinde ilerler. Gece çoğu kişi uyur; dükkânlar ve
    kurumlar kapalıdır.
11. Sahneyi karakterlerin tepkisinden SONRA, oyuncunun karar vermesi gereken bir anda bitir.
12. Seçenekleri ikinci tekil emir kipinde yaz ("... sor", "... git"). Birbirinden farklı yönlere açılsınlar;
    oyuncunun zaten yaptığı ya da sorduğu şeyi tekrar önerme.
13. Oyuncu dünyaya aykırı bir şey yapmaya çalışırsa, bunun neden olmadığını hikâyenin içinde göster.
14. Yalnızca aşağıdaki biçimde JSON döndür, başka hiçbir şey yazma.

{{
  "akis": [
    {{"anlatim": "anlatım paragrafı"}},
    {{"konusan": "karakter id'si", "replik": "söylenen söz, tırnaksız"}},
    {{"anlatim": "anlatım paragrafı"}}
  ],
  "mekan": "sahnenin geçtiği mekânın id'si (yukarıdaki listeden)",
  "zaman": "sahne sonundaki gün ve vakit, ör. \\"1. gün, gece\\"",
  "karakterler": ["sahnede bulunan karakterlerin id'leri"],
  "yeni_olgular": [{{"metin": "bu sahnede kesinleşen yeni bir gerçek", "ilgili": ["karakter/mekân id'leri"]}}],
  "secenekler": ["oyuncunun yapabileceği birbirinden farklı 3 şey"]
}}

akis: sahne baştan sona bu parçalardan oluşur, toplam 120-220 kelime. Her konuşma ayrı bir replik
parçasıdır; konuşmayı anlatım parçasının içine gömme. Replik yalnızca sahnede O ANDA bir karakterin
söylediği sözdür; hatırlanan ya da başkasından aktarılan sözleri anlatımın içinde ver.

yeni_olgular: bu sahnede hikâyede KESİNLEŞEN kalıcı gerçekler (0-3 adet): biri bir sır açıkladı,
bir eşya el değiştirdi, bir yer keşfedildi, bir söz verildi. Tahmin, ima ya da şüphe yazma
("X bir şey biliyor olabilir" olgu değildir). Zaten bilineni tekrar yazma."""

_OZET_SISTEM = (
    "Bir interaktif hikâyenin özetini tutuyorsun. Kısa, olgusal ve Türkçe yaz. "
    "Yalnızca güncellenmiş özeti döndür."
)

_EDITOR_SISTEM = (
    "Sen Türkçe bir interaktif hikâye oyununun editörüsün. Hikâye yazmıyorsun; az önce yazılan "
    "sahneyi dünya kanonuna, karakter kartlarına ve hikâyenin gidişatına karşı denetliyorsun. "
    "Titiz ve kısa ol. Yalnızca istenen JSON'u döndür."
)


def _karakter_satiri(k) -> str:
    gorunus = f" [{k.gorunen_ad}]" if k.gorunen_ad != k.ad else ""
    return f"- {k.id}: {k.ad}{gorunus} — {k.tanim}"


def _taninan_satiri(dunya: Dunya, taninan) -> str:
    adlar = [dunya.karakterler[k].ad for k in taninan if k in dunya.karakterler]
    return ", ".join(adlar) if adlar else "(henüz kimse)"


def sistem_istemi(dunya: Dunya) -> str:
    return _SISTEM.format(
        ad=dunya.ad,
        ton=dunya.ton,
        oyuncu=dunya.oyuncu,
        mekanlar="\n".join(f"- {m.id}: {m.ad} — {m.tanim}" for m in dunya.mekanlar.values()),
        karakterler="\n".join(_karakter_satiri(k) for k in dunya.karakterler.values()),
    )


def sahne_metni(sahne: Sahne, dunya: Dunya) -> str:
    mekan = dunya.mekanlar[sahne.mekan].ad
    zaman = f", {sahne.zaman}" if sahne.zaman else ""
    eylem = f"Oyuncunun eylemi: {sahne.eylem}\n" if sahne.eylem else ""
    return f"Sahne {sahne.no} ({mekan}{zaman})\n{eylem}{sahne.metin}"


def sahne_istemi(dunya: Dunya, baglam, eylem: str | None, ek: list[str] | None = None,
                 zaman: str = "", taninan=(), eylemler=()) -> str:
    """ek: editörden gelen bölümler (açık vaatler, çelişki ve karakter uyarıları, yazar notu).
    eylemler: oyuncunun şimdiye kadarki eylemleri — kısa bellekten düşseler de
    tekrar sorulmasınlar, tekrar önerilmesinler diye her stratejide gider."""
    bolumler = []
    if baglam.ozet:
        bolumler.append(f"[HİKÂYENİN ŞİMDİYE KADARKİ ÖZETİ]\n{baglam.ozet}")
    if baglam.olgular:
        bolumler.append("[BİLİNEN OLGULAR]\n" + "\n".join(f"- {o}" for o in baglam.olgular))
    if baglam.karakter_kartlari:
        bolumler.append("[İLGİLİ KARAKTERLER]\n" + "\n\n".join(baglam.karakter_kartlari))
    bolumler.extend(ek or [])
    if eylemler:
        bolumler.append("[OYUNCUNUN ŞİMDİYE KADAR YAPTIKLARI — karakterler bunları hatırlar; "
                        "tekrar sordurma, seçenek olarak tekrar önerme]\n"
                        + "\n".join(f"{i}. {e}" for i, e in enumerate(eylemler, 1)))
    bolumler.append(f"[ŞU AN] {zaman or dunya.baslangic_zamani}\n"
                    f"[OYUNCUNUN ADINI BİLDİĞİ KARAKTERLER] {_taninan_satiri(dunya, taninan)}")

    if eylem is None:
        bolumler.append(f"[AÇILIŞ]\n{dunya.giris}")
        bolumler.append("Hikâyenin ilk sahnesini yaz. Açılış metnini aynen tekrarlama, oradan devam et. "
                        "Oyuncu henüz bir şey söylemedi ya da yapmadı.")
    else:
        bolumler.append("[ÖNCEKİ SAHNELER]\n" + "\n\n".join(baglam.son_sahneler))
        bolumler.append(f"[OYUNCUNUN EYLEMİ]\n{eylem}")
        bolumler.append("Bu eylemin sonucunu anlatan bir sonraki sahneyi yaz.")
    return "\n\n".join(bolumler)


def ozet_istemi(dunya: Dunya, eski_ozet: str, sahne: Sahne) -> tuple[str, str]:
    kullanici = (
        f"MEVCUT ÖZET:\n{eski_ozet or '(henüz yok)'}\n\n"
        f"YENİ SAHNE:\n{sahne_metni(sahne, dunya)}\n\n"
        "Özeti bu sahneyle güncelle. En fazla 200 kelime. Kim neyi öğrendi, ne el değiştirdi, "
        "hangi sözler verildi, oyuncu nerede ve saat kaç — bunları koru; betimlemeyi at."
    )
    return _OZET_SISTEM, kullanici


def editor_istemi(dunya: Dunya, durum: Durum, sahne: Sahne, ilkeler: list[dict],
                  zanaat_acik: bool, oyun_olgulari: list[OyunOlgusu] | None = None) -> tuple[str, str]:
    """Az önce eklenen sahneyi (durum.sahneler[-1]) denetleten istem. oyun_olgulari
    verilmezse hepsi gider; uzun oyunlarda editor.py yalnızca ilgilileri seçer."""
    oyun_olgulari = durum.olgular if oyun_olgulari is None else oyun_olgulari
    bolumler = [
        f"[DÜNYA KANONU — değişmez gerçekler]\nOyuncu: {dunya.oyuncu}\nAçılış: {dunya.giris}\n"
        "Karakterler:\n"
        + "\n".join(_karakter_satiri(k) for k in dunya.karakterler.values())
        + "\nMekânlar:\n"
        + "\n".join(f"- {m.id}: {m.ad} — {m.tanim}" for m in dunya.mekanlar.values())
        + "\nOlgular:\n"
        + "\n".join(f"- [{o.id}] {o.metin}" for o in dunya.olgular),
    ]
    if oyun_olgulari:
        bolumler.append("[OYUNDA KESİNLEŞEN OLGULAR]\n"
                        + "\n".join(f"- [{o.id}] {o.metin}" for o in oyun_olgulari))
    kartlar = [dunya.karakterler[k].kart() for k in sahne.karakterler]
    if kartlar:
        bolumler.append("[SAHNEDEKİ KARAKTERLERİN KARTLARI]\n" + "\n\n".join(kartlar))
    acik = [v for v in durum.acik_vaatler if v.acildigi_sahne < sahne.no]
    if acik:
        bolumler.append("[AÇIK VAATLER — okurun cevabını beklediği sorular]\n"
                        + "\n".join(f"- [{v.id}] {v.metin}" for v in acik))
    if len(durum.sahneler) >= 2:
        bolumler.append(f"[ÖNCEKİ SAHNE]\n{sahne_metni(durum.sahneler[-2], dunya)}")
    secenekler = "\n".join(f"- {s}" for s in sahne.secenekler)
    bolumler.append(
        f"[OYUNCUNUN ADINI BİLDİĞİ KARAKTERLER] {_taninan_satiri(dunya, durum.taninan)}\n\n"
        f"[DENETLENECEK SAHNE]\n{sahne_metni(sahne, dunya)}\n\nSunulan seçenekler:\n{secenekler}"
    )

    gorevler = [
        "1. iddialar: Sahnedeki somut ve kalıcı iddiaları çıkar: görünüş, sayılar, akrabalık, "
        "sahiplik, kim neyi biliyor, kesinleşen olaylar. Yalnızca ileride çelişilirse okurun fark "
        "edeceği, hikâyeye etkisi olan gerçekler. En fazla 6, bunlardan en fazla 3'ü yeni. "
        "Her biri için durum:\n"
        '   - "biliniyor": kanonda, mekân/karakter tanımlarında ya da oyun olgularında zaten var '
        '("olgu": o id; mekân/karakter tanımıysa null). "yeni" demeden önce hepsine tek tek bak: '
        "aynı bilgiyi başka sözcüklerle söyleyen varsa biliniyordur.\n"
        '   - "celisiyor": bir olguyla çelişiyor ("olgu": çelişilen id)\n'
        '   - "yeni": hiçbir yerde yok ve hikâyede kesinleşti.\n'
        "   ALMA: anlık durumlar (\"Tekin'in elinde çorba var\"), görünen haller (\"Selvi yorgun "
        "görünüyor\"), duygu, düşünce ve tutumlar (\"Nehir acısının dinmediğini düşünüyor\", \"konuşmaya "
        "istekli hale geldi\" — tutum değişimi karakter_degisimleri'ne yazılır), karakterlerin "
        "hareketleri (\"Nehir masaya doğru yürüyor\"), sıradan mekân betimlemeleri (\"ocağın çevresinde "
        "minderler var\", \"içerisi loş\"), açılış metninde zaten yazanlar, tahmin ve imalar, atmosfer.",
        "2. vaatler:\n"
        "   - acilan: sahnenin açtığı, okurun cevabını merak edeceği YENİ sorular (en fazla 2). "
        "Açık bir vaatle aynı soruyu başka sözcüklerle sorma; öyleyse o vaadi ilerleyen say. "
        "Vaat hikâye dünyasına dair bir sırdır (\"Yabancı neyi arıyor?\"); oyuncunun seçimleri "
        "hakkındaki \"oyuncu şunu yaparsa ne olur?\" soruları vaat DEĞİLDİR.\n"
        '   - ilerleyen: [{"id": "v1", "kanit": "bu sahnede o soruya dair yeni bilgi ya da adım"}]. '
        "Sorunun yalnızca anılması ya da bilinen bir şeyin tekrar söylenmesi ilerleme DEĞİLDİR; "
        "kanıt olarak YENİ bir bilgi gösteremiyorsan yazma.\n"
        '   - cozulen: [{"id": "v2", "kanit": "cevabın verildiği yer"}]',
        "3. karakter_denetimi: sahnede konuşan ya da bir şey yapan her karakter için, kartına göre:\n"
        '   - kisilik: "uygun" ya da "sapma" (ör. şüpheci biri ilk tanıştığı yabancıya sırlarını '
        "döküyorsa sapma)\n"
        '   - konusma: "uygun" ya da "sapma" (kartındaki üsluba uymuyorsa ya da başka bir karakterin '
        "hitabını, kalıbını kullanıyorsa sapma)\n"
        '   - bilgi: "uygun" ya da "sizinti" (söylediğini bilemeyecekse sizinti: ör. oyuncunun kim '
        "olduğunu, oyuncu kendini tanıtmadan biliyor)\n"
        "   - gerekce: sapma ya da sızıntı varsa bir cümle, yoksa boş",
        "4. oyuncu_bilgi_sizintisi: anlatım ya da SEÇENEKLER oyuncuya bilemeyeceği bir şeyi (kanonda "
        "olup kimsenin ona söylemediği, görmediği bir kişi ya da yer) biliyormuş gibi atfediyorsa ya da "
        "anlatım oyuncuya seçmediği bir söz ve hareket yüklüyorsa bir cümleyle yaz, yoksa boş bırak.",
        "5. karakter_degisimleri: bir karakterin tutumunda, inancında ya da oyuncuyla ilişkisinde "
        "bu sahnede kalıcı bir değişim olduysa. Yoksa boş liste.",
    ]
    ornek_zanaat = ""
    if zanaat_acik:
        sahne_ilkeleri = [i for i in ilkeler if i["kapsam"] == "sahne"]
        hikaye_ilkeleri = [i for i in ilkeler if i["kapsam"] == "hikaye"]
        gorevler.append(
            '6. zanaat: her ölçüt için "iyi" ya da "zayif" ver, gerekçeyi bir cümleyle yaz.\n'
            + "\n".join(f"   - {i['id']}: {i['soru']}" for i in sahne_ilkeleri)
        )
        gorevler.append(
            "7. yazar_notu: yazara bir sonraki sahne için en fazla iki cümlelik SOMUT öneri: kim ne "
            "söyleyebilir, ne olabilir (ör. \"Nehir Hanım oda fiyatını söyleyip karşılığında oyuncunun "
            "kim olduğunu sorabilir\"). \"Sağla\", \"güçlendir\", \"ima et\" gibi genel ifadeler yazma; "
            "bir karakterin cevap vermemesini ya da susmasını önerme. "
            "Zayıf bulduğun ölçütlere ve şu genel ilkelere dayan:\n"
            + "\n".join(f"   - {i['id']}: {i['ilke']}" for i in hikaye_ilkeleri)
            + "\n   Oyuncunun seçimlerine saygı göster: oyuncunun ne yapacağına karar verme, "
            "dünyanın ve karakterlerin ona nasıl karşılık vereceğini öner."
        )
        ornek_zanaat = (
            ',\n  "zanaat": [{"ilke": "ölçüt id", "sonuc": "iyi ya da zayif", "gerekce": "bir cümle"}],'
            '\n  "yazar_notu": "en fazla iki cümle"'
        )

    bolumler.append("GÖREVLER:\n" + "\n".join(gorevler))
    bolumler.append(
        "JSON BİÇİMİ:\n{\n"
        '  "iddialar": [{"metin": "iddia", "durum": "yeni, biliniyor ya da celisiyor", '
        '"olgu": "ilgili olgu id\'si ya da null", "ilgili": ["karakter/mekân id\'leri"]}],\n'
        '  "vaatler": {"acilan": ["yeni soru"], "ilerleyen": [{"id": "v1", "kanit": "..."}], '
        '"cozulen": []},\n'
        '  "karakter_denetimi": [{"karakter": "id", "kisilik": "uygun", "konusma": "uygun", '
        '"bilgi": "uygun", "gerekce": ""}],\n'
        '  "oyuncu_bilgi_sizintisi": "",\n'
        '  "karakter_degisimleri": [{"karakter": "id", "degisim": "ne değişti"}]'
        + ornek_zanaat + "\n}"
    )
    return _EDITOR_SISTEM, "\n\n".join(bolumler)
