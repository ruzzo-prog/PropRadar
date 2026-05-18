import { workflow, node, trigger, ifElse, expr, newCredential } from '@n8n/workflow-sdk';

const CHAT = '6992138349';
const API_KEY = '1070c85b1047ef76267777d7eb6fe847';

const schedule0900 = trigger({
  type: 'n8n-nodes-base.scheduleTrigger',
  version: 1.3,
  config: {
    name: 'Schedule 09:00',
    position: [0, 96],
    parameters: {
      rule: { interval: [{ field: 'cronExpression', expression: '0 9 * * *' }] },
    },
  },
  output: [{}],
});

const manualStart = trigger({
  type: 'n8n-nodes-base.manualTrigger',
  version: 1,
  config: { name: 'Manual Start', position: [0, 288] },
  output: [{}],
});

const tgStart = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Старт',
    position: [224, 192],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr('=🚀 <b>PropRadar — myhome sync</b>\n⏰ {{ $now.toFormat("HH:mm dd.MM.yyyy") }}'),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: true }],
});

const testWorker = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Тест воркера',
    position: [448, 192],
    executeOnce: true,
    parameters: {
      method: 'GET',
      url: 'http://playwright-worker:8001/health',
      options: {
        response: { response: { neverError: true } },
        timeout: 10000,
      },
    },
  },
  output: [{ status: 'ok' }],
});

const workerOk = ifElse({
  version: 2.3,
  config: {
    name: 'Воркер доступен?',
    position: [672, 192],
    parameters: {
      conditions: {
        combinator: 'and',
        options: { caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 1 },
        conditions: [
          {
            id: 'w1',
            leftValue: '={{ $json.status }}',
            rightValue: 'ok',
            operator: { type: 'string', operation: 'equals' },
          },
        ],
      },
    },
  },
});

const tgWorkerFail = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Воркер недоступен',
    position: [896, 288],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: '❌ <b>playwright-worker недоступен</b>\nПарсинг остановлен. Проверь контейнер.',
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: false }],
});

// Прокси проверяется сразу после воркера — snapshot refresh тоже идёт через прокси
const getProxyCheck = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'GET /proxy/check',
    position: [896, 96],
    executeOnce: true,
    onError: 'continueRegularOutput',
    parameters: {
      method: 'GET',
      url: 'http://playwright-worker:8001/proxy/check',
      options: {
        response: { response: { neverError: true } },
        timeout: 20000,
      },
    },
  },
  output: [{ ok: true, ip: '203.0.113.1' }],
});

const proxyOk = ifElse({
  version: 2.3,
  config: {
    name: 'Прокси OK?',
    position: [1120, 96],
    parameters: {
      conditions: {
        combinator: 'and',
        options: { caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 1 },
        conditions: [
          {
            id: 'p1',
            leftValue: '={{ $json.ok }}',
            rightValue: true,
            operator: { type: 'boolean', operation: 'equals' },
          },
        ],
      },
    },
  },
});

const tgProxyFail = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Прокси недоступен',
    position: [1344, 288],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr('=❌ <b>Прокси недоступен:</b> {{ $json.reason }}\nПарсинг остановлен.'),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: false }],
});

const tgProxyOk = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Прокси OK',
    position: [1344, 96],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr(
        '={{ $json.skipped ? "ℹ️ <b>Прокси не настроен</b>, продолжаем" : "✅ <b>Прокси работает</b> (IP: " + $json.ip + ")" }}',
      ),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: true }],
});

const getSnapshotStatus = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'GET ids-snapshot/status',
    position: [1568, 96],
    executeOnce: true,
    alwaysOutputData: true,
    parameters: {
      method: 'GET',
      url: 'http://api:8000/api/myhome/ids-snapshot/status',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'X-API-Key', value: API_KEY }] },
      options: { timeout: 10000 },
    },
  },
  output: [{ ready: true, count: 100, age_seconds: 3600, refreshing: false }],
});

const snapshotReady = ifElse({
  version: 2.3,
  config: {
    name: 'Снапшот ready?',
    position: [1792, 96],
    parameters: {
      conditions: {
        combinator: 'and',
        options: { caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 1 },
        conditions: [
          {
            id: 'sr1',
            leftValue: '={{ $json.ready }}',
            rightValue: true,
            operator: { type: 'boolean', operation: 'equals' },
          },
        ],
      },
    },
  },
});

