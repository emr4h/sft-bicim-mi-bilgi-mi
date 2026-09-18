# SFT: biçim mi öğretiyor, bilgi mi?

Bir dil modelini kendi görevime göre eğitmeye çalıştım ve bir hipotezim vardı:
*"İlk denemem başarısızdı çünkü 20 örnek azdı."* Veriyi 17 katına çıkardım.

Hipotez çürüdü. Kazanç yok denecek kadar azdı.

Ama asıl öğretici olan neden çürüdüğüydü. O cevap, ince ayarı ne zaman
kullanmam gerektiği konusunda fikrimi değiştirdi. Bu repoda deneyin kodu,
ölçümleri ve yolda karşılaştığım hatalar var.

Her şey NVIDIA DGX Spark üzerinde (GB10, 128 GB birleşik bellek) Eylül
2026'da koşturuldu. Modeller Qwen3-0.6B ve Qwen3-8B.

## Önce terimler: SFT ne, LoRA ne?

### SFT nedir

SFT'nin açılımı supervised fine-tuning, Türkçesi denetimli ince ayar.
Modele "şu soru gelince şöyle cevap ver" çiftleri gösterip davranışını
şekillendirmek.

Modeli sıfırdan eğitmiyorsunuz. Zaten eğitilmiş bir modelin önüne kendi
örneklerinizi koyup yeni bir alışkanlık kazandırıyorsunuz. Sıfırdan eğitim
milyonlarca dolar ve aylar ister; SFT bu repodaki koşularda beş dakika
sürdü.

### Nasıl çalışıyor

Veri tek bir biçimde: bir konuşma. Sistem talimatı, kullanıcının sorusu,
olması gereken cevap. Bu depoda `sft_hazirla.py` her kaydı şuna çeviriyor:

```json
{"messages": [
  {"role": "system",    "content": "You are a security analyst..."},
  {"role": "user",      "content": "Bir olay müdahale sorusu"},
  {"role": "assistant", "content": "Olması gereken cevap"}
]}
```

Eğitim sırasında model cevabı kelime kelime tahmin etmeye çalışıyor.
Tutturamadığı her kelimede ağırlıkları biraz düzeltiliyor. Binlerce adım
sonra o cevap tarzı modele yerleşiyor.

Önemli bir ayrıntı: kayıp yalnızca `assistant` kısmında hesaplanmalı. Model
sizin sorunuzu üretmeyi öğrenmemeli, cevabı üretmeyi öğrenmeli. TRL bunu
`assistant_only_loss` ile yapıyor ve Qwen'in sohbet şablonunda gereken
etiket olmadığı için `egit_lora.py` veriyi otomatik olarak prompt/completion
biçimine çeviriyor.

### LoRA nedir

SFT "hangi hedefle eğitiyoruz" sorusuna cevap veriyor. LoRA ise "hangi
parametreleri eğitiyoruz" sorusuna.

Modelin milyarlarca ağırlığını güncellemek yerine, yanına küçük matrisler
ekleyip yalnızca onları eğitiyorsunuz. Taban model donuyor. Bu deneyde
eğitilen parametre oranı yüzde 1,7. Bellek birkaç kat düşüyor, sonuç
neredeyse aynı kalıyor.

Kullandığım ayarlar ve gerekçeleri:

| Ayar | Değer | Neden |
|---|---|---|
| `r` | 16 | Rütbe. 8-16 üslup ve biçim için yeter, 32-64 yeni alan bilgisi için |
| `lora_alpha` | 32 | Ölçek katsayısı. Yaygın kural alpha = 2r |
| `lora_dropout` | 0.05 | Küçük veride ezberi frenliyor |
| Katmanlar | 7 doğrusal katmanın hepsi | Yalnızca dikkat katmanları daha hızlı ama daha az öğreniyor |
| `learning_rate` | 2e-4 | LoRA için yaygın başlangıç. Kayıp fırlarsa yarıya indirin |
| Etkin batch | 16 | 4 x 4 accumulation |

