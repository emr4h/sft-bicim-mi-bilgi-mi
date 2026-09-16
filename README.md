# SFT: biçim mi öğretiyor, bilgi mi?

Bir dil modelini kendi görevime göre eğitmeye çalıştım ve bir hipotezim vardı:
*"İlk denemem başarısızdı çünkü 20 örnek azdı."* Veriyi 17 katına çıkardım.

Hipotez çürüdü. Kazanç yok denecek kadar azdı.

Ama asıl öğretici olan neden çürüdüğüydü — ve o cevap, ince ayarı ne zaman
kullanmam gerektiği konusunda fikrimi değiştirdi. Bu repoda deneyin kodu,
ölçümleri ve yolda karşılaştığım hatalar var.

Her şey NVIDIA DGX Spark üzerinde (GB10, 128 GB birleşik bellek) Eylül
2026'da koşturuldu. Modeller Qwen3-0.6B ve Qwen3-8B.

## Önce: SFT nedir, LoRA nedir?

**SFT** (supervised fine-tuning, denetimli ince ayar), modele "şu soru
gelince şöyle cevap ver" çiftleri göstererek davranışını şekillendirmek.
Modeli sıfırdan eğitmiyorsunuz; zaten eğitilmiş bir modele yeni bir alışkanlık
kazandırıyorsunuz.

**LoRA** bunu ucuza yapmanın yolu. Modelin milyarlarca ağırlığını
güncellemek yerine, yanına küçük matrisler ekleyip yalnızca onları
eğitiyorsunuz. Bu deneyde eğitilen parametre oranı **yüzde 1,7** — gerisi
donduruldu. Bellek birkaç kat düşüyor, sonuç neredeyse aynı kalıyor.

İkisi farklı sorulara cevap veriyor: SFT "hangi hedefle eğitiyoruz", LoRA
"hangi parametreleri eğitiyoruz". Açık kaynak ince ayarların çoğu "LoRA ile
SFT"dir; varsayılan yol bu.

## Neden bu deneyi yaptım?

Daha önce 20 örnekle iki eğitim koşmuştum, 10 ve 30 epoch. İkisi de bozuk
model verdi. 30 epoch ezberledi, 10 epoch hiçbir şey öğrenemedi.

Kayıp eğrisine bakıp *"epoch 10'da durmalıydık"* diye düşündüm. Sonra o
hipotezi test ettim ve tutmadı — asıl kısıt epoch değildi. Geriye tek
açıklama kalmış gibi görünüyordu: **veri azdı.**

Bu sefer onu ölçtüm.

## Görev ve veri

Model bir olay müdahale sorusu alıyor, NIST SP 800-61 yapısında bir müdahale
planı yazıyor.

