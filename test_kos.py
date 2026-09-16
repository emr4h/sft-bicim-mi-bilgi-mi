"""
Eğitilmiş modeli test setinde koşturur ve çıktıları kaydeder.

NOT: Referans cevap gerekmiyor — skorlama tamamen programatik.
`skorla.py` çıktıyı kaynak dokümanla karşılaştırıyor; hakem modeli de
referans üretimini de gereksiz kılıyor.

KULLANIM
    python test_kos.py --cikti cikti/test_temel.jsonl              # eğitimsiz
    python test_kos.py --adapter ckpt/sft_344 --cikti cikti/test_344.jsonl
"""
import argparse
import json
import time
from pathlib import Path

from sft_hazirla import SISTEM

BURASI = Path(__file__).parent
VERI = BURASI / "veri"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3-0.6B")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--test", default=str(VERI / "havuz_test.jsonl"))
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--adet", type=int, default=60)
    ap.add_argument("--batch", type=int, default=16)
    # Havuzdaki çıktılar 300-3000 karakter; 3000 karakter İngilizcede
    # kabaca 700 token eder. 900 pay bırakıyor.
    ap.add_argument("--max-yeni", type=int, default=900)
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(args.model, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map="auto")
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()
    print(f"model: {args.model}"
          + (f" + {args.adapter}" if args.adapter else " (eğitimsiz)"), flush=True)

    kayitlar = [json.loads(s) for s in
                open(args.test, encoding="utf-8") if s.strip()][:args.adet]

    def istem(k):
        kullanici = k["instruction"]
        if k.get("input"):
            kullanici += "\n\n" + k["input"]
        m = [{"role": "system", "content": SISTEM},
             {"role": "user", "content": kullanici}]
        try:
            return tok.apply_chat_template(m, tokenize=False,
                                           add_generation_prompt=True,
                                           enable_thinking=False)
        except TypeError:
            return tok.apply_chat_template(m, tokenize=False,
                                           add_generation_prompt=True)

    sonuclar, t0 = [], time.time()
    for i in range(0, len(kayitlar), args.batch):
        grup = kayitlar[i:i + args.batch]
        g = tok([istem(k) for k in grup], return_tensors="pt", padding=True,
                truncation=True, max_length=1400).to(model.device)
        with torch.no_grad():
            c = model.generate(**g, max_new_tokens=args.max_yeni,
                               temperature=0.3, do_sample=True, top_p=0.9,
                               pad_token_id=tok.pad_token_id)
        for j, k in enumerate(grup):
            metin = tok.decode(c[j][g["input_ids"].shape[1]:],
                               skip_special_tokens=True).strip()
            # skorla.py 'output_tr' alanını okuyor; adı dilden bağımsız
            # olmalıydı ama geriye dönük uyum için koruyoruz.
            sonuclar.append({**k, "output_tr": metin})
        print(f"  {len(sonuclar)}/{len(kayitlar)}  "
              f"{time.time()-t0:.0f} sn", flush=True)

    Path(args.cikti).parent.mkdir(parents=True, exist_ok=True)
    with open(args.cikti, "w", encoding="utf-8") as f:
        for s in sonuclar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"-> {args.cikti}  ({time.time()-t0:.0f} sn)")


if __name__ == "__main__":
    main()
