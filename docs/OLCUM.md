# Ölçüm sonuçları

Projenin amacı, hikâye uzadıkça karakterlerin ve olayların tutarlı kalmasını sağlamak ve
bunu **ölçmek**. Bu belge şimdiye kadarki ölçümleri ve sınırlarını özetliyor. Komutlar için
[README](../README.md#ölçüm), yöntemin kaynakları için
[BENZER_PROJELER.md](BENZER_PROJELER.md) (3. bölüm).

Tarih: 10 Ekim 2026 · Model: gemini-2.5-flash

## 1. Kayıtlardan rapor: editör ne diyor? (`olcum.py rapor`, ücretsiz)

Editörlü tüm test oyunları: 15 oturum, 93 tur, ~9.500 sözcük; çoğu Tuzhan'dan. Sayılanlar
editörün *kararlarıdır*; doğru oldukları varsayılmaz.

| Ölçüt | Değer |
|---|---|
| Editörün bulduğu çelişki | 5 |
| CED (10 bin sözcük başına çelişki) | 5,24 |
| Oyuncuya bilgi sızıntısı (editör) | 7 |
| Editörün geçerli yanıt veremediği tur | 1 / 93 |
| Kodun editörü düzelttiği yerler | tür 19, tahmin 18, yeniden sınıflama 16, olgu sınırı 10, tekrar vaat 8, kanıtsız vaat 3 |
| Kod denetimleri | tanışma 39, biçim 5, eşya/para 2, ses karışması 1 |

10. turdan sonrasına ait veri tek bir oyundan geliyor; çelişkilerin hikâyenin neresinde
yığıldığını söylemek için yetersiz.

## 2. Enjeksiyon deneyi: editör ne kadar doğru diyor? (`olcum.py enjeksiyon`, ücretli)

**Yöntem** (FlawedFictions'tan uyarlandı):
- Gerçek oyun kayıtlarından 25 sahne seçilir.
- Gemini her sahneye, sahneyle ilgili bir dünya olgusuyla açıkça çelişen tek bir cümle yazar; cümle sahneye eklenir.
- Editör, oyundaki durumu kayıttan yeniden kurulmuş hâliyle, orijinal ve bozulmuş sahneyi ayrı ayrı denetler.
- Üç koşu da **aynı 25 sahneyi ve aynı cümleleri** kullandı.

| Koşu | Editör modu | Eklenen çelişkiyi doğru olguyla yakalama | Dokunulmamış sahnede alarm | Maliyet |
|---|---|---|---|---|
| 1 | denetim | 20/25 (%80) | 4/25 (%16) | $0,16 |
| 2 | **tam** (oyundaki ayar) | 22/25 (%88) | 4/25 (%16) | $0,24 |
| 3 | **tam**, aynısının tekrarı | 20/24 (%83) | 3/24 (%12,5) | $0,23 |

**Koşudan koşuya oynama.** 2. ve 3. koşu birebir aynı ayar ve girdiyle yapıldı. Yine de 25
sahnenin 2'sinde yakalama kararı, 3'ünde alarm kararı değişti. 3. koşuda bir sahnede editör
geçerli yanıt veremedi. Bu boyuttaki bir testte **8-12 puanlık fark gürültüdür**. Bir değişikliğin
işe yaradığını söylemek için daha büyük örneklem ve sahne başına birkaç tekrar gerekir.

**Bundan çıkan ders.** Bu deney ilk kez, bir değişikliğin ardından "%80'den %72'ye düştü" sonucu
vermişti. O fark da bu gürültünün içindeydi; ne iyileşme ne kötüleşme gösteriyordu. O
değişiklikler (alıntı süzgeci, yalan muafiyeti, olgulara bilgi etiketi, yazarın envanter
bildirmesi) faydası gösterilemediği ve bazılarının yan etkisi olabileceği için geri alındı.

**Nasıl okunmalı:**
- **Editör açık çelişkileri çoğunlukla yakalıyor:** oyundaki `tam` ayarında %83-88. Ama eklenen
  çelişkiler tek cümlelik ve bariz. Literatüre göre editörün zorlandığı ince ve dağınık çelişkiler
  burada ölçülmüyor.
- **"Dokunulmamış sahnede alarm" yanlış alarm demek değil.** Orijinal sahneler test oyunlarından
  geliyor ve kendileri hatalı olabiliyor. Örnekler arasında gerçek çelişkiler var: oyuncunun
  olmayan bir tabancayı çekmesi (kural k1) ve "oda kirası yirmi akçe" (olgu o12: beş akçe).
- **Eklenen cümleler elle doğrulanmadı ve bazıları çelişki değil.** Örneğin "feneri sağ elinin
  beş parmağıyla sıkıyor" cümlesi, eksik parmakların *sol* elde olduğunu söyleyen o2 ile
  çelişmiyor. Yakalama oranı bu yüzden olduğundan düşük görünüyor olabilir.

## 3. Sınırlar

- Örneklem küçük (25 sahne) ve neredeyse tamamı tek bir dünyadan.
- Yalnızca tek cümlelik, açık çelişkiler ölçülüyor. Karakter sesi ve bilgi sızıntısı için bilinen
  bir doğru yok.
- Editör ile çelişki yazarı aynı model.

## 4. Sonraki adımlar

1. Enjeksiyon cümlelerini elle ayıklamak (çelişki olmayanları atmak).
2. Örneklemi ~100 sahneye çıkarıp her birini 2-3 kez denetlemek. Maliyet ≈ $2-3. Bir değişikliği
   ancak bundan sonra karşılaştırmak anlamlı olur.
3. Editörün kararlarını insan etiketiyle karşılaştırmak (~100 karar).
4. Aynı set üzerinde BERTurk + NLI-TR ile LLM dışı bir dedektör denemek.
