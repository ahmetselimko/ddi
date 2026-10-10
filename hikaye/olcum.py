"""
Ölçüm: oyun kayıtlarından (oturumlar/*.jsonl) tutarlılık raporu ve editörün
çelişki yakalama başarısını bilinen doğruya karşı ölçen enjeksiyon deneyi.

  rapor        Kayıtlardaki editör ve kod bulgularını sayar: 10 bin sözcük başına
               çelişki (CED, ConStory-Bench), 10 turluk dilimler, karakter sapmaları,
               kod uyarıları, editörün başarısızlık oranı, token ve maliyet.
  enjeksiyon   Gerçek sahnelere, sahneyle ilgili bir dünya olgusuyla açıkça çelişen tek
               bir cümle eklenir (FlawedFictions yöntemi). Editör orijinal ve bozulmuş
               sahneyi ayrı ayrı denetler: eklenen çelişkiyi yakalıyor mu, dokunulmamış
               sahnede alarm veriyor mu. Editör oyundaki gibi "tam" modda çalışır.
               Eklenen cümleler elle doğrulanmaz: bazıları gerçek çelişki olmayabilir.

Editörün kararları "doğru" kabul edilmez: rapor editörün ne dediğini sayar, enjeksiyon
deneyi ise ne kadar doğru dediğini ölçer.
"""
import copy
import json
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .dunya import Dunya, dunya_yukle
from .durum import Durum, OyunOlgusu, Replik, Sahne
from .editor import Editor
from .llm import dolar, json_coz
from .motor import ETIKETLI_SATIR

DILIM = 10                    # tur dilimi (çelişkiler hikâyenin ortasında mı yığılıyor?)

# Kod uyarılarının türleri: uyarı metninin başına göre
UYARI_TURLERI = [
    ("oyuncu adına konuşma", ("oyuncu adına replik",)),
    ("tanışma", ("anlatım, oyuncunun adını", "seçenekler, oyuncunun adını")),
    ("tekrar", ("önceki sahneden aynen", "seçenek oyuncunun zaten")),
    ("örnek replik kopyası", ("örnek replik aynen",)),
    ("ses karışması", ("ses karışması",)),
    ("eşya ve para", ("oyuncunun üzerinde olmayan", "seçenek oyuncuda olmayan", "eylem denetimi:")),
    ("envanter uyuşmazlığı", ("envanter uyuşmazlığı",)),
    ("zaman", ("zaman geri gidemez",)),
    ("karakter durumu", ("karakter durumu reddedildi",)),
    ("konuşmasız sahne", ("sahnede karakter var ama",)),
    ("biçim", ("bilinmeyen", "konuşan id'si", "akış yerine", "replikte bilinmeyen")),
]


def uyari_turu(uyari: str) -> str:
    if re.search(r"\d+ (\S+ )?parası var", uyari):
        return "eşya ve para"
    for tur, onekler in UYARI_TURLERI:
        if uyari.startswith(onekler):
            return tur
    return "diğer"


# ── Kayıttan durum kurma ─────────────────────────────────────────────────────

def kayit_oku(yol: Path) -> list[dict]:
    satirlar = []
    for satir in Path(yol).read_text(encoding="utf-8").splitlines():
        if satir.strip():
            try:
                satirlar.append(json.loads(satir))
            except ValueError:
                continue                     # yarım kalmış satır
    return satirlar


def gecerli_turlar(satirlar: list[dict]) -> list[dict]:
    """Yeniden yazılan (geri_al) turlar atılmış, numara sırasıyla turlar."""
    turlar: list[dict] = []
    for s in satirlar:
        if s.get("tip") == "tur":
            turlar.append(s)
        elif s.get("tip") == "geri_al":
            turlar = [t for t in turlar if t["no"] < s["no"]]
    return sorted(turlar, key=lambda t: t["no"])


def dunya_bul(ad: str, klasor: Path) -> tuple[str, Dunya] | None:
    """Kayıttaki dünya adını (ör. "Tuzhan") dosyasıyla eşler."""
    for yol in sorted(Path(klasor).glob("*.yaml")):
        try:
            d = dunya_yukle(yol)
        except Exception:
            continue
        if d.ad == ad:
            return yol.stem, d
    return None


def _sahne(s: dict) -> Sahne:
    return Sahne(**{**s, "replikler": [Replik(**r) for r in s.get("replikler", [])]})


