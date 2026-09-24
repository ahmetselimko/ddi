"""Modele giden istemler. Tüm metin kalıpları burada."""
from .durum import Sahne
from .dunya import Dunya

_SISTEM = """Sen Türkçe bir interaktif hikâye oyununun anlatıcısısın.

DÜNYA: {ad}
TON: {ton}
OYUNCU: {oyuncu}

MEKÂNLAR (id: ad — tanım):
{mekanlar}

KARAKTERLER (id: ad):
{karakterler}

KURALLAR:
1. Oyuncuya ikinci tekil şahısla, şimdiki zamanda anlat ("Kapıyı itiyorsun.").
2. Her sahne 120-220 kelime olsun. Oyuncunun yerine karar verme; sahneyi bir seçim anında bitir.
3. Karakterleri kartlarındaki kişilik ve konuşma üslubuyla konuştur. Bir karakter bilmediği bir şeyi söylemesin.
4. Verilen olgularla, özetle ve önceki sahnelerle çelişme. Emin olmadığın ayrıntıyı uydurma, belirsiz bırak.
5. Oyuncu dünyaya aykırı bir şey yapmaya çalışırsa, bunun neden olmadığını hikâyenin içinde göster.
6. Yalnızca aşağıdaki biçimde JSON döndür, başka hiçbir şey yazma.

{{
  "sahne": "sahnenin anlatımı",
  "mekan": "sahnenin geçtiği mekânın id'si (yukarıdaki listeden)",
  "karakterler": ["sahnede bulunan karakterlerin id'leri"],
  "replikler": [{{"karakter": "id", "metin": "o karakterin bu sahnede söylediği replik, sahnedeki haliyle aynen"}}],
  "yeni_olgular": [{{"metin": "bu sahnede kesinleşen yeni bir gerçek", "ilgili": ["karakter/mekân id'leri"]}}],
  "secenekler": ["oyuncunun yapabileceği birbirinden farklı 3 şey"]
}}

yeni_olgular: yalnızca ileride önemli olacak kalıcı gerçekler (0-3 adet) — biri bir sır açtı,
bir eşya el değiştirdi, bir yer keşfedildi, bir söz verildi. Zaten bilineni tekrar yazma."""

_OZET_SISTEM = (
    "Bir interaktif hikâyenin özetini tutuyorsun. Kısa, olgusal ve Türkçe yaz. "
    "Yalnızca güncellenmiş özeti döndür."
)


def sistem_istemi(dunya: Dunya) -> str:
    return _SISTEM.format(
        ad=dunya.ad,
        ton=dunya.ton,
        oyuncu=dunya.oyuncu,
        mekanlar="\n".join(f"- {m.id}: {m.ad} — {m.tanim}" for m in dunya.mekanlar.values()),
        karakterler="\n".join(f"- {k.id}: {k.ad}" for k in dunya.karakterler.values()),
    )


def sahne_metni(sahne: Sahne, dunya: Dunya) -> str:
    mekan = dunya.mekanlar[sahne.mekan].ad
    eylem = f"Oyuncunun eylemi: {sahne.eylem}\n" if sahne.eylem else ""
    return f"Sahne {sahne.no} ({mekan})\n{eylem}{sahne.metin}"


def sahne_istemi(dunya: Dunya, baglam, eylem: str | None) -> str:
    bolumler = []
    if baglam.ozet:
        bolumler.append(f"[HİKÂYENİN ŞİMDİYE KADARKİ ÖZETİ]\n{baglam.ozet}")
    if baglam.olgular:
        bolumler.append("[BİLİNEN OLGULAR]\n" + "\n".join(f"- {o}" for o in baglam.olgular))
    if baglam.karakter_kartlari:
        bolumler.append("[İLGİLİ KARAKTERLER]\n" + "\n\n".join(baglam.karakter_kartlari))

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
