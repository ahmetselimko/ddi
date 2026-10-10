"""
Manga: oynanan sahneleri panellere böler, panelleri bir görsel servisine çizdirir,
sayfaya dizer ve Türkçe konuşma balonlarını ekler. İsteğe bağlıdır, varsayılan kapalı.

  1. Görünüm   Her karakterin ve mekânın İngilizce görsel etiketleri (prompt_en). Dünya
               dosyasında yoksa model bir kez üretir ve dünya başına önbelleğe yazılır;
               böylece bir karakter her panelde aynı tarifle çizilir.
  2. Plan      Model sahneyi en fazla 4 panele böler: kamera, panelde görünenler,
               İngilizce eylem etiketleri, hangi replik hangi panelde. Model yanıt
               veremezse kod basit bir plan kurar. Görünüş etiketlerini kod ekler.
  3. Çizim     Görsel servisi (yerel, RunPod ya da API, hepsi aynı HTTP arayüzü) PNG döndürür.
               Türkçe metin görsele gömülmez.
  4. Sayfa     Paneller sayfaya dizilir, balonlar ve anlatım kutuları Pillow ile yazılır.
"""
import io
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .llm import json_coz
from .motor import ETIKETLI_SATIR

KAMERALAR = {"genis": "wide shot", "orta": "medium shot", "yakin": "close-up"}
BOYUTLAR = {"genis": (1216, 832), "orta": (832, 1216), "yakin": (832, 1216)}   # servis panel boyutları
EN_FAZLA_PANEL = 4
BALON_SINIRI = 3              # bir panelde en fazla balon
KAYNAKLAR = ("yerel", "runpod", "api")
STILLER = ("siyahbeyaz", "renkli")
_ETIKET = re.compile(r"^[a-z0-9 ,.()'\-:_/]*$")     # İngilizce etiket: Türkçe harf, cümle işareti yok


# ── Sahne metni ───────────────────────────────────────────────────────────────

def sahne_parcalari(metin: str) -> list[dict]:
    """Motorun kurduğu sahne metni: anlatım satırları ve 'Etiket: "replik"' satırları."""
    parcalar = []
    for satir in metin.split("\n"):
        satir = satir.strip()
        if not satir:
            continue
        e = ETIKETLI_SATIR.match(satir)
        if e:
            parcalar.append({"tur": "replik", "konusan": satir.split(":", 1)[0].strip(), "metin": e.group(1)})
        else:
            parcalar.append({"tur": "anlatim", "metin": satir})
    return parcalar


def _replik_sahipleri(sahne, parcalar) -> list[str | None]:
    """Her replik parçasını söyleyen karakterin id'si (sahne.replikler metinle eşleştirilir)."""
    sahibi = {r.metin.strip(): r.karakter for r in getattr(sahne, "replikler", [])}
    return [sahibi.get(p["metin"].strip()) for p in parcalar if p["tur"] == "replik"]


def _kisalt(metin: str, sinir: int = 160) -> str:
    metin = " ".join(metin.split())
    if len(metin) <= sinir:
        return metin
    kesik = metin[:sinir].rsplit(" ", 1)[0]
    return kesik.rstrip(",;:") + "…"


# ── 1. Görünüm ───────────────────────────────────────────────────────────────

_GORUNUM_SISTEM = """Sen manga çizimi için görsel etiket yazarısın. Türkçe karakter ve mekân
tanımlarını, anime/manga görsel modellerinin anladığı İngilizce etiketlere çevirirsin.

Kurallar:
- Yalnızca İngilizce, küçük harf, virgülle ayrılmış kısa etiketler. Cümle, ad, Türkçe sözcük yok.
- Karakter: önce tür ve sayı (1girl, 1boy, 1woman, 1man, 1other; insan değilse ör. "anthropomorphic
  ant"), sonra yaş, yapı, saç, yüz, kıyafet, ayırt edici işaretler. Tanımda olmayanı dönemine ve
  tonuna uygun, sade biçimde tamamla; her karakter ötekilerden kolayca ayırt edilsin.
- Mekân: yalnızca yeri anlatan etiketler; insan, karakter ekleme.
- dunya: tüm panellere eklenecek dönem/ortam etiketleri (3-6 etiket).
- Yasak ya da olmayan şeyleri ("no guns") YAZMA; yalnızca görünmesi gerekenleri yaz.

JSON:
{"dunya": "...", "karakterler": {"<id>": "..."}, "mekanlar": {"<id>": "..."}}"""