Açık kaynak ince ayarların çoğu "LoRA ile SFT"dir. Varsayılan yol bu.

### Ne için kullanılır, ne için kullanılmaz

Bu deneyin sonucunu baştan söyleyeyim, çünkü bu bölümün asıl cevabı o:

SFT modele **nasıl cevap vereceğini** öğretiyor. Biçim, üslup, uzunluk,
hangi başlıkların hangi sırayla geleceği. Bunları çok az örnekle kapıyor.

SFT modele **ne bileceğini** öğretmiyor. Bir ATT&CK kimliğinin hangi tekniğe
karşılık geldiği, dün yayınlanan bir CVE'nin ne olduğu, sizin müşteri
listeniz. Bunlar için doğru araç RAG.

Bu ayrımı deneyden önce bu kadar net bilmiyordum. Aşağıdaki sayılar nasıl
çıktığını gösteriyor.

## Neden bu deneyi yaptım?

Daha önce 20 örnekle iki eğitim koşmuştum, 10 ve 30 epoch. İkisi de bozuk
model verdi. 30 epoch ezberledi, 10 epoch hiçbir şey öğrenemedi.

Bir epoch, eğitim setinin baştan sona bir kez gezilmesi demek. Az veriniz
varsa aynı örnekleri defalarca göstermeniz gerekiyor, ama fazla gösterirseniz
model onları ezberliyor.

### Ezber nasıl görünüyor?

Ezberlemenin (overfitting) tek erken uyarı sinyali `eval_loss`. Veri ikiye
bölünüyor; model yüzde 90'ıyla eğitiliyor, yüzde 10'unu hiç görmüyor:

```python
veri = veri.train_test_split(test_size=0.1, seed=TOHUM)
```

`train_loss` gördüğü veride ne kadar yanıldığını, `eval_loss` görmediği
veride ne kadar yanıldığını ölçüyor. Model genellenebilir bir şey
öğreniyorsa ikisi birlikte düşüyor. Ezberliyorsa yolları ayrılıyor.

20 örnek, 30 epoch, Qwen3-0.6B. Bu depodaki koşudan:

```
epoch   train_loss   eval_loss
   5      2.296        2.349
  10      1.220        1.847
  15      0.810        1.592    <- eval_loss dibi
  20      0.530        1.663    <- yükselmeye başladı
  25      0.343        1.754
  30      0.270        1.772
```

Epoch 15'e kadar ikisi de düşüyor. Sonra `train_loss` inmeye devam ederken
`eval_loss` yükseliyor. Model epoch 15'te durmalıydı. Bitişte gördüğü veride
0,270, görmediğinde 1,772. Altı buçuk kat fark.

Doğrulama seti ayırmak zorunlu değil, ama ayırmazsanız bunu göremezsiniz.
Elinizde yalnızca güzelce düşen bir `train_loss` kalır ve her şey yolunda
sanırsınız.

Tekrarlamak için:

```bash
python egit_lora.py --veri veri/sft_20.jsonl --cikti ckpt/ezber --epoch 30
```

### Hipotez sırası

Bu eğriyi görünce *"epoch 10'da durmalıydık"* diye düşündüm. Mantıklıydı.
Test ettim, tutmadı. Asıl kısıt epoch değildi. Geriye tek açıklama kalmış
gibi görünüyordu: veri azdı.

Bu sefer onu ölçtüm.

## Görev ve veri

Model bir olay müdahale sorusu alıyor, NIST SP 800-61 yapısında bir müdahale
planı yazıyor. Yani hazırlık, tespit, sınırlama, temizleme, kurtarma,
çıkarılan dersler.

