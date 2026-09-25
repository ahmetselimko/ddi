"""
Editör: her sahneden sonra ikinci bir model çağrısı. Sahneyi yazmaz, denetler.

  yok      editör kapalı; yeni olguları yazar modelin kendisi bildirir
  denetim  sahnedeki iddiaları kanona karşı sınıflar (yeni / biliniyor / çelişiyor),
           vaat defterini ve karakter değişimlerini tutar
  tam      + usta yazarların derslerinden çıkarılmış ölçütlerle değerlendirme
           ve yazara bir sonraki sahne için not (ilkeler/zanaat.yaml)

Bulgular bir sonraki turda yazara geri döner: açık vaatler, çelişki uyarısı
ve (tam modda) editör notu. Böylece editör yalnızca ölçmez, yönlendirir de.
"""
from pathlib import Path

import yaml

from . import istem
from .dunya import Dunya
from .durum import Celiski, Durum, KarakterDegisimi
from .llm import json_coz

MODLAR = ("yok", "denetim", "tam")
ILKE_DOSYASI = Path(__file__).parent.parent / "ilkeler" / "zanaat.yaml"
_IDDIA_DURUMLARI = {"yeni", "biliniyor", "celisiyor"}


class EditorHatasi(ValueError):
    pass


def ilkeleri_yukle(yol: str | Path = ILKE_DOSYASI) -> list[dict]:
    return yaml.safe_load(Path(yol).read_text(encoding="utf-8"))["ilkeler"]


def editor_yanit_coz(metin: str, dunya: Dunya, durum: Durum) -> dict:
    """Editör yanıtını doğrular; bilinmeyen id'leri ve geçersiz kayıtları ayıklar."""
    try:
        veri = json_coz(metin)
    except ValueError as e:
        raise EditorHatasi(str(e)) from e

    bilinen = set(dunya.karakterler) | set(dunya.mekanlar)
    olgu_idleri = {o.id for o in dunya.olgular} | {o.id for o in durum.olgular}
    iddialar = []
    for i in veri.get("iddialar") or []:
        if not isinstance(i, dict) or i.get("durum") not in _IDDIA_DURUMLARI:
            continue
        metin_ = str(i.get("metin") or "").strip()
        if not metin_:
            continue
        olgu = i.get("olgu") if i.get("olgu") in olgu_idleri else None
        if i["durum"] == "celisiyor" and olgu is None:
            continue                        # neyle çeliştiği belli olmayan çelişki sayılmaz
        iddialar.append({
            "metin": metin_,
            "durum": i["durum"],
            "olgu": olgu,
            "ilgili": [x for x in i.get("ilgili") or [] if x in bilinen],
        })

    acik = {v.id for v in durum.acik_vaatler}
    ham_vaatler = veri.get("vaatler") or {}
    vaatler = {
        "acilan": [str(m).strip() for m in ham_vaatler.get("acilan") or [] if str(m).strip()][:2],
        "ilerleyen": [v for v in ham_vaatler.get("ilerleyen") or [] if v in acik],
        "cozulen": [v for v in ham_vaatler.get("cozulen") or [] if v in acik],
    }

    degisimler = [
        {"karakter": d["karakter"], "degisim": str(d.get("degisim") or "").strip()}
        for d in veri.get("karakter_degisimleri") or []
        if isinstance(d, dict) and d.get("karakter") in dunya.karakterler and str(d.get("degisim") or "").strip()
    ]

    zanaat = [
        {"ilke": z["ilke"], "sonuc": z["sonuc"], "gerekce": str(z.get("gerekce") or "").strip()}
        for z in veri.get("zanaat") or []
        if isinstance(z, dict) and z.get("ilke") and z.get("sonuc") in ("iyi", "zayif")
    ]

    return {
        "iddialar": iddialar,
        "vaatler": vaatler,
        "karakter_degisimleri": degisimler,
        "zanaat": zanaat,
        "yazar_notu": str(veri.get("yazar_notu") or "").strip(),
    }


