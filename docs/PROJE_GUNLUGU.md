# Proje Günlüğü

Doğal Dil İşleme dersi projesi: **Türkçe interaktif hikâye oyunu.** Bu belge, projenin
geliştirildiği sohbetin derli toplu özetidir: nasıl başladığı, hangi kararların neden
alındığı, test oyunlarında neler görüldüğü ve sırada ne olduğu. Nasıl kurulup
çalıştırılacağı için [README](../README.md).

Son güncelleme: 27 Eylül 2026 · 86 birim testi · ~6.300 satır

---

## 1. Kısaca

Oyuncunun seçimleriyle ilerleyen, sahnelerini bir dil modelinin (Gemini) yazdığı Türkçe bir
hikâye oyunu. Odak noktası: **hikâye uzadıkça karakterlerin ve olayların tutarlı kalmasını
sağlamak ve bunu ölçmek.**

Bugünkü hâli:
- Web arayüzünden oynanıyor; oyuncu isterse kendi dünyasını birkaç cümleyle kurduruyor.
- Her sahneyi ikinci bir model çağrısı ("editör") denetliyor; bir kısım denetimi de kod,
  modelden bağımsız yapıyor.
- Oyunlar her turdan sonra kaydediliyor, sonradan kaldığı yerden sürüyor.
- Her tur ayrıntılı olarak kaydediliyor (`oturumlar/*.jsonl`); tutarlılık ölçümü bu kayıtlardan yapılacak.

## 2. Nasıl başladı

Derse iki fikir sunuldu:
1. **Mevzuat soru-cevap sistemi:** yapı mevzuatı üzerinde soruya ilgili maddeleri bulup cevap veren bir sistem.
2. **Türkçe interaktif hikâye oyunu:** oyuncunun seçimleriyle ilerleyen, metni dil modelinin
   ürettiği bir oyun; odak, uzun anlatıda tutarlılık.

İkincisi seçildi. Hocaya yazılan e-postadaki tanım projenin amacı olarak korunuyor:
*"Odak noktası, hikâye uzadıkça karakterlerin ve olayların tutarlı kalmasını sağlamak ve bunu ölçmek."*

> Not: Geliştirmenin başında yapay zekâ asistanı bu amacı "dört bellek yöntemini karşılaştıran
> bir deney" diye genişletmişti. Öğrenci bunu düzeltti: amaç **oynanabilir bir oyun**; ölçüm
> için oyunun zaten tuttuğu kayıtlar yeterli. Bellek seçenekleri kodda isteğe bağlı olarak duruyor.

## 3. Yapı

```
Oyuncu eylemi
   │
   ├─ Kod: eylem ön denetimi ─────────────── olmayan eşya? yetmeyen para?
   │
   ▼
Yazar model ── hikâyenin tamamı + dünya kuralları + ilgili olgu ve kartlar + editör notları
   │            (yalnızca sahneyi ve seçenekleri yazar)
   ▼
Kod: sahneyi kurar ────────────────────── oyuncu adına konuşma atılır, tanışma, tekrar,
   │                                        imza sözü karışması, gün sayısı, seçenek denetimi
   ▼
Editör model ── mekân/zaman/karakterler/eşya değişimi, iddialar (yeni·biliniyor·çelişiyor),
   │             karakter denetimi, vaat defteri, usta yazar ölçütleri, yazara not
   ▼
Kod: editörü süzer ─────────────────────── tahmin/duygu atılır, kanonla örtüşen "yeni" düzeltilir,
   │                                        olgu ve vaat sınırları
   ▼
Kayıt (oturumlar/*.jsonl) + otomatik oyun kaydı (kayitlar/*.json)
```

## 4. Kararlar ve nedenleri

