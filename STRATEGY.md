# SEO Autopilot — Metro City / State Strategy (2026-10-26)

## 1. Amaç

İki dizin sitesini yerel aramalarda büyütmek:

- **sleepclinicdirectory.com** — ABD'deki sleep clinic'leri şehir/eyalet bazında üst sıralara çıkarmak.
- **findsleepdoctors.com** — ABD, UK, Kanada, Avustralya, NZ ve İrlanda'daki sleep doctor/merkezlerini şehir/bölge bazında üst sıralara çıkarmak.

Ana kaldıraç: **metro şehir ve eyalet/bölge rehberleri** + clinic/doctor sayfalarına güçlü iç linkleme. Blog yazısı değil, “şehir rehberi” işlevi gören, veriye dayalı sayfalar.

## 2. Mevcut durum

| Site | Clinic/Doctor | Makale | Şehir/eyalet altyapısı |
|---|---:|---:|---|
| sleepclinicdirectory.com | 7.522 clinic | 207 yayında | `/states/[state]`, `/states/[state]/[city]`, `/clinic/[slug]` |
| findsleepdoctors.com | 21.343 doctor/merkez | 194 yayında | `/[country]/[region]`, `/[country]/[region]/[city]`, `/[country]/[region]/[city]/[doctor]` |

Hedef kitle: belirti/teşhis sonrası yerel sleep clinic veya sleep doctor arayan hastalar; ikinci hedef, clinic/doctor sayfalarının kendi marka aramalarında güçlenmesi.

## 3. İki site ayrımı (kanibalizasyon önleme)

| Konu | sleepclinicdirectory | findsleepdoctors |
|---|---|---|
| Odak | Clinic, sleep study, CPAP, tedavi, sigorta | Doctor/specialist bulma, credentials, referral, randevu |
| Coğrafya | ABD, eyalet/şehir | 6 ülke, region/city |
| Başlık dili | “Sleep clinics in …” | “Sleep doctors in …” |
| İç link hedefi | `/clinic/...` + `/states/...` | `/[country]/[region]/[city]/[doctor]` + city/region |
| Veri | clinic adı/adres/telefon/hizmet | doctor adı/credentials/specialty/clinic/telefon |

Aynı şehir adı iki sitede geçebilir; **metin, niyet ve URL farklı** olur. Aynı içerik iki domainde kopyalanmaz.

## 4. Sayfa tipleri ve şablonlar

### A. Metro şehir rehberi

- **SCD:** “Sleep Clinics in Houston, TX: How to Choose One and What to Expect”
- **FSD:** “Sleep Doctors in Houston: How to Find the Right Specialist”
- URL: mevcut `/articles/[slug]` altyapısı.
  - SCD slug: `sleep-clinics-<city>-<state>`
  - FSD slug: `sleep-doctors-<city>-<region>-<country>`

Zorunlu bloklar:

1. **Quick answer** (50–80 kelime): kaç clinic/doctor listelendiği + rehberin kapsamı.
2. **At a glance** tablosu: 8–10 clinic/doctor; ad, bölge/ZIP, telefon, hizmet/credentials; her satır ilgili profil sayfasına link.
3. **How to choose**: 5–6 kriter; yerel veriye bağlı.
4. **What to expect**: ilk randevu, test/teşhis, tedavi; genel bilgi, tıbbi tavsiye değil.
5. **Insurance, cost and access**: ülkeye uygun genel çerçeve; fiyat uydurma yok.
6. **Neighborhoods and access**: yalnızca verideki ZIP/adres/şehir bilgisi; seyahat süresi uydurma yok.
7. **Questions to ask**: 6–8 pratik soru.
8. **FAQ**: 6 soru; FAQPage JSON-LD.
9. **How we built this guide**: veri kaynağı, AASM/NHLBI/Medicare/NHS gibi kaynaklar, son güncelleme, byline, tıbbi uyarı.

### B. Eyalet / bölge hub’ı

- **SCD:** “Sleep Clinics in Texas: Metro-by-Metro Guide”
- **FSD:** “Sleep Doctors in Texas: How to Find a Specialist”
- İçerik: eyalet/bölgedeki metro şehirleri tablosu (clinic/doctor sayısı + link), öne çıkan clinic/doctor tablosu, seçim kriterleri, sigorta/erişim, FAQ, metodoloji.
- Şehir rehberlerine ve clinic/doctor sayfalarına link verir; hub-and-spoke mimarisinin üst katmanı.

### C. Mevcut clinic/doctor sayfaları

- Şablon değişikliği şimdilik yok; yeni rehberler bu sayfalara link verir.
- Sonraki fazda clinic/doctor sayfasına “Local guide” linki eklenebilir; bu, kod değişikliği ve build gerektirir.