def durumlari_kur(satirlar: list[dict], dunya: Dunya) -> list[tuple[dict, Durum]]:
    """Kaydı baştan oynatır. Her tur için (tur kaydı, editörün gördüğü durum): durum
    sahneden ÖNCEKİ hâlindedir ve sahne sahneler'in sonuna eklenmiştir (editör böyle görür)."""
    durum = Durum(mekan=dunya.baslangic_mekan, zaman=dunya.baslangic_zamani,
                  esyalar=list(dunya.oyuncu_esyalar), akce=dunya.oyuncu_akce)
    for soru in dunya.vaatler:
        durum.vaat_ac(soru, 0)
    sonuc = []
    for t in gecerli_turlar(satirlar):
        sahne = _sahne(t["sahne"])
        gorulen = copy.deepcopy(durum)
        gorulen.sahneler.append(sahne)
        sonuc.append((t, gorulen))

        durum.sahneler.append(sahne)
        for o in t.get("yeni_olgular") or []:
            durum.olgular.append(OyunOlgusu(**o))
        e = t.get("editor")
        if e:
            vaatler = {v.id: v for v in durum.vaatler}
            ham = e.get("vaatler") or {}            # eski kayıtlarda alanlar eksik olabilir
            for x in ham.get("ilerleyen") or []:
                if isinstance(x, dict) and x.get("id") in vaatler:
                    vaatler[x["id"]].ilerledigi_sahneler.append(sahne.no)
            for x in ham.get("cozulen") or []:
                if isinstance(x, dict) and x.get("id") in vaatler:
                    vaatler[x["id"]].cozuldugu_sahne = sahne.no
            for m in ham.get("acilan") or []:
                durum.vaat_ac(str(m), sahne.no)
        durum.taninan = list(t.get("taninan") or durum.taninan)
        durum.esyalar = list(t.get("esyalar") if t.get("esyalar") is not None else durum.esyalar)
        durum.akce = t.get("akce", durum.akce)
        if sahne.mekan in dunya.mekanlar:
            durum.mekan = sahne.mekan
        durum.zaman = sahne.zaman or durum.zaman
    return sonuc


# ── Rapor ────────────────────────────────────────────────────────────────────

def _sozcuk(metin: str) -> int:
    return len(metin.split())


def _ced(celiski: int, sozcuk: int) -> float | None:
    return round(celiski * 10000 / sozcuk, 2) if sozcuk else None


@dataclass
class OturumOzeti:
    ad: str
    dunya: str
    editor: str
    tur: int = 0
    sozcuk: int = 0
    celiski: int = 0
    dilimler: dict = field(default_factory=dict)          # dilim başlangıcı → [çelişki, sözcük]
    sapmalar: Counter = field(default_factory=Counter)
    oyuncu_sizintisi: int = 0
    uyarilar: Counter = field(default_factory=Counter)
    editor_basarisiz: int = 0
    otomatik: Counter = field(default_factory=Counter)
    eylem: Counter = field(default_factory=Counter)       # editöre göre eylem karşılandı mı
    girdi: int = 0
    cikti: int = 0
    dolar: float = 0.0
    sure: float = 0.0


def oturum_ozeti(yol: Path) -> OturumOzeti | None:
    satirlar = kayit_oku(yol)
    meta = next((s for s in satirlar if s.get("tip") == "meta"), None)
    turlar = gecerli_turlar(satirlar)
    if meta is None or not turlar or str(meta.get("llm", "")).startswith("sahte"):
        return None                          # sahte modelle yapılan denemeler ölçüme girmez
    o = OturumOzeti(ad=Path(yol).stem, dunya=meta.get("dunya", "?"), editor=meta.get("editor", "?"))
    model = meta.get("llm", "")
    for t in turlar:
        metin = t["sahne"]["metin"]
        o.tur += 1
        o.sozcuk += _sozcuk(metin)
        dilim = (t["no"] - 1) // DILIM * DILIM + 1
        o.dilimler.setdefault(dilim, [0, 0])[1] += _sozcuk(metin)
        e = t.get("editor")
        if e:
            celiski = sum(i.get("durum") == "celisiyor" for i in e.get("iddialar") or [])
            o.celiski += celiski
            o.dilimler[dilim][0] += celiski
            for d in e.get("karakter_denetimi") or []:
                for alan in ("kisilik", "konusma", "bilgi"):
                    if d.get(alan, "uygun") != "uygun":
                        o.sapmalar[alan] += 1
            o.oyuncu_sizintisi += bool(e.get("oyuncu_bilgi_sizintisi"))
            for k, v in (e.get("otomatik") or {}).items():
                o.otomatik[k] += len(v)
            if t.get("eylem") and isinstance(e.get("eylem"), dict):
                o.eylem[e["eylem"].get("karsilandi", "?")] += 1
        o.editor_basarisiz += bool(t.get("editor_basarisiz"))
        for u in t.get("uyarilar") or []:
            o.uyarilar[uyari_turu(u)] += 1
        o.girdi += t.get("girdi_token") or 0
        o.cikti += t.get("cikti_token") or 0
        o.sure += t.get("sure") or 0
    o.dolar = dolar(model, o.girdi, o.cikti) or 0.0
    return o


