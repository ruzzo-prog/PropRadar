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

const tgWorkerOk = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Воркер OK',
    position: [896, 96],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: '🔌 <b>Воркер:</b> ✅ доступен\n▶️ Запускаем парсинг...',
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: true }],
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

const fetchIds = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Fetch IDs myhome',
    position: [1120, 96],
    executeOnce: true,
    alwaysOutputData: true,
    parameters: {
      method: 'GET',
      url: 'http://api:8000/api/myhome/fetch-ids?city=tbilisi&category=apartment&seller_type=private&object_type=apartment&limit=650',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'X-API-Key', value: API_KEY }] },
      options: { timeout: 30000 },
    },
  },
  output: [{ id: '12345' }],
});

const dedupIds = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Дедупликация IDs',
    position: [1344, 96],
    executeOnce: true,
    parameters: {
      jsCode:
        'const apiItems = $items("Fetch IDs myhome");\nconst apiIds = apiItems.map(i => String(i.json));\nreturn [{ json: { api_ids: apiIds, total_api: apiIds.length } }];',
    },
  },
  output: [{ api_ids: ['1'], total_api: 1 }],
});

const existingIds = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'Существующие IDs в БД',
    position: [1568, 96],
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
    position: [1792, 96],
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
    position: [2016, 96],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr(
        '=📊 <b>Fetch IDs</b>\n🔢 API вернул: {{ $json.total_api }}\n🗄 В базе: {{ $json.existing_count }}\n✨ Новых: {{ $json.new_count }}',
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
    position: [2240, 96],
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

const buildIngest = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Build Ingest Body',
    position: [2464, 32],
    executeOnce: true,
    parameters: {
      jsCode:
        'const ids = $("Фильтр новых IDs").first().json.new_ids;\nreturn [{ json: { ids } }];',
    },
  },
  output: [{ ids: ['99'] }],
});

const postIngest = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'POST /ingest',
    position: [2688, 32],
    executeOnce: true,
    onError: 'continueRegularOutput',
    parameters: {
      method: 'POST',
      url: 'http://api:8000/api/myhome/ingest',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'X-API-Key', value: API_KEY }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: '={{ JSON.stringify({ ids: $json.ids }) }}',
      options: { timeout: 300000 },
    },
  },
  output: [{ parsed: 1, new: 1, errors: [] }],
});

const tgIngest = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Ingest результат',
    position: [2912, 32],
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
    position: [3136, 96],
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
    position: [3360, 96],
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

const getProxyCheck = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'GET /proxy/check',
    position: [3584, 0],
    executeOnce: true,
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
    position: [3808, 0],
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

const tgProxyOk = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Прокси OK',
    position: [4032, -96],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr(
        '={{ $json.skipped ? "ℹ️ <b>Прокси не настроен</b>, enrich продолжается" : "✅ <b>Прокси работает</b> (IP: " + $json.ip + ")" }}',
      ),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: true }],
});

const tgProxyFail = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'TG: Прокси недоступен',
    position: [4032, 96],
    executeOnce: true,
    parameters: {
      chatId: CHAT,
      text: expr('=❌ <b>Прокси недоступен:</b> {{ $json.reason }}. Обогащение остановлено.'),
      additionalFields: { appendAttribution: false, parse_mode: 'HTML' },
    },
    credentials: { telegramApi: newCredential('Telegram') },
  },
  output: [{ ok: false }],
});

const postEnrichPhone = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'POST /enrich phone',
    position: [4256, 0],
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
    position: [4480, 0],
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
    position: [4704, 0],
    parameters: { amount: 480 },
  },
  output: [{}],
});

const waitPollStatus = node({
  type: 'n8n-nodes-base.wait',
  version: 1.1,
  config: {
    name: 'Wait poll 30s',
    position: [4928, 0],
    parameters: { amount: 30 },
  },
  output: [{}],
});

const getWorkerStatus = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'GET /status',
    position: [5152, 0],
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
    position: [5376, 0],
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
    position: [5600, 96],
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
    position: [5824, 192],
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
    position: [6048, 0],
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
    position: [6272, 0],
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
    position: [3584, 192],
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

const ingestToQueue = tgIngest.to(queuePending);

export default workflow('yG1JxQnR6kX0Vlgt', 'PropRadar — myhome v4')
  .add(schedule0900)
  .to(tgStart)
  .add(manualStart)
  .to(tgStart)
  .add(tgStart)
  .to(testWorker)
  .to(
    workerOk
      .onTrue(
        tgWorkerOk.to(
          fetchIds.to(
            dedupIds.to(
              existingIds.to(
                filterNewIds.to(
                  tgFetch.to(
                    hasNewIds
                      .onTrue(buildIngest.to(postIngest.to(ingestToQueue)))
                      .onFalse(queuePending),
                  ),
                ),
              ),
            ),
          ),
        ),
      )
      .onFalse(tgWorkerFail),
  )
  .add(queuePending)
  .to(
    hasPendingPhone
      .onTrue(
        getProxyCheck.to(
          proxyOk
            .onTrue(
              tgProxyOk.to(
                postEnrichPhone.to(
                  tgEnrichStarted.to(
                    waitEnrichInitial.to(
                      waitPollStatus.to(
                        getWorkerStatus.to(
                          statusIdle
                            .onTrue(sqlEnrichStats.to(tgEnrichDone))
                            .onFalse(
                              enrichPollTimeout
                                .onTrue(
                                  tgEnrichPollTimeout.to(sqlEnrichStats.to(tgEnrichDone)),
                                )
                                .onFalse(waitPollStatus),
                            ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            )
            .onFalse(tgProxyFail),
        ),
      )
      .onFalse(tgAllPhones),
  );
