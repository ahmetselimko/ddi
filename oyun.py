"""
Türkçe interaktif hikâye oyunu — komut satırı.

  python oyun.py                                   # demo dünya, Gemini, özet+kanon bellek
  python oyun.py --bellek son                      # taban çizgisi: yalnızca son sahneler
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


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Türkçe interaktif hikâye oyunu")
    ap.add_argument("--dunya", default=str(KOK / "dunyalar" / "tuzhan.yaml"), help="Dünya dosyası (YAML)")
    ap.add_argument("--llm", choices=["gemini", "yerel", "sahte"], default="gemini", help="Dil modeli arka ucu")
    ap.add_argument("--model", help="Model adı (verilmezse .env ya da arka ucun varsayılanı)")
    ap.add_argument("--bellek", choices=STRATEJILER, default="ozet+kanon", help="Bellek stratejisi")
    ap.add_argument("--otomatik", type=int, metavar="N", help="N tur boyunca seçenekleri rastgele seçerek kendi oynar")
    ap.add_argument("--tohum", type=int, default=0, help="Otomatik oyuncunun rastgelelik tohumu")
    args = ap.parse_args()

    env_yukle(KOK / ".env")
    dunya = dunya_yukle(args.dunya)
    llm = llm_olustur(args.llm, dunya=dunya, model=args.model)
    kayitci = Kayitci(KOK / "oturumlar", meta={
        "dunya": dunya.ad, "llm": llm.ad, "bellek": args.bellek,
        "otomatik": args.otomatik, "tohum": args.tohum,
    })
    motor = Motor(dunya, llm, Bellek(args.bellek), kayitci)

    print(f"{dunya.ad} · model: {llm.ad} · bellek: {args.bellek}")
    sahne = motor.basla()
    sahne_yazdir(sahne, dunya)

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
        tur += 1

    motor.durum.kaydet(kayitci.yol.with_suffix(".durum.json"))
    print(f"\nKayıt: {kayitci.yol.relative_to(KOK)}")


if __name__ == "__main__":
    main()