Kaynak: [`reloading0101/threat-intelligence-dataset`](https://huggingface.co/datasets/reloading0101/threat-intelligence-dataset)
(CC BY 4.0). İçinden iki görev türünü aldım:

| Görev türü | Kayıt | Ne |
|---|---|---|
| `ir-playbook` | 294 | Olay müdahale planı |
| `alert-triage` | 110 | Alarm triyaj adımları, müdahalenin ilk aşaması |
| | **404** | 344 eğitim + 60 test |

Her kayıtta bir talimat, isteğe bağlı bir girdi ve uzman cevabı var. Cevabın
içinde ATT&CK teknik kimlikleri (T1216.001 gibi), azaltma kodları (M1038
gibi) ve log kaynakları geçiyor. Skorlamanın en kritik bileşeni bu
kimliklerin çıktıda korunup korunmadığı.

Bu seti seçmemin sebebi, içinde **soru ve uzman cevabının birlikte** olması.
Sadece etiketli bir set alsaydım (metin artı 0/1 etiketi), istediğim çıktıyı
üretmek için modele analizi sıfırdan uydurtmam gerekirdi. Burada uydurmuyor,
var olanı yeniden düzenliyor.

## Deney kurgusu

Aynı görev, üç farklı eğitim seti boyutu: 20, 100, 344.

Alt kümeler **iç içe**: `sft_20 ⊂ sft_100 ⊂ sft_344`. Bu şart. Farklı
kayıtlardan oluşsalardı skor farkının miktardan mı yoksa hangi kayıtların
seçildiğinden mi geldiğini ayıramazdım.

Görev türü dağılımı da her boyutta korunuyor. Havuz yüzde 73 playbook, yüzde
27 triyaj. 20'lik alt küme düz rastgele seçilseydi kolayca tek türe kayardı.

Karşılaştırma çapası olarak eğitimsiz modelin skorunu da aldım. O olmadan
"0,779 iyi mi kötü mü" sorusunun cevabı yok.

## Sonuç: hipotez çürüdü

60 kayıtlık test setinde, Qwen3-0.6B:

```
             temel     20     100     344
kimlik       0.443   0.413   0.439   0.496
dil          1.000   1.000   1.000   1.000
yapi         0.133   0.625   0.713   0.683
uzunluk      0.067   0.967   0.950   0.867
baslik       0.221   0.892   0.921   0.946
TOPLAM       0.373   0.779   0.805   0.798
```

Eğitim işini yapıyor: 0,373'ten 0,779'a. Büyük sıçrama.

Ama **sıçramanın tamamı ilk 20 örnekte.** 20'den 344'e giderken, yani 17 kat
veriyle, kazanç 0,019. Gürültü seviyesinde. 344 hatta 100'ün altında kaldı.

Yani "veri azdı" açıklaması yanlıştı.

## Asıl bulgu: biçim öğreniliyor, bilgi öğrenilmiyor

Toplam skora bakınca eğri düz. Bileşenlere bakınca iki ayrı şey görünüyor.

**`uzunluk` 0,067'den 0,967'ye tek adımda fırlıyor.** Model "ne kadar uzun
yazacağım" sorusunu 20 örnekte cevaplıyor. `baslik` ve `yapi` de benzer.
Hangi başlıkları koyacağını, adımları nasıl numaralandıracağını hemen
kapıyor.

**`kimlik` ise hiç öğrenilmiyor.** 0,443'ten 0,496'ya. Veri 17 kat arttı,
ATT&CK kimliklerini, azaltma kodlarını ve log kaynaklarını doğru taşıma
neredeyse hiç iyileşmedi. Hatta eğitimsiz model, 20 örnekle eğitilmiş
olandan daha iyi (0,443'e karşı 0,413).

İkisi arasındaki fark şu: **biçim bir davranış, kimlik bir bilgi.**

Model rapor formatını öğrenebiliyor çünkü format her örnekte tekrar ediyor
ve içerikten bağımsız bir kalıp. Ama "bu teknik için doğru ATT&CK kimliği
hangisi" sorusu bilgi gerektiriyor ve o bilgi her örnekte farklı. 344 örnek
göstererek modele MITRE ATT&CK'i ezberletemezsiniz.

Bu, ince ayarın ne zaman doğru araç olduğunu değiştiriyor:

| Problem | Doğru araç |
|---|---|
| Çıktının biçimi, üslubu, yapısı | **SFT** |
| Hangi bilginin doğru olduğu | **RAG**, bilgiyi getirin, gömmeyin |

Güvenlikte bu ayrım daha da keskin, çünkü alanın bilgisi hızla eskiyor. Dün
yayınlanan bir CVE'yi eğitimle öğretmek hem pahalı hem bir hafta sonra
geçersiz.

Sektörde kurgu da zaten böyle: SFT ile biçim oturtuluyor, bilgi çalışma
anında bağlama konuyor.

## Yolda karşılaştığım üç sorun

### 1. Ölçüm bana ters sonuç gösterdi ve neredeyse inanıyordum

Bu depodaki yan deneylerden birinde tablo, hipotezimin tam tersini
gösteriyordu. Sonuca varmadan önce çıktıları açıp okudum: model, prompt'a
koyduğum terim sözlüğünü alıp cevabının başına yapıştırmıştı. Metrik çeviri
kalitesini değil, benim prompt hatamı ölçüyormuş.

Temizleyince fark kayboldu. Tabloya güvenip yazsaydım yanlış bir sonuç
yayınlayacaktım.

### 2. Makul bir açıklama buldum, yanlıştı

Başka bir koşuda bir skor beklenmedik biçimde düşüktü. Kendimden emin bir
açıklamam vardı: *"Türkçe iki kat token tutuyor, bütçe yetmemiştir."*
Kulağa doğru geliyordu, üstelik kendi ölçümümle de tutarlıydı.

Bütçeyi ikiye katladım. Durum **kötüleşti**. Sebep tamamen başkaymış. Model
tekrar döngüsüne giriyordu, fazla bütçe ona daha çok tekrarlama alanı verdi.

Makul bir açıklama bulmakla doğru açıklamayı bulmak aynı şey değil, ve makul
olan daha tehlikeli: aramayı durduruyor.

### 3. Model prompt'umu içerik sanıyor

Aynı arıza üç ayrı biçimde tekrarladı. Model prompt bloklarını
işlenecek içerik sanıp çıktısına kopyalıyordu:

| Nerede | Ne kopyalandı | Oran |
|---|---|---|
| Sözlüklü üretim | terim listesi | 2-3 / 30 |
| Soru üretimi (ilk sürüm) | talimat satırları | **29 / 70** |
| Soru üretimi (düzeltilmiş) | `<soru>` etiketi | kozmetik |

Çözüm hep aynı çıktı: **içeriği başa, talimatı sona koymak.** Talimat
baştayken 70 kaydın 29'u bozuktu; sırayı çevirince 1'e indi.

## Bu deneyin zayıf noktaları

Epoch sayısı boyuta göre değişti: 20 örnek için 30 epoch, 100 için 8, 344
için 3. Küçük sette daha çok tur gerekiyor, yoksa optimizasyon adımı sayısı
anlamlı öğrenmeye yetmiyor.

Bu bir karıştırıcı değişken. "20 yeter" sonucu saf değil, 20'lik koşu 30 tur
gördü. Ama bu, hipotezin *aleyhine* çalışıyor: 344 örnek yalnızca 3 turda
20'yi yakaladı. Kesinleştirmek isteyen sabit epoch'la tekrarlayabilir.

Bir de veri şablonlu. Eğitim havuzuna düşen 250 `ir-playbook` kaydının 159'u aynı cümleyle
başlıyor; değişen kısım kimlikler ve bir iki cümle. Bu kadar tekrarlı bir
biçimin 20 örnekte öğrenilmesi şaşırtıcı değil. Daha çeşitli bir görevde
eğri farklı olabilir.

Üçüncüsü, tek bir görev ve tek bir veri seti. "SFT biçim öğretir" sonucu
burada net çıktı ama genel bir yasa olarak sunmuyorum.

## Repoda ne var

Yedi dosya, bir deney. Akış şöyle:

```
veri_sec.py       kaynak seti indir, iki görev türünü ayıkla,
                  katmanlı böl            -> havuz_egitim / havuz_test
      |
sft_hazirla.py    havuzu messages biçimine çevir,
                  iç içe alt kümelere böl -> sft_20 / sft_100 / sft_344
      |
egit_lora.py      LoRA adaptörü eğit      -> ckpt/
      |
test_kos.py       60 test kaydında koştur -> cikti/*.jsonl
      |
skorla.py         beş bileşeni hesapla    -> tablo
```

`deney_kos.sh` bu zinciri her boyut için sırayla çalıştırıyor, eğitimsiz
temel ölçümü de alıyor.

| Dosya | Ne işe yarar |
|---|---|
| `veri_sec.py` | Kaynak veri setini indirir, `ir-playbook` ve `alert-triage` kayıtlarını ayıklar, görev türü dağılımını koruyarak eğitim/test böler |
| `sft_hazirla.py` | Havuzu `messages` biçimine çevirir, 20 ⊂ 100 ⊂ 344 iç içe alt kümeleri yazar |
| `egit_lora.py` | LoRA + SFT eğitimi. Doğrulama seti ayırır, `eval_loss` raporlar |
| `test_kos.py` | Eğitilmiş adaptörü test setinde koşturur, çıktıyı jsonl yazar |
| `skorla.py` | Beş bileşeni kodla hesaplar, LLM hakem yok |
| `terimler.py` | Kimlik desenleri (T-kodu, M-kodu, CVE), bölüm başlığı sözlüğü |
| `deney_kos.sh` | Hepsini sırayla koşturur |

### Skorlama nasıl çalışıyor

Beş bileşen, hepsi programatik, hepsi 0 ile 1 arasında. Toplam bunların
ortalaması.

| Bileşen | Ne ölçüyor |
|---|---|
| `kimlik` | Kaynakta geçen ATT&CK/azaltma/CVE kimliklerinin kaçı çıktıda duruyor |
| `dil` | Çıktı hedef dilde mi |
| `yapi` | Başlık ve adım sayısı kaynağa yakın mı |
| `uzunluk` | Uzunluk oranı 0,7 ile 1,8 arasında mı |
| `baslik` | Kaynaktaki bölüm başlıkları çıktıda var mı |

### Neden LLM hakem yok?

Bu görevde en kritik özellik tartışmasız ölçülebiliyor. Model bir ATT&CK
kimliğini düşürürse ya da değiştirirse çıktı yanlıştır. Bir analist o kimliği
arayacak. Burada yorum payı yok.

Ölçüm kesin olabiliyorken hakem çağırmak hem pahalı hem tekrarlanabilirliği
düşürür: aynı çıktıya iki koşuda farklı puan gelir.

## Nasıl tekrarlanır

Bir GPU ve `transformers`, `trl`, `peft`, `datasets` gerekiyor.

```bash
python veri_sec.py            # kaynak veriyi indirip havuzu kurar
./deney_kos.sh                # 20, 100, 344: eğitim + test + skorlama
./deney_kos.sh 20 100         # yalnızca ikisi
```

Küçük modelde bir boyut yaklaşık beş dakika sürüyor.

## Kaynaklar

- Kaynak veri seti: [reloading0101/threat-intelligence-dataset](https://huggingface.co/datasets/reloading0101/threat-intelligence-dataset) (CC BY 4.0)
- NIST SP 800-61, olay müdahale çerçevesi
- MITRE ATT&CK, teknik ve azaltma kimlikleri
- Türkçe veri stratejisi ölçümlerim: [emr4h/turkce-llm-veri-stratejisi](https://github.com/emr4h/turkce-llm-veri-stratejisi)

## Lisans

Kod MIT. Kaynak veri seti CC BY 4.0; türev veri bu repoda yayınlanmıyor,
scriptler kaynağı kendileri indiriyor.
