"""
Dil modeli arka uçları.

  gemini  Google Gemini API (.env içinde GEMINI_API_KEY gerekir)
  yerel   OpenAI uyumlu bir sunucu: Ollama, vLLM, LM Studio...
          Hocanın GPU'lu makinesinde çalışan bir model de bu yolla bağlanır.
  sahte   Ağ kullanmayan, dünyadaki id'lerle geçerli yanıt üreten model — testler için
"""
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LLMYanit:
    metin: str
    sure: float
    girdi_token: int | None = None
    cikti_token: int | None = None


def json_coz(metin: str) -> dict:
    """Model yanıtından JSON nesnesini çıkarır; ```json ... ``` sarmalını açar.
    Geçersizse ValueError fırlatır."""
    metin = metin.strip()
    if metin.startswith("```"):
        metin = metin.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        veri = json.loads(metin)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON çözülemedi: {e}") from e
    if not isinstance(veri, dict):
        raise ValueError("Yanıt bir JSON nesnesi değil.")
    return veri


def env_yukle(yol: Path) -> None:
    """ANAHTAR=değer satırlarını okur; zaten tanımlı ortam değişkenlerini ezmez."""
    if not yol.exists():
        return
    for satir in yol.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        anahtar, deger = satir.split("=", 1)
        os.environ.setdefault(anahtar.strip(), deger.strip().strip("\"'"))


# Yazar modeli seçenekleri. Editör ve özet her zaman temel (hızlı) modeli kullanır.
# model None: .env'deki GEMINI_MODEL. dusunme: düşünme bütçesi (token); None: modelin varsayılanı.
YAZAR_SECENEKLERI = {
    "hizli":   {"model": None, "dusunme": 0,
                "aciklama": "Gemini 2.5 Flash, düşünmesiz. En hızlı ve en ucuz (varsayılan)."},
    "dusunen": {"model": None, "dusunme": 1024,
                "aciklama": "Aynı model, yazmadan önce düşünür. Daha tutarlı, tur başına ~1,5-2 kat maliyet."},
    "guclu":   {"model": "gemini-3.8-flash", "dusunme": None,
                "aciklama": "Daha yeni ve güçlü model. En iyi anlatım, tur başına ~2-3 kat maliyet."},
}


class GeminiLLM:
    def __init__(self, model: str, dusunme: int | None = 0):
        from google import genai
        from google.genai import types

        anahtar = os.environ.get("GEMINI_API_KEY")
        if not anahtar:
            raise RuntimeError("GEMINI_API_KEY tanımlı değil; .env dosyasına ekleyin (.env.example'a bakın).")
        self._istemci = genai.Client(api_key=anahtar)
        self._types = types
        self.model = model
        self.dusunme = dusunme
        self.ad = f"gemini:{model}"

    def _dusunme_ayari(self):
        # Düşünme bütçesi yalnızca 2.5 ailesinde ayarlanır; 3.x modelleri kendi
        # varsayılanıyla düşünür (bütçe 0'ı desteklemeyebilirler). Pro modeller kapatılamaz.
        if not self.model.startswith("gemini-2.5") or self.dusunme is None:
            return None
        if self.dusunme == 0 and "pro" in self.model:
            return None
        return self._types.ThinkingConfig(thinking_budget=self.dusunme)

    def uret(self, sistem: str, kullanici: str, json_mod: bool = True, sicaklik: float = 0.8) -> LLMYanit:
        ayar = self._types.GenerateContentConfig(
            system_instruction=sistem,
            temperature=sicaklik,
            response_mime_type="application/json" if json_mod else "text/plain",
            thinking_config=self._dusunme_ayari(),
        )
        bas = time.monotonic()
        yanit = self._istemci.models.generate_content(model=self.model, contents=kullanici, config=ayar)
        kullanim = yanit.usage_metadata
        cikti = getattr(kullanim, "candidates_token_count", None)
        dusunce = getattr(kullanim, "thoughts_token_count", None) or 0   # düşünme de çıktı fiyatından
        return LLMYanit(
            metin=yanit.text or "",
            sure=time.monotonic() - bas,
            girdi_token=getattr(kullanim, "prompt_token_count", None),
            cikti_token=(cikti or 0) + dusunce if cikti is not None or dusunce else None,
        )