_SAPMA_ADLARI = {"kisilik": "kişilik", "konusma": "konuşma", "bilgi": "bilgi sızıntısı"}


def rapor(yollar: list[Path]) -> str:
    """Kayıtlardan Markdown rapor. Editörsüz oturumlar çelişki ölçümüne katılmaz."""
    ozetler = [o for o in (oturum_ozeti(y) for y in yollar) if o]
    if not ozetler:
        return "Raporlanacak tur kaydı bulunamadı.\n"
    editorlu = [o for o in ozetler if o.editor in ("denetim", "tam")]
    s = ["# Tutarlılık raporu", "",
         f"{len(ozetler)} oturum, {sum(o.tur for o in ozetler)} tur, {sum(o.sozcuk for o in ozetler)} sözcük. "
         f"Çelişkiler editörün kararlarıdır; doğruluğu `enjeksiyon` deneyiyle ölçülür.", "",
         "## Oturumlar", "",
         "| Oturum | Dünya | Editör | Tur | Sözcük | Çelişki | CED | Sapma | Oyuncu sızıntısı | Editör başarısız | $ |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for o in ozetler:
        var = o in editorlu
        ced = _ced(o.celiski, o.sozcuk) if var else None
        s.append(f"| {o.ad} | {o.dunya} | {o.editor} | {o.tur} | {o.sozcuk} | "
                 f"{o.celiski if var else '—'} | {ced if ced is not None else '—'} | "
                 f"{sum(o.sapmalar.values())} | {o.oyuncu_sizintisi} | {o.editor_basarisiz} | {o.dolar:.3f} |")

    if editorlu:
        sozcuk = sum(o.sozcuk for o in editorlu)
        celiski = sum(o.celiski for o in editorlu)
        s += ["", "## Editörlü oturumların toplamı", "",
              f"- Çelişki: {celiski} · **CED (10 bin sözcük başına): {_ced(celiski, sozcuk)}**",
              f"- Editörün başarısız olduğu tur: {sum(o.editor_basarisiz for o in editorlu)} / "
              f"{sum(o.tur for o in editorlu)}"]
        sapma = sum((o.sapmalar for o in editorlu), Counter())
        if sapma:
            s.append("- Karakter sapmaları: " + ", ".join(f"{_SAPMA_ADLARI[k]} {v}" for k, v in sapma.most_common()))
        s.append(f"- Oyuncuya bilgi sızıntısı: {sum(o.oyuncu_sizintisi for o in editorlu)}")
        eylem = sum((o.eylem for o in editorlu), Counter())
        if eylem:
            s.append("- Oyuncunun eylemi karşılandı mı (editöre göre): "
                     + ", ".join(f"{k} {eylem[k]}" for k in ("evet", "kismen", "hayir") if eylem[k]))
        otomatik = sum((o.otomatik for o in editorlu), Counter())
        if otomatik:
            s.append("- Kodun editörü düzelttiği yerler: "
                     + ", ".join(f"{k} {v}" for k, v in otomatik.most_common() if v))

        dilimler: dict = {}
        for o in editorlu:
            for d, (c, w) in o.dilimler.items():
                dilimler.setdefault(d, [0, 0])
                dilimler[d][0] += c
                dilimler[d][1] += w
        s += ["", f"### {DILIM} turluk dilimlere göre", "", "| Turlar | Çelişki | Sözcük | CED |", "|---|---|---|---|"]
        for d in sorted(dilimler):
            c, w = dilimler[d]
            s.append(f"| {d}–{d + DILIM - 1} | {c} | {w} | {_ced(c, w)} |")

    uyarilar = sum((o.uyarilar for o in ozetler), Counter())
    s += ["", "## Kod denetimleri (modelden bağımsız)", ""]
    s += [f"- {k}: {v}" for k, v in uyarilar.most_common()] or ["- uyarı yok"]
    tur = sum(o.tur for o in ozetler)
    s += ["", "## Maliyet ve süre", "",
          f"- Token: {sum(o.girdi for o in ozetler)} girdi, {sum(o.cikti for o in ozetler)} çıktı",
          f"- Tahmini: ${sum(o.dolar for o in ozetler):.3f} (her tur yazar modelin fiyatıyla; yaklaşık)",
          f"- Tur başına ortalama süre: {sum(o.sure for o in ozetler) / tur:.1f} sn"]
    return "\n".join(s) + "\n"


# ── Enjeksiyon deneyi ────────────────────────────────────────────────────────

_CELISKI_SISTEM = (
    "Sen bir tutarlılık testi için veri hazırlayan çelişki cümlesi yazarısın. Sana bir hikâye "
    "sahnesi ve o hikâyenin kesin bir gerçeği verilir. Sahneye eklenecek, o gerçekle AÇIKÇA çelişen "
    "TEK bir cümle yazarsın. Yalnızca istenen JSON'u döndür."
)


def celiski_istemi(sahne_metni: str, olgu_metni: str) -> str:
    return (f"KESİN GERÇEK: {olgu_metni}\n\nSAHNE:\n{sahne_metni}\n\n"
            "Bu sahnenin anlatımına eklenecek, sahnenin üslubunda (ikinci tekil şahıs, şimdiki zaman) "
            "tek bir cümle yaz. Cümle yukarıdaki gerçekle açıkça çelişsin: sayıyı, sahibi, akrabalığı ya "
            "da durumu tersine çevir ya da değiştir (ör. \"kilitli\" → \"ardına kadar açık\"). Cümle tek "
            "başına okununca çelişki anlaşılsın; \"belki\", \"sanki\" gibi yumuşatıcılar kullanma. "
            "Karakter repliği değil, anlatım cümlesi olsun.\n\n"
            'JSON: {"cumle": "..."}')


def cumle_ekle(metin: str, cumle: str) -> str:
    """Cümleyi sahnenin ortasındaki anlatım satırının sonuna ekler (replik satırlarına değil)."""
    satirlar = metin.split("\n")
    anlatim = [i for i, s in enumerate(satirlar) if s.strip() and not ETIKETLI_SATIR.match(s.strip())]
    if not anlatim:
        orta = len(satirlar) // 2
        return "\n".join(satirlar[:orta] + [cumle] + satirlar[orta:])
    i = anlatim[len(anlatim) // 2]
    satirlar[i] = f"{satirlar[i].rstrip()} {cumle}"
    return "\n".join(satirlar)


def hedef_olgular(dunya: Dunya, durum: Durum) -> list:
    """Sahnenin mekânı ve karakterleriyle ilgili somut dünya olguları (açılış ve kurallar hariç)."""
    sahne = durum.sahneler[-1]
    idler = set(sahne.karakterler + [sahne.mekan])
    return [o for o in dunya.olgular if idler & set(o.ilgili)]


class _Hazir(Exception):
    """Cümle önceki koşudan geldi; üretim atlanır."""


def _celiskiler(bulgular: dict | None) -> list[dict]:
    return [i for i in (bulgular or {}).get("iddialar", []) if i.get("durum") == "celisiyor"]


@dataclass
class Ornek:
    oturum: str
    sahne_no: int
    olgu: str
    cumle: str
    orijinal: list = field(default_factory=list)       # orijinal sahnedeki çelişki kararları
    bozuk: list = field(default_factory=list)
    orijinal_basarisiz: bool = False
    bozuk_basarisiz: bool = False

    @property
    def siki(self) -> bool:
        return any(c["olgu"] == self.olgu for c in self.bozuk)

    @property
    def gevsek(self) -> bool:
        return bool(self.bozuk)


def ornek_havuzu(yollar: list[Path], dunya_klasoru: Path) -> list[tuple[str, Dunya, Durum]]:
    """Editörlü kayıtlardaki, ilgili dünya olgusu olan sahneler."""
    havuz = []
    for yol in yollar:
        satirlar = kayit_oku(yol)
        meta = next((s for s in satirlar if s.get("tip") == "meta"), {})
        if meta.get("editor") not in ("denetim", "tam") or str(meta.get("llm", "")).startswith("sahte"):
            continue
        bulunan = dunya_bul(meta.get("dunya", ""), dunya_klasoru)
        if not bulunan:
            continue
        _, dunya = bulunan
        for t, durum in durumlari_kur(satirlar, dunya):
            sahne = durum.sahneler[-1]
            if sahne.mekan in dunya.mekanlar and durum.mekan in dunya.mekanlar and hedef_olgular(dunya, durum):
                havuz.append((Path(yol).stem, dunya, durum))
    return havuz


def enjeksiyon(havuz, llm, editor_llm=None, ornek: int = 25, tohum: int = 7,
               en_fazla_dolar: float | None = None, ilerleme=None, hazir: dict | None = None,
               editor_modu: str = "tam") -> dict:
    """Her örnek: 1 çelişki cümlesi üretimi + orijinal ve bozuk sahnede birer editör denetimi.
    hazir: {(oturum, sahne_no): (olgu id, cümle)} — önceki bir koşunun cümleleri; önce/sonra
    karşılaştırmasında iki editör aynı çelişkilerle sınansın diye (üretim de atlanır)."""
    editor_llm = editor_llm or llm
    rastgele = random.Random(tohum)
    secilen = rastgele.sample(havuz, min(ornek, len(havuz)))
    sonuclar: list[Ornek] = []
    harcama = 0.0
    for oturum, dunya, durum in secilen:
        if en_fazla_dolar is not None and harcama >= en_fazla_dolar:
            break
        sahne = durum.sahneler[-1]
        olgu = rastgele.choice(hedef_olgular(dunya, durum))
        if hazir is not None:
            if (oturum, sahne.no) not in hazir:
                continue
            olgu_id, cumle = hazir[(oturum, sahne.no)]
            olgu = next(o for o in dunya.olgular if o.id == olgu_id)
        else:
            cumle = None
        try:
            if cumle is not None:
                raise _Hazir
            yanit = llm.uret(_CELISKI_SISTEM, celiski_istemi(sahne.metin, olgu.metin), sicaklik=0.7)
            harcama += dolar(llm.ad, yanit.girdi_token or 0, yanit.cikti_token or 0) or 0
            cumle = str(json_coz(yanit.metin).get("cumle") or "").strip()
        except _Hazir:
            pass
        except Exception:
            continue
        if not cumle or len(cumle.split()) > 45:
            continue
        o = Ornek(oturum=oturum, sahne_no=sahne.no, olgu=olgu.id, cumle=cumle)
        for bozuk in (False, True):
            d = copy.deepcopy(durum)
            if bozuk:
                d.sahneler[-1].metin = cumle_ekle(d.sahneler[-1].metin, cumle)
            bulgular, yanitlar = Editor(editor_modu).denetle(dunya, d, editor_llm)
            harcama += sum(dolar(editor_llm.ad, y.girdi_token or 0, y.cikti_token or 0) or 0 for y in yanitlar)
            if bozuk:
                o.bozuk, o.bozuk_basarisiz = _celiskiler(bulgular), bulgular is None
            else:
                o.orijinal, o.orijinal_basarisiz = _celiskiler(bulgular), bulgular is None
        sonuclar.append(o)
        if ilerleme:
            ilerleme(len(sonuclar), len(secilen), harcama)
    return {"ornekler": sonuclar, "dolar": round(harcama, 4), "havuz": len(havuz)}


def enjeksiyon_ozeti(sonuc: dict) -> dict:
    ornekler = [o for o in sonuc["ornekler"] if not (o.orijinal_basarisiz or o.bozuk_basarisiz)]
    n = len(ornekler)
    oran = lambda k: round(k / n, 3) if n else None   # noqa: E731
    return {
        "ornek": n,
        "editor_basarisiz": len(sonuc["ornekler"]) - n,
        "yakalama_siki": oran(sum(o.siki for o in ornekler)),
        "yakalama_gevsek": oran(sum(o.gevsek for o in ornekler)),
        "orijinalde_alarm": oran(sum(bool(o.orijinal) for o in ornekler)),
        "dolar": sonuc["dolar"],
        "havuz": sonuc["havuz"],
    }