const tgColdStart = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Cold start',
    position: [2016, 288],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: '❌ <b>Cold start</b>\nСнапшот ID пуст. Запустите <code>POST /api/myhome/ids-snapshot/refresh</code> и дождитесь готовности.',
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: false }],
});

const snapshotStale = ifElse({
  version: 2.3,
  config: {
    name: 'Снапшот устарел?',
    position: [2016, 96],
    parameters: {
      conditions: {
        combinator: 'and',
        options: { caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 1 },
        conditions: [
          {
            id: 'st1',
            leftValue: '={{ $json.age_seconds }}',
            rightValue: 86400,
            operator: { type: 'number', operation: 'gt' },
          },
        ],
      },
    },
  },
});

const tgStaleWarning = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Snapshot stale',
    position: [2240, 192],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr(
        '=⚠️ <b>Снапшот устарел</b> ({{ $json.age_seconds }} с). Продолжаем ingest; пометка inactive пропущена.',
      ),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: true }],
});

const getSnapshot = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'GET ids-snapshot',
    position: [2240, 96],
    executeOnce: true,
    alwaysOutputData: true,
    parameters: {
      method: 'GET',
      url: 'http://api:8000/api/myhome/ids-snapshot',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'X-API-Key', value: API_KEY }] },
      options: { timeout: 10000 },
    },
  },
  output: [{ ids: ['12345'], count: 1, ready: true }],
});

const idsNewInDb = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'IDs new в БД',
    position: [2464, 192],
    executeOnce: true,
    alwaysOutputData: true,
    parameters: {
      operation: 'executeQuery',
      query: "SELECT external_id FROM leads WHERE source='myhome' AND status='new'",
      options: { connectionTimeout: 30 },
    },
    credentials: { postgres: newCredential('Postgres') },
  },
  output: [{ external_id: '1' }],
});

const dedupIds = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Дедупликация IDs',
    position: [2464, 96],
    executeOnce: true,
    parameters: {
      jsCode:
        'const snap = $("GET ids-snapshot").first().json;\nconst apiIds = (snap.ids || []).map(id => String(id));\nreturn [{ json: { api_ids: apiIds, total_api: apiIds.length } }];',
    },
  },
  output: [{ api_ids: ['1'], total_api: 1 }],
});

const existingIds = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'Существующие IDs в БД',
    position: [2688, 96],
    executeOnce: true,
    alwaysOutputData: true,
    parameters: {
      operation: 'executeQuery',
      query: "SELECT external_id FROM leads WHERE source='myhome'",
      options: { connectionTimeout: 30 },
    },
    credentials: { postgres: newCredential('Postgres') },
  },
  output: [{ external_id: '1' }],
});

const filterNewIds = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Фильтр новых IDs',
    position: [2912, 96],
    executeOnce: true,
    parameters: {
      jsCode:
        'const apiIds = $("Дедупликация IDs").first().json.api_ids;\nconst totalApi = $("Дедупликация IDs").first().json.total_api;\nconst dbItems = $("Существующие IDs в БД").all();\nconst existingSet = new Set(dbItems.map(i => String(i.json.external_id)));\nconst newIds = apiIds.filter(id => !existingSet.has(id));\nreturn [{ json: {\n  new_ids: newIds,\n  new_count: newIds.length,\n  existing_count: existingSet.size,\n  total_api: totalApi\n}}];',
    },
  },
  output: [{ new_ids: [], new_count: 0, existing_count: 1, total_api: 1 }],
});

const tgFetch = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Результат fetch',
    position: [3136, 96],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr(
        '=📊 <b>Snapshot IDs</b>\n🔢 В снапшоте: {{ $json.total_api }}\n🗄 В базе: {{ $json.existing_count }}\n✨ Новых: {{ $json.new_count }}',
      ),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: true }],
});

const hasNewIds = ifElse({
  version: 2.3,
  config: {
    name: 'Есть новые IDs?',
    position: [3360, 96],
    parameters: {
      conditions: {
        combinator: 'and',
        options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 1 },
        conditions: [
          {
            id: 'n1',
            leftValue: '={{ $("Фильтр новых IDs").first().json.new_count }}',
            rightValue: 0,
            operator: { type: 'number', operation: 'gt' },
          },
        ],
      },
    },
  },
});

