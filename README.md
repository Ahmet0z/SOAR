# SOAR Platformu

Python (FastAPI + SQLModel) tabanlı bir backend ile React (Vite) tabanlı bir arayüzden oluşan uçtan uca SOAR prototipi. Incidents, indicators, automations ve playbooks modülleri kimlik doğrulamalı API üzerinden yönetilir ve frontend tarafında sürükle-bırak akış tasarımı, kod editörü ve context şeması düzenleyicileri bulunur.

## Proje Yapısı

```
backend/   # FastAPI uygulaması, SQLModel veri katmanı ve servisler
frontend/  # React + Vite arayüzü, React Query, React Flow ve CodeMirror
```

## Backend'i Çalıştırma

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Veritabanı şeması Alembic üzerinden yönetilir; ilk kurulumda `alembic upgrade head` ile tüm tablolar oluşturulur. Otomasyon kuyruğu Redis üzerinde tutulduğundan lokalde örneğin `docker run -p 6379:6379 redis:7` komutu ile bir Redis örneği çalıştırmanız ve ayrı bir terminalde `python -m app.rq_worker` ile RQ worker'ı başlatmanız gerekir. Başlangıçta SQLite veritabanı (`soar.db`) oluşturulur ve `admin / admin123` kimlik bilgilerine sahip varsayılan bir kullanıcı eklenir. API'ye erişirken OAuth2 password flow üzerinden alınan JWT kullanılır (`/api/auth/token`). `.env` dosyası üzerinden aşağıdaki ayarları özelleştirebilirsiniz:

```bash
# Ayrı terminalde worker'ı başlatın
cd backend
python -m app.rq_worker
```

| Anahtar | Açıklama |
| --- | --- |
| `SOAR_SECRET_KEY` | JWT imzalama anahtarı |
| `SOAR_DATABASE_URL` | SQLModel tarafından kullanılacak veritabanı bağlantısı |
| `SOAR_CORS_ORIGINS` | Frontend domain listesi (virgülle ayrılmış) |
| `SOAR_DEFAULT_TENANT`, `SOAR_DEFAULT_TENANT_NAME` | İlk organizasyon bilgileri |
| `SOAR_DEFAULT_ADMIN_USERNAME`, `SOAR_DEFAULT_ADMIN_PASSWORD` | Başlangıç yönetici kullanıcı bilgileri |
| `SOAR_INVITE_EXPIRY_HOURS` | Organizasyon davetlerinin geçerli olacağı süre |
| `SOAR_REDIS_URL` | Otomasyon kuyruğu ve gerçek zamanlı yayınlar için Redis adresi |
| `SOAR_AUTOMATION_QUEUE` | RQ kuyruğunun adı (varsayılan `automation-runs`) |

### Docker Compose ile hızlı başlangıç

Redis, FastAPI uygulaması ve RQ worker'ını tek komutla ayağa kaldırmak için kökteki `docker-compose.yml` dosyasını kullanabilirsiniz:

```bash
docker compose up --build
```

Komut, backend klasörünü konteyner içine bağlar, API'yi `http://localhost:8000` adresine yayınlar ve aynı anda worker ile Redis servisini başlatır. Ortam değişkenlerini özelleştirmek için `backend/.env` dosyası oluşturabilir veya `docker compose` komutuna `SOAR_` prefiksli değişkenler geçebilirsiniz.

### Öne Çıkan Backend Modülleri

