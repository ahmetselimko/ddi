# Türkçe İnteraktif Hikâye Oyunu — Uzun Anlatıda Tutarlılık

Oyuncunun seçimleriyle ilerleyen, sahnelerini bir dil modelinin yazdığı Türkçe
bir hikâye oyunu. Odak noktası: hikâye uzadıkça karakterlerin ve olayların tutarlı
kalmasını sağlamak ve bunu ölçmek.

- **Sağlamak:** model her turda hikâyenin tamamını görür (sohbetin hatırlaması gibi);
  bir editör model her sahneyi denetler ve bulgularını yazara geri verir; bazı
  sorunları da kod doğrudan yakalar.
- **Ölçmek:** editörün ve kodun bulduğu her şey (çelişkiler, karakter sapmaları,
  bilgi sızıntıları, vaatler) oturum kaydına yazılır.

Doğal Dil İşleme dersi projesi. Nasıl başladığı, alınan kararlar ve test oyunlarının
bulguları: [docs/PROJE_GUNLUGU.md](docs/PROJE_GUNLUGU.md).

## Hızlı başlangıç

Python 3.12 ile geliştirildi. Bir [Gemini API anahtarı](https://aistudio.google.com/apikey) gerekir.

```bash
pip install -r requirements.txt
cp .env.example .env          # GEMINI_API_KEY'i doldur
python web.py                 # web arayüzü: tarayıcıda http://127.0.0.1:8000 açılır
python oyun.py                # ya da terminalde oyna: seçenek numarası ya da serbest eylem, çıkış: q
python oyun.py --ayrinti      # terminalde editörün her sahnedeki bulgularını da göster
```

### Web arayüzü

[web.py](web.py) küçük bir yerel sunucu, [web/index.html](web/index.html) tek sayfalık arayüz.
Ek paket gerekmez. Sahneler sohbet gibi akar; seçenekler buton olarak gelir ya da serbest
eylem yazılır (klavyeden 1-4 de seçer). **Editör** düğmesi yan paneli açar: son sahnenin
çelişkileri, karakter uyarıları, vaat defteri, tanışılan karakterler ve tahmini harcama.
Sayfa yenilense de, sunucu kapanıp açılsa da oyun kaldığı yerden devam eder (aşağıda
**Kayıt ve devam**).

**↻ Yeniden yaz** son sahneyi geri alıp aynı eylemle yeniden yazdırır (olgular, vaatler,
eşyalar da geri alınır); komut satırında `y`.

Sunucu yalnızca bu bilgisayardan erişilir. `--host 0.0.0.0` ile aynı ağdaki telefondan da
açılabilir, ama o zaman ağdaki herkes senin API anahtarınla oynayabilir.

Ağ ya da API anahtarı olmadan denemek için:

```bash
python oyun.py --llm sahte --otomatik 5
python -m unittest discover testler -v
```

## Nasıl çalışır

Her turda **oyun motoru** ([hikaye/motor.py](hikaye/motor.py)):

1. Modele verilecek bağlamı kurar: varsayılan olarak **tüm sahneler**, dünyadan ilgili olgular
   ve sahnedeki karakterlerin kartları
2. Bağlamı, editörün önceki turdan notlarını ve oyuncunun eylemini **yazar modele** gönderir
3. Modelin JSON yanıtını doğrular ve sahneyi anlatım/replik parçalarından kendisi kurar
4. Sahneyi **editör modele** denetletir (aşağıda)
5. Her şeyi `oturumlar/*.jsonl` dosyasına yazar

### Kodla yapılan denetimler (modelden bağımsız)

Bazı sorunları modele sormak yerine kod her seferinde aynı şekilde yakalar. Bulunanlar
**uyarı** olarak kaydedilir ve editör açıksa bir sonraki turda yazara geri döner:

| Denetim | Ne yapar |
|---|---|
| Oyuncu adına konuşma | Modelin oyuncuya yazdığı replik atılır; oyuncunun sözünü oyuncu seçer |
| Tanışma | Adı sesli söylenmeyen karakter görünüşüyle etiketlenir ("İri yapılı kadın:"); anlatım ya da seçenek adını erken kullanırsa uyarı |
| Tekrar | Önceki sahneden aynen kopyalanan parçalar atılır; oyuncunun zaten yaptığını öneren seçenekler ayıklanır |
| Örnek replik | Karakter kartındaki örnek cümle aynen kullanılırsa uyarı |
| Konuşmayan karakter | Sahnedeki karakterler hiç konuşmadıysa uyarı |
| Bilinmeyen id | Dünyada olmayan karakter/mekân uydurulursa uyarı; konuşan adındaki küçük yazım kaymaları düzeltilir |
| Eylem ön denetimi | Eylemde geçen ama oyuncuda olmayan eşya (kılıç, ip, fener... Türkçe/İngilizce), daha önce elden çıkmış eşya ya da parasını aşan ödeme: yazara eylemin hemen önünde kesin not |
| Eşya ve akçe | Oyuncunun üzerindekiler takip edilir; olmayan eşya çıkarılamaz, yetmeyen akçe ödenemez; olmayan eşyayı kullanan seçenek uyarı üretir |
| Zaman | Saati kod tutar (oyun başından beri dakika). Editör her sahnenin süresini tahmin eder (yürüme, bekleme, uyku dahil); kod süreyi sınırlar (yer değiştiyse en az 10 dk, en fazla yarım gün), vakit adını ve gün sayısını kendisi çıkarır. Anlatım vakti açıkça söylerse ("sabahın ilk ışıkları") saat o vakte ileri sarılır. Zaman geri gitmez. Saat rakamı yazara gitmez, yalnızca vakit adı |
| Eylem | Yazara oyuncunun eyleminin hemen ardından "önce bu eylemi sonuçlandır; soruysa cevap versin" hatırlatması gider. Editör eylemin karşılanıp karşılanmadığını değerlendirir; açık "hayır"da bir sonraki tura not gider, "kısmen" yalnızca ölçülür |
| Konuşmasız sahne | Karakter var ama replik yoksa yazara not gider ve ölçüm için kaydedilir |
| Ses karışması | Bir karakter başka birinin imza sözünü (Nehir'in "evlat"ı) kullanırsa uyarı |

## Editör

Aynı dil modeline ikinci bir çağrı; bu kez hikâye yazdırılmaz, az önce yazılan
sahne denetletilir ([hikaye/editor.py](hikaye/editor.py)).

| `--editor` | Ne yapar |
|---|---|
| `yok` | Editör kapalı. Yeni olguları yazar modelin kendisi bildirir. |
| `denetim` | Sahnedeki somut iddiaları kanona karşı sınıflar: **yeni** (kanona eklenir, model sonra ona sadık kalır), **biliniyor**, **çelişiyor** (kaydedilir, bir sonraki turda yazara düzeltme uyarısı gider). Karakterleri kartlarına karşı denetler: **kişilik**, **konuşma üslubu**, **bilgi sızıntısı** (bilemeyeceği bir şeyi bilmek); oyuncuya bilemeyeceği bir şey atfedilmiş mi bakar. **Vaat defterini** (açılan, kanıtla ilerleyen, çözülen sorular) ve **karakter değişimlerini** tutar. |
| `tam` (varsayılan) | + sahneyi usta yazarların derslerinden çıkarılmış ölçütlerle değerlendirir ve yazara bir sonraki sahne için not yazar. |

Ölçütler [ilkeler/zanaat.yaml](ilkeler/zanaat.yaml) dosyasında; kaynakları ve
derslerin özetleri [ilkeler/KAYNAKLAR.md](ilkeler/KAYNAKLAR.md) içinde: Brandon
Sanderson, Andrew Stanton, Trey Parker ve Matt Stone, Robert McKee, Kurt Vonnegut,
Pixar, Mary Robinette Kowal, Dan Harmon, Orhan Pamuk. Dosyayı düzenleyerek
ölçüt eklenip çıkarılabilir.

Editörün yanıtı da kodla süzülür: tahmin ve zihinsel durum bildiren iddialar
("görünüyor", "düşünüyor", "istekli hale geldi") atılır; kanonla kök düzeyinde büyük
ölçüde örtüşen "yeni" iddialar "biliniyor"a çevrilir; sahne başına en fazla 3 yeni
olgu eklenir; kanıtsız vaat ilerlemesi sayılmaz; açık bir vaadin tekrarı açılmaz. Bu
düzeltmeler kayıtta `editor.otomatik` altında durur, editörün hata oranı buradan izlenir.

Editör her tur bir model çağrısı daha demek, yani süre yaklaşık iki katına çıkar.
Editör geçerli yanıt veremezse oyun durmaz; o tur editörsüz devam eder.

## Yazar modeli

| `--yazar` / web'de "Yazar modeli" | Ne | Tur başına |
|---|---|---|
| `hizli` (varsayılan) | Gemini 2.5 Flash, düşünmesiz | ~0,6-0,9 sent |
| `dusunen` | Aynı model, yazmadan önce düşünür (bütçe 1024 token) | ~1,5-2 kat |
| `guclu` | gemini-3.8-flash | ~1,5 kat (testte ~1,1 sent) |

Seçenek yalnızca yazarı etkiler; editör ve özet temel modelde kalır. Editör açıkken yazar
**hafif** çalışır: yalnızca sahneyi ve seçenekleri yazar; mekân, zaman, sahnedeki karakterler,
eşya/akçe değişimi ve olguları editör çıkarır.

## Rollere ayrı model

Yazar, editör ve özet farklı modellerle çalışabilir (`--editor-model`, `--ozet-model`
ya da `.env` içinde `EDITOR_MODEL`, `OZET_MODEL`). Özet basit bir iş, ucuz model yeter;
editör ise ölçümlerin kaynağı, zayıf model ölçümü de zayıflatır.

## Ölçüm

```bash
python olcum.py rapor                       # oturumlar/*.jsonl → tutarlılık raporu (ücretsiz)
python olcum.py enjeksiyon --ornek 25       # editörü bilinen çelişkilerle sına (ücretli, ~$0,25)
python olcum.py enjeksiyon --onceki olcumler/ham/<önceki>.json   # aynı sahne ve cümlelerle tekrar
```

- **rapor:** Kayıtlardaki editör ve kod bulgularını sayar. Bunlar editörün *dediği* şeylerdir:
  10 bin sözcük başına çelişki (CED), 10 turluk dilimler, karakter sapmaları, kod uyarıları
  türlerine göre, editörün başarısız olduğu turlar, maliyet.
- **enjeksiyon:** Editörün ne kadar *doğru* dediğini ölçer. Gerçek sahnelere sahneyle ilgili bir
  dünya olgusuyla çelişen tek bir cümle eklenir; editörün bunu yakalayıp yakalamadığına ve
  dokunulmamış sahnede alarm verip vermediğine bakılır. Ayrıntılar sahne metinleri içerdiği için
  `olcumler/ham/` altına yazılır (git'e girmez).

Sonuçlar ve sınırları: [docs/OLCUM.md](docs/OLCUM.md). Özetle: oyundaki ayarda editör eklenen
açık çelişkilerin %83-88'ini yakalıyor. Ama aynı test iki kez koşulduğunda kararların bir kısmı
değişiyor; 25 sahnelik bir testte 10 puana yakın fark gürültüdür.

## Bellek

| `--bellek` | Modele verilen |
|---|---|
| `tam` (varsayılan) | Hikâyenin **tüm** sahneleri + dünya ve oyun olguları arasından BM25 ile getirilen 6 olgu |
| `son` | Yalnızca son 2 sahne |
| `ozet` | Son 2 sahne + her sahneden sonra güncellenen hikâye özeti |
| `kanon` | Son 2 sahne + BM25 ile getirilen olgular |
| `ozet+kanon` | Son 2 sahne + ikisi birden |

Tüm seçeneklerde sahnedeki karakterlerin kartları ve oyuncunun şimdiye kadarki
eylemleri de gider. `tam`, sohbet uygulamalarının "hatırlaması" ile aynı şeydir:
her turda o ana kadarki her şey yeniden gönderilir. Gemini 2.5 Flash'ın bağlam
penceresi uzun bir oyunun tamamını rahatça alır. Diğerleri, oyun çok uzarsa maliyeti
düşürmek ya da karşılaştırma yapmak için var.

Getirim ([hikaye/getirim.py](hikaye/getirim.py)) Türkçeye göre ayarlı: `I/İ` doğru
küçültülür, kesme ekleri atılır, kök olarak ilk 5 harf alınır (F5 kök bulma).

## Dil modeli arka uçları

| `--llm` | Ne | Gerekli |
|---|---|---|
| `gemini` | Google Gemini API | `.env` içinde `GEMINI_API_KEY` |
| `yerel` | OpenAI uyumlu sunucu: Ollama, vLLM, LM Studio | `YEREL_LLM_URL`, `YEREL_LLM_MODEL` |
| `sahte` | Ağsız, sabit yanıtlı test modeli | — |

GPU'lu bir makinede çalışan bir model `yerel` ile bağlanır: sunucunun adresini
`YEREL_LLM_URL`'e yazmak yeterli. Bu yol henüz gerçek bir yerel modelle denenmedi.

## Kayıt ve devam

Oyun her turdan sonra kendiliğinden `kayitlar/` altına kaydedilir (sahneler, olgular, vaatler,
eşyalar, tanışılanlar, zaman, editör notları, harcama). Sunucu kapansa da bir şey kaybolmaz:
**Oyunlar** düğmesi kayıtlı oyunları listeler; **Devam et** kaldığın sahneden açar, **Yeniden
yaz** da çalışmaya devam eder. Tur kayıtları aynı `oturumlar/*.jsonl` dosyasına eklenmeye
sürer, yani ölçüm verisi bölünmez. Kayıt, yazılırken bozulmasın diye önce geçici dosyaya
yazılıp sonra yerine konur.

## Manga (isteğe bağlı)

Oynanan sahnelerden manga panelleri ve sayfaları çıkarır. **Varsayılan kapalı**, çünkü görsel
üretimi ek maliyet demek. Kapalıyken hiçbir şey çizilmez ve hiçbir yere gönderilmez.

- **Oyun sırasında:** Oyunlar penceresinde "Manga" seçilir (siyah-beyaz ya da renkli) ve bir
  görsel kaynağı seçilir. Her sahneden sonra paneller arka planda çizilir, oyun beklemez.
  Paneller sahnenin altında görünür; **Yeniden yaz** o sahnenin panellerini de yeniler. Başlamış
  bir oyunda üstteki **Manga** düğmesiyle açılabilir.
- **Kayıttan:** Kayıtlı oyunlar listesindeki **Manga** düğmesi oyunun tamamını çizer
  (daha önce çizilmiş sahneleri atlar) ve sayfaları dizer.

Nasıl çalışır ([hikaye/manga.py](hikaye/manga.py)):

1. **Görünüm:** Her karakterin ve mekânın İngilizce görsel tarifi (`prompt_en`). Dünya
   dosyasında yoksa model bir kez üretir, `manga/_gorunum/<dünya>.json` dosyasına yazar.
   Böylece bir karakter her panelde aynı tarifle çizilir.
2. **Plan:** Model her sahneyi 2-4 panele böler. Her panel için kamerayı (geniş/orta/yakın),
   panelde görünenleri, İngilizce eylemi ve hangi repliğin hangi panele gireceğini belirler.
   Planı kod doğrular: bilinmeyen karakter ve Türkçe etiket atılır, konuşan karakter panele
   eklenir. Model yanıt veremezse kod basit bir plan kurar. Sahne başına bir Gemini çağrısı;
   sahne metni zaten Gemini'ye gittiği için yeni bir paylaşım yok.
3. **Çizim:** Görsel servisi (`yerel`, `runpod` ya da `api`; hepsi aynı HTTP arayüzü) PNG
   döndürür. Adresler `.env` içinde (`MANGA_*_ADRES`, `MANGA_*_TOKEN`). Türkçe metin
   görsele gömülmez.
4. **Sayfa:** Paneller A4 sayfaya dizilir; konuşma balonları ve anlatım kutuları Pillow ile
   Türkçe yazılır. Sayfalar `http://127.0.0.1:8000/manga/<oyun>/` adresinde açılır.

Çıktı `manga/<oyun>/` klasöründedir (git'e girmez): paneller, `paneller.json` (her panelin
istemi, seed'i, replikleri) ve `sayfa_01.png`...

Görsel servisinin kendisi bu depoda değil. Görsel modeli henüz seçilmedi: ilk denemede
(Animagine XL, NoobAI XL) sonuçlar beğenilmedi, doğal dil anlayan modeller deneniyor.

## Kendi dünyanı kur

Web arayüzünde **Dünya kur** (ya da **Oyunlar** penceresinde "+ Kendi dünyanı kur"):

1. **Fikir:** Tür ve hikâyeyi birkaç cümleyle yazarsın; istersen kim olduğunu, mutlaka
   olmasını ve olmamasını istediklerini de eklersin.
2. **Taslak:** Model bu fikirden tam bir dünya kurar: mekânlar, karakterler (konuşma
   biçimleri ve imza sözleriyle), somut gerçekler, kurallar, para birimi, açılış. Senin
   yazdıklarını değiştirmez, yalnızca genişletir. Bir istek, dünya başına ~1 sent.
3. **Önizleme:** Kaydet, **Yeniden oluştur** ya da **Düzenle**. Düzenle, her alanı tek tek
   değiştirebileceğin ayrıntılı sihirbazı taslakla dolu açar. Ayrıntılı sihirbaz, modeli hiç
   kullanmadan boş da başlatılabilir ("Ayrıntılı kur").

Dünyayı oyun sırasında anlık uydurmak yerine başta toplu kurmak, editörün somut bir
kanona karşı denetim yapabilmesi için. Oyunun ihtiyaç duyduğu teknik alanları
[hikaye/dunya_kurucu.py](hikaye/dunya_kurucu.py) kurallarla çıkarır: kimlikler, metinde anılma
kalıpları (karakterde unvansız özel ad, mekânda "kule*" gibi kök kalıbı; "göl" gibi kısa
köklerde "gölge"yi yakalamasın diye tam çekimler), gerçeklerin hangi karakter ve mekânla
ilgili olduğu. Karakter sırları kanona girer; büyük sorular oyun başında açık vaat olur.
Kaydedilen dünya `dunyalar/` altında düz bir YAML dosyasıdır; listede kalır, elle de
düzenlenebilir. Yarım kalan fikir ve taslak tarayıcıda saklanır.

## Dünya dosyası

[dunyalar/tuzhan.yaml](dunyalar/tuzhan.yaml) örnek dünyadır (yapay zekâyla yazıldı): 5 mekân, 5 karakter,
14 olgu. Olgular bilerek somut seçildi (yedi numaralı oda kilitli, anahtar yalnızca
Nehir Hanım'da; kervanda on bir deve vardı...), çünkü tutarlılık bunlara karşı
ölçülecek. Karakterlerin konuşma üslupları da ölçülebilir işaretler taşıyor
("evlat", "abi/abla", "sevgili dostum").

Karakterlerde isteğe bağlı sabit özellikler: `hedef`, `yapabilir`, `yapamaz`, `esyalar` (oyun
başında üzerindekiler) ve `iliskiler` (diğer karakterin id'si → ona bakışı). Bunlar, `gorunum`'un
Türkçe alanlarıyla birlikte karakter kartında yazara gider. Dünya kurucuda da sorulur; boş
bırakılabilir.

**Oyun içinde değişen karakter durumu.** Her karakterin son bilinen yeri, üzerindekiler ve bedeni
(ör. "sol kolu sarılı") tutulur ve yazara "son bilinen durum (sahne N)" olarak gider.
- **Yer:** kod belirler; sahnede görülen karakter o sahnenin mekânındadır.
- **Eşya ve beden:** editör bildirir, kod doğrular. Karakterde olmayan eşya çıkamaz; reddedilen
  bildirim yalnızca kayda geçer.
- Editör panelindeki **Karakterler** sekmesi, görülen karakterlerin bu durumunu gösterir. Sırlar
  ve başlangıç eşyaları gösterilmez.

- **Oyuncu ile karakter arasında el değiştirme:** editör oyuncunun envanterini bildirirken eşyanın
  kime verildiğini ya da kimden alındığını da yazar ({"esya": "pusula", "kime": "nehir"}). Kod,
  eşya gerçekten oyuncudan çıktıysa karaktere geçirir. Karşı taraf almayı reddettiyse eşya oyuncuda kalır.

Gerçek denemelerde (toplam 14 tur):
- Yer takibi her seferinde doğruydu.
- Çocuğa verilen harita defteri ona geçti ve sonraki sahnede de ondaydı.
- Kadının almayı reddettiği pusula oyuncuda kaldı. Bu kural eklenmeden önceki denemede pusula ortadan
  kaybolmuştu.
- Örneklem çok küçük; eşya devrinin her durumda doğru işlediği kanıtlanmış değil.

Başka bir dünya için aynı biçimde yeni bir YAML yazıp `--dunya` ile verin. Karakterlerde
`adlar` alanına **yalnızca özel adlar** yazın: "yabancı", "çocuk" gibi sıradan kelimeler her
geçtikleri yerde o karakter sanılır. `gorunen_ad`, oyuncu tanışmadan önceki etikettir. Manga için isteğe bağlı alanlar:
karakterde `gorunum` (`sac`, `yuz`, `kiyafet`, `ayirt_edici`, `prompt_en`), mekânda
`prompt_en`, dünyada `gorsel_en` (dönem/ortam). Tuzhan'da hepsi dolu.

## Klasörler

```
web.py               web arayüzünün yerel sunucusu
web/index.html       web arayüzü (tek dosya)
oyun.py              komut satırı
hikaye/
  dunya.py           dünya kanonu (YAML) ve doğrulama
  dunya_kurucu.py    oyuncunun cevaplarından dünya dosyası
  durum.py           oynanan sahneler, oyun olguları, özet
  bellek.py          bellek stratejileri
  getirim.py         Türkçe BM25
  editor.py          editör: tutarlılık, vaat defteri, zanaat notları
  istem.py           tüm istem metinleri
  llm.py             dil modeli arka uçları
  motor.py           tur döngüsü ve yanıt doğrulama
  kayit.py           tur kaydı (JSONL) ve devam edilebilir oyun kaydı
  manga.py           manga: görünüm, panel planı, görsel servisi, sayfa ve balonlar
docs/                proje günlüğü
dunyalar/            dünya dosyaları
ilkeler/             usta yazar ölçütleri ve kaynak özetleri
testler/             birim testleri
oturumlar/           tur kayıtları, ölçüm verisi (git'e girmez)
kayitlar/            devam edilebilir oyun kayıtları (git'e girmez)
manga/               manga panelleri ve sayfaları (git'e girmez)
```

## Bilinen eksikler

Proje çalışıyor ve oynanabilir, ama bitmiş değil. Test oyunlarında görülen ve henüz
çözülmemiş sorunlar:

**Hikâye kalitesi**
- Anlatım bazen oyuncunun bilmediği bir şeyi sızdırıyor: henüz öğrenilmemiş bir akrabalık
  ("amcasının"), seçeneklerde daha duyulmamış bir ayrıntı.
- Ara sıra döneme uymayan sözcük ya da ayrıntı çıkıyor (Tuzhan'da "halüsinasyon", deve
  kervanında "tekerlek izi"). Dünya kuralı var, ama model her seferinde uymuyor.
- Model kendi kurduğu dünyada tarih ve süreleri bazen birbiriyle çelişkili yazabiliyor. İsteme
  kural eklendi, gerçek modelle yeniden denenmedi.

**Editör**
- Gürültülü: yanlış alarm veriyor (5 + 1 akçeyi "çelişki" sayması gibi), bazı çelişkileri
  kaçırıyor, önemsiz olguları kanona ekliyor.
- Zanaat puanları neredeyse hep tam; ölçüt olarak ayırt edici değil.
- Vaat ilerlemesinin kanıtı bazen zayıf.
- Eşya ve para değişimini editör çıkarıyor; editör kaçırırsa envanter yanlış kalıyor.
- Ara sıra geçerli yanıt veremiyor; o tur editörsüz geçiyor.

**Ölçüm** (projenin amaçlarından biri)
- Editörün doğruluğu yalnızca küçük bir enjeksiyon deneyiyle ölçüldü (25 sahne, tek cümlelik
  açık çelişkiler, elle doğrulanmamış). İnsan etiketi yok.
- Bellek seçenekleri (`tam`, `ozet`, `kanon`...) karşılaştırılmadı.

**Kullanım**
- Web sunucusu tek oyunculu: aynı anda tek oyun açık, tüm sekmeler aynı oyunu görür. Giriş ya
  da parola yok; yalnızca kendi bilgisayarında çalıştırmak için.
- Her tur iki model çağrısını sırayla bekliyor (yazar + editör); metin akış hâlinde gelmiyor.
- Her turda hikâyenin tamamı yeniden gönderiliyor; uzun oyunda maliyet artıyor. İstem
  önbelleği kullanılmıyor. En uzun test oyunu 24 tur.
- Yeniden yaz yalnızca son sahne için; sahneyi elle düzenleme ya da birkaç tur geri gitme yok.
- Dünyalar arayüzden silinemiyor ya da kaydedildikten sonra düzenlenemiyor (YAML dosyası elle düzenlenir).
- Komut satırı (`oyun.py`) kayıttan devam etmeyi desteklemiyor; bu yalnızca web arayüzünde var.
- `yerel` arka ucu gerçek bir yerel modelle denenmedi; testler yalnızca sahte modelle çalışıyor.
- Yalnızca Türkçe. Kök bulma kaba (ilk 5 harf); kısa köklerde getirim kaçırabiliyor.

**Manga**
- Görsel modeli seçilmedi; panellerin gerçek bir modelle nasıl göründüğü henüz bilinmiyor.
  Seçilecek model düz İngilizce cümle isterse `prompt_en` biçimi değişecek.
- Karakter tutarlılığı yalnızca aynı görünüm tarifine dayanıyor; karaktere özel model (LoRA)
  ya da referans görsel yok. Aynı karakter panelden panele farklı görünebilir.
- Balonlar panelin üstüne sırayla dizilir; yüzlerin üstüne gelip gelmediğine bakılmaz.
- Komut satırında (`oyun.py`) manga yok; yalnızca web arayüzünde.

## Yol haritası

- [x] Oynanabilir çekirdek, tüm hikâyeyi hatırlayan bellek, kayıt
- [x] Editör: kanona karşı iddia sınıflama, karakter denetimi, vaat defteri, zanaat notları
- [x] Kodla denetimler: oyuncu adına konuşma, tanışma, tekrar, örnek replik kopyası, eşya, para, zaman
- [x] Web arayüzü, yeniden yaz, yazar modeli seçeneği
- [x] Dünya kurucu: oyuncu fikrini yazar, model dünyayı kurar
- [x] Kayıt ve devam
- [x] Ölçüm: kayıtlardan tutarlılık raporu, editörü bilinen çelişkilerle sınayan enjeksiyon deneyi
- [ ] Editörün doğruluğunun elle kontrolü (~100 karar)
- [ ] Editörün en çok hata yaptığı iş için küçük, kendi eğittiğimiz bir model (ör. BERTurk ile
  çelişki tespiti); ~20-30 oyun ve 200-300 elle düzeltilmiş örnek biriktikten sonra
- [ ] Maliyet: istem önbelleği, kısa editör çıktısı
- [x] Manga: panel planı, sayfa dizme, Türkçe balonlar, ayar (varsayılan kapalı)
- [ ] Manga: görsel modelinin seçimi ve gerçek panellerle deneme

## Yapay zekâ kullanımı

Kod, örnek dünya Tuzhan ve `ilkeler/` klasöründeki özetler Claude (Anthropic) ile yazıldı.
Fikir, yön, test oyunları ve kararlar projenin sahibine ait. Ayrıntılar için
[docs/PROJE_GUNLUGU.md](docs/PROJE_GUNLUGU.md).