## 5. Hedef seçimi ve öncelik

### sleepclinicdirectory

- **Eyalet hub’ları:** en az 20 clinic’i olan 48 eyalet/DC. Önce bunlar (hub otoritesi).
- **Metro şehirler:** en az 8 clinic’i olan, clinic sayısına göre ilk 160 şehir.
- Toplam kuyruk: **175 hedef** (48 hub + 127 şehir).
- Küçük/az verili şehirler üretilmez; thin content ve doorway riski önlenir.

### findsleepdoctors

- **Bölge hub’ları:** en az 20 doctor/merkez içeren 66 bölge.
- **Metro şehirler:** en az 10 doctor/merkez içeren, ülke içinde en yoğun 220 şehir.
- Toplam kuyruk: **286 hedef**.
- ABD dışı ülkelerde “sleep doctor” ve “sleep centre” farkı korunur; US sigorta varsayımı yapılmaz.

## 6. AEO / SEO / GEO / EEAT kuralları

### AEO (Answer Engine Optimization)

- İlk 60–80 kelimede doğrudan cevap; “Quick answer” bloğu.
- Soru formatlı H2/H3; 6 FAQ.
- Tablo ve listeler; tek paragraf yığını yok.
- FAQPage + Article/MedicalWebPage JSON-LD (site şablonu + inline FAQ).
- “Kaç clinic/doctor var?” sorusuna veriye dayalı net cevap.

### SEO

- Title ≤60, meta description ≤160.
- H1 yalnızca şablonun başlığı; gövdede H1 yok.
- Anahtar kelime URL, H1, ilk paragraf ve en az bir H2’de.
- 3–5 internal link / 1000 kelime; anchor çeşitliliği.
- Kanonik: self; mevcut `/articles/[slug]` altyapısı.
- Sitemap + IndexNow; yeni URL’ler 24 saat içinde gönderilir.

### GEO (Generative Engine Optimization)

- Kendi kendine yeten, alıntılanabilir cevap blokları.
- Somut yerel veri: clinic/doctor sayısı, isimler, adresler, ZIP’ler, hizmetler.
- Birincil kaynaklara link (AASM, NHLBI, Medicare.gov, NHS, ilgili sağlık otoritesi).
- Son güncelleme tarihi ve editör byline’ı.
- Sayfa SSR; AI crawler’lar için robots/llms.txt mevcut altyapıda korunur.
- Uydurma istatistik, hasta yorumu, “en iyi” iddiası yok.

### EEAT

- Byline: “Sleep Clinic Directory Editorial Team” / “Find Sleep Doctors Editorial Team”.
- “How we built this guide”: veri kaynağı, metodoloji, son güncelleme, düzeltme politikası.
- Tıbbi uyarı: “directory information, not medical advice”.
- Gerçek olmayan doktor/medikal reviewer kimliği **yok**; ileride gerçek isim/credentials olmadan eklenmez.
- Clinic/doctor verisi yalnızca dizin kaydından; rating/uydurma yorum yok.

## 7. İç linkleme modeli

```
Home
 ├─ State/Region hub
 │   ├─ Metro city guide
 │   │   ├─ 8–10 clinic/doctor profile
 │   │   ├─ Nearby city guides (3–4)
 │   │   └─ 2–3 ilgili rehber (sleep study, CPAP, insurance)
 │   └─ Diğer city guide’lar
 └─ Mevcut rehberler
```

- Şehir rehberi → 8–10 clinic/doctor + state/region + 3–4 yakın şehir + 2–3 makale.
- Eyalet/bölge hub → tüm metro şehirleri + öne çıkan clinic/doctor.
- Anchor metinleri çeşitli; aynı “sleep clinic Houston” tekrarı yok.
- Linkler absolute; her link 200 doğrulanır.
- Gelecek faz: clinic/doctor sayfasından şehir rehberine geri link (kod değişikliği).

## 8. Kalite kapıları (programmatic SEO)

Her makale yayınlanmadan önce:

| Kontrol | Eşik |
|---|---|
| Kelime | 700–2500 (hedef 900–1500) |
| Quick answer | İlk blokta |
| H2 | ≥5 |
| FAQ | tam 6 + geçerli FAQPage |
| Meta title/description | ≤60 / ≤160 |
| Internal link | ≥3; hepsi 200 |
| Duplicate slug/title/focus | 0 |
| Benzerlik | Mevcut makalelerle Jaccard <0.35 |
| Yasaklı ifade | delve/unlock/landscape/… yok |
| “best/top-rated/#1/guarantee/cure/100%” | yok |
| Tıbbi uyarı | var |
| Veri uydurma | Clinic/doctor dışı rating, fiyat, bekleme süresi yok |

Ek koruma:

- Şehirde minimum clinic/doctor sayısı (SCD 8, FSD 10); altındaki hedef kuyruğa girmez.
- Şehir adı değiştirilince anlamı bozulan “swap test” sayfaları reddedilir.
- 25’lik batch’te başarısızlık >%20 ise otomatik durdurma ve alert.
- İnsan örneklemi: ilk 100 sayfanın en az %10’u manuel okunmalı; otomatik validator tek başına yeterli değil.

## 9. Yayın hızı ve ramp

Kullanıcı hedefi: **saatte 25 yazı**. Uygulama:

- Pilot: 1 şehir + 3 eyalet/region her site (tamamlandı).
- Saatlik timer: her site için 25, toplam 50/saat.
- İlk 2 saatten sonra `STATUS.md` ve `ALERTS.md` kontrol edilir.
- Başarısızlık >%20, canlı 200 <%%98, `/articles` sayısı DB ile uyuşmuyor veya servis down ise timer durdurulur.
- 600/gün/site agresif bir hızdır; Google’ın scaled content abuse politikası nedeniyle kalite kapıları ve insan örneklemi zorunludur. Gerekirse 25/saat toplam’a düşürülür.

## 10. Model yönlendirme

- Öncelik: `deepseek-v4.1-flash-free` → `glm-5.3-flash-free` → `reflection/beam-free` (Kilo ücretsiz).
- DeepSeek ve GLM bu egress IP’de **429 FreeUsageLimit** verdi; Kilo `reflection/beam-free` çalışıyor.
- Kilo’ya yalnızca **public** site/clinic/doctor verisi gider; credential, şifre, özel müşteri verisi asla gitmez.
- Kilo da başarısız olursa paid `opencode-go/deepseek-v4.1-flash` fallback; loglanır ve raporda belirtilir.
- Her çağrı `logs/events.jsonl`’e model, süre, hata/fallback olarak yazılır.

## 11. Pipeline

```
queue (DB → metro/state targets)
  → data (clinic/doctor + nearby + internal links)
  → prompt (AEO/SEO/GEO/EEAT şablonu)
  → model (free cascade → paid fallback)
  → validate (kelime, link, FAQ, duplicate, similarity, yasaklı ifade)
  → insert (SQLite + SCD JSON source)
  → publish (DB-only rsync + service restart)
  → SCD: on-demand revalidate /articles + sitemap
  → IndexNow
  → monitor (STATUS.md / ALERTS.md)
```

Kod: `/root/seo-autopilot/`
- `autopilot.py` — queue/data/CLI
- `pipeline.py` — generation, validation, publish
- `run_hourly.py` — 25/site/saat + lock
- `monitor.py` — kontrol raporu
- `queue/`, `logs/`, `backups/`, `generated/`, `STATUS.md`, `ALERTS.md`

## 12. Monitoring / alert

`monitor.py` her 15 dakikada:

- DB published vs `/articles` canlı sayısı
- servis active mi
- DB integrity
- son run zamanı ve hata oranı
- kuyrukta pending/failed
- son örnek URL

`STATUS.md` her zaman güncel; hata varsa `ALERTS.md` yazılır ve script exit 1 döner (systemd journal’da görünür). Kritik eşikler:

- Son run >90 dk ve pending >0
- Son run hata oranı >%20
- `/articles` sayısı DB ile uyuşmuyor
- Servis active değil
- DB integrity != ok

## 13. 30 günlük plan

| Gün | İş |
|---|---|
| 1 | Pilot 8 sayfa (tamamlandı), validator/monitor, timer |
| 2–3 | 50/saat; ilk 100 sayfa; manuel %10 örneklem |
| 4–7 | Kalan state/region hub’ları; city guide’lar |
| 8–14 | İlk 300 sayfa; Search Console/IndexNow izleme; zayıf sayfaları düzelt |
| 15–30 | Kalan kuyruk; internal link optimizasyonu; clinic/doctor sayfalarına geri link fazı |

## 14. Riskler

- **Scaled content abuse:** 25/saat agresif; kalite kapıları, veri farklılaşması ve kademeli izleme zorunlu.
- **Thin/doorway:** Minimum clinic/doctor eşiği, swap testi, benzerlik kontrolü.
- **Tıbbi YMYL:** Teşhis/tedavi iddiası yok; kaynak + uyarı.
- **Model rate limit:** Kilo/paid fallback; başarısızlıkta durdurma.
- **Veri kalitesi:** Clinic/doctor kayıtları eksik olabilir; eksik alan uydurulmaz.
- **Index bloat:** Yalnızca eşiği geçen şehirler; düşük değerli sayfa üretilmez.
- **Kopya içerik:** İki site arasında metin paylaşılmaz; farklı niyet/dil.