- **Incidents & Indicators** – SQLModel tabanlı CRUD uçları, tenant bazlı erişim kontrolü, dinamik context şeması doğrulaması ve alan bazlı ekleme/çıkarma işlemleri.
- **Context Şemaları** – `/api/context-schemas/{entity_type}` uçları ile context alanları için tip (string/integer/boolean) ve zorunluluk bilgisi tanımlanır. Her alan versiyonlanır, geçmiş `/history` uçlarıyla görüntülenir ve audit log'lara kaydedilir.
- **Automations** – Python kodu tutulan otomasyon kayıtları ve güvenli yürütme kuyruğu (`/api/automations/{id}/runs`). Kodlar `run(payload)` fonksiyonu içermelidir, her çalışma `AutomationRun` tablosunda saklanır ve worker thread tarafından izole şekilde yürütülür.
- **Automations** – Python kodu tutulan otomasyon kayıtları ve güvenli yürütme kuyruğu (`/api/automations/{id}/runs`). Kodlar `run(payload)` fonksiyonu içermelidir, her çalışma `AutomationRun` tablosunda saklanır, tekrar deneme/zaman aşımı politikaları ve bekleme/süre metrikleri otomatik tutulur.
- **Automation run olayları** – Her çalışmanın kuyruğa alınmasından tamamlanmasına kadar tüm durum değişimleri `AutomationRunEvent` tablosunda saklanır ve `/api/automation-runs/{id}/events` ucu üzerinden veya gerçek zamanlı websocket yayınlarıyla görüntülenebilir.
- **Playbooks** – Düğüm ve kenar tanımlarını JSON olarak saklayan modeller, graf doğrulama uçları ve otomasyonları sırayla çalıştıran yürütme motoru (`/api/playbooks/{id}/run`).
- **Organizations & Audit Logs** – Çok kiracılı senaryolar için organizasyon uçları, kullanıcı üyelik/davet/switch operasyonları, davet token süre sonu ve public kabul uçları ile self-servis kayıt, her kritik aksiyonu saklayan ve filtrelenebilir/CSV dışa aktarılabilir audit log API'si.
- **Automation telemetry** – Kuyruklanan otomasyonlar için latency/süre/timeout metrikleri, yeniden kuyruğa alma uçları ve worker heartbeat bilgisini dönen sağlık ucu.

## Frontend'i Çalıştırma

```bash
cd frontend
npm install
npm run dev
```

Arayüz `http://localhost:5173` adresinde çalışır ve varsayılan olarak `http://localhost:8000/api` taban adresine bağlanır. Farklı ortamlar için `.env` içine `VITE_API_BASE_URL` ekleyebilirsiniz.

### Arayüz Özellikleri

- **Giriş & RBAC** – Admin kullanıcı bilgileri ile giriş yapılır, JWT localStorage'da saklanır ve yetkisiz yanıtlar otomatik olarak oturumu sonlandırır.
- **React Query veri katmanı** – Tüm CRUD işlemleri merkezi önbellekten yönetilir ve optimistic güncellemeler yapılır.
- **Context düzenleyicileri** – Incidents ve indicators modüllerinde şema tabanlı modal ile context alanı ekleme/silme yapılır, şema yöneticisinden alan geçmişi (versiyon/tarih) görüntülenebilir.
- **Automation kod editörü** – Automations panelinde CodeMirror + Python dili ile sözdizimi vurgulu editör ve JSON tabanlı test kuyruğu bulunur; her çalışma Redis destekli kuyruğa alınır, durum/çıktı geçmişi gerçek zamanlı WebSocket akışıyla güncellenir, başarısız koşular yeniden kuyruğa alınabilir.
- **Playbook tasarımcısı** – React Flow ile sürükle-bırak düğüm/ok oluşturma, otomasyon eşleme, edge koşulu düzenleme ve doğrulama/çalıştırma çıktısı görüntüleme.
- **Audit & Organization panelleri** – Denetim kayıtları gerçek zamanlı listelenir, aksiyon/varlık/tarih filtreleriyle aratılabilir ve CSV olarak indirilebilir. Organizasyon ekranında üyelikler, davet token son kullanma tarihleri ve kabul zamanları görüntülenir, davet linkleri self-servis kabul ekranıyla paylaşılabilir.
- **Automation analitikleri ve worker sağlığı** – Son koşumlar için zaman serisi grafiği, ortalama metrikler, timeout sayıları ve worker kuyruğunun güncel durumu tek kartta görüntülenir; RQ kuyruğu/worker telemetrisi WebSocket olaylarıyla panelde eşzamanlı güncellenir.
- **Otomasyon olay zaman çizelgesi ve bildirimler** – Seçilen çalışmanın ayrıntı panelinde gerçek zamanlı `AutomationRunEvent` akışı gösterilir, başarı/başarısızlık gibi kritik olaylar toast bildirimleriyle duyurulur.

## Test

Backend için pytest ve sözdizimi kontrolü:

```bash
cd backend
pytest
pytest tests/test_automation_jobs.py
python -m compileall app
```

Frontend için test ve build kontrolü:

```bash
cd frontend
npm run test
npm run build
```
