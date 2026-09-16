"""
Havuzu SFT eğitim formatına çevirir ve farklı boyutlarda alt kümelere böler.

GİRDİ  : veri/havuz_egitim.jsonl   (instruction / input / output_en / task_type)
ÇIKTI  : veri/sft_<n>.jsonl        (messages formatı)

NEDEN AYRI ADIM?
    Aynı havuzdan farklı boyutlarda alt küme üretmek, her deney için veriyi
    yeniden hazırlamaktan hızlı. Alt kümeler İÇ İÇE geçer: sft_20 ⊂ sft_100 ⊂
    sft_344. Bu şart — küçük ve büyük set farklı kayıtlardan oluşsaydı, skor
    farkının veri MİKTARINDAN mı yoksa hangi kayıtların seçildiğinden mi
    geldiğini ayıramazdık.

GÖREV TÜRÜ DAĞILIMI KORUNUR
    Havuz %74 ir-playbook, %26 alert-triage. 20 kayıtlık bir alt küme düz
    rastgele seçilirse kolayca tek türe kayar ve o boyutta modeli tek görev
    türüyle eğitmiş oluruz.

KULLANIM
    python sft_hazirla.py                      # 20 100 344
    python sft_hazirla.py --boyutlar 20 50 100
"""
import argparse
import json
import random
from pathlib import Path

BURASI = Path(__file__).parent
VERI = BURASI / "veri"

# Eğitimde kullanılacak sistem promptu. Kısa tutuluyor: öğrenci modelin her
# seferinde uzun kuralları okumasına gerek yok, davranışı ağırlıklara işleyecek.
SISTEM = ("You are a security analyst. Given an incident or alert, you write a "
          "structured incident response plan following NIST SP 800-61.")


def kayit_cevir(k):
    kullanici = k["instruction"]
    if k.get("input"):
        kullanici += "\n\n" + k["input"]
    return {"messages": [
        {"role": "system", "content": SISTEM},
        {"role": "user", "content": kullanici},
        {"role": "assistant", "content": k["output_en"]},
    ]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--girdi", default=str(VERI / "havuz_egitim.jsonl"))
    ap.add_argument("--boyutlar", type=int, nargs="+", default=[20, 100, 344])
    ap.add_argument("--tohum", type=int, default=42)
    args = ap.parse_args()

    if not Path(args.girdi).exists():
        print(f"  ! Havuz bulunamadı: {args.girdi}")
        print("    Önce kaynak veriyi indirin:  python veri_sec.py")
        raise SystemExit(1)

    kayitlar = [json.loads(s) for s in
                open(args.girdi, encoding="utf-8") if s.strip()]
    print(f"havuz: {len(kayitlar)} kayıt")

    # Görev türüne göre grupla, her grubu bir kez karıştır. Alt kümeler bu
    # sıralamanın BAŞINDAN alınır -> iç içe geçmeleri garanti.
    r = random.Random(args.tohum)
    gruplar = {}
    for k in kayitlar:
        gruplar.setdefault(k["task_type"], []).append(k)
    for g in gruplar.values():
        r.shuffle(g)
    for tur, g in sorted(gruplar.items()):
        print(f"  {tur:<16} {len(g):>4}")

    for n in args.boyutlar:
        if n > len(kayitlar):
            print(f"  ! {n} havuzdan büyük, atlanıyor")
            continue
        alt = []
        for tur, g in sorted(gruplar.items()):
            pay = round(n * len(g) / len(kayitlar))
            alt += g[:pay]
        # Yuvarlama artığını en büyük gruptan tamamla/kırp
        buyuk = max(gruplar, key=lambda t: len(gruplar[t]))
        while len(alt) < n:
            aday = gruplar[buyuk][len(alt)]
            if aday not in alt:
                alt.append(aday)
            else:
                break
        alt = alt[:n]
        r.shuffle(alt)

        yol = VERI / f"sft_{n}.jsonl"
        with open(yol, "w", encoding="utf-8") as f:
            for k in alt:
                f.write(json.dumps(kayit_cevir(k), ensure_ascii=False) + "\n")
        dagilim = {}
        for k in alt:
            dagilim[k["task_type"]] = dagilim.get(k["task_type"], 0) + 1
        print(f"  {yol.name:<16} {len(alt):>4} kayıt  {dagilim}")


if __name__ == "__main__":
    main()
