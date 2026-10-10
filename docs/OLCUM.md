# Ölçüm sonuçları

Projenin amacı, hikâye uzadıkça karakterlerin ve olayların tutarlı kalmasını sağlamak ve
bunu **ölçmek**. Bu belge şimdiye kadarki ölçümleri ve sınırlarını özetliyor. Ölçümler
`python olcum.py` ile yeniden üretilebilir (bkz. [README](../README.md#ölçüm)). Yöntemin
kaynakları için [BENZER_PROJELER.md](BENZER_PROJELER.md) dosyasının 3. bölümüne bakın.

Tarih: 10 Ekim 2026 · Model: gemini-2.5-flash (editör, düşünmesiz, sıcaklık 0.2)

## 1. Kayıtlardan rapor: editör ne diyor?

Elimizdeki tüm editörlü test oyunları: 15 oturum, 93 tur, yaklaşık 9.500 sözcük, tek dünya
(Tuzhan, iki oturum Karınca Yolu). Burada sayılanlar editörün *kararlarıdır*, doğru oldukları
varsayılmaz.

| Ölçüt | Değer |
|---|---|
| Editörün bulduğu çelişki | 5 |
| CED (10 bin sözcük başına çelişki) | 5,24 |
| Oyuncuya bilgi sızıntısı (editör) | 7 |
| Editörün geçerli yanıt veremediği tur | 1 / 93 |
| Kodun editörü düzelttiği yerler | tür 19, tahmin 18, yeniden sınıflama 16, olgu sınırı 10, tekrar vaat 8, kanıtsız vaat 3 |
| Kod denetimleri | tanışma 39, biçim 5, eşya/para 2, ses karışması 1 |

Tüm çelişkiler ilk 10 turda. Ama 10. turdan sonraki veri tek bir oyundan geliyor (~1.700
sözcük); ConStory-Bench'in bulduğu "çelişkiler öykünün ortasında yığılır" etkisini sınamak için
çok az. Kodun editörü düzelttiği 74 yer, editörün ham çıktısının ne kadar gürültülü olduğunu
gösteriyor.

## 2. Enjeksiyon deneyi: editör ne kadar doğru diyor?

**Yöntem** (FlawedFictions, Ahuja vd. 2025): Gerçek oyun kayıtlarından 25 sahne seçildi
(tohum 7). Her sahne için mekânıyla ya da karakterleriyle ilgili bir dünya olgusu seçildi.
Gemini, sahnenin üslubunda bu olguyla açıkça çelişen tek bir cümle yazdı ve cümle sahnenin
ortasındaki bir anlatım paragrafına eklendi. Editör, oyundaki durumu kayıttan yeniden kurulmuş
hâliyle, orijinal ve bozulmuş sahneyi ayrı ayrı denetledi.

**Önce / sonra.** "Önce" mevcut editördü. "Sonra" bu sürümün editörüdür: çelişki kararı için
sahneden alıntı ister ve kod alıntıyı doğrular; kişiliğe uygun yalanı ve olaylarla değişen durumu
çelişki saymaz; olgularda bilgi etiketleri vardır. İki koşu **aynı 25 sahneyi ve aynı çelişki
cümlelerini** kullandı.

| Ölçüt | Önce | Sonra |
|---|---|---|
| Eklenen çelişkiyi doğru olguyla yakalama | 20/25 (%80) | 18/25 (%72) |
| Herhangi bir çelişki bulma | 20/25 (%80) | 19/25 (%76) |
| Dokunulmamış sahnede alarm | 4/25 (%16) | 3/25 (%12) |
| Alıntısı eklenen cümleyi gösteren | — | 19/19 |
| Editörün geçerli yanıt veremediği | 0 | 0 |
| Maliyet | $0,16 | $0,18 |

**Nasıl okunmalı:**
- **Fark istatistiksel olarak anlamsız.** 25 örnekte 2 sahnelik fark, editörün aynı sahnede
  farklı çalışmalarda farklı karar vermesiyle açıklanabilir. Bu deney "sonra daha iyi" ya da
  "daha kötü" demeye yetmiyor. Anlamlı bir karşılaştırma için örneklem büyütülmeli ve her sahne
  birkaç kez denetlenmeli.
- **Alıntı istemek işe yarıyor:** editörün gösterdiği alıntılar her seferinde gerçekten çelişen
  cümleydi. Bu, kararların insanca doğrulanmasını kolaylaştırıyor.
- **"Dokunulmamış sahnede alarm" yanlış alarm demek değil.** Orijinal sahneler test oyunlarından
  geliyor ve kendileri hatalı olabiliyor. "Sonra"daki 3 alarmın ikisi gerçek çelişki: oyuncunun
  olmayan bir tabancayı çekmesi (kural k1) ve "oda kirası yirmi akçe" (olgu o12: beş akçe).
  Biri yanlış alarm: kulenin yıkık basamakları (o10 ile uyumlu). Yani gerçek yanlış alarm oranı
  yaklaşık 1/25.
- **Yakalama oranı az ölçülmüş olabilir.** Eklenen cümleler elle doğrulanmadı ve bazıları çelişki
  değil. Örneğin "feneri sağ elinin beş parmağıyla sıkıyor" cümlesi, eksik parmakların *sol* elde
  olduğunu söyleyen o2 ile çelişmiyor. FlawedFictions bu yüzden üretilen her örneği elle
  doğruluyor; burada bu adım yapılmadı.

## 3. Sınırlar

- Örneklem küçük (25 sahne) ve neredeyse tamamı tek bir dünyadan.
- Eklenen çelişkiler tek cümlelik ve açık. İnce çelişkiler (zaman çizelgesi, birkaç sahneye
  yayılan mantık) ölçülmüyor; literatüre göre editörün asıl zorlandığı yer orası.
- Ölçüm, karakter sesi ve bilgi sızıntısı için bilinen bir doğru içermiyor.
- Editör ve çelişki yazarı aynı model. Literatür, aynı aileden modellerin birbirini kayırabileceğini
  söylüyor.
- Yazar envanteri ve bilgi etiketleri gibi oyun içi değişikliklerin etkisi, yeni oyunlar
  oynanmadan ölçülemez. Rapor betiği bunun için hazır.

## 4. Sonraki adımlar

1. Enjeksiyon setini elle doğrulamak (çelişki olmayan cümleleri ayıklamak) ve örneklemi ~100'e
   çıkarmak. Maliyet yaklaşık $0,70.
2. Editörün kararlarını insan etiketiyle karşılaştırmak (~100 karar, ikinci bir etiketleyiciyle).
3. Aynı set üzerinde BERTurk + NLI-TR ile LLM dışı bir dedektör denemek.
4. Yeni sürümle birkaç oyun oynayıp `olcum.py rapor` ile envanter uyuşmazlıklarını ve bilgi
   sızıntılarını eski oyunlarla karşılaştırmak.
