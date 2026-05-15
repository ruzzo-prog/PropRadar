PropRadar — myhome.ge Phone Enricher  
Документация по отладке и деплою | 12.05.2026  
══════════════════════════════════════════════════════════════════

1\. ЗАДАЧА  
─────────────────────────────────────────────────────────────────  
Автоматически извлекать номер телефона владельца с листингов myhome.ge через Playwright headless-браузер внутри Docker-контейнера propradar-playwright-worker-1.  
Телефон скрыт за кнопкой «ნომრის ნახვა» (показать номер) — нажатие запускает reCAPTCHA v3 и делает запрос к внутреннему API tnet.ge/phone/show.

2\. ОКРУЖЕНИЕ  
─────────────────────────────────────────────────────────────────  
Контейнер:     propradar-playwright-worker-1  
Основной файл: /app/src/parsers/adapters/myhome/phone.py  
Скрипт логина: /app/scripts/myhome\_login.py  
Файл сессии:   /data/adapter\_sessions/myhome\_session.json  
Прокси:        http://utcso6t3nr.cn.fxdx.in:15539  (user: matteledge120851)  
База данных:   postgresql://leads:\*\*\*@leads-db:5432/leads  
Worker API:    POST /enrich  {adapter: myhome, phase: phone, limit: N}  
Login API:     POST /login   {adapter: myhome}

3\. НАЙДЕННЫЕ ПРИЧИНЫ СБОЕВ И ИСПРАВЛЕНИЯ  
─────────────────────────────────────────────────────────────────

3.1  Один browser на весь батч (50 лидов)  
Проблема: Playwright-инстанс не освобождал ресурсы между лидами. Накапливались zombie-процессы chromium → exit 137\.  
Решение: Каждый лид получает свой sync\_playwright() \+ browser. Перед и после: pkill \-9 chromium \+ os.waitpid(-1, WNOHANG) для reaping зомби.

3.2  BTN\_SELECTORS с Playwright-синтаксисом в querySelectorAll  
Проблема: Селекторы вида button:has(span:text("...")) — Playwright-специфичны, querySelectorAll выбрасывал SyntaxError. Кнопка — это SPAN внутри DIV, не \<button\>.  
Решение: Заменено на page.locator("text=ნომრის ნახვა").first — нативный text-локатор Playwright.

3.3  React hydration delay (\~4–9 сек после domcontentloaded)  
Проблема: Кнопка есть в DOM но скрыта (display:none) до завершения гидратации React/Next.js. locator.click() падал с "element is not visible".  
Решение: wait\_for(state="attached", timeout=30000) — ждём появления в DOM, не видимости.

3.4  Кнопка скрыта предками (display:none у родителей)  
Проблема: Даже после гидратации click() падал на hidden-предке.  
Решение: JS evaluate раскрывает всю цепочку предков перед el.click():  
  while (e && e \!== document.body) {  
    if (getComputedStyle(e).display \=== 'none') e.style.display \= 'block';  
    if (getComputedStyle(e).visibility \=== 'hidden') e.style.visibility \= 'visible';  
    e \= e.parentElement;  
  }  
  el.click();

3.5  DOM-поллинг не находил телефон  
Проблема: Телефон приходит в JSON-ответе API phone/show, не всегда рендерится в span.  
Решение: page.expect\_response(lambda r: "phone/show" in r.url and r.status \== 200\) — перехватываем JSON напрямую. Фильтр status==200 исключает OPTIONS preflight (204).

3.6  Истечение AccessToken (TTL 11 мин) на батче 50 лидов  
Проблема: Батч из 50 лидов занимает \~40 мин. Токен истекал — все последующие запросы к phone/show возвращали 401/403.  
Решение:  
  1\) Сессия читается с диска перед каждым лидом (\_load\_storage).  
  2\) Авто-перелогин: если remaining \< 60s → subprocess.run(myhome\_login.py).  
  3\) context.storage\_state() сохраняется на диск в finally каждого лида  
     (JS на странице продлевает токен — фиксируем обновление).

3.7  Cloudflare rate-limiting (8/50 лидов)  
Проблема: После быстрой серии запросов CF выдавал "Just a moment..." challenge. Проверка по title срабатывала, но CF иногда включался ПОСЛЕ domcontentloaded.  
Решение:  
  1\) page.wait\_for\_load\_state("networkidle", timeout=10s) после goto —  
     даёт CF-JS время выполниться и пройти challenge автоматически.  
  2\) time.sleep(random.uniform(2.0, 4.0)) между лидами —  
     снижает частоту запросов ниже порога CF.

4\. АРХИТЕКТУРА АВТОРИЗАЦИИ myhome.ge / tnet.ge  
─────────────────────────────────────────────────────────────────  
Сайт работает на трёх независимых контурах авторизации:

