"""
Olay müdahale alt kümesini seçer.

KAYNAK: reloading0101/threat-intelligence-dataset (CC BY 4.0)
    Bu script train.jsonl + eval.jsonl okuyor: 9.970 kayıt (ölçüldü 15.09.2026).
    Veri setinde ayrıca train_blended.jsonl ve train_multiturn.jsonl var;
    farklı şekilde oldukları için kullanılmıyorlar. Havuz büyütmek gerekirse
    ilk bakılacak yer burası.
    instruction/input/output biçiminde, metadata.task_type ile kategorili.
    Olguları MITRE ATT&CK, CISA KEV ve CWE'ye karşı doğrulanmış;
    doğrulanamayan kayıtlar yayıncı tarafından atılmış.

NEDEN BU KAYNAK — "B türü" veri
    Uzman çıktısı ZATEN veride var. Öğretmen modelin işi analiz uydurmak
    değil, var olanı Türkçeye aktarmak. İlk denemede A türü bir set
    (metin + 0/1) kullanılmış ve öğretmen analizi sıfırdan uydurmak zorunda
    kalmıştı; sonuç "E-postayı atla" gibi tuhaflıklardı.

SEÇİLEN ALT KÜME
    ir-playbook    294   olay müdahale planı (NIST SP 800-61 yapısında)
    alert-triage   110   alarm triyaj adımları — müdahalenin ilk aşaması
                   ---
                   404

KULLANIM
    python veri_sec.py
"""
import argparse
import json
import random
import re
from pathlib import Path

BURASI = Path(__file__).parent
VERI = BURASI / "veri"

REPO = "reloading0101/threat-intelligence-dataset"
GOREVLER = {"ir-playbook", "alert-triage"}

# Çıktı uzunluk sınırları (karakter). Ortanca ~1245.
# Üst sınır: Türkçe çıktı ~1,7 kat uzayacağı için kaynağı 3000'de kesiyoruz;
# aksi hâlde öğretmenin üretimi bağlam penceresini zorluyor.
MIN_CIKTI = 300
MAX_CIKTI = 3000


def yukle():
    from huggingface_hub import hf_hub_download
    kayitlar = []
    for d in ["data/train.jsonl", "data/eval.jsonl"]:
        yol = hf_hub_download(REPO, d, repo_type="dataset")
        with open(yol, encoding="utf-8") as f:
            for satir in f:
                satir = satir.strip()
                if satir:
                    kayitlar.append(json.loads(satir))
    return kayitlar


def sec(kayitlar):
    print(f"  ham kayıt          : {len(kayitlar):,}")
    alt = [k for k in kayitlar
           if k.get("metadata", {}).get("task_type") in GOREVLER]
    print(f"  görev filtresinden : {len(alt):,}  ({', '.join(sorted(GOREVLER))})")

    uygun = [k for k in alt if MIN_CIKTI <= len(str(k["output"])) <= MAX_CIKTI]
    print(f"  uzunluk filtresinden: {len(uygun):,}  "
          f"({MIN_CIKTI}-{MAX_CIKTI} karakter)")

    # Aynı tekniğin farklı ifadelerle tekrarı olabilir; çıktı üzerinden tekille
    gorulen, tekil = set(), []
    for k in uygun:
        imza = re.sub(r"\s+", " ", str(k["output"]).lower())[:400]
        if imza in gorulen:
            continue
        gorulen.add(imza)
        tekil.append(k)
    print(f"  tekilleştirmeden   : {len(tekil):,}")
    return tekil


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", type=int, default=60)
    ap.add_argument("--tohum", type=int, default=42)
    args = ap.parse_args()

    VERI.mkdir(exist_ok=True)
    print("=== SEÇİM ===")
    kayitlar = sec(yukle())

    # Görev türü dağılımını hem eğitimde hem testte koru — test seti tek
    # görev türüne kayarsa ölçüm o türü ölçer, görevin tamamını değil.
    r = random.Random(args.tohum)
    gruplar = {}
    for k in kayitlar:
        gruplar.setdefault(k["metadata"]["task_type"], []).append(k)
    for g in gruplar.values():
        r.shuffle(g)

    test, egitim = [], []
    for tur, g in gruplar.items():
        pay = round(args.test * len(g) / len(kayitlar))
        test += g[:pay]
        egitim += g[pay:]
        print(f"    {tur:<16} {len(g):>4} → test {pay}, eğitim {len(g)-pay}")
    r.shuffle(test); r.shuffle(egitim)

    def yaz(kayitlar, ad):
        yol = VERI / ad
        with open(yol, "w", encoding="utf-8") as f:
            for k in kayitlar:
                f.write(json.dumps({
                    "instruction": k["instruction"],
                    "input": k.get("input", ""),
                    "output_en": k["output"],
                    "task_type": k["metadata"]["task_type"],
                }, ensure_ascii=False) + "\n")
        print(f"  {ad:<22} {len(kayitlar):>4} kayıt")

    print("\n=== YAZILDI ===")
    yaz(egitim, "havuz_egitim.jsonl")
    yaz(test, "havuz_test.jsonl")
    yaz(r.sample(egitim, min(20, len(egitim))), "gozle_oku.jsonl")

    print("\nSıradaki adım: gozle_oku.jsonl dosyasını AÇIP OKUYUN.")


if __name__ == "__main__":
    main()