class YerelLLM:
    def __init__(self, model: str, taban_url: str, anahtar: str = ""):
        import requests

        self._requests = requests
        self.taban_url = taban_url.rstrip("/")
        self.model = model
        self._anahtar = anahtar
        self.ad = f"yerel:{model}"

    def uret(self, sistem: str, kullanici: str, json_mod: bool = True, sicaklik: float = 0.8) -> LLMYanit:
        govde = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sistem},
                {"role": "user", "content": kullanici},
            ],
            "temperature": sicaklik,
        }
        if json_mod:
            govde["response_format"] = {"type": "json_object"}
        basliklar = {"Authorization": f"Bearer {self._anahtar}"} if self._anahtar else {}

        bas = time.monotonic()
        r = self._requests.post(f"{self.taban_url}/chat/completions",
                                json=govde, headers=basliklar, timeout=300)
        r.raise_for_status()
        veri = r.json()
        kullanim = veri.get("usage") or {}
        return LLMYanit(
            metin=veri["choices"][0]["message"]["content"] or "",
            sure=time.monotonic() - bas,
            girdi_token=kullanim.get("prompt_tokens"),
            cikti_token=kullanim.get("completion_tokens"),
        )


class SahteLLM:
    """Ağ kullanmaz. Motorun ve bellek stratejilerinin uçtan uca testi için."""

    def __init__(self, dunya=None):
        self.ad = "sahte"
        self._mekanlar = list(dunya.mekanlar) if dunya else []
        self._karakterler = list(dunya.karakterler) if dunya else []
        self._olgular = [o.id for o in dunya.olgular] if dunya else []
        self.cagri_sayisi = 0
        self.editor_cagrisi = 0

    # Dünya taslağı isteğine sahte yanıt (dunya_kurucu.taslak_uret testleri için)
    DUNYA_TASLAGI = {
        "ad": "Sisli Liman", "tur": "Gizem", "ton": "Nemli, kasvetli, fısıltılı",
        "donem": "Yelkenli gemiler çağı; buhar makinesi yok",
        "yoklar": ["Büyü yok", "Ateşli silah çok nadir ve pahalı"], "para_birimi": "gümüş",
        "oyuncu": {"kim": "Limana yeni gelen bir sigorta müfettişi", "neden": "Batan bir geminin kaydını incelemek",
                   "esyalar": ["not defteri", "mühürlü mektup"], "para": 12},
        "sir": ["Martı gemisi neden battı?"],
        "mekanlar": [{"ad": "Rıhtım Meyhanesi", "tanim": "Tavanı alçak, balık kokulu bir meyhane; yedi masa var."},
                     {"ad": "Liman Deposu", "tanim": "Kilitli, nemli bir ambar."}],
        "karakterler": [{"ad": "Meyhaneci Duru", "kisa_ad": "Duru", "gorunus": "Kızıl saçlı, kolları dövmeli",
                         "gorunen_ad": "Kızıl saçlı kadın", "kisilik": "Neşeli ama sır tutar",
                         "konusma": "Hızlı, şakacı", "imza": ["tatlım"], "ornek": "Otur tatlım, rom soğumasın.",
                         "sir": "Martı'nın kaptanını son gören o.", "yer": "Rıhtım Meyhanesi"}],
        "gercekler": ["Martı gemisi on iki gün önce battı; mürettebattan yalnızca ikisi kurtuldu.",
                      "Liman Deposu'nun anahtarı Meyhaneci Duru'da."],
        "acilis": {"mekan": "Rıhtım Meyhanesi", "zaman": "1. gün, akşam",
                   "metin": "Sis limanı yutarken meyhanenin kapısını itiyorsun."},
    }

    def uret(self, sistem: str, kullanici: str, json_mod: bool = True, sicaklik: float = 0.8) -> LLMYanit:
        self.cagri_sayisi += 1
        n = self.cagri_sayisi
        if not json_mod:
            return LLMYanit(metin=f"Özet {n}: oyuncu kasabada iz sürüyor.", sure=0.0)
        if "editörüsün" in sistem:
            return LLMYanit(metin=json.dumps(self._editor_yaniti(n, kullanici), ensure_ascii=False), sure=0.0)
        if "dünya tasarlayan" in sistem:
            return LLMYanit(metin=json.dumps(self.DUNYA_TASLAGI, ensure_ascii=False), sure=0.0)
        k = self._karakterler[n % len(self._karakterler)]
        veri = {
            "akis": [
                {"anlatim": f"Sahne {n}. Rüzgâr tuz taşıyor."},
                {"konusan": k, "replik": "Buradayım."},
            ],
            "mekan": self._mekanlar[n % len(self._mekanlar)],
            "zaman": f"{n}. gün, akşam",
            "karakterler": [k],
            "yeni_olgular": [{"metin": f"Sahte olgu {n}: körük onarıldı.", "ilgili": [k]}],
            "secenekler": [f"Seçenek {n}.{i}" for i in (1, 2, 3)],
        }
        return LLMYanit(metin=json.dumps(veri, ensure_ascii=False), sure=0.0)

    # Birbiriyle ve demo kanonla örtüşmeyen metinler: editörün tekrar denetimi bunları ayrı sayar
    YENI_OLGULAR = ["Kuyunun ipi yepyeni.", "Ahırın kapısı mavi boyalı.", "Demirhanenin çatısı akıyor.",
                    "Rafta kırmızı ciltli bir kitap duruyor.", "Kulenin dibinde bir eşek bağlı.",
                    "Pazarcı kadın incir satıyor."]
    SORULAR = ["Kuyu neden kurudu?", "Kulede kim yaşıyor?", "Mavi ışıklar nereden geliyor?",
               "Kâhyanın mektubu nerede?", "Pazar yeri niçin kapandı?", "Eski harita kimin elinde?"]

    def _editor_yaniti(self, n: int, kullanici: str) -> dict:
        """Her editör çağrısında: bir yeni iddia, bir çelişki, bir yeni vaat, bir karakter
        sapması; açık bir vaat varsa onu çözer."""
        i = self.editor_cagrisi
        self.editor_cagrisi += 1
        acik_vaatler = re.findall(r"^- \[(v\d+)\]", kullanici, re.M)
        yanit = {
            "iddialar": [
                {"metin": self.YENI_OLGULAR[i % len(self.YENI_OLGULAR)], "durum": "yeni", "olgu": None, "ilgili": []},
                {"metin": f"Sahte çelişki {n}", "durum": "celisiyor", "olgu": self._olgular[0], "ilgili": []},
            ],
            "vaatler": {
                "acilan": [self.SORULAR[i % len(self.SORULAR)]],
                "ilerleyen": [],
                "cozulen": [{"id": v, "kanit": "Sahte kanıt."} for v in acik_vaatler[:1]],
            },
            "karakter_denetimi": [{"karakter": self._karakterler[0], "kisilik": "sapma",
                                   "konusma": "uygun", "bilgi": "uygun", "gerekce": f"Sahte sapma {n}."}],
            "oyuncu_bilgi_sizintisi": "",
            "karakter_degisimleri": [{"karakter": self._karakterler[0], "degisim": f"Sahte değişim {n}"}],
        }
        if "zanaat:" in kullanici:
            yanit["zanaat"] = [{"ilke": "neden_sonuc", "sonuc": "zayif", "gerekce": "Sahte gerekçe."}]
            yanit["yazar_notu"] = f"Sahte not {n}."
        return yanit


def llm_olustur(tur: str, dunya=None, model: str | None = None, yazar: str | None = None):
    """yazar: YAZAR_SECENEKLERI'nden biri (yalnızca gemini'de anlamlı; diğerleri yok sayar)."""
    if tur == "gemini":
        secenek = YAZAR_SECENEKLERI[yazar or "hizli"]
        model = model or secenek["model"] or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        return GeminiLLM(model, dusunme=secenek["dusunme"])
    if tur == "yerel":
        return YerelLLM(
            model=model or os.environ.get("YEREL_LLM_MODEL", "qwen2.5:7b-instruct"),
            taban_url=os.environ.get("YEREL_LLM_URL", "http://localhost:11434/v1"),
            anahtar=os.environ.get("YEREL_LLM_ANAHTAR", ""),
        )
    if tur == "sahte":
        return SahteLLM(dunya)
    raise ValueError(f"Bilinmeyen model arka ucu: {tur}")
