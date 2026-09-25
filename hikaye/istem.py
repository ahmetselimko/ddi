"""Modele giden istemler. Tüm metin kalıpları burada."""
from .durum import Durum, Sahne
from .dunya import Dunya

_SISTEM = """Sen Türkçe bir interaktif hikâye oyununun anlatıcısısın.

DÜNYA: {ad}
TON: {ton}
OYUNCU: {oyuncu}

MEKÂNLAR (id: ad — tanım):
{mekanlar}

KARAKTERLER (id: ad — tanım):
{karakterler}

KURALLAR:
1. Oyuncuya ikinci tekil şahısla, şimdiki zamanda anlat ("Kapıyı itiyorsun.").
2. Oyuncunun eyleminin SONUCUNU göster. Oyuncu bir şey sorduysa karşısındaki karakter cevap verir;
   sır saklıyorsa bile kaçamak, yarım ya da yanıltıcı bir cevapla konuşur. Susmak ve bakışmak cevap değildir.
3. Her sahnede bir şey değişsin: yeni bir bilgi, bir olay, bir engel, bir pazarlık ya da ilişkide bir kırılma.
   Yalnızca mekân ve atmosfer anlatan sahne yazma.
4. Sahnede karakter varsa konuşur: sahnede en az 2 replik olsun. Betimleme sahnenin en fazla üçte biri olsun.
5. Karakterlerin görünüşü yukarıdaki tanımlara uysun; kartlarındaki kişilik ve konuşma üslubuyla konuşsunlar.
   Bir karakter bilmediği şeyi söylemez; bilmiyorsa bunu kendi üslubuyla söyler.
6. Verilen olgularla, özetle ve önceki sahnelerle çelişme. Kanonda olmayan küçük ayrıntıları uydurabilirsin;
   hikâyenin ana sırlarını ise tek sahnede çözme.
7. Sahneyi karakterlerin tepkisinden SONRA, oyuncunun karar vermesi gereken bir anda bitir.
   Oyuncunun yerine karar verme.
8. Seçenekler birbirinden farklı yönlere açılsın; oyuncunun zaten yaptığı ya da sorduğu şeyi tekrar önerme.
9. Oyuncu dünyaya aykırı bir şey yapmaya çalışırsa, bunun neden olmadığını hikâyenin içinde göster.
10. Yalnızca aşağıdaki biçimde JSON döndür, başka hiçbir şey yazma.

{{
  "akis": [
    {{"anlatim": "anlatım paragrafı"}},
    {{"konusan": "karakter id'si (oyuncu konuşuyorsa \\"oyuncu\\")", "replik": "söylenen söz, tırnaksız"}},
    {{"anlatim": "anlatım paragrafı"}}
  ],
  "mekan": "sahnenin geçtiği mekânın id'si (yukarıdaki listeden)",
  "karakterler": ["sahnede bulunan karakterlerin id'leri"],
  "yeni_olgular": [{{"metin": "bu sahnede kesinleşen yeni bir gerçek", "ilgili": ["karakter/mekân id'leri"]}}],
  "secenekler": ["oyuncunun yapabileceği birbirinden farklı 3 şey"]
}}

akis: sahne baştan sona bu parçalardan oluşur, toplam 120-220 kelime. Her konuşma ayrı bir replik
parçasıdır; konuşmayı anlatım parçasının içine gömme. Replik yalnızca sahnede O ANDA söylenen
sözdür; hatırlanan ya da başkasından aktarılan sözleri anlatımın içinde ver.

yeni_olgular: bu sahnede hikâyede KESİNLEŞEN kalıcı gerçekler (0-3 adet): biri bir sır açıkladı,
bir eşya el değiştirdi, bir yer keşfedildi, bir söz verildi. Tahmin, ima ya da şüphe yazma
("X bir şey biliyor olabilir" olgu değildir). Zaten bilineni tekrar yazma."""