class Editor:
    def __init__(self, mod: str = "tam", ilkeler: list[dict] | None = None):
        if mod not in MODLAR:
            raise ValueError(f"Bilinmeyen editör modu: {mod} (seçenekler: {', '.join(MODLAR)})")
        self.mod = mod
        self.acik = mod != "yok"
        self.zanaat_acik = mod == "tam"
        if ilkeler is None:
            ilkeler = ilkeleri_yukle() if self.zanaat_acik else []
        self.ilkeler = ilkeler

    def denetle(self, dunya: Dunya, durum: Durum, llm, deneme: int = 2):
        """Son sahneyi denetler ve durumu günceller. (bulgular, yanıtlar) döndürür;
        editör geçerli yanıt veremezse bulgular None olur ve oyun sürer."""
        sahne = durum.sahneler[-1]
        sistem, kullanici = istem.editor_istemi(dunya, durum, sahne, self.ilkeler, self.zanaat_acik)
        yanitlar, istek = [], kullanici
        for _ in range(deneme):
            yanit = llm.uret(sistem, istek, sicaklik=0.2)
            yanitlar.append(yanit)
            try:
                bulgular = editor_yanit_coz(yanit.metin, dunya, durum)
                break
            except EditorHatasi as e:
                istek = f"{kullanici}\n\nÖnceki yanıtın geçersizdi ({e}). Yalnızca istenen JSON'u döndür."
        else:
            return None, yanitlar
        self._uygula(bulgular, durum, sahne.no)
        return bulgular, yanitlar

    def _uygula(self, bulgular: dict, durum: Durum, no: int) -> None:
        for i in bulgular["iddialar"]:
            if i["durum"] == "yeni":
                durum.olgu_ekle(i["metin"], i["ilgili"], no)
            elif i["durum"] == "celisiyor":
                durum.celiskiler.append(Celiski(sahne_no=no, iddia=i["metin"], olgu_id=i["olgu"]))

        vaatler = {v.id: v for v in durum.vaatler}
        for vid in bulgular["vaatler"]["ilerleyen"]:
            vaatler[vid].ilerledigi_sahneler.append(no)
        for vid in bulgular["vaatler"]["cozulen"]:
            vaatler[vid].cozuldugu_sahne = no
        for metin in bulgular["vaatler"]["acilan"]:
            durum.vaat_ac(metin, no)

        for d in bulgular["karakter_degisimleri"]:
            durum.karakter_degisimleri.append(KarakterDegisimi(sahne_no=no, **d))
        if self.zanaat_acik:
            durum.editor_notu = bulgular["yazar_notu"]
            durum.zanaat_gecmisi.append([z["ilke"] for z in bulgular["zanaat"] if z["sonuc"] == "zayif"])

    def yazara_bolumler(self, dunya: Dunya, durum: Durum) -> list[str]:
        """Bir sonraki sahneyi yazacak modele gidecek editör bölümleri."""
        if not self.acik or not durum.sahneler:
            return []
        bolumler = []
        simdiki = len(durum.sahneler)

        if durum.acik_vaatler:
            bolumler.append(
                "[AÇIK VAATLER — okurun cevabını beklediği sorular. Unutma, ilerlet; "
                "ama hepsini birden çözme. En son açılan en önce kapanır.]\n"
                + "\n".join(f"- [{v.id}] {v.metin} ({simdiki - v.acildigi_sahne + 1} sahnedir açık)"
                            for v in durum.acik_vaatler)
            )

        son_celiskiler = [c for c in durum.celiskiler if c.sahne_no == simdiki]
        if son_celiskiler:
            olgular = {o.id: o.metin for o in dunya.olgular} | {o.id: o.metin for o in durum.olgular}
            bolumler.append(
                "[DİKKAT — son sahne şu olgularla çelişti; bundan sonra olgulara uy]\n"
                + "\n".join(f'- Yazılan: "{c.iddia}" · Doğrusu: {olgular.get(c.olgu_id, c.olgu_id)}'
                            for c in son_celiskiler)
            )

        # Modele sorulmadan, doğrudan sayılarak bulunan sorun: karakterler sahnedeydi ama konuşmadı
        son = durum.sahneler[-1]
        konusanlar = {r.karakter for r in son.replikler}
        susanlar = [dunya.karakterler[k].ad for k in son.karakterler if k not in konusanlar]
        if son.karakterler and not konusanlar:
            bolumler.append(f"[DİKKAT — önceki sahnede {', '.join(susanlar)} hiç konuşmadı. "
                            "Bu sahnede sahnedeki karakterler konuşsun ve oyuncuya cevap versin.]")

        if self.zanaat_acik:
            tekrarlayan = _tekrarlayan_zayiflar(durum.zanaat_gecmisi)
            if tekrarlayan:
                ilke_metni = {i["id"]: i["ilke"] for i in self.ilkeler}
                bolumler.append(
                    "[TEKRARLAYAN SORUN — son iki sahnede de zayıftı; bu sahnede mutlaka düzelt]\n"
                    + "\n".join(f"- {i}: {ilke_metni.get(i, '')}" for i in tekrarlayan)
                )
            if durum.editor_notu:
                bolumler.append(f"[EDİTÖR NOTU]\n{durum.editor_notu}")
        return bolumler


def _tekrarlayan_zayiflar(gecmis: list[list[str]]) -> list[str]:
    if len(gecmis) < 2:
        return []
    return [i for i in gecmis[-1] if i in gecmis[-2]]
