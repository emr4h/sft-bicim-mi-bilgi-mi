"""
Terim sözlüğü ve teknik kimlik desenleri — üretim ve skorlama ortak kullanır.

NEDEN SÖZLÜK?
    Türkçe güvenlik terminolojisi oturmuş değil. Aynı kavram farklı
    yerlerde farklı çevrilirse model tutarsızlık öğrenir. Bir kez karar
    verilir, her yerde ona uyulur (dil kuralları, madde 4).

NEDEN BAZI TERİMLER ÇEVRİLMİYOR?
    payload, host, log gibi kelimeler Türk güvenlik ekiplerinde İngilizce
    kullanılıyor. Zorla çevirmek doğal olmayan metin üretir (dil kuralları,
    madde 3).
"""
import re

# Bölüm başlıkları — çıktının iskeleti. Tutarlı olması SFT'nin öğreteceği
# biçimin belkemiği.
BASLIKLAR = {
    "Detection & Analysis": "Tespit ve Analiz",
    "Containment, Eradication & Recovery": "Sınırlama, Temizleme ve Kurtarma",
    "Post-Incident Activity": "Olay Sonrası Faaliyetler",
    "Hypothesis": "Hipotez",
    "Data Sources for Querying": "Sorgulanacak Veri Kaynakları",
    "Hunt Guidance": "Av Rehberi",
    "Severity": "Önem Derecesi",
    "Triage Playbook": "Triyaj Rehberi",
    "Incident Response Plan": "Olay Müdahale Planı",
}

TERIMLER = {
    "threat actor": "tehdit aktörü",
    "false positive": "hatalı pozitif",
    "compromised": "ele geçirilmiş",
    "adversary": "saldırgan",
    "detection rule": "tespit kuralı",
    "lessons learned": "çıkarılan dersler",
    "known-good state": "bilinen temiz duruma",
    "privilege escalation": "yetki yükseltme",
    "lateral movement": "yanal hareket",
    "persistence": "kalıcılık",
    "exfiltration": "sızdırma",
}

# Çevrilmeyecekler — İngilizce kalması doğal olan terimler
KORUNAN = ["payload", "host", "log", "endpoint", "hash", "script",
           "registry", "shell", "firewall", "proxy", "sandbox"]

# --- Teknik kimlikler: Türkçe çıktıda AYNEN geçmeli --------------------------
# Bunlar skorlamanın kesin bileşenini oluşturuyor. Model bir ATT&CK
# kimliğini düşürürse ya da değiştirirse çıktı yanlıştır — bunu kodla
# tartışmasız ölçebiliriz.
KIMLIK_DESENLERI = {
    "attack_teknik": r"\bT\d{4}(?:\.\d{3})?\b",
    "attack_taktik": r"\bTA\d{4}\b",
    "azaltma":       r"\bM\d{4}\b",
    "cve":           r"\bCVE-\d{4}-\d{4,7}\b",
    "kural_uuid":    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    "log_kaynagi":   r"\b[A-Za-z_]{3,}:[A-Za-z_]{3,}\b",
    "cerceve":       r"\bNIST SP \d+-\d+\b|\bISO/IEC \d+\b",
}


def kimlikleri_cikar(metin):
    """Metindeki tüm teknik kimlikleri tür tür döndürür."""
    return {ad: set(re.findall(desen, metin))
            for ad, desen in KIMLIK_DESENLERI.items()}


def sozluk_metni():
    """Prompta gömülecek sözlük."""
    b = "\n".join(f"  {en} → {tr}" for en, tr in BASLIKLAR.items())
    t = "\n".join(f"  {en} → {tr}" for en, tr in TERIMLER.items())
    return (f"BÖLÜM BAŞLIKLARI (aynen bu karşılıkları kullan):\n{b}\n\n"
            f"TERİMLER:\n{t}\n\n"
            f"ÇEVİRME, İngilizce bırak: {', '.join(KORUNAN)}")