_OZET_SISTEM = (
    "Bir interaktif hikâyenin özetini tutuyorsun. Kısa, olgusal ve Türkçe yaz. "
    "Yalnızca güncellenmiş özeti döndür."
)

_EDITOR_SISTEM = (
    "Sen Türkçe bir interaktif hikâye oyununun editörüsün. Hikâye yazmıyorsun; az önce yazılan "
    "sahneyi dünya kanonuna ve hikâyenin gidişatına karşı denetliyorsun. Titiz ve kısa ol. "
    "Yalnızca istenen JSON'u döndür."
)


def sistem_istemi(dunya: Dunya) -> str:
    return _SISTEM.format(
        ad=dunya.ad,
        ton=dunya.ton,
        oyuncu=dunya.oyuncu,
        mekanlar="\n".join(f"- {m.id}: {m.ad} — {m.tanim}" for m in dunya.mekanlar.values()),
        karakterler="\n".join(f"- {k.id}: {k.ad} — {k.tanim}" for k in dunya.karakterler.values()),
    )


def sahne_metni(sahne: Sahne, dunya: Dunya) -> str:
    mekan = dunya.mekanlar[sahne.mekan].ad
    eylem = f"Oyuncunun eylemi: {sahne.eylem}\n" if sahne.eylem else ""
    return f"Sahne {sahne.no} ({mekan})\n{eylem}{sahne.metin}"


def sahne_istemi(dunya: Dunya, baglam, eylem: str | None, ek: list[str] | None = None) -> str:
    """ek: editörden gelen bölümler (açık vaatler, çelişki uyarısı, yazar notu)."""
    bolumler = []
    if baglam.ozet:
        bolumler.append(f"[HİKÂYENİN ŞİMDİYE KADARKİ ÖZETİ]\n{baglam.ozet}")
    if baglam.olgular:
        bolumler.append("[BİLİNEN OLGULAR]\n" + "\n".join(f"- {o}" for o in baglam.olgular))
    if baglam.karakter_kartlari:
        bolumler.append("[İLGİLİ KARAKTERLER]\n" + "\n\n".join(baglam.karakter_kartlari))
    bolumler.extend(ek or [])

    if eylem is None:
        bolumler.append(f"[AÇILIŞ]\n{dunya.giris}")
        bolumler.append("Hikâyenin ilk sahnesini yaz.")
    else:
        bolumler.append("[SON SAHNELER]\n" + "\n\n".join(baglam.son_sahneler))
        bolumler.append(f"[OYUNCUNUN EYLEMİ]\n{eylem}")
        bolumler.append("Bu eylemin sonucunu anlatan bir sonraki sahneyi yaz.")
    return "\n\n".join(bolumler)


def ozet_istemi(dunya: Dunya, eski_ozet: str, sahne: Sahne) -> tuple[str, str]:
    kullanici = (
        f"MEVCUT ÖZET:\n{eski_ozet or '(henüz yok)'}\n\n"
        f"YENİ SAHNE:\n{sahne_metni(sahne, dunya)}\n\n"
        "Özeti bu sahneyle güncelle. En fazla 200 kelime. Kim neyi öğrendi, ne el değiştirdi, "
        "hangi sözler verildi, oyuncu nerede — bunları koru; betimlemeyi at."
    )
    return _OZET_SISTEM, kullanici


