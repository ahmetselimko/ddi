# Türkçe İnteraktif Hikâye Oyunu — Uzun Anlatıda Tutarlılık

Oyuncunun seçimleriyle ilerleyen, sahnelerini bir dil modelinin yazdığı Türkçe
bir hikâye oyunu. Araştırma sorusu: **hikâye uzadıkça karakterlerin ve olayların
tutarlı kalması için modele neyi hatırlatmak gerekir?**

## Hızlı başlangıç

```bash
cp .env.example .env          # GEMINI_API_KEY'i doldur
python oyun.py                # oyna: seçenek numarası ya da serbest eylem, çıkış: q
```

Ağ ya da API anahtarı olmadan denemek için:

```bash
python oyun.py --llm sahte --otomatik 5
python -m unittest discover testler -v
```

## Nasıl çalışır

Her turda **oyun motoru** ([hikaye/motor.py](hikaye/motor.py)):

1. **Bellek stratejisi** ile modele verilecek bağlamı kurar
2. Bağlamı ve oyuncunun eylemini **dil modeline** gönderir
3. Modelin JSON yanıtını doğrular: sahne, mekân, karakterler, replikler, yeni olgular, seçenekler.
   Dünyada olmayan bir karakter ya da mekân uydurulmuşsa bunu **uyarı** olarak kaydeder.
4. Yeni olguları oyun kanonuna ekler; her şeyi `oturumlar/*.jsonl` dosyasına yazar

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

Başka bir dünya için aynı biçimde yeni bir YAML yazıp `--dunya` ile verin.

## Klasörler

```
oyun.py              komut satırı
hikaye/
  dunya.py           dünya kanonu (YAML) ve doğrulama
  durum.py           oynanan sahneler, oyun olguları, özet
  bellek.py          bellek stratejileri
  getirim.py         Türkçe BM25
  istem.py           tüm istem metinleri
  llm.py             dil modeli arka uçları
  motor.py           tur döngüsü ve yanıt doğrulama
  kayit.py           oturum kaydı (JSONL)
dunyalar/            dünya dosyaları
testler/             birim testleri
oturumlar/           oyun kayıtları (git'e girmez)
```

## Yol haritası

- [x] **Aşama 1:** oynanabilir çekirdek, 4 bellek stratejisi, kayıt
- [ ] **Aşama 2:** tutarlılık ölçümü
  - olgu çelişkisi: üretilen sahneleri kanona karşı denetleme (otomatik + elle örneklem)
  - karakter sesi: replikten konuşanı tahmin eden sınıflandırıcı; üretilen replikler doğru karaktere atanıyor mu
  - uydurma oranı: kayıttaki bilinmeyen karakter/mekân uyarıları
- [ ] **Aşama 3:** deney: aynı tohumlarla her stratejide N turluk otomatik oyunlar, sonuç tabloları