• Cloudflare (CF): CDN-защита. Fingerprinting браузера \+ IP-репутация прокси.  
  Обходится playwright-stealth \+ пауза между запросами.

• reCAPTCHA v3 (Google): Невидимая капча при клике на кнопку телефона.  
  Score формируется браузерным fingerprint. Пока проходит без доп. обработки.

• AccessToken / RefreshToken (tnet.ge): JWT в cookie-домене .tnet.ge. TTL AccessToken ≈ 11 мин, RefreshToken долгоживущий.  
  Страница обновляет AccessToken через JS автоматически.  
  Токен копируется в www.myhome.ge domain в \_load\_storage() для корректной отправки.

5\. ИТОГОВЫЕ РЕЗУЛЬТАТЫ ТЕСТОВ  
─────────────────────────────────────────────────────────────────  
Тест 1 (3 лида)                 → 2/3         TimeoutError на 1 просроченном объявлении  
Тест 2 (10 лидов)               → 9/10        RuntimeError — снятые объявления  
Тест 3 (50 лидов — старый код)  → 19/50 (38%) Токен истёк, CF-блокировки  
Тест 4 (50 лидов — новый код)   → 42/50 (84%) CF rate-limit на 8 лидов  
Тест 5 (retry 8 лидов \+ CF fix) → 7/8         1 лид стабильно блокируется CF  
ИТОГО                           → 49/50 \= 98% ext=23971326 — стабильная CF-блокировка

6\. КЛЮЧЕВЫЕ ФРАГМЕНТЫ КОДА  
─────────────────────────────────────────────────────────────────

── click\_show\_phone — перехват API-ответа: ──  
def click\_show\_phone(page, external\_id):  
    btn\_loc \= page.locator("text=ნომრის ნახვა").first  
    btn\_loc.wait\_for(state="attached", timeout=TW\_MS)  
    with page.expect\_response(  
        lambda r: "phone/show" in r.url and r.status \== 200,  
        timeout=TW\_MS,  
    ) as resp\_info:  
        btn\_loc.evaluate("""el \=\> {  
            let e \= el;  
            while (e && e \!== document.body) {  
                if (getComputedStyle(e).display \=== 'none') e.style.display \= 'block';  
                if (getComputedStyle(e).visibility \=== 'hidden') e.style.visibility \= 'visible';  
                e \= e.parentElement;  
            }  
            el.click();  
        }""")  
    payload \= resp\_info.value.json()  
    return payload\["data"\]\["phone\_number"\].strip()

── \_load\_storage — чтение сессии \+ авто-перелогин: ──  
def \_load\_storage(self):  
    storage \= json.loads(self.\_storage\_state\_path.read\_text())  
    token \= next((c for c in storage\["cookies"\] if c\["name"\] \== "AccessToken"), None)  
    if token:  
        payload \= json.loads(base64.b64decode(token\["value"\].split(".")\[1\] \+ "=="))  
        remaining \= payload\["expires\_at"\] \- time.time()  
        if remaining \< 60:  
            subprocess.run(\["python3", str(login\_script)\], timeout=120)  
            storage \= json.loads(self.\_storage\_state\_path.read\_text())  
    \# копируем токен на www.myhome.ge domain  
    tnet\_tok \= next((c for c in storage\["cookies"\] if c\["name"\] \== "AccessToken"), None)  
    if tnet\_tok:  
        mh \= copy.deepcopy(tnet\_tok)  
        mh\["domain"\] \= "www.myhome.ge"  
        storage\["cookies"\].append(mh)  
    return storage

── enrich\_leads — основной цикл с CF-паузой: ──  
for lead in items:  
    lead\_storage \= self.\_load\_storage()  
    subprocess.run(\["pkill", "-9", "-f", "chromium"\], capture\_output=True)  
    with sync\_playwright() as pw:  
        browser \= pw.chromium.launch(\*\*launch\_kw)  
        try:  
            err \= self.\_enrich\_one\_isolated(browser, lead, lead\_storage)  
        finally:  
            browser.close()  
    subprocess.run(\["pkill", "-9", "-f", "chromium"\], capture\_output=True)  
    try:  
        while True:  
            pid, \_ \= os.waitpid(-1, os.WNOHANG)  
            if pid \== 0: break  
    except ChildProcessError:  
        pass  
    time.sleep(random.uniform(2.0, 4.0))   \# CF rate-limit protection

── \_enrich\_one\_isolated — CF-обход при загрузке страницы: ──  
page.goto(url, wait\_until="domcontentloaded", timeout=TW\_MS)  
\# Ждём networkidle — CF-JS должен успеть выполниться и пройти challenge  
try:  
    page.wait\_for\_load\_state("networkidle", timeout=10000)  