def _gorunum_istemi(dunya, eksik_karakterler, eksik_mekanlar) -> str:
    satirlar = [f"DÜNYA: {dunya.ad}", f"Ton: {' '.join(dunya.ton.split())}"]
    if dunya.kurallar:
        satirlar.append("Kurallar: " + " ".join(k.metin for k in dunya.kurallar))
    if eksik_karakterler:
        satirlar.append("\nKARAKTERLER:")
        for k in eksik_karakterler:
            gor = "; ".join(f"{a}: {v}" for a, v in k.gorunum.items() if a != "prompt_en")
            satirlar.append(f"- [{k.id}] {k.gorunen_ad}. {k.tanim}" + (f" Görünüş: {gor}" if gor else ""))
    if eksik_mekanlar:
        satirlar.append("\nMEKÂNLAR:")
        satirlar += [f"- [{m.id}] {m.ad}. {m.tanim}" for m in eksik_mekanlar]
    return "\n".join(satirlar)


def _etiket_mi(metin) -> bool:
    return isinstance(metin, str) and bool(metin.strip()) and bool(_ETIKET.match(metin.strip().lower()))


def gorunumleri_hazirla(dunya, llm, onbellek: Path | None) -> dict:
    """{"dunya": str, "karakterler": {id: str}, "mekanlar": {id: str}}. Öncelik: dünya
    dosyası > önbellek > model. Model yoksa ya da hata verirse eksikler boş kalır."""
    sonuc = {"dunya": dunya.gorsel_en,
             "karakterler": {k: c.gorunum["prompt_en"] for k, c in dunya.karakterler.items()
                             if c.gorunum.get("prompt_en")},
             "mekanlar": {m: x.prompt_en for m, x in dunya.mekanlar.items() if x.prompt_en}}
    kayitli = {}
    if onbellek and onbellek.exists():
        try:
            kayitli = json.loads(onbellek.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            kayitli = {}
    sonuc["dunya"] = sonuc["dunya"] or kayitli.get("dunya", "")
    for alan in ("karakterler", "mekanlar"):
        for i, v in (kayitli.get(alan) or {}).items():
            sonuc[alan].setdefault(i, v)

    eksik_k = [k for k in dunya.karakterler.values() if k.id not in sonuc["karakterler"]]
    eksik_m = [m for m in dunya.mekanlar.values() if m.id not in sonuc["mekanlar"]]
    if llm is None or not (eksik_k or eksik_m or not sonuc["dunya"]):
        return sonuc
    try:
        yanit = llm.uret(_GORUNUM_SISTEM, _gorunum_istemi(dunya, eksik_k, eksik_m), sicaklik=0.4)
        ham = json_coz(yanit.metin)
    except Exception:            # ağ, kota, bozuk JSON: manga yine çizilir, etiketler eksik kalır
        return sonuc
    if not sonuc["dunya"] and _etiket_mi(ham.get("dunya")):
        sonuc["dunya"] = ham["dunya"].strip()
    for alan, gecerli in (("karakterler", eksik_k), ("mekanlar", eksik_m)):
        gelen = ham.get(alan) if isinstance(ham.get(alan), dict) else {}
        for x in gecerli:
            if _etiket_mi(gelen.get(x.id)):
                sonuc[alan][x.id] = gelen[x.id].strip()
    if onbellek:
        onbellek.parent.mkdir(parents=True, exist_ok=True)
        uretilen = {"dunya": sonuc["dunya"],
                    "karakterler": {k.id: sonuc["karakterler"][k.id] for k in eksik_k if k.id in sonuc["karakterler"]},
                    "mekanlar": {m.id: sonuc["mekanlar"][m.id] for m in eksik_m if m.id in sonuc["mekanlar"]}}
        for alan in ("karakterler", "mekanlar"):
            uretilen[alan] = {**(kayitli.get(alan) or {}), **uretilen[alan]}
        onbellek.write_text(json.dumps(uretilen, ensure_ascii=False, indent=2), encoding="utf-8")
    return sonuc


# ── 2. Panel planı ───────────────────────────────────────────────────────────

_PLAN_SISTEM = f"""Sen bir manga sahne planlayıcısısın. Türkçe bir hikâye sahnesini en fazla
{EN_FAZLA_PANEL} manga paneline bölersin. Görsel modeli İngilizce etiketlerle çalışır.

Kurallar:
- 2-{EN_FAZLA_PANEL} panel; sahnenin en önemli anlarını sırasıyla seç.
- kamera: "genis" (mekân, kalabalık, varış), "orta" (karakterler belden yukarı, konuşma),
  "yakin" (yüz, duygu, önemli bir nesne).
- karakterler: panelde GÖRÜNEN karakterlerin id'leri, yalnızca verilen listeden. Oyuncu ("sen")
  çizilmez; oyuncunun gözünden bakılıyorsa eylem_en'e "pov" yaz.
- eylem_en: İngilizce, küçük harf, virgülle ayrılmış kısa etiketler: duruş, eylem, yüz ifadesi,
  önemli nesneler, ışık, hava. Karakterlerin görünüşünü YAZMA (eklenir). Ad, Türkçe sözcük, cümle yok.
- replikler: bu panelin balonlarına girecek replik numaraları ([R0], [R1]... → 0, 1). Her replik
  en fazla bir panelde, bir panelde en fazla {BALON_SINIRI}. Konuşan karakter o panelde görünmeli.
- anlatim: panelin anlatım kutusu; sahnedeki anlatımdan kısaltılmış tek kısa Türkçe cümle ya da "".

JSON:
{{"paneller": [{{"kamera": "orta", "karakterler": ["<id>"], "eylem_en": "...", "replikler": [0], "anlatim": ""}}]}}"""


def _plan_istemi(sahne, dunya, parcalar) -> str:
    mekan = dunya.mekanlar.get(sahne.mekan)
    satirlar = [f"MEKÂN: {mekan.ad} — {mekan.tanim}" if mekan else f"MEKÂN: {sahne.mekan}"]
    if sahne.zaman:
        satirlar.append(f"ZAMAN: {sahne.zaman}")
    satirlar.append("KARAKTERLER (yalnızca bunlar çizilebilir):")
    for kid in dunya.karakterler:
        k = dunya.karakterler[kid]
        satirlar.append(f"- [{kid}] {k.gorunen_ad} ({k.ad}). {k.tanim}")
    if sahne.eylem:
        satirlar.append(f"\nOYUNCUNUN EYLEMİ: {sahne.eylem}")
    satirlar.append("\nSAHNE:")
    r = 0
    for p in parcalar:
        if p["tur"] == "replik":
            satirlar.append(f'[R{r}] {p["konusan"]}: "{p["metin"]}"')
            r += 1
        else:
            satirlar.append(p["metin"])
    return "\n".join(satirlar)


def _istem_kur(karakterler, eylem_en, mekan, kamera, gorunum) -> str:
    parcalar = [gorunum["karakterler"].get(k, "") for k in karakterler]
    if not karakterler:
        parcalar.append("no humans")
    parcalar += [eylem_en, gorunum["mekanlar"].get(mekan, ""), gorunum["dunya"], KAMERALAR[kamera]]
    return ", ".join(p.strip(" ,") for p in parcalar if p and p.strip(" ,"))


def _panel(sahne, no, kamera, karakterler, eylem_en, replikler, anlatim, gorunum) -> dict:
    genislik, yukseklik = BOYUTLAR[kamera]
    return {"sahne_no": sahne.no, "panel_no": no, "kamera": kamera, "karakterler": karakterler,
            "prompt_en": _istem_kur(karakterler, eylem_en, sahne.mekan, kamera, gorunum),
            "replikler": replikler, "anlatim": anlatim, "genislik": genislik, "yukseklik": yukseklik}


def plani_coz(ham: dict, sahne, dunya, parcalar, gorunum) -> list[dict]:
    """Modelin planını doğrular ve panel listesine çevirir. Geçersiz alanlar düzeltilir ya da
    atılır; hiç geçerli panel yoksa ValueError."""
    replikler = [p for p in parcalar if p["tur"] == "replik"]
    sahipler = _replik_sahipleri(sahne, parcalar)
    kullanilan: set[int] = set()
    paneller = []
    for p in (ham.get("paneller") or [])[:EN_FAZLA_PANEL]:
        if not isinstance(p, dict):
            continue
        kamera = p.get("kamera") if p.get("kamera") in KAMERALAR else "orta"
        karakterler = [k for k in dict.fromkeys(p.get("karakterler") or []) if k in dunya.karakterler]
        eylem = p.get("eylem_en") if _etiket_mi(p.get("eylem_en")) else ""
        secilen = []
        for i in p.get("replikler") or []:
            if isinstance(i, int) and 0 <= i < len(replikler) and i not in kullanilan and len(secilen) < BALON_SINIRI:
                kullanilan.add(i)
                secilen.append(i)
                if sahipler[i] and sahipler[i] not in karakterler:   # konuşan görünmeli
                    karakterler.append(sahipler[i])
        anlatim = _kisalt(p["anlatim"]) if isinstance(p.get("anlatim"), str) and p["anlatim"].strip() else ""
        paneller.append(_panel(sahne, len(paneller) + 1, kamera, karakterler, eylem,
                               [{"konusan": replikler[i]["konusan"], "metin": replikler[i]["metin"]} for i in secilen],
                               anlatim, gorunum))
    if not paneller:
        raise ValueError("Planda geçerli panel yok.")
    return paneller


def basit_plan(sahne, dunya, parcalar, gorunum) -> list[dict]:
    """Model olmadan: bir açılış (geniş) paneli, sonra konuşan her karakter için bir panel."""
    anlatimlar = [p["metin"] for p in parcalar if p["tur"] == "anlatim"]
    replikler = [p for p in parcalar if p["tur"] == "replik"]
    sahipler = _replik_sahipleri(sahne, parcalar)
    paneller = [_panel(sahne, 1, "genis", [], "establishing shot", [],
                       _kisalt(anlatimlar[0]) if anlatimlar else "", gorunum)]
    gruplar: dict = {}
    for i, r in enumerate(replikler):
        gruplar.setdefault(sahipler[i] or r["konusan"], []).append(r)
    for anahtar, liste in list(gruplar.items())[:EN_FAZLA_PANEL - 1]:
        karakterler = [anahtar] if anahtar in dunya.karakterler else []
        paneller.append(_panel(sahne, len(paneller) + 1, "orta", karakterler, "talking",
                               [{"konusan": r["konusan"], "metin": r["metin"]} for r in liste[:BALON_SINIRI]],
                               "", gorunum))
    return paneller


def sahne_plani(sahne, dunya, gorunum, llm=None) -> tuple[list[dict], object | None]:
    """(paneller, LLMYanit ya da None). Model başarısız olursa basit plana düşer."""
    parcalar = sahne_parcalari(sahne.metin)
    if llm is not None:
        try:
            yanit = llm.uret(_PLAN_SISTEM, _plan_istemi(sahne, dunya, parcalar), sicaklik=0.5)
            return plani_coz(json_coz(yanit.metin), sahne, dunya, parcalar, gorunum), yanit
        except Exception:
            pass
    return basit_plan(sahne, dunya, parcalar, gorunum), None


# ── 3. Görsel servisi ────────────────────────────────────────────────────────

class GorselHatasi(RuntimeError):
    pass


class GorselServisi:
    """Panel çizen HTTP servisi. Yerel, RunPod ve API aynı arayüzü kullanır:
    GET /saglik, POST /panel (Authorization: Bearer <token>) → image/png, X-Seed başlığı."""

    def __init__(self, adres: str, token: str = "", stil: str = "siyahbeyaz", zaman_asimi: float = 300):
        if stil not in STILLER:
            raise ValueError(f"Bilinmeyen stil: {stil}")
        self.adres = adres.rstrip("/")
        self.token = token
        self.stil = stil
        self.zaman_asimi = zaman_asimi

    def _istek(self, yol: str, govde: dict | None = None, zaman_asimi: float | None = None):
        basliklar = {"Content-Type": "application/json"}
        if self.token:
            basliklar["Authorization"] = f"Bearer {self.token}"
        veri = None if govde is None else json.dumps(govde).encode()
        istek = urllib.request.Request(self.adres + yol, data=veri, headers=basliklar)
        try:
            return urllib.request.urlopen(istek, timeout=zaman_asimi or self.zaman_asimi)
        except urllib.error.HTTPError as h:
            raise GorselHatasi(f"Görsel servisi {h.code} döndürdü: {h.read()[:200].decode('utf-8', 'replace')}") from h
        except OSError as e:
            raise GorselHatasi(f"Görsel servisine ulaşılamadı ({self.adres}): {e}") from e

    def saglik(self) -> dict:
        with self._istek("/saglik", zaman_asimi=10) as y:
            return json.loads(y.read())

    def ciz(self, prompt: str, genislik: int, yukseklik: int, seed: int | None = None) -> tuple[bytes, int | None]:
        with self._istek("/panel", {"prompt": prompt, "stil": self.stil, "genislik": genislik,
                                    "yukseklik": yukseklik, "seed": seed}) as y:
            png = y.read()
            seed = y.headers.get("X-Seed")
        if not png.startswith(b"\x89PNG"):
            raise GorselHatasi("Görsel servisi PNG döndürmedi.")
        return png, int(seed) if seed and seed.lstrip("-").isdigit() else None


class SahteGorsel:
    """Ağsız: istemi üzerine yazılmış gri bir panel. Testler ve arayüz denemesi için."""

    def __init__(self, stil: str = "siyahbeyaz"):
        self.stil = stil
        self.adres = "sahte"
        self.cizilen: list[dict] = []

    def saglik(self) -> dict:
        return {"ok": True, "model": "sahte", "cihaz": "yok"}

    def ciz(self, prompt: str, genislik: int, yukseklik: int, seed: int | None = None) -> tuple[bytes, int | None]:
        self.cizilen.append({"prompt": prompt, "genislik": genislik, "yukseklik": yukseklik})
        renk = (200, 200, 200) if self.stil == "siyahbeyaz" else (190, 210, 230)
        img = Image.new("RGB", (genislik, yukseklik), renk)
        ImageDraw.Draw(img).text((20, yukseklik // 2), prompt[:60], fill=(60, 60, 60))
        tampon = io.BytesIO()
        img.save(tampon, "PNG")
        return tampon.getvalue(), len(self.cizilen)


def kaynak_ayari(kaynak: str) -> tuple[str, str]:
    """(.env'deki adres, token). MANGA_YEREL_ADRES, MANGA_RUNPOD_TOKEN..."""
    on = f"MANGA_{kaynak.upper()}_"
    return os.environ.get(on + "ADRES", "").strip(), os.environ.get(on + "TOKEN", "").strip()


def hazir_kaynaklar() -> dict[str, bool]:
    """Hangi kaynağın adresi .env'de tanımlı."""
    return {k: bool(kaynak_ayari(k)[0]) for k in KAYNAKLAR}


def servis_olustur(kaynak: str, stil: str):
    if kaynak == "sahte":
        return SahteGorsel(stil)
    if kaynak not in KAYNAKLAR:
        raise ValueError(f"Bilinmeyen görsel kaynağı: {kaynak}")
    adres, token = kaynak_ayari(kaynak)
    if not adres:
        raise ValueError(f"{kaynak} görsel kaynağının adresi yok: .env içine MANGA_{kaynak.upper()}_ADRES yaz.")
    return GorselServisi(adres, token, stil)


# ── 4. Sayfa ve balonlar ─────────────────────────────────────────────────────

SAYFA = (1654, 2339)          # A4, ~200 dpi
KENAR, ARALIK, CERCEVE = 60, 30, 5
_YAZI_TIPLERI = ["comicbd.ttf", "comic.ttf", "arialbd.ttf", "arial.ttf",
                 "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]
_FONT_ONBELLEK: dict = {}


def yazi_tipi(boyut: int):
    """Türkçe harfleri (ğ, ş, ı, İ) olan bir yazı tipi. MANGA_FONT ile değiştirilebilir."""
    if boyut in _FONT_ONBELLEK:
        return _FONT_ONBELLEK[boyut]
    adaylar = [os.environ.get("MANGA_FONT", "")] + _YAZI_TIPLERI
    adaylar += [str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / a) for a in _YAZI_TIPLERI]
    font = None
    for aday in filter(None, adaylar):
        try:
            font = ImageFont.truetype(aday, boyut)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default(boyut)
    _FONT_ONBELLEK[boyut] = font
    return font


def gorsel_ac(yol: Path) -> Image.Image:
    """Dosyayı okuyup hemen kapatır (Windows'ta açık kalan dosya üzerine yazılamaz)."""
    with Image.open(yol) as img:
        return img.convert("RGB")


def satirlara_bol(metin: str, font, genislik: float) -> list[str]:
    satirlar, satir = [], ""
    for kelime in metin.split():
        aday = f"{satir} {kelime}".strip()
        if not satir or font.getlength(aday) <= genislik:
            satir = aday
        else:
            satirlar.append(satir)
            satir = kelime
    if satir:
        satirlar.append(satir)
    return satirlar


def _metin_yaz(cizim, satirlar, font, merkez_x, ust_y, satir_yuksekligi):
    for i, s in enumerate(satirlar):
        cizim.text((merkez_x - font.getlength(s) / 2, ust_y + i * satir_yuksekligi), s, font=font, fill="black")


def balonlari_ciz(cizim, kutu, replikler, anlatim, olcek: float = 1.0) -> int:
    """Paneldeki balonlar (üstte, soldan sağa, okuma sırasıyla) ve anlatım kutusu (altta).
    Sığmayan balon atlanır; atlanan sayısı döner."""
    x0, y0, x1, y1 = kutu
    font = yazi_tipi(max(18, int(30 * olcek)))
    sy = font.size * 1.22
    pay = 18
    atlanan = 0

    alt_sinir = y1 - pay
    if anlatim:
        satirlar = satirlara_bol(anlatim, font, (x1 - x0) * 0.62)
        g = max(font.getlength(s) for s in satirlar) + 28
        y = y1 - pay - len(satirlar) * sy - 22
        cizim.rectangle([x0 + pay, y, x0 + pay + g, y1 - pay], fill="white", outline="black", width=3)
        for i, s in enumerate(satirlar):
            cizim.text((x0 + pay + 14, y + 11 + i * sy), s, font=font, fill="black")
        alt_sinir = y - 10

    sutun_y = [y0 + pay, y0 + pay]
    for i, r in enumerate(replikler):
        satirlar = satirlara_bol(r["metin"], font, max(220, (x1 - x0) * 0.36))
        tw = max(font.getlength(s) for s in satirlar)
        th = len(satirlar) * sy
        bw, bh = tw * 1.36 + 36, th * 1.36 + 34
        sutun = i % 2 if (x1 - x0) > bw * 2.1 else 0
        bx = x0 + pay if sutun == 0 else x1 - pay - bw
        by = sutun_y[sutun]
        if by + bh + 34 > alt_sinir:
            atlanan += 1
            continue
        sutun_y[sutun] = by + bh + 40
        cx, cy = bx + bw / 2, by + bh / 2
        yon = 1 if cx < (x0 + x1) / 2 else -1             # kuyruk panelin ortasına doğru
        kuyruk = [(cx - 16, by + bh - 10), (cx + 16, by + bh - 10), (cx + yon * 34, by + bh + 34)]
        cizim.polygon(kuyruk, fill="white", outline="black", width=3)
        cizim.ellipse([bx, by, bx + bw, by + bh], fill="white", outline="black", width=3)
        _metin_yaz(cizim, satirlar, font, cx, cy - th / 2 + (sy - font.size) / 2, sy)
    return atlanan


KARMA_YUKSEKLIK = 760          # dikey + geniş panelin yan yana durduğu satır


def _dikey(p) -> bool:
    return p["kamera"] != "genis"


def _satirlar(paneller) -> list[list[dict]]:
    """Okuma sırasını bozmadan sayfa satırları: iki dikey yan yana; yalnız kalacak bir dikey
    komşusu olan geniş panelle aynı satırı paylaşır; geniş panel başka türlü tek başına."""
    satirlar, i = [], 0
    while i < len(paneller):
        p = paneller[i]
        sonraki = paneller[i + 1] if i + 1 < len(paneller) else None
        sonraki2 = paneller[i + 2] if i + 2 < len(paneller) else None
        if _dikey(p) and sonraki is not None:
            satirlar.append([p, sonraki])            # dikey+dikey ya da dikey+geniş
            i += 2
        elif not _dikey(p) and sonraki is not None and _dikey(sonraki) and not (sonraki2 and _dikey(sonraki2)):
            satirlar.append([p, sonraki])            # geniş+dikey: dikey yoksa yalnız kalırdı
            i += 2
        else:
            satirlar.append([p])
            i += 1
    return satirlar


def _satir_olculeri(satir, ic_genislik) -> tuple[int, list[tuple[int, int]]]:
    """(yükseklik, [(x ofseti, genişlik)...])."""
    gw, gh = BOYUTLAR["genis"]
    dw, dh = BOYUTLAR["orta"]
    yarim = int((ic_genislik - ARALIK) / 2)
    if len(satir) == 1:
        if _dikey(satir[0]):                         # yalnız dikey: yarım genişlik, ortada
            return int(yarim * dh / dw), [((ic_genislik - yarim) // 2, yarim)]
        return int(ic_genislik * gh / gw), [(0, ic_genislik)]
    if _dikey(satir[0]) and _dikey(satir[1]):
        return int(yarim * dh / dw), [(0, yarim), (yarim + ARALIK, yarim)]
    dikey_g = int(KARMA_YUKSEKLIK * dw / dh)
    genis_g = ic_genislik - ARALIK - dikey_g
    if _dikey(satir[0]):
        return KARMA_YUKSEKLIK, [(0, dikey_g), (dikey_g + ARALIK, genis_g)]
    return KARMA_YUKSEKLIK, [(0, genis_g), (genis_g + ARALIK, dikey_g)]


EN_AZ_OLCEK, EN_COK_OLCEK = 0.8, 1.25       # sayfayı doldurmak için satır yükseklik ölçeği


def sayfalari_diz(paneller: list[dict], gorsel_oku) -> list[Image.Image]:
    """paneller: sahne/panel sırasıyla; gorsel_oku(panel) → PIL Image. Satırlar sayfalara
    dağıtılır, her sayfanın satırları sayfayı dolduracak kadar ölçeklenir (son sayfa doğal
    boyda kalır); görseller hücreye kırpılarak (bozmadan) yerleşir."""
    w, h = SAYFA
    ic_genislik, ic_yukseklik = w - 2 * KENAR, h - 2 * KENAR
    gruplar: list[list] = [[]]
    for satir in _satirlar(paneller):
        olcu = _satir_olculeri(satir, ic_genislik)
        grup = gruplar[-1]
        toplam = sum(o[0] for _, o in grup) + olcu[0]
        if grup and toplam * EN_AZ_OLCEK + ARALIK * len(grup) > ic_yukseklik:
            gruplar.append([])
        gruplar[-1].append((satir, olcu))

    sayfalar = []
    for n, grup in enumerate(gruplar):
        bos = ic_yukseklik - ARALIK * (len(grup) - 1)
        olcek = min(EN_COK_OLCEK, bos / sum(o[0] for _, o in grup))
        if n == len(gruplar) - 1:
            olcek = min(olcek, 1.0)
        sayfa = Image.new("RGB", SAYFA, "white")
        cizim = ImageDraw.Draw(sayfa)
        y = KENAR
        for satir, (yukseklik, hucreler) in grup:
            yukseklik = int(yukseklik * olcek)
            for p, (ofset, genislik) in zip(satir, hucreler):
                x = KENAR + ofset
                gorsel = ImageOps.fit(gorsel_oku(p).convert("RGB"), (genislik, yukseklik), centering=(0.5, 0.35))
                sayfa.paste(gorsel, (x, y))
                cizim.rectangle([x, y, x + genislik, y + yukseklik], outline="black", width=CERCEVE)
                p["sigmayan_balon"] = balonlari_ciz(cizim, (x, y, x + genislik, y + yukseklik),
                                                    p.get("replikler") or [], p.get("anlatim") or "")
            y += yukseklik + ARALIK
        sayfalar.append(sayfa)
    return sayfalar


# ── Bir oyunun mangası ───────────────────────────────────────────────────────

@dataclass
class Kullanim:
    girdi: int = 0
    cikti: int = 0
    gorsel: int = 0


class MangaUretici:
    """Bir oyunun manga klasörü: s001p1.png..., paneller.json, sayfa_01.png...
    gorunum_onbellegi: dünya başına model üretimi görünüm etiketleri (her oyunda aynı tarif)."""

    def __init__(self, dunya, servis, klasor: Path, llm=None, gorunum_onbellegi: Path | None = None):
        self.dunya = dunya
        self.servis = servis
        self.klasor = Path(klasor)
        self.llm = llm
        self.gorunum_onbellegi = gorunum_onbellegi
        self._gorunum: dict | None = None
        self.kullanim = Kullanim()

    @property
    def gorunum(self) -> dict:
        if self._gorunum is None:
            self._gorunum = gorunumleri_hazirla(self.dunya, self.llm, self.gorunum_onbellegi)
        return self._gorunum

    @property
    def _liste_yolu(self) -> Path:
        return self.klasor / "paneller.json"

    def paneller(self) -> list[dict]:
        try:
            return json.loads(self._liste_yolu.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _paneller_yaz(self, paneller: list[dict]) -> None:
        self.klasor.mkdir(parents=True, exist_ok=True)
        paneller.sort(key=lambda p: (p["sahne_no"], p["panel_no"]))
        gecici = self._liste_yolu.with_suffix(".tmp")
        gecici.write_text(json.dumps(paneller, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(gecici, self._liste_yolu)

    def sahne_ciz(self, sahne) -> list[dict]:
        """Sahnenin panellerini planlar ve çizer; aynı sahnenin eski panellerinin yerini alır
        (yeniden yazılan sahne)."""
        plan, yanit = sahne_plani(sahne, self.dunya, self.gorunum, self.llm)
        if yanit is not None:
            self.kullanim.girdi += yanit.girdi_token or 0
            self.kullanim.cikti += yanit.cikti_token or 0
        self.klasor.mkdir(parents=True, exist_ok=True)
        for p in plan:
            png, seed = self.servis.ciz(p["prompt_en"], p["genislik"], p["yukseklik"])
            p["dosya"] = f"s{sahne.no:03d}p{p['panel_no']}.png"
            (self.klasor / p["dosya"]).write_bytes(png)
            p["seed"], p["stil"] = seed, self.servis.stil
            self.kullanim.gorsel += 1
        eski = [p for p in self.paneller() if p["sahne_no"] == sahne.no]
        for p in eski:
            if p["dosya"] not in {y["dosya"] for y in plan}:
                (self.klasor / p["dosya"]).unlink(missing_ok=True)
        self._paneller_yaz([p for p in self.paneller() if p["sahne_no"] != sahne.no] + plan)
        return plan

    def sayfalari_kaydet(self) -> list[str]:
        paneller = [p for p in self.paneller() if (self.klasor / p["dosya"]).exists()]
        for eski in self.klasor.glob("sayfa_*.png"):
            eski.unlink()
        if not paneller:
            return []
        sayfalar = sayfalari_diz(paneller, lambda p: gorsel_ac(self.klasor / p["dosya"]))
        adlar = []
        for i, s in enumerate(sayfalar, 1):
            ad = f"sayfa_{i:02d}.png"
            s.save(self.klasor / ad, optimize=True)
            adlar.append(ad)
        return adlar