// Разбивает new_ids на чанки по 500 — каждый чанк = отдельный item для POST /ingest
const buildChunks = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Build Chunks',
    position: [3584, 32],
    executeOnce: true,
    parameters: {
      jsCode:
        'const ids = $("Фильтр новых IDs").first().json.new_ids;\nconst CHUNK_SIZE = 500;\nconst chunks = [];\nfor (let i = 0; i < ids.length; i += CHUNK_SIZE) {\n  chunks.push({ json: { ids: ids.slice(i, i + CHUNK_SIZE) } });\n}\nif (chunks.length === 0) chunks.push({ json: { ids: [] } });\nreturn chunks;',
    },
  },
  output: [{ ids: ['99'] }],
});

// Без executeOnce — вызывается по одному разу на каждый чанк
const postIngest = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'POST /ingest',
    position: [3808, 32],
    onError: 'continueRegularOutput',
    parameters: {
      method: 'POST',
      url: 'http://api:8000/api/myhome/ingest',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'X-API-Key', value: API_KEY }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: '={{ JSON.stringify({ ids: $json.ids }) }}',
      options: { timeout: 60000 },
    },
  },
  output: [{ parsed: 1, new: 1, errors: [] }],
});

// Суммирует parsed/new/errors со всех чанков в один результат
const aggregateResults = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Aggregate Ingest',
    position: [4032, 32],
    executeOnce: true,
    parameters: {
      jsCode:
        'const items = $input.all();\nlet parsed = 0, newCount = 0;\nconst errors = [];\nfor (const item of items) {\n  parsed += Number(item.json.parsed || 0);\n  newCount += Number(item.json["new"] || 0);\n  if (Array.isArray(item.json.errors)) errors.push(...item.json.errors);\n}\nreturn [{ json: { parsed, new: newCount, errors } }];',
    },
  },
  output: [{ parsed: 1, new: 1, errors: [] }],
});

const tgIngest = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Ingest результат',
    position: [4256, 32],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr(
        '=📥 <b>Ingest завершён</b>\n✅ Спарсено: {{ $json.parsed }}\n🆕 Новых: {{ $json.new }}\n❌ Ошибок: {{ ($json.errors || []).length }}',
      ),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: true }],
});

const queuePending = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'Очередь обогащения',
    position: [4480, 96],
    executeOnce: true,
    alwaysOutputData: true,
    parameters: {
      operation: 'executeQuery',
      query:
        "SELECT COUNT(*)::int AS pending FROM leads WHERE source='myhome' AND status='new' AND (phone IS NULL OR phone='') AND phone_retries < 3",
      options: { connectionTimeout: 30 },
    },
    credentials: { postgres: newCredential('Postgres') },
  },
  output: [{ pending: 5 }],
});

const hasPendingPhone = ifElse({
  version: 2.3,
  config: {
    name: 'Есть лиды без телефона?',
    position: [4704, 96],
    parameters: {
      conditions: {
        combinator: 'and',
        options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 1 },
        conditions: [
          {
            id: 'e1',
            leftValue: '={{ $json.pending }}',
            rightValue: 0,
            operator: { type: 'number', operation: 'gt' },
          },
        ],
      },
    },
  },
});

const postEnrichPhone = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'POST /enrich phone',
    position: [4928, 0],
    executeOnce: true,
    onError: 'continueRegularOutput',
    parameters: {
      method: 'POST',
      url: 'http://playwright-worker:8001/enrich',
      sendBody: true,
      specifyBody: 'json',
      jsonBody:
        '={{ JSON.stringify({ adapter: "myhome", phase: "phone", limit: $("Очередь обогащения").first().json.pending }) }}',
      options: { timeout: 10000 },
    },
  },
  output: [{ status: 'accepted' }],
});

const tgEnrichStarted = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Обогащение запущено',
    position: [5152, 0],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr(
        '=📞 <b>Обогащение телефонов запущено</b>\n⏳ В очереди: {{ $("Очередь обогащения").first().json.pending }} лидов\nРезультат — в Metabase',
      ),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: true }],
});

const waitEnrichInitial = node({
  type: 'n8n-nodes-base.wait',
  version: 1.1,
  config: {
    name: 'Wait enrich 480s',
    position: [5376, 0],
    parameters: { amount: 480 },
  },
  output: [{}],
});

const waitPollStatus = node({
  type: 'n8n-nodes-base.wait',
  version: 1.1,
  config: {
    name: 'Wait poll 30s',
    position: [5600, 0],
    parameters: { amount: 30 },
  },
  output: [{}],
});

const getWorkerStatus = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'GET /status',
    position: [5824, 0],
    executeOnce: true,
    parameters: {
      method: 'GET',
      url: 'http://playwright-worker:8001/status',
      options: {
        response: { response: { neverError: true } },
        timeout: 10000,
      },
    },
  },
  output: [{ status: 'idle', job: null, elapsed_seconds: null }],
});

