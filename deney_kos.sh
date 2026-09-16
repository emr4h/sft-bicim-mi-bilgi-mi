#!/usr/bin/env bash
# VERİ MİKTARI DENEYİ — aynı görev, üç farklı eğitim seti boyutu.
#
# CEVAPLANAN SORU
#   "Model bozuktu çünkü 20 örnek azdı" — doğru muydu?
#   Önceki denemede 20 örnekle iki eğitim koşuldu (10 ve 30 epoch), ikisi de
#   bozuk model verdi. Kayıp eğrisine bakıp "epoch 10'da durmalıydık"
#   hipotezi kuruldu ve çürütüldü. Geriye "veri azdı" açıklaması kalmıştı —
#   bu deney onu ölçer.
#
# NEDEN ALT KÜMELER İÇ İÇE?
#   sft_20 ⊂ sft_100 ⊂ sft_344. Farklı kayıtlardan oluşsalardı skor farkının
#   miktardan mı seçimden mi geldiğini ayıramazdık.
#
# EPOCH BOYUTA GÖRE DEĞİŞİR
#   Küçük sette daha çok tur gerekiyor, yoksa optimizasyon adımı sayısı
#   anlamlı öğrenmeye yetmiyor. Bu bir karıştırıcı değişken — sonuç
#   yorumlanırken akılda tutulmalı. Sabit epoch'la tekrarlamak için
#   aşağıdaki case bloğunu tek değere sabitleyin.
#
# KULLANIM
#   ./deney_kos.sh              # 20 100 344
#   ./deney_kos.sh 20 100       # yalnızca ikisi
#   MODEL=Qwen/Qwen3-8B ./deney_kos.sh

set -uo pipefail
BURASI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="${MODEL:-Qwen/Qwen3-0.6B}"
IMAJ="${IMAJ:-unsloth-spark:playbook}"
BOYUTLAR=("$@"); [ $# -eq 0 ] && BOYUTLAR=(20 100 344)

# Konteyner kullanmıyorsanız bu fonksiyonu `D() { "$@"; }` yapın.
#
# HF önbelleği /hf'e bağlanıyor, /root'a değil: konteyner root olmayan
# kullanıcıyla koşuyor ve /root'a giremiyor (mode 700).
D() {
  docker run --rm --gpus=all --ipc=host --user "$(id -u):$(id -g)" \
    --ulimit memlock=-1 --ulimit stack=67108864 \
    -v "$BURASI":/p -v "$HOME/.cache/huggingface":/hf \
    -e HF_HOME=/hf -e HOME=/tmp -w /p \
    "$IMAJ" "$@"
}

echo "== 0. Veri setleri hazırlanıyor =="
D python -u sft_hazirla.py --boyutlar "${BOYUTLAR[@]}" 2>&1 | grep -E "havuz:|sft_|!"

echo
echo "== 1. Eğitimsiz temel ölçüm =="
# Karşılaştırma çapası. Bu olmadan skorlar anlamsız.
if [ ! -f "$BURASI/cikti/test_temel.jsonl" ]; then
  D python -u test_kos.py --model "$MODEL" --cikti cikti/test_temel.jsonl 2>&1 | tail -2
else
  echo "   (cikti/test_temel.jsonl zaten var, atlanıyor)"
fi

for n in "${BOYUTLAR[@]}"; do
    echo
    echo "== $n örnekle eğitim =="
    case "$n" in
        20)   EP=30 ;;
        100)  EP=8  ;;
        *)    EP=3  ;;
    esac
    D python -u egit_lora.py --model "$MODEL" \
        --veri "veri/sft_${n}.jsonl" --cikti "ckpt/sft_${n}" --epoch "$EP" 2>&1 \
        | grep -E "veri:|trainable params|'eval_loss'|'train_loss'|Bitti" | tail -6

    echo "-- test --"
    D python -u test_kos.py --model "$MODEL" --adapter "ckpt/sft_${n}" \
        --cikti "cikti/test_${n}.jsonl" 2>&1 | tail -2
done

echo
echo "############ SONUÇLAR ############"
for f in cikti/test_temel.jsonl $(for n in "${BOYUTLAR[@]}"; do echo "cikti/test_${n}.jsonl"; done); do
    [ -f "$BURASI/$f" ] || continue
    echo
    D python -u skorla.py "$f" --hedef en 2>&1 \
      | grep -E "^=== |^  (kimlik|dil|yapi|uzunluk|baslik|TOPLAM)|0.9 altı"
done
