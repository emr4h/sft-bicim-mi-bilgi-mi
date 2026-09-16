"""
Türkçe çıktıyı KODLA skorlar. LLM hakem yok.

NEDEN HAKEM YOK?
    Asıl sebep basit: bu görevde en önemli doğruluk özelliği tartışmasız
    ölçülebilir. Kimlik koruma kesin, yapı sayılabilir, dil taranabilir.
    Ölçüm kesin olabiliyorken hakem çağırmak hem pahalı hem gereksiz hem de
    tekrarlanabilirliği düşürür — aynı çıktıya iki koşuda farklı puan gelir.

    İkincil bir sebep daha var ama zayıf kaynaklı olduğunu bilerek yazıyoruz:
    LLM hakemlerin çeviri kokan metni tercih ettiğine dair bir bulgu var
    (arXiv 2603.10351), fakat bu henüz hakem sürecinden geçmemiş bir ön baskı.
    Kararımız buna dayanmıyor; dayansaydı zemini sağlam olmazdı.
    (15.09.2026 denetimi — gerekçenin tamamı README'de)

EN ÖNEMLİ BİLEŞEN: KİMLİK KORUMA
    Model bir ATT&CK kimliğini (T1216.001), azaltma kodunu (M1038) ya da log
    kaynağını (WinEventLog:Sysmon) düşürür veya değiştirirse çıktı YANLIŞTIR.
    Bir analist o kimliği arayacak. Bu kesin ölçülebilir ve pazarlığı yok.

KULLANIM
    python skorla.py veri/uretilen_tr.jsonl
    python skorla.py cikti/test_344.jsonl --ayrinti
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

from terimler import BASLIKLAR, KIMLIK_DESENLERI, KORUNAN, kimlikleri_cikar

TR_HARF = set("çğıöşüÇĞİÖŞÜ")

# Teknik terimler İngilizce kalabilir; dil ölçümünde onları saymayalım.
IZINLI_EN = set(KORUNAN) | {
    "windows", "linux", "powershell", "sysmon", "event", "security", "cloud",
    "aws", "azure", "gcp", "nist", "iso", "mitre", "att", "ck", "sp", "id",
    "url", "ip", "dns", "http", "https", "api", "cli", "exe", "dll", "vbs",
}

# Türkçe olmadığını ele veren yaygın İngilizce kelimeler
EN_ISARET = {"the", "and", "this", "that", "with", "from", "for", "are", "was",
             "were", "have", "has", "been", "will", "should", "would", "can",
             "identify", "review", "ensure", "validate", "monitor", "confirm",
             "activity", "following", "affected", "malicious", "incident"}


def dil_skoru(metin, hedef="tr"):
    """hedef='tr' -> çıktı Türkçe mi?   hedef='en' -> çıktı İngilizce mi?

    İngilizce mod 1. paketin ana deneyinde kullanılıyor: orada ölçülen şey
    dil değil veri miktarı, o yüzden çıktı da kaynak da İngilizce kalıyor.
    Bileşen yine de duruyor — model dil kaydırırsa yakalansın diye.
    """
    kelimeler = [k for k in re.findall(r"[a-zçğıöşüA-ZÇĞİÖŞÜ]{2,}", metin.lower())
                 if k not in IZINLI_EN]
    if not kelimeler:
        return 0.0, "kelime yok"
    en_oran = sum(1 for k in kelimeler if k in EN_ISARET) / len(kelimeler)

    if hedef == "en":
        # İngilizce beklerken Türkçe harf görmek dil kaymasıdır.
        tr_oran = sum(1 for c in metin if c in TR_HARF) / max(1, len(metin))
        if tr_oran > 0.005:
            return 0.0, f"Türkçe sızmış (%{tr_oran*100:.1f})"
        return 1.0, ""

    if en_oran > 0.08:
        return 0.0, f"İngilizce yoğun (%{en_oran*100:.0f})"
    if not (set(metin) & TR_HARF):
        return 0.0, "Türkçe harf yok"
    return 1.0, ""


def yapi_sayilari(metin):
    return (len(re.findall(r"\*\*[^*\n]+\*\*", metin)),      # kalın başlıklar
            len(re.findall(r"^\s*\d+\.\s", metin, re.M)))    # numaralı adımlar


def skorla_kayit(k, hedef="tr"):
    kaynak, cikti = k["output_en"], (k.get("output_tr") or "")
    s, notlar = {}, []

    if not cikti.strip():
        return {a: 0.0 for a in ["kimlik", "dil", "yapi", "uzunluk",
                                 "baslik", "TOPLAM"]}, ["boş çıktı"]

    # 1) KİMLİK KORUMA — en kritik bileşen, kesin ölçüm
    kay_k, cik_k = kimlikleri_cikar(kaynak), kimlikleri_cikar(cikti)
    beklenen = set().union(*kay_k.values())
    bulunan = set().union(*cik_k.values())
    if beklenen:
        eksik = beklenen - bulunan
        s["kimlik"] = 1 - len(eksik) / len(beklenen)
        if eksik:
            notlar.append(f"düşen kimlik: {sorted(eksik)[:4]}")
    else:
        s["kimlik"] = 1.0

    # 2) DİL
    s["dil"], sebep = dil_skoru(cikti, hedef)
    if sebep:
        notlar.append(f"dil: {sebep}")

    # 3) YAPI — başlık ve adım sayısı kaynağa yakın mı
    kb, ka = yapi_sayilari(kaynak)
    cb, ca = yapi_sayilari(cikti)
    def yakin(a, b):
        if a == 0:
            return 1.0 if b == 0 else 0.5
        return max(0.0, 1 - abs(a - b) / a)
    s["yapi"] = (yakin(kb, cb) + yakin(ka, ca)) / 2
    if s["yapi"] < 0.8:
        notlar.append(f"yapı kaydı: başlık {kb}→{cb}, adım {ka}→{ca}")

    # 4) UZUNLUK — Türkçe biraz uzar; 0.7-1.8 kat makul.
    oran = len(cikti) / max(1, len(kaynak))
    s["uzunluk"] = 1.0 if 0.7 <= oran <= 1.8 else 0.0
    if s["uzunluk"] == 0:
        notlar.append(f"uzunluk oranı {oran:.2f}")

    # 5) BAŞLIK — kaynakta geçen bölüm başlıkları çıktıda var mı?
    # Türkçe modda sözlükteki karşılığı aranır, İngilizce modda başlığın
    # kendisi. İkisi de aynı şeyi ölçüyor: çıktı kaynağın iskeletini kurmuş mu.
    if hedef == "en":
        beklenen_b = [en for en in BASLIKLAR if en.lower() in kaynak.lower()]
    else:
        beklenen_b = [tr for en, tr in BASLIKLAR.items() if en.lower() in kaynak.lower()]
    if beklenen_b:
        var = sum(1 for tr in beklenen_b if tr.lower() in cikti.lower())
        s["baslik"] = var / len(beklenen_b)
        if var < len(beklenen_b):
            eks = [tr for tr in beklenen_b if tr.lower() not in cikti.lower()]
            notlar.append(f"sözlük başlığı yok: {eks[:3]}")
    else:
        s["baslik"] = 1.0

    s["TOPLAM"] = sum(s[a] for a in ["kimlik", "dil", "yapi", "uzunluk", "baslik"]) / 5
    return s, notlar


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dosya")
    ap.add_argument("--ayrinti", action="store_true")
    ap.add_argument("--hedef", choices=["tr", "en"], default="tr",
                    help="Beklenen çıktı dili (varsayılan tr)")
    args = ap.parse_args()

    kayitlar = [json.loads(s) for s in open(args.dosya, encoding="utf-8") if s.strip()]
    toplam, sorunlar, kotu = Counter(), Counter(), []
    for k in kayitlar:
        s, notlar = skorla_kayit(k, args.hedef)
        for a, v in s.items():
            toplam[a] += v
        for n in notlar:
            sorunlar[n.split(":")[0]] += 1
        if s["TOPLAM"] < 0.9:
            kotu.append((s["TOPLAM"], k, notlar))

    n = len(kayitlar)
    print(f"=== {Path(args.dosya).name} · {n} kayıt ===\n")
    print(f"  {'bileşen':<10}{'skor':>8}")
    print("  " + "-" * 18)
    for a in ["kimlik", "dil", "yapi", "uzunluk", "baslik"]:
        print(f"  {a:<10}{toplam[a]/n:>8.3f}")
    print("  " + "-" * 18)
    print(f"  {'TOPLAM':<10}{toplam['TOPLAM']/n:>8.3f}")

    if sorunlar:
        print("\n  en sık sorunlar:")
        for s_, c in sorunlar.most_common(6):
            print(f"    {c:>4}×  {s_}")
    print(f"\n  0.9 altı kayıt: {len(kotu)}/{n}")

    if args.ayrinti:
        for skor, k, notlar in sorted(kotu)[:6]:
            print(f"\n  --- {skor:.2f} --- {'; '.join(notlar)}")
            print(f"  {(k.get('output_tr') or '')[:260]}")


if __name__ == "__main__":
    main()
