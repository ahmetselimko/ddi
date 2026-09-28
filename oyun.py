"""
Türkçe interaktif hikâye oyunu — komut satırı.

  python oyun.py                                   # demo dünya, Gemini, tüm hikâyeyi hatırlar, tam editör
  python oyun.py --ayrinti                         # editörün bulgularını da göster
  python oyun.py --bellek son --editor yok         # yalnızca son sahneler, editörsüz
  python oyun.py --llm yerel --model qwen2.5:7b    # OpenAI uyumlu yerel sunucu (Ollama, vLLM)
  python oyun.py --llm sahte --otomatik 10         # ağsız deneme, 10 tur kendi oynar

Oyunda seçeneğin numarasını ya da serbest bir eylem yaz; son sahneyi yeniden yazdırmak
için y, çıkmak için q.
"""
import argparse
import os
import random
import sys
import textwrap
from pathlib import Path

from hikaye.bellek import STRATEJILER, Bellek
from hikaye.dunya import dunya_yukle
from hikaye.editor import MODLAR, Editor
from hikaye.kayit import Kayitci
from hikaye.llm import YAZAR_SECENEKLERI, env_yukle, llm_olustur
from hikaye.motor import Motor, YanitHatasi

KOK = Path(__file__).parent


def sahne_yazdir(sahne, dunya) -> None:
    zaman = f" · {sahne.zaman}" if sahne.zaman else ""
    print(f"\n── Sahne {sahne.no} · {dunya.mekanlar[sahne.mekan].ad}{zaman} " + "─" * 30)
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
    sapmalar = [f'{d["karakter"]} ({alan}): {d["gerekce"]}' for d in b["karakter_denetimi"]
                for alan in ("kisilik", "konusma", "bilgi") if d[alan] != "uygun"]
    if b["oyuncu_bilgi_sizintisi"]:
        sapmalar.append(f'oyuncu (bilgi): {b["oyuncu_bilgi_sizintisi"]}')
    oto = b["otomatik"]
    duzeltmeler = [f"{len(oto[k])} {ad}" for k, ad in (
        ("yeniden_siniflanan", "olgu zaten biliniyordu"), ("atilan_tahmin", "tahmin atıldı"),
        ("fazla_olgu", "sınır aşan olgu atıldı"),
        ("tekrar_vaat", "tekrar vaat atıldı"), ("kanitsiz_vaat", "kanıtsız ilerleme sayılmadı")) if oto[k]]
    print("\n  ┌ editör")
    for etiket, liste in (("yeni olgu", yeni), ("ÇELİŞKİ", celisen), ("KARAKTER", sapmalar),
                          ("yeni vaat", v["acilan"]),
                          ("ilerleyen vaat", [f'{x["id"]}: {x["kanit"]}' for x in v["ilerleyen"]]),
                          ("çözülen vaat", [f'{x["id"]}: {x["kanit"]}' for x in v["cozulen"]]),
                          ("karakter değişimi", [f'{d["karakter"]}: {d["degisim"]}'
                                                 for d in b["karakter_degisimleri"]])):
        for oge in liste:
            print(f"  │ {etiket}: {oge}")
    kod = [u for u in motor.durum.sahneler[-1].uyarilar if "düzeltildi" not in u]
    for u in kod:
        print(f"  │ kod: {u}")
    if duzeltmeler:
        print(f"  │ otomatik düzeltme: {', '.join(duzeltmeler)}")
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
    ap.add_argument("--model", help="Yazar modelin adı (verilmezse .env ya da arka ucun varsayılanı)")
    ap.add_argument("--editor-model", help="Editör için ayrı model (varsayılan: .env EDITOR_MODEL ya da yazarınki)")
    ap.add_argument("--ozet-model", help="Özet için ayrı model (varsayılan: .env OZET_MODEL ya da yazarınki)")
    ap.add_argument("--yazar", choices=list(YAZAR_SECENEKLERI), default="hizli",
                    help="hizli (varsayılan) · dusunen: yazmadan önce düşünür · guclu: daha güçlü model")
    ap.add_argument("--bellek", choices=STRATEJILER, default="tam",
                    help="tam: modele tüm hikâye gider (varsayılan); diğerleri bağlamı kısaltır")
    ap.add_argument("--editor", choices=MODLAR, default="tam",
                    help="yok: editörsüz · denetim: tutarlılık + vaat defteri · tam: + usta yazar ölçütleri")
    ap.add_argument("--ayrinti", action="store_true", help="Her sahneden sonra editörün bulgularını göster")
    ap.add_argument("--otomatik", type=int, metavar="N", help="N tur boyunca seçenekleri rastgele seçerek kendi oynar")
    ap.add_argument("--tohum", type=int, default=0, help="Otomatik oyuncunun rastgelelik tohumu")
    args = ap.parse_args()

    env_yukle(KOK / ".env")
    dunya = dunya_yukle(args.dunya)
    llm = llm_olustur(args.llm, dunya=dunya, model=args.model, yazar=args.yazar)
    # Güçlü/düşünen seçenek yalnızca yazarı etkiler; editör ve özet temel modelde kalır
    temel = llm if args.yazar == "hizli" else llm_olustur(args.llm, dunya=dunya, yazar="hizli")
    editor_modeli = args.editor_model or os.environ.get("EDITOR_MODEL")
    ozet_modeli = args.ozet_model or os.environ.get("OZET_MODEL")
    editor_llm = llm_olustur(args.llm, dunya=dunya, model=editor_modeli) if editor_modeli else temel
    ozet_llm = llm_olustur(args.llm, dunya=dunya, model=ozet_modeli) if ozet_modeli else temel

    kayitci = Kayitci(KOK / "oturumlar", meta={
        "dunya": dunya.ad, "llm": llm.ad, "editor_llm": editor_llm.ad, "ozet_llm": ozet_llm.ad,
        "yazar": args.yazar, "bellek": args.bellek, "editor": args.editor, "otomatik": args.otomatik, "tohum": args.tohum,
    })
    motor = Motor(dunya, llm, Bellek(args.bellek), kayitci, editor=Editor(args.editor),
                  editor_llm=editor_llm, ozet_llm=ozet_llm)

    roller = f"model: {llm.ad}"
    if editor_llm is not llm:
        roller += f" · editör modeli: {editor_llm.ad}"
    if ozet_llm is not llm:
        roller += f" · özet modeli: {ozet_llm.ad}"
    print(f"{dunya.ad} · {roller} · bellek: {args.bellek} · editör: {args.editor}")
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
            if args.otomatik is None and eylem.lower() == "y":
                sahne = motor.yeniden_yaz()          # son sahneyi aynı eylemle yeniden yazdır
                print("\n[Son sahne yeniden yazıldı]")
            else:
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