| Karar | Neden |
|---|---|
| **Gemini API, sohbet uygulaması değil** | Sohbet aboneliği programla sürülemez (kullanım şartları); editör, kod denetimleri ve kayıt sohbette çalışmaz. API maliyeti zaten düşük (§7). |
| **Bellek varsayılanı: hikâyenin tamamı** | Sohbet uygulamalarının "hatırlaması" da budur. Gemini'nin bağlam penceresi uzun bir oyunu rahatça alıyor. Kısa bellek seçenekleri çok uzun oyunlar için duruyor. |
| **Editör: ikinci model çağrısı** | Yazar hem yazıp hem denetleyemiyor. Editör, yazarı bir sonraki turda notlarla yönlendiriyor. |
| **Denetimlerin bir kısmı kodla** | Modelin yargısı gürültülü (yanlış alarm, kaçan çelişki). Olmayan eşya, para, gün sayısı, tanışma, imza sözü gibi kurallar kodla her seferinde aynı sonucu veriyor. |
| **Usta yazar ölçütleri** ([ilkeler/](../ilkeler/KAYNAKLAR.md)) | Sanderson, Stanton, Parker & Stone, McKee, Vonnegut, Pixar, Kowal, Harmon, Pamuk. Ölçüm için değil, **yönlendirme** için: modelin kalite yargısına güvenilmiyor. |
| **Editör notları istemin sonunda** | Modeller üretime en yakın talimata daha çok uyuyor (AI Dungeon'daki "Author's Note" gibi). |
| **Hafif yazar** | Yazar yalnızca sahneyi ve seçenekleri yazıyor; form doldurma yükü düz yazının kalitesini düşürüyordu. Sahne bilgilerini editör çıkarıyor. |
| **Sahne = anlatım/replik parçaları** | İlk sürümde model konuşmaları ayrı alana yazıp sahneye koymuyordu; artık metni kod kuruyor, konuşan kesin biliniyor. |
| **Mekâna bağlı olgular her zaman yazara gidiyor** | Türkçe kısa köklerde BM25 kaçırıyordu ("kuleye" ≠ "kulenin"): ipsiz kuleye tırmanıldı, soğuk demirhanede fırın yandı. |
| **Dünyayı oyuncu kurar, model genişletir** | Oyuncu birkaç cümle yazıyor; model somut bir kanon kuruyor; oyuncu önizleyip kaydediyor. Dünyayı oyun sırasında anlık uydurmak yerine başta kurmak, editöre somut bir kanon veriyor. |
| **Yazar modeli seçenekli** | Hızlı (varsayılan) / düşünen / güçlü (gemini-3.8-flash). Yalnızca yazarı etkiler, editör ucuz modelde kalır. |
| **Kendi modelini eğitmek: şimdilik hayır** | Yazar için Gemini'yi geçmek gerçekçi değil. Editörün dar işleri (çelişki, iddia türü, karakter sesi) için küçük modeller mantıklı, ama önce veri birikmeli (§9). |

## 5. İlk oyunlarda görülenler ve düzeltmeler

| Görülen | Düzeltme |
|---|---|
| Karakterler hiç konuşmadı; model replikleri sahneye koymadı | Sahne anlatım/replik parçalarından kod tarafından kuruluyor |
| Tutarlılık kuralları modeli pasifleştirdi, hikâye ilerlemedi | "Eylemin sonucunu göster, sır susarak değil kaçamak cevapla saklanır" |
| Editörün "ima et" notu karakterleri susturdu | Stanton'ın 2+2 ilkesi "cevabı esirgemek değildir" diye yeniden yazıldı |
| Model oyuncunun ağzından konuştu, oyuncuya bilgi sızdırdı | Oyuncu replikleri atılıyor; editör oyuncu bilgi sızıntısını denetliyor |
| Tanışılmayan karakter adıyla anıldı | Görünüş adı etiketi; ad ancak söylenince tanışma sayılıyor |
| Hikâye döngüye girdi, sahne kopyalandı | Oyuncunun eylem geçmişi her turda gidiyor; tekrar eden parça ve seçenek kodla atılıyor |
| Olmayan silahla ateş edildi; vurulan karakter saldırganını içeri davet etti | Eşya/para takibi, dünya kuralları, karakterin yaşadıklarının hatırlatılması |

## 6. 24 turluk test oyunu (26 Eylül)

Oyun, alışılmadık ve zorlayıcı eylemlerle 24 tur oynandı; bulunan sorunlar düzeltilip 7 turla yeniden denendi.

| Durum | İlk test | Düzeltmeden sonra |
|---|---|---|
| Olmayan kılıcı kullanmak (İngilizce) | ❌ Kılıç uyduruldu, hikâyede kaldı | ✅ "Kılıcın yok. Elin boşluğa uzanıyor." |
| 15 akçeyle 50 akçe teklif | ❌ Para uzatıldı | ✅ "Cebinden yalnızca on beş akçe çıkıyor." |
| İpsiz kuleye tırmanmak | ❌ Tepeye çıktı | ✅ "Merdivenlerin yarısı yok olmuş." |
| Soğuk demirhane (körük kırık) | ❌ "Kızıl fırın, çekiç sesleri" | ✅ "Çekiç sesleri gelmiyor" |
| Demircinin sesi | ❌ Hancının "evlat"ını kullandı | ✅ Atasözüyle konuşuyor |
| Anlamsız girdi, talimat verme girişimi | ❌ Model oyuncunun yerine seçenek seçti | ✅ "Söylediğin tuhaf sesler" |
| Gün sayısı | ❌ Hep "1. gün" | ✅ Sabah olunca "2. gün" |
| Tokat → hemen özür; 17 sahne sonra dönüş | ✅ Affetmedi; ✅ hatırladı | — |

Güçlü yazar (gemini-3.8-flash) iki turda belirgin biçimde daha zengin ve dünyayla tutarlı
anlatım verdi; tur başına maliyeti hızlının ~1,5 katı.

## 7. Maliyet (ücretli katman, Gemini 2.5 Flash)

| | |
|---|---|
| Tur başına (yazar + editör) | ~0,6-0,9 sent, hikâye uzadıkça yavaşça artar |
| 20 turluk oyun | ~15 sent |
| Dünya taslağı kurmak | ~0,6 sent |
| Geliştirme boyunca tüm testler | ~0,5 dolar |

Harcamanın çoğu çıktı token'larından geliyor. Ucuzlatma seçenekleri (henüz yapılmadı):
ücretsiz katman anahtarıyla geliştirme, önbelleğe uygun istem sırası, editör çıktısını kısaltmak.

## 8. Açık sorunlar

- **Anlatım bazen bilgi sızdırıyor:** oyuncunun bilmediği akrabalıklar, seçeneklerde henüz duyulmamış ayrıntılar.
- **Editör gürültülü:** yanlış alarm ("5 + 1 akçe çelişki"), kaçan çelişki, önemsiz olgular; zanaat puanları çoğunlukla 8/8.
- **Envanter değişikliği editörün fark etmesine bağlı:** bazen kaçıyor.
- **Ara sıra anakronizm:** "halüsinasyon" sözcüğü, deve kervanında "tekerlek izi".
- **Model kurduğu dünyada bazen kendiyle çelişebiliyor:** tarih ve süre tutarsızlıkları; istemde kural var, gerçek modelle yeniden denenmedi.

## 9. Sonraki adımlar

1. **Ölçüm:** Birkaç oyun oynayıp editörün 100 kararını elle kontrol etmek; hangi işte ne kadar hata yaptığını görmek.
2. **Kendi modellerimiz:** En çok hata yapılan işte küçük bir model eğitmek, büyük ihtimalle
   çelişki tespiti (NLI, BERTurk + NLI-TR + oyunlardan etiketlenmiş çiftler). Sonra iddia türü
   sınıflandırıcı ve karakter sesi sınıflandırıcı. Gemini editörüyle aynı test örneklerinde
   karşılaştırmak. Eşik: ~20-30 oyun ve 200-300 elle düzeltilmiş örnek. Gemini çıktılarıyla
   model eğitmeden önce kullanım şartları kontrol edilmeli.
3. **İsteğe bağlı:** Sahneyi elle düzenleme (AI Dungeon'daki gibi), dünya kurucuda alan başına "öner" düğmesi, maliyet düşürme.

## 10. Yapay zekâ kullanımı

Kod, demo dünya **Tuzhan** ve `ilkeler/` klasöründeki ölçüt ve özetler Claude (Anthropic) ile
yazıldı. Projenin fikri, yönü, test oyunları, bulguların değerlendirilmesi ve hangi özelliklerin
nasıl olacağına dair kararlar öğrenciye ait. Commit'lerdeki `Co-Authored-By` satırları bunu gösterir.

## 11. Sürüm geçmişi

| Tarih | Değişiklik |
|---|---|
| 24.09 | Oynanabilir çekirdek: dünya kanonu, bellek seçenekleri, Türkçe BM25, kayıt |
| 25.09 | Editör model, vaat defteri, usta yazar ölçütleri |
| 25.09 | Sahne akışı; karakter tutarlılığı, oyuncu özgürlüğü, kod denetimleri; tam bellek; tanışma |
| 26.09 | Web arayüzü; eşya ve dünya kuralları; tekrarlanan sözcükler |
| 26.09 | Yeniden yaz, hafif yazar, yazar modeli seçeneği; 24 turluk testin düzeltmeleri |
| 27.09 | Dünya kurucu (oyuncu yazar), dünya taslağı (model genişletir) |
| 27.09 | Kayıt ve devam |