except Exception:  
    pass  
if "Just a moment" in page.title() or "cf-challenge" in page.content():  
    logger.warning("cloudflare\_block ext=%s", lead.external\_id)  
    return "CloudflareBlock"

7\. API-КОМАНДЫ ДЛЯ ЗАПУСКА  
─────────────────────────────────────────────────────────────────

Логин (обновление сессии):  
  curl \-X POST http://localhost:8001/login \\  
    \-H 'Content-Type: application/json' \\  
    \-d '{"adapter": "myhome"}'

Запуск обогащения:  
  curl \-X POST http://localhost:8001/enrich \\  
    \-H 'Content-Type: application/json' \\  
    \-d '{"phase": "phone", "adapter": "myhome", "limit": 50}'

Прямой тест из контейнера:  
  docker exec propradar-playwright-worker-1 timeout 300 python3 \-c "  
  import sys, logging; sys.path.insert(0, '/app/src')  
  logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')  
  from config.settings import Settings  
  from parsers.adapters.myhome.phone import MyHomePhoneEnricher  
  from repositories.postgres\_lead\_repository import PostgresLeadRepository, PostgresSessionFactory  
  settings \= Settings()  
  sessions \= PostgresSessionFactory.from\_database\_url(str(settings.database\_url))  
  repo \= PostgresLeadRepository(sessions)  
  leads \= repo.list\_pending\_phone\_enrichment('myhome', limit=10)  
  e \= MyHomePhoneEnricher(repo, headless=True, storage\_state\_path=settings.myhome\_session\_path)  
  r \= e.enrich\_leads(leads)  
  print('enriched=%d failed=%d' % (r.enriched, r.failed))  
  " 2\>&1

8\. ЧТО ОСТАЛОСЬ / ЧТО МОЖНО УЛУЧШИТЬ  
─────────────────────────────────────────────────────────────────

ВЫСОКИЙ  │ Zombie-процессы — системное решение  
         │ Добавить init: true в docker-compose.yml для playwright-worker.  
         │ PID 1 \= tini/init → автоматически reap-ает зомби.  
         │ Текущий os.waitpid работает, но ненадёжен при краше Python.

ВЫСОКИЙ  │ Планировщик обогащения  
         │ Сейчас запускается вручную через curl.  
         │ Нужен cron или n8n workflow: POST /login → sleep 5s → POST /enrich.  
         │ Рекомендуется: батчи по 50, раз в час (с учётом TTL токена).

СРЕДНИЙ  │ Retry для CF-заблокированных лидов  
         │ CloudflareBlock попадает в следующий батч автоматически.  
         │ Но ext=23971326 стабильно блокируется.  
         │ Нужен счётчик попыток \+ экспоненциальный backoff (5 мин → 1 час → 1 день).

СРЕДНИЙ  │ Мониторинг success rate  
         │ Нет алертов при падении. После каждого батча — метрика в Redis/DB.  
         │ Уведомление в Telegram/Slack если enriched/total \< 80%.

СРЕДНИЙ  │ Ротация прокси  
         │ Один прокси-IP на все запросы. При росте объёма (500+ лидов/день)  
         │ CF reputation IP будет ухудшаться.  
         │ Рассмотреть пул residential прокси с ротацией.

НИЗКИЙ   │ Параллельная обработка  
         │ Сейчас: 1 лид \~60с → 50 лидов \= \~50 мин.  
         │ Можно 2-3 worker thread с разными прокси-IP.  
         │ Требует row-level locking записей в БД при выборке.

НИЗКИЙ   │ Detail / PDF фазы обогащения  
         │ Phone enricher работает. Есть ещё phase=detail и phase=pdf.  
         │ Их статус и корректность не проверялись в этой сессии.

НИЗКИЙ   │ Автоперезапуск контейнера  
         │ После длинного батча накапливается память.  
         │ Рассмотреть restart playwright-worker после каждого батча  
         │ или ограничение \--memory в docker-compose.

9\. ИЗВЕСТНЫЕ ОГРАНИЧЕНИЯ  
─────────────────────────────────────────────────────────────────  
• AccessToken TTL \= 11 мин. Авто-перелогин работает, но добавляет \~15с задержки на триггер.  
• reCAPTCHA v3 score: пока не было отказов. При росте трафика нужен 2captcha/CapMonster.  
• myhome.ge периодически меняет DOM. Если кнопка не находится — обновить локатор "text=ნომრის ნახვა".  
• Listings могут быть сняты между парсингом и обогащением — ожидаемое поведение, не баг.  
• ext=23971326 стабильно блокируется CF независимо от сессии/прокси. Причина неизвестна.  