const statusIdle = ifElse({
  version: 2.3,
  config: {
    name: 'Worker idle?',
    position: [6048, 0],
    parameters: {
      conditions: {
        combinator: 'and',
        options: { caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 1 },
        conditions: [
          {
            id: 's1',
            leftValue: '={{ $json.status }}',
            rightValue: 'idle',
            operator: { type: 'string', operation: 'equals' },
          },
        ],
      },
    },
  },
});

const enrichPollTimeout = ifElse({
  version: 2.3,
  config: {
    name: 'Poll timeout 3600s?',
    position: [6272, 96],
    parameters: {
      conditions: {
        combinator: 'and',
        options: { caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 1 },
        conditions: [
          {
            id: 't1',
            leftValue:
              '={{ $now.toMillis() - DateTime.fromISO($execution.startedAt).toMillis() }}',
            rightValue: 3600000,
            operator: { type: 'number', operation: 'gt' },
          },
        ],
      },
    },
  },
});

const tgEnrichPollTimeout = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Таймаут обогащения',
    position: [6496, 192],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr(
        '=⚠️ <b>Обогащение: таймаут 3600 с</b>\nWorker всё ещё {{ $json.status }}. Проверьте логи playwright-worker.',
      ),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: true }],
});

const sqlEnrichStats = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'SQL enrich stats',
    position: [6720, 0],
    executeOnce: true,
    alwaysOutputData: true,
    parameters: {
      operation: 'executeQuery',
      query:
        "SELECT\n  COUNT(*)::bigint AS total,\n  COUNT(*) FILTER (WHERE phone IS NOT NULL AND phone != '') AS with_phone,\n  COUNT(*) FILTER (WHERE (phone IS NULL OR phone='') AND phone_retries >= 3) AS failed,\n  COUNT(*) FILTER (WHERE (phone IS NULL OR phone='') AND phone_retries < 3) AS pending\nFROM leads WHERE source='myhome'",
      options: { connectionTimeout: 30 },
    },
    credentials: { postgres: newCredential('Postgres') },
  },
  output: [{ total: 10, with_phone: 5, failed: 1, pending: 4 }],
});

const tgEnrichDone = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Обогащение завершено',
    position: [6944, 0],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr(
        '=📞 Обогащение завершено\n✅ Получили телефон: {{ $json.with_phone }}\n❌ Не удалось: {{ $json.failed }}\n⏳ Осталось без телефона: {{ $json.pending }}\n🗄 Всего лидов в базе: {{ $json.total }}',
      ),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: true }],
});

const tgAllPhones = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Все телефоны есть',
    position: [4928, 192],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: '✅ <b>Все телефоны получены</b>\nОбогащение не требуется.',
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: true }],
});

const buildDisappeared = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Build disappeared',
    position: [7168, 96],
    executeOnce: true,
    parameters: {
      jsCode:
        'const snap = $("GET ids-snapshot").first().json;\nconst apiSet = new Set((snap.ids || []).map(id => String(id)));\nconst status = $("GET ids-snapshot/status").first().json;\nconst age = status.age_seconds;\nconst stale = age != null && Number(age) > 86400;\nconst dbItems = $("IDs new в БД").all();\nconst disappeared = dbItems\n  .map(i => String(i.json.external_id))\n  .filter(id => id && !apiSet.has(id));\nconst safe = disappeared.filter(id => /^[0-9]+$/.test(id));\nlet update_sql = null;\nif (!stale && safe.length > 0) {\n  const inList = safe.map(id => "\'" + id + "\'").join(",");\n  update_sql =\n    "UPDATE leads SET status=\'inactive\', status_reason=\'disappeared_from_api\', updated_at=now() "\n    + "WHERE source=\'myhome\' AND status=\'new\' AND external_id IN (" + inList + ")";\n}\nreturn [{ json: {\n  disappeared_count: safe.length,\n  stale,\n  skip_mark: stale || safe.length === 0,\n  update_sql\n}}];',
    },
  },
  output: [{ disappeared_count: 0, stale: false, skip_mark: true, update_sql: null }],
});

const hasMarkInactive = ifElse({
  version: 2.3,
  config: {
    name: 'Пометить inactive?',
    position: [7392, 96],
    parameters: {
      conditions: {
        combinator: 'and',
        options: { caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 1 },
        conditions: [
          {
            id: 'm1',
            leftValue: '={{ $json.skip_mark }}',
            rightValue: false,
            operator: { type: 'boolean', operation: 'equals' },
          },
        ],
      },
    },
  },
});

