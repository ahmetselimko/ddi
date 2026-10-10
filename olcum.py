"""
Tutarlılık ölçümü (komut satırı).

  python olcum.py rapor                         # oturumlar/*.jsonl → Markdown rapor
  python olcum.py rapor oturumlar/x.jsonl -o rapor.md
  python olcum.py enjeksiyon --ornek 25 --en-fazla-dolar 1 --etiket once
  python olcum.py enjeksiyon --llm sahte --ornek 3       # ağsız deneme

enjeksiyon gerçek modelle ÜCRETLİDİR (örnek başına ~1 sent). Ayrıntılı sonuçlar sahne
metinlerini içerdiği için olcumler/ham/ altına yazılır (git'e girmez); ekrana yalnızca
sayılar basılır.
"""
import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from hikaye.llm import env_yukle, llm_olustur
from hikaye.olcum import enjeksiyon, enjeksiyon_ozeti, ornek_havuzu, rapor

KOK = Path(__file__).parent


def _yollar(verilen: list[str]) -> list[Path]:
    return [Path(y) for y in verilen] if verilen else sorted((KOK / "oturumlar").glob("*.jsonl"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Tutarlılık ölçümü")
    alt = ap.add_subparsers(dest="komut", required=True)

    r = alt.add_parser("rapor", help="Tur kayıtlarından tutarlılık raporu")
    r.add_argument("kayitlar", nargs="*", help="jsonl dosyaları (varsayılan: oturumlar/*.jsonl)")
    r.add_argument("-o", "--cikti", help="Raporu dosyaya yaz")

    e = alt.add_parser("enjeksiyon", help="Editörün çelişki yakalama başarısını ölç (ücretli)")
    e.add_argument("kayitlar", nargs="*", help="jsonl dosyaları (varsayılan: oturumlar/*.jsonl)")
    e.add_argument("--ornek", type=int, default=25)
    e.add_argument("--tohum", type=int, default=7)
    e.add_argument("--en-fazla-dolar", type=float, default=1.0, help="Bu harcamaya ulaşınca dur")
    e.add_argument("--llm", choices=["gemini", "yerel", "sahte"], default="gemini")
    e.add_argument("--model", help="Hem çelişki yazarı hem editör için model")
    e.add_argument("--etiket", default="olcum", help="Sonuç dosyasının adı (ör. once, sonra)")
    e.add_argument("--onceki", help="Önceki koşunun sonuç dosyası: aynı sahneler ve aynı çelişki cümleleri")
    args = ap.parse_args()

    if args.komut == "rapor":
        metin = rapor(_yollar(args.kayitlar))
        if args.cikti:
            Path(args.cikti).write_text(metin, encoding="utf-8")
            print(f"Rapor yazıldı: {args.cikti}")
        else:
            print(metin)
        return

    env_yukle(KOK / ".env")
    havuz = ornek_havuzu(_yollar(args.kayitlar), KOK / "dunyalar")
    if not havuz:
        raise SystemExit("Editörlü ve ilgili dünya olgusu olan sahne bulunamadı.")
    llm = llm_olustur(args.llm, dunya=havuz[0][1], model=args.model)
    print(f"Havuz: {len(havuz)} sahne · örnek: {min(args.ornek, len(havuz))} · model: {llm.ad} · "
          f"bütçe: ${args.en_fazla_dolar}")
    hazir = None
    if args.onceki:
        onceki = json.loads(Path(args.onceki).read_text(encoding="utf-8"))
        hazir = {(o["oturum"], o["sahne_no"]): (o["olgu"], o["cumle"]) for o in onceki["ornekler"]}
        args.tohum = onceki.get("tohum", args.tohum)
    sonuc = enjeksiyon(havuz, llm, ornek=args.ornek, tohum=args.tohum, en_fazla_dolar=args.en_fazla_dolar,
                       ilerleme=lambda i, n, d: print(f"  {i}/{n}  ${d:.3f}", flush=True), hazir=hazir)
    ozet = enjeksiyon_ozeti(sonuc)

    klasor = KOK / "olcumler" / "ham"
    klasor.mkdir(parents=True, exist_ok=True)
    yol = klasor / f"enjeksiyon_{args.etiket}_{datetime.now():%Y%m%d-%H%M%S}.json"
    yol.write_text(json.dumps({"ozet": ozet, "model": llm.ad, "tohum": args.tohum,
                               "ornekler": [asdict(o) for o in sonuc["ornekler"]]},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(ozet, ensure_ascii=False, indent=1))
    print(f"Ayrıntılar: {yol}")


if __name__ == "__main__":
    main()
