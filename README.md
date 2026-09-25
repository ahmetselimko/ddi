# Türkçe İnteraktif Hikâye Oyunu — Uzun Anlatıda Tutarlılık

Oyuncunun seçimleriyle ilerleyen, sahnelerini bir dil modelinin yazdığı Türkçe
bir hikâye oyunu. Araştırma sorusu: **hikâye uzadıkça karakterlerin ve olayların
tutarlı kalması için modele neyi hatırlatmak gerekir?**

## Hızlı başlangıç

```bash
cp .env.example .env          # GEMINI_API_KEY'i doldur
python oyun.py                # oyna: seçenek numarası ya da serbest eylem, çıkış: q
python oyun.py --ayrinti      # editörün her sahnedeki bulgularını da göster
```

Ağ ya da API anahtarı olmadan denemek için:

```bash
python oyun.py --llm sahte --otomatik 5
python -m unittest discover testler -v
```

## Nasıl çalışır

Her turda **oyun motoru** ([hikaye/motor.py](hikaye/motor.py)):

1. **Bellek stratejisi** ile modele verilecek bağlamı kurar
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

## Rollere ayrı model

Yazar, editör ve özet farklı modellerle çalışabilir (`--editor-model`, `--ozet-model`
ya da `.env` içinde `EDITOR_MODEL`, `OZET_MODEL`). Özet basit bir iş, ucuz model yeter;
editör ise ölçümlerin kaynağı, zayıf model ölçümü de zayıflatır.

## Bellek stratejileri (deneyin bağımsız değişkeni)

| `--bellek` | Modele verilen |
|---|---|
| `son` | Son 2 sahne + sahnedeki karakterlerin kartları (taban çizgisi) |
| `ozet` | + her sahneden sonra güncellenen hikâye özeti |
| `kanon` | + dünya ve oyun olguları arasından BM25 ile getirilen 6 olgu |
| `ozet+kanon` | ikisi birden (varsayılan) |

Getirim ([hikaye/getirim.py](hikaye/getirim.py)) Türkçeye göre ayarlı: `I/İ` doğru
küçültülür, kesme ekleri atılır, kök olarak ilk 5 harf alınır (F5 kök bulma).

## Dil modeli arka uçları

| `--llm` | Ne | Gerekli |
|---|---|---|
| `gemini` | Google Gemini API | `.env` içinde `GEMINI_API_KEY` |
| `yerel` | OpenAI uyumlu sunucu: Ollama, vLLM, LM Studio | `YEREL_LLM_URL`, `YEREL_LLM_MODEL` |
| `sahte` | Ağsız, sabit yanıtlı test modeli | — |

Hocanın GPU'lu makinesinde çalışan bir model `yerel` ile bağlanır: sunucunun
adresini `YEREL_LLM_URL`'e yazmak yeterli.

## Dünya dosyası

[dunyalar/tuzhan.yaml](dunyalar/tuzhan.yaml) örnek dünyadır: 5 mekân, 5 karakter,
14 olgu. Olgular bilerek somut seçildi (yedi numaralı oda kilitli, anahtar yalnızca
Nehir Hanım'da; kervanda on bir deve vardı...), çünkü tutarlılık bunlara karşı
ölçülecek. Karakterlerin konuşma üslupları da ölçülebilir işaretler taşıyor
("evlat", "abi/abla", "sevgili dostum").

Başka bir dünya için aynı biçimde yeni bir YAML yazıp `--dunya` ile verin. Karakterlerde
`adlar` alanına **yalnızca özel adlar** yazın: "yabancı", "çocuk" gibi sıradan kelimeler her
geçtikleri yerde o karakter sanılır. `gorunen_ad`, oyuncu tanışmadan önceki etikettir.

## Klasörler

```
oyun.py              komut satırı
hikaye/
  dunya.py           dünya kanonu (YAML) ve doğrulama
  durum.py           oynanan sahneler, oyun olguları, özet
  bellek.py          bellek stratejileri
  getirim.py         Türkçe BM25
  editor.py          editör: tutarlılık, vaat defteri, zanaat notları
  istem.py           tüm istem metinleri
  llm.py             dil modeli arka uçları
  motor.py           tur döngüsü ve yanıt doğrulama
  kayit.py           oturum kaydı (JSONL)
dunyalar/            dünya dosyaları
ilkeler/             usta yazar ölçütleri ve kaynak özetleri
testler/             birim testleri
oturumlar/           oyun kayıtları (git'e girmez)
```

## Yol haritası

- [x] **Aşama 1:** oynanabilir çekirdek, 4 bellek stratejisi, kayıt
- [x] **Editör:** kanona karşı iddia sınıflama, vaat defteri, karakter değişimleri, zanaat notları
- [ ] **Aşama 2:** ölçüm
  - oyundan bağımsız değerlendirici: kayıtlı oturumları sonradan aynı editörle tarar, böylece
    editörsüz oyunlar da aynı ölçüyle ölçülür
  - editörün kendi doğruluğu: işaretlediği çelişkilerden bir örneklemin elle kontrolü
  - karakter sesi: replikten konuşanı tahmin eden sınıflandırıcı; üretilen replikler doğru karaktere atanıyor mu
  - vaatler: kaç vaat açıldı, kaçı çözüldü, ortalama kaç sahne açık kaldı
- [ ] **Aşama 3:** deney: bellek (4) × editör (3) koşulunda, aynı tohumlarla N turluk otomatik oyunlar, sonuç tabloları