const sqlMarkInactive = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'SQL mark inactive',
    position: [7616, 0],
    executeOnce: true,
    parameters: {
      operation: 'executeQuery',
      query: '={{ $("Build disappeared").first().json.update_sql }}',
      options: { connectionTimeout: 30 },
    },
    credentials: { postgres: newCredential('Postgres') },
  },
  output: [{ ok: true }],
});

const tgDisappeared = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Исчезнувшие',
    position: [7840, 0],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr(
        '=📤 <b>Исчезнувшие</b>\nПомечено inactive: {{ $("Build disappeared").first().json.disappeared_count }}',
      ),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: true }],
});

const postRefreshSnapshot = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'POST refresh snapshot',
    position: [8064, 96],
    executeOnce: true,
    onError: 'continueRegularOutput',
    parameters: {
      method: 'POST',
      url: 'http://api:8000/api/myhome/ids-snapshot/refresh',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'X-API-Key', value: API_KEY }] },
      options: { timeout: 10000 },
    },
  },
  output: [{ status: 'accepted' }],
});

const finalizeSync = buildDisappeared.to(
  hasMarkInactive
    .onTrue(sqlMarkInactive.to(tgDisappeared.to(postRefreshSnapshot)))
    .onFalse(postRefreshSnapshot),
);

const loginFailed = ifElse({
  version: 2.3,
  config: {
    name: 'Логин упал?',
    position: [6272, 0],
    parameters: {
      conditions: {
        combinator: 'and',
        options: { caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 1 },
        conditions: [
          {
            id: 'lf1',
            leftValue: '={{ ($json.last_enrich?.phone_http_errors || []).some(e => String(e).startsWith("login_failed")) }}',
            rightValue: true,
            operator: { type: 'boolean', operation: 'equals' },
          },
        ],
      },
    },
  },
});

const tgLoginFailed = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Логин myhome упал',
    position: [6496, 0],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr(
        '=❌ <b>Логин myhome не удался</b>\nОбогащение телефонов пропущено.\nОшибка: <code>{{ ($json.last_enrich?.phone_http_errors || []).join(", ") }}</code>\n⏳ Pending: {{ $("Очередь обогащения").first().json.pending }} лидов',
      ),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: false }],
});

const enrichFromQueue = queuePending.to(
  hasPendingPhone
    .onTrue(
      postEnrichPhone.to(
        tgEnrichStarted.to(
          waitEnrichInitial.to(
            waitPollStatus.to(
              getWorkerStatus.to(
                statusIdle
                  .onTrue(
                    loginFailed
                      .onTrue(tgLoginFailed.to(finalizeSync))
                      .onFalse(sqlEnrichStats.to(tgEnrichDone.to(finalizeSync))),
                  )
                  .onFalse(
                    enrichPollTimeout
                      .onTrue(
                        tgEnrichPollTimeout.to(
                          sqlEnrichStats.to(tgEnrichDone.to(finalizeSync)),
                        ),
                      )
                      .onFalse(waitPollStatus),
                  ),
              ),
            ),
          ),
        ),
      ),
    )
    .onFalse(tgAllPhones.to(finalizeSync)),
);

const snapshotIngestChain = idsNewInDb.to(
  dedupIds.to(
    existingIds.to(
      filterNewIds.to(
        tgFetch.to(
          hasNewIds
            .onTrue(buildChunks.to(postIngest.to(aggregateResults.to(tgIngest.to(queuePending)))))
            .onFalse(queuePending),
        ),
      ),
    ),
  ),
);

const snapshotReadyChain = snapshotStale
  .onTrue(tgStaleWarning.to(getSnapshot.to(snapshotIngestChain)))
  .onFalse(getSnapshot.to(snapshotIngestChain));

export default workflow('yG1JxQnR6kX0Vlgt', 'PropRadar — myhome v7 chunked-ingest')
  .add(schedule0900)
  .to(tgStart)
  .add(manualStart)
  .to(tgStart)
  .add(tgStart)
  .to(testWorker)
  .to(
    workerOk
      .onTrue(
        getProxyCheck.to(
          proxyOk
            .onTrue(
              tgProxyOk.to(
                getSnapshotStatus.to(
                  snapshotReady.onTrue(snapshotReadyChain).onFalse(tgColdStart),
                ),
              ),
            )
            .onFalse(tgProxyFail),
        ),
      )
      .onFalse(tgWorkerFail),
  );