Kaynak: [`reloading0101/threat-intelligence-dataset`](https://huggingface.co/datasets/reloading0101/threat-intelligence-dataset)
(CC BY 4.0). İçinden `ir-playbook` ve `alert-triage` görev türlerini aldım:
404 kayıt, 344 eğitim + 60 test.

Bu seti seçmemin sebebi, içinde **soru ve uzman cevabının birlikte** olması.
Sadece etiketli bir set (metin + 0/1) alsaydım, istediğim çıktıyı üretmek
için modele analizi sıfırdan uydurtmam gerekirdi.

## Deney

Aynı görev, üç farklı eğitim seti boyutu. Alt kümeler **iç içe**:
`sft_20 ⊂ sft_100 ⊂ sft_344`. Bu şart — farklı kayıtlardan oluşsalardı skor
farkının miktardan mı yoksa hangi kayıtların seçildiğinden mi geldiğini
ayıramazdım.

Görev türü dağılımı da her boyutta korunuyor. Havuz %73 playbook, %27 triyaj;
20'lik alt küme düz rastgele seçilseydi kolayca tek türe kayardı.

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

Ama **sıçramanın tamamı ilk 20 örnekte.** 20'den 344'e — 17 kat veri —
kazanç 0,019. Gürültü seviyesinde. 344 hatta 100'ün altında kaldı.

Yani "veri azdı" açıklaması yanlıştı.

## Asıl bulgu: biçim öğreniliyor, bilgi öğrenilmiyor

Toplam skora bakınca eğri düz. Bileşenlere bakınca iki ayrı şey görünüyor:

**`uzunluk` 0,067'den 0,967'ye tek adımda fırlıyor.** Model "ne kadar uzun
yazacağım" sorusunu 20 örnekte cevaplıyor. `baslik` ve `yapi` de benzer —
hangi başlıkları koyacağını, adımları nasıl numaralandıracağını hemen
kapıyor.

**`kimlik` ise hiç öğrenilmiyor.** 0,443'ten 0,496'ya. Veri 17 kat arttı,
ATT&CK kimliklerini (T1216.001), azaltma kodlarını (M1038) ve log
kaynaklarını doğru taşıma neredeyse hiç iyileşmedi. Hatta eğitimsiz model,
20 örnekle eğitilmiş olandan *daha iyi* (0,443'e karşı 0,413).

İkisi arasındaki fark şu: **biçim bir davranış, kimlik bir bilgi.**

Model rapor formatını öğrenebiliyor çünkü format her örnekte tekrar ediyor
ve dilden bağımsız bir kalıp. Ama "bu teknik için doğru ATT&CK kimliği
hangisi" sorusu bilgi gerektiriyor ve o bilgi her örnekte farklı. 344 örnek
göstererek modele MITRE ATT&CK'i ezberletemezsiniz.

Bu, ince ayarın ne zaman doğru araç olduğunu değiştiriyor:

| Problem | Doğru araç |
|---|---|
| Çıktının biçimi, üslubu, yapısı | **SFT** |
| Hangi bilginin doğru olduğu | **RAG** — bilgiyi getirin, gömmeyin |

Güvenlikte bu ayrım daha da keskin, çünkü alanın bilgisi hızla eskiyor. Dün
yayınlanan bir CVE'yi eğitimle öğretmek hem pahalı hem bir hafta sonra
geçersiz.

## Yolda karşılaştığım üç sorun

### 1. Ölçüm bana ters sonuç gösterdi ve neredeyse inanıyordum

Bu depodaki yan deneylerden birinde tablo, hipotezimin tam tersini
gösteriyordu. Sonuca varmadan önce çıktıları açıp okudum: model, prompt'a
koyduğum terim sözlüğünü alıp cevabının başına yapıştırmıştı. Metrik
çeviri kalitesini değil, benim prompt hatamı ölçüyormuş.

Temizleyince fark kayboldu. Tabloya güvenip yazsaydım yanlış bir sonuç
yayınlayacaktım.

### 2. Makul bir açıklama buldum, yanlıştı

Başka bir koşuda bir skor beklenmedik biçimde düşüktü. Kendimden emin bir
açıklamam vardı: *"Türkçe iki kat token tutuyor, bütçe yetmemiştir."*
Kulağa doğru geliyordu, üstelik kendi ölçümümle de tutarlıydı.

Bütçeyi ikiye katladım. Durum **kötüleşti**. Sebep tamamen başkaymış —
model tekrar döngüsüne giriyordu, fazla bütçe ona daha çok tekrarlama alanı
verdi.

Makul bir açıklama bulmakla doğru açıklamayı bulmak aynı şey değil, ve
makul olan daha tehlikeli: aramayı durduruyor.

### 3. Model prompt'umu içerik sanıyor

Aynı arıza üç ayrı biçimde tekrarladı. Model prompt bloklarını çevrilecek/
işlenecek içerik sanıp çıktısına kopyalıyordu:

| Nerede | Ne kopyalandı | Oran |
|---|---|---|
| Sözlüklü üretim | terim listesi | 2-3 / 30 |
| Soru üretimi (ilk sürüm) | talimat satırları | **29 / 70** |
| Soru üretimi (düzeltilmiş) | `<soru>` etiketi | kozmetik |

Çözüm hep aynı çıktı: **içeriği başa, talimatı sona koymak.** Talimat
baştayken 70 kaydın 29'u bozuktu; sırayı çevirince 1'e indi.

## Bu deneyin zayıf noktası

Epoch sayısı boyuta göre değişti: 20 örnek için 30 epoch, 100 için 8, 344
için 3. Küçük sette daha çok tur gerekiyor, yoksa optimizasyon adımı sayısı
anlamlı öğrenmeye yetmiyor.

Bu bir karıştırıcı değişken — "20 yeter" sonucu saf değil, 20'lik koşu 30 tur
gördü. Ama bu, hipotezin *aleyhine* çalışıyor: 344 örnek yalnızca 3 turda
20'yi yakaladı. Kesinleştirmek isteyen sabit epoch'la tekrarlayabilir.

Bir de veri şablonlu. 250 `ir-playbook` kaydının 159'u aynı cümleyle
başlıyor; değişen kısım kimlikler ve bir iki cümle. Bu kadar tekrarlı bir
biçimin 20 örnekte öğrenilmesi şaşırtıcı değil. Daha çeşitli bir görevde
eğri farklı olabilir.

## Nasıl tekrarlanır

Bir GPU ve `transformers`, `trl`, `peft`, `datasets` gerekiyor.

```bash
python veri_sec.py            # kaynak veriyi indirip havuzu kurar
./deney_kos.sh                # 20, 100, 344 — eğitim + test + skorlama
./deney_kos.sh 20 100         # yalnızca ikisi
```

`deney_kos.sh` her boyut için sırayla: alt kümeyi hazırlar, eğitir, test
setinde koşturur, skorlar. Eğitimsiz temel ölçümü de alır — karşılaştırma
çapası olmadan skorlar anlamsız.

## Dosyalar

| Dosya | Ne işe yarar |
|---|---|
| `veri_sec.py` | Kaynak veri setinden alt kümeyi seçer, katmanlı böler |
| `sft_hazirla.py` | Havuzu `messages` formatına çevirir, iç içe alt kümelere böler |
| `egit_lora.py` | LoRA + SFT eğitimi |
| `test_kos.py` | Eğitilmiş modeli test setinde koşturur |
| `skorla.py` | Çıktıyı kodla skorlar — LLM hakem yok |
| `terimler.py` | Teknik kimlik desenleri, terim sözlüğü |
| `deney_kos.sh` | Hepsini sırayla koşturur |

## Neden LLM hakem yok?

Skorlama tamamen kodla yapılıyor. Sebebi basit: bu görevde en kritik özellik
tartışmasız ölçülebiliyor. Model bir ATT&CK kimliğini düşürürse ya da
değiştirirse çıktı yanlıştır — bir analist o kimliği arayacak. Burada yorum
yok.

Ölçüm kesin olabiliyorken hakem çağırmak hem pahalı hem tekrarlanabilirliği
düşürür: aynı çıktıya iki koşuda farklı puan gelir.

Beş bileşen var, hepsi programatik: kimlik koruma, dil, yapı (başlık ve adım
sayısı), uzunluk oranı, başlık sözlüğü uyumu.

## Kaynaklar

- Kaynak veri seti — [reloading0101/threat-intelligence-dataset](https://huggingface.co/datasets/reloading0101/threat-intelligence-dataset) (CC BY 4.0)
- NIST SP 800-61 — olay müdahale çerçevesi
- MITRE ATT&CK — teknik ve azaltma kimlikleri
- Türkçe veri stratejisi ölçümlerim — [emr4h/turkce-llm-veri-stratejisi](https://github.com/emr4h/turkce-llm-veri-stratejisi)

## Lisans

Kod MIT. Kaynak veri seti CC BY 4.0; türev veri bu repoda yayınlanmıyor,
scriptler kaynağı kendileri indiriyor.
