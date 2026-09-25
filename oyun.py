"""
Türkçe interaktif hikâye oyunu — komut satırı.

  python oyun.py                                   # demo dünya, Gemini, özet+kanon bellek, tam editör
  python oyun.py --ayrinti                         # editörün bulgularını da göster
  python oyun.py --bellek son --editor yok         # taban çizgisi: yalnızca son sahneler, editörsüz
  python oyun.py --llm yerel --model qwen2.5:7b    # OpenAI uyumlu yerel sunucu (Ollama, vLLM)
  python oyun.py --llm sahte --otomatik 10         # ağsız deneme, 10 tur kendi oynar

Oyunda seçeneğin numarasını ya da serbest bir eylem yaz; çıkmak için q.
"""
import argparse
import random
import sys
import textwrap
from pathlib import Path

from hikaye.bellek import STRATEJILER, Bellek
from hikaye.dunya import dunya_yukle
from hikaye.editor import MODLAR, Editor
from hikaye.kayit import Kayitci
from hikaye.llm import env_yukle, llm_olustur
from hikaye.motor import Motor, YanitHatasi

KOK = Path(__file__).parent


def sahne_yazdir(sahne, dunya) -> None:
    print(f"\n── Sahne {sahne.no} · {dunya.mekanlar[sahne.mekan].ad} " + "─" * 30)
    for paragraf in sahne.metin.split("\n"):
        if paragraf.strip():
            print(textwrap.fill(paragraf.strip(), 88))
    print()
    for i, secenek in enumerate(sahne.secenekler, 1):
        print(f"  {i}) {secenek}")


def bulgulari_yazdir(motor) -> None:
    b = motor.son_bulgular
    if b is None:
        if motor.editor:
            print("  [editör] geçerli yanıt vermedi")
        return
    yeni = [i["metin"] for i in b["iddialar"] if i["durum"] == "yeni"]
    celisen = [f'{i["metin"]} ↔ {i["olgu"]}' for i in b["iddialar"] if i["durum"] == "celisiyor"]
    v = b["vaatler"]
    print("\n  ┌ editör")
    for etiket, liste in (("yeni olgu", yeni), ("ÇELİŞKİ", celisen), ("yeni vaat", v["acilan"]),
                          ("ilerleyen vaat", v["ilerleyen"]), ("çözülen vaat", v["cozulen"]),
                          ("karakter değişimi", [f'{d["karakter"]}: {d["degisim"]}'
                                                 for d in b["karakter_degisimleri"]])):
        for oge in liste:
            print(f"  │ {etiket}: {oge}")
    zayif = [z["ilke"] for z in b["zanaat"] if z["sonuc"] == "zayif"]
    if b["zanaat"]:
        print(f"  │ zanaat: {len(b['zanaat']) - len(zayif)}/{len(b['zanaat'])} iyi"
              + (f" · zayıf: {', '.join(zayif)}" if zayif else ""))
    if b["yazar_notu"]:
        print(f"  │ not: {b['yazar_notu']}")
    print("  └")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Türkçe interaktif hikâye oyunu")
    ap.add_argument("--dunya", default=str(KOK / "dunyalar" / "tuzhan.yaml"), help="Dünya dosyası (YAML)")
    ap.add_argument("--llm", choices=["gemini", "yerel", "sahte"], default="gemini", help="Dil modeli arka ucu")
    ap.add_argument("--model", help="Model adı (verilmezse .env ya da arka ucun varsayılanı)")
    ap.add_argument("--bellek", choices=STRATEJILER, default="ozet+kanon", help="Bellek stratejisi")
    ap.add_argument("--editor", choices=MODLAR, default="tam",
                    help="yok: editörsüz · denetim: tutarlılık + vaat defteri · tam: + usta yazar ölçütleri")
    ap.add_argument("--ayrinti", action="store_true", help="Her sahneden sonra editörün bulgularını göster")
    ap.add_argument("--otomatik", type=int, metavar="N", help="N tur boyunca seçenekleri rastgele seçerek kendi oynar")
    ap.add_argument("--tohum", type=int, default=0, help="Otomatik oyuncunun rastgelelik tohumu")
    args = ap.parse_args()

    env_yukle(KOK / ".env")
    dunya = dunya_yukle(args.dunya)
    llm = llm_olustur(args.llm, dunya=dunya, model=args.model)
    kayitci = Kayitci(KOK / "oturumlar", meta={
        "dunya": dunya.ad, "llm": llm.ad, "bellek": args.bellek, "editor": args.editor,
        "otomatik": args.otomatik, "tohum": args.tohum,
    })
    motor = Motor(dunya, llm, Bellek(args.bellek), kayitci, editor=Editor(args.editor))

    print(f"{dunya.ad} · model: {llm.ad} · bellek: {args.bellek} · editör: {args.editor}")
    sahne = motor.basla()
    sahne_yazdir(sahne, dunya)
    if args.ayrinti:
        bulgulari_yazdir(motor)

    rastgele = random.Random(args.tohum)
    tur = 0
    while args.otomatik is None or tur < args.otomatik:
        if args.otomatik is not None:
            eylem = rastgele.choice(sahne.secenekler)
            print(f"\n> {eylem}")
        else:
            try:
                giris = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if giris.lower() in {"q", "çık", "cik"}:
                break
            if not giris:
                continue
            if giris.isdigit() and 1 <= int(giris) <= len(sahne.secenekler):
                eylem = sahne.secenekler[int(giris) - 1]
            else:
                eylem = giris

        try:
            sahne = motor.oyna(eylem)
        except YanitHatasi as e:
            print(f"\n[Model geçerli bir sahne üretemedi: {e}]")
            if args.otomatik is not None:
                break
            continue
        sahne_yazdir(sahne, dunya)
        if args.ayrinti:
            bulgulari_yazdir(motor)
        tur += 1

    motor.durum.kaydet(kayitci.yol.with_suffix(".durum.json"))
    print(f"\nKayıt: {kayitci.yol.relative_to(KOK)}")


if __name__ == "__main__":
    main()