def editor_istemi(dunya: Dunya, durum: Durum, sahne: Sahne,
                  ilkeler: list[dict], zanaat_acik: bool) -> tuple[str, str]:
    """Az önce eklenen sahneyi (durum.sahneler[-1]) denetleten istem."""
    bolumler = [
        f"[DÜNYA KANONU — değişmez gerçekler]\nOyuncu: {dunya.oyuncu}\nKarakterler:\n"
        + "\n".join(f"- {k.id}: {k.ad} — {k.tanim}" for k in dunya.karakterler.values())
        + "\nMekânlar:\n"
        + "\n".join(f"- {m.id}: {m.ad} — {m.tanim}" for m in dunya.mekanlar.values())
        + "\nOlgular:\n"
        + "\n".join(f"- [{o.id}] {o.metin}" for o in dunya.olgular),
    ]
    if durum.olgular:
        bolumler.append("[OYUNDA KESİNLEŞEN OLGULAR]\n"
                        + "\n".join(f"- [{o.id}] {o.metin}" for o in durum.olgular))
    acik = [v for v in durum.acik_vaatler if v.acildigi_sahne < sahne.no]
    if acik:
        bolumler.append("[AÇIK VAATLER — okurun cevabını beklediği sorular]\n"
                        + "\n".join(f"- [{v.id}] {v.metin}" for v in acik))
    if len(durum.sahneler) >= 2:
        bolumler.append(f"[ÖNCEKİ SAHNE]\n{sahne_metni(durum.sahneler[-2], dunya)}")
    secenekler = "\n".join(f"- {s}" for s in sahne.secenekler)
    bolumler.append(f"[DENETLENECEK SAHNE]\n{sahne_metni(sahne, dunya)}\n\nSunulan seçenekler:\n{secenekler}")

    gorevler = [
        "1. iddialar: Sahnedeki somut ve kalıcı iddiaları çıkar: görünüş, sayılar, akrabalık, "
        "sahiplik, kim neyi biliyor, kesinleşen olaylar. Anlık hareketleri, duyguları, bakışları, "
        "atmosferi ve betimlemeyi (ses, ışık, koku, sessizlik) ALMA; yalnızca ileride doğru ya da "
        "yanlış çıkabilecek kalıcı gerçekler. En fazla 6. Her biri için durum:\n"
        '   - "biliniyor": kanonda ya da oyun olgularında zaten var ("olgu": o id)\n'
        '   - "celisiyor": bir olguyla çelişiyor ("olgu": çelişilen id)\n'
        '   - "yeni": hiçbir yerde yok ve hikâyede kesinleşti. Tahmin, ima ya da bir karakterin '
        "şüphesi yeni olgu değildir; onları hiç yazma.",
        "2. vaatler: acilan = sahnenin açtığı, okurun cevabını merak edeceği yeni sorular "
        "(en fazla 2, zaten açık olanı tekrar yazma); ilerleyen = bu sahnede ilerleyen açık "
        "vaatlerin id'leri; cozulen = bu sahnede cevabı verilen açık vaatlerin id'leri.",
        "3. karakter_degisimleri: bir karakterin tutumunda, inancında ya da oyuncuyla ilişkisinde "
        "bu sahnede kalıcı bir değişim olduysa. Yoksa boş liste.",
    ]
    ornek_zanaat = ""
    if zanaat_acik:
        sahne_ilkeleri = [i for i in ilkeler if i["kapsam"] == "sahne"]
        hikaye_ilkeleri = [i for i in ilkeler if i["kapsam"] == "hikaye"]
        gorevler.append(
            '4. zanaat: her ölçüt için "iyi" ya da "zayif" ver, gerekçeyi bir cümleyle yaz.\n'
            + "\n".join(f"   - {i['id']}: {i['soru']}" for i in sahne_ilkeleri)
        )
        gorevler.append(
            "5. yazar_notu: yazara bir sonraki sahne için en fazla iki cümlelik SOMUT öneri: kim ne "
            "söyleyebilir, ne olabilir (ör. \"Nehir Hanım oda fiyatını söyleyip karşılığında oyuncunun "
            "kim olduğunu sorabilir\"). \"Sağla\", \"güçlendir\", \"ima et\" gibi genel ifadeler yazma. "
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
        '  "vaatler": {"acilan": ["yeni soru"], "ilerleyen": ["v1"], "cozulen": []},\n'
        '  "karakter_degisimleri": [{"karakter": "id", "degisim": "ne değişti"}]'
        + ornek_zanaat + "\n}"
    )
    return _EDITOR_SISTEM, "\n\n".join(bolumler)
