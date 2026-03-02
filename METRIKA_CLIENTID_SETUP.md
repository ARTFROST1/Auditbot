# Передача Яндекс.Метрика ClientId в Telegram-бот через Deep Link

## Содержание

1. [Как это работает](#1-как-это-работает)
2. [Получение ClientId через JavaScript](#2-получение-clientid-через-javascript)
3. [Реализация кнопки на сайте](#3-реализация-кнопки-на-сайте)
4. [Альтернатива — кука `_ym_uid`](#4-альтернатива--кука-_ym_uid)
5. [Проверка и отладка](#5-проверка-и-отладка)
6. [Важные ограничения Яндекс.Метрики](#6-важные-ограничения-яндексметрики)

---

## 1. Как это работает

### Схема потока данных

```
Пользователь заходит на сайт
        │
        ▼
Яндекс.Метрика присваивает ClientId (хранится в куке _ym_uid)
        │
        ▼
Пользователь нажимает кнопку «Написать в Telegram»
        │
        ▼
JavaScript читает ClientId из счётчика Метрики
        │
        ▼
JS строит deep link: https://t.me/ВАШ_БОТ?start=cid_XXXXXXXX
        │
        ▼
Браузер открывает Telegram (приложение или веб)
        │
        ▼
Бот получает команду /start с параметром cid_XXXXXXXX
        │
        ▼
Бот парсит ClientId и сохраняет его в базу данных
        │
        ▼
При отправке оффлайн-конверсии — бот передаёт ClientId в Метрику
через Management API (метод offline-conversions/upload)
```

### Зачем это нужно

Яндекс.Метрика умеет принимать **оффлайн-конверсии** — события, которые произошли вне сайта (например, заявка через Telegram-бот, звонок, оплата). Чтобы Метрика смогла привязать конверсию к конкретному визиту и источнику трафика, нужен **ClientId** — уникальный идентификатор браузерной сессии, который Метрика присваивает каждому посетителю.

Без ClientId невозможно узнать, с какого рекламного канала (Директ, SEO, соцсети) пришёл пользователь, который написал в бот.

---

## 2. Получение ClientId через JavaScript

Яндекс.Метрика предоставляет два способа получить ClientId на стороне JavaScript.

### Способ 1: Через колбэк `getClientID` (рекомендуемый)

Это **асинхронный** метод. Метрика гарантирует, что ClientId будет передан в колбэк после инициализации счётчика.

```javascript
// COUNTER_ID — числовой ID вашего счётчика Метрики, например 12345678
ym(COUNTER_ID, 'getClientID', function(clientId) {
    console.log('ClientId из Метрики:', clientId);
    // clientId — строка вида "1234567890123456"
    // Здесь строим deep link и открываем Telegram
});
```

**Преимущества:**
- Работает всегда, когда счётчик загружен
- Не зависит от времени загрузки страницы
- Официальный поддерживаемый метод

**Когда использовать:** при клике на кнопку, когда счётчик точно уже загружен.

---

### Способ 2: Через куку `_ym_uid` (запасной)

Это **синхронный** метод. Метрика сохраняет ClientId в куку `_ym_uid` при первом визите.

```javascript
function getClientIdFromCookie() {
    const match = document.cookie.match(/_ym_uid=([^;]+)/);
    return match ? match[1] : null;
}

const clientId = getClientIdFromCookie();
console.log('ClientId из куки:', clientId);
```

**Ограничения:**
- Кука может не появиться, если скрипт Метрики ещё не загрузился
- Не работает при заблокированных куках (редко, но бывает)
- Может отличаться от официального ClientId в редких случаях

**Когда использовать:** как запасной вариант, если `getClientID` недоступен.

---

## 3. Реализация кнопки на сайте

### HTML-структура кнопки

```html
<!-- Кнопка открытия Telegram-бота -->
<button id="tg-open-btn" class="btn-telegram">
    Написать в Telegram
</button>
```

### JavaScript — основной код

Вставьте этот скрипт **после** кода счётчика Метрики на странице:

```html
<script>
(function() {
    // ======================================================
    // НАСТРОЙКИ — измените под ваш проект
    // ======================================================
    var COUNTER_ID = 12345678;          // ID счётчика Метрики (число)
    var BOT_USERNAME = 'ВАШ_БОТ';      // Имя бота без @, например AuditDirectBot
    var BUTTON_ID = 'tg-open-btn';     // ID кнопки на странице
    // ======================================================

    /**
     * Читает ClientId из куки _ym_uid как запасной вариант
     */
    function getClientIdFromCookie() {
        var match = document.cookie.match(/_ym_uid=([^;]+)/);
        return match ? match[1] : null;
    }

    /**
     * Строит Telegram deep link с ClientId
     * @param {string|null} clientId
     * @returns {string}
     */
    function buildTelegramLink(clientId) {
        var base = 'https://t.me/' + BOT_USERNAME;
        if (clientId) {
            return base + '?start=cid_' + clientId;
        }
        return base;
    }

    /**
     * Открывает Telegram-бот с ClientId из Метрики
     */
    function openTelegramBot() {
        // Проверяем, доступна ли функция ym (счётчик загружен)
        if (typeof ym === 'function') {
            ym(COUNTER_ID, 'getClientID', function(clientId) {
                var link = buildTelegramLink(clientId);
                console.log('[TG Bot] Открываем ссылку:', link);
                window.open(link, '_blank');
            });
        } else {
            // Запасной вариант: читаем из куки
            var clientId = getClientIdFromCookie();
            var link = buildTelegramLink(clientId);
            console.warn('[TG Bot] Счётчик Метрики не найден, используем куку. Ссылка:', link);
            window.open(link, '_blank');
        }
    }

    // Вешаем обработчик после загрузки DOM
    document.addEventListener('DOMContentLoaded', function() {
        var btn = document.getElementById(BUTTON_ID);
        if (btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                openTelegramBot();
            });
        } else {
            console.error('[TG Bot] Кнопка с ID "' + BUTTON_ID + '" не найдена на странице');
        }
    });
})();
</script>
```

### Полный пример HTML-страницы

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Моя страница</title>
</head>
<body>

    <!-- Контент страницы -->
    <h1>Получите бесплатный аудит рекламы</h1>
    <p>Напишите нам в Telegram — ответим в течение часа.</p>

    <!-- Кнопка открытия бота -->
    <button id="tg-open-btn" style="
        background-color: #0088cc;
        color: white;
        border: none;
        padding: 14px 28px;
        font-size: 16px;
        border-radius: 8px;
        cursor: pointer;
    ">
        ✈ Написать в Telegram
    </button>

    <!-- Счётчик Яндекс.Метрики (стандартный код) -->
    <!-- ЗАМЕНИТЕ 12345678 на ваш реальный ID счётчика -->
    <script type="text/javascript">
        (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
        m[i].l=1*new Date();
        for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
        (window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");

        ym(12345678, "init", {
            clickmap: true,
            trackLinks: true,
            accurateTrackBounce: true
        });
    </script>
    <noscript>
        <div><img src="https://mc.yandex.ru/watch/12345678" style="position:absolute; left:-9999px;" alt="" /></div>
    </noscript>

    <!-- Скрипт кнопки — вставить ПОСЛЕ кода Метрики -->
    <script>
    (function() {
        var COUNTER_ID = 12345678;       // ← ваш ID счётчика
        var BOT_USERNAME = 'ВАШ_БОТ';   // ← имя вашего бота без @
        var BUTTON_ID = 'tg-open-btn';

        function getClientIdFromCookie() {
            var match = document.cookie.match(/_ym_uid=([^;]+)/);
            return match ? match[1] : null;
        }

        function buildTelegramLink(clientId) {
            var base = 'https://t.me/' + BOT_USERNAME;
            if (clientId) {
                return base + '?start=cid_' + clientId;
            }
            return base;
        }

        function openTelegramBot() {
            if (typeof ym === 'function') {
                ym(COUNTER_ID, 'getClientID', function(clientId) {
                    window.open(buildTelegramLink(clientId), '_blank');
                });
            } else {
                var clientId = getClientIdFromCookie();
                window.open(buildTelegramLink(clientId), '_blank');
            }
        }

        document.addEventListener('DOMContentLoaded', function() {
            var btn = document.getElementById(BUTTON_ID);
            if (btn) {
                btn.addEventListener('click', function(e) {
                    e.preventDefault();
                    openTelegramBot();
                });
            }
        });
    })();
    </script>

</body>
</html>
```

### Как работает deep link в Telegram

Формат ссылки: `https://t.me/ВАШ_БОТ?start=cid_XXXXXXXXXXXXXXXX`

- `cid_` — префикс, по которому бот определяет, что это ClientId
- `XXXXXXXXXXXXXXXX` — числовой ClientId (обычно 16 цифр)

Когда пользователь переходит по ссылке и нажимает «START» в боте, Telegram отправляет боту команду:
```
/start cid_1234567890123456
```

Бот парсит параметр и извлекает ClientId:
```python
# Пример парсинга в боте (Python, aiogram/python-telegram-bot)
async def start_handler(message: Message):
    args = message.text.split()
    client_id = None
    if len(args) > 1 and args[1].startswith('cid_'):
        client_id = args[1].replace('cid_', '')
        logger.info(f"ClientId из deep-link получен: {client_id}")
    # ... сохраняем client_id в БД
```

---

## 4. Альтернатива — кука `_ym_uid`

Если по каким-то причинам объект `ym` недоступен (счётчик заблокирован, загружается позже), можно читать ClientId напрямую из куки `_ym_uid`.

```javascript
function getYmClientId() {
    // Вариант 1: Через API Метрики (рекомендуется)
    if (typeof ym === 'function') {
        return new Promise(function(resolve) {
            ym(12345678, 'getClientID', resolve);
        });
    }

    // Вариант 2: Из куки (запасной)
    var match = document.cookie.match(/_ym_uid=([^;]+)/);
    var cookieId = match ? match[1] : null;
    return Promise.resolve(cookieId);
}

// Использование:
getYmClientId().then(function(clientId) {
    if (clientId) {
        console.log('ClientId:', clientId);
    } else {
        console.warn('ClientId недоступен — счётчик заблокирован или кука удалена');
    }
});
```

**Важно:** Значение куки `_ym_uid` совпадает с ClientId, но Яндекс официально рекомендует использовать метод `getClientID`. Кука — только запасной вариант.

**Почему кука менее надёжна:**
- Пользователь мог очистить куки после визита — тогда `_ym_uid` будет новым, а старые визиты останутся под прежним ClientId
- Некоторые браузеры (Safari ITP) ограничивают срок жизни кук, установленных JS

---

## 5. Проверка и отладка

### Шаг 1: Проверка передачи ClientId в браузере

1. Откройте страницу с кнопкой
2. Откройте DevTools (F12) → вкладка **Console**
3. Выполните вручную:
   ```javascript
   ym(12345678, 'getClientID', function(id) { console.log('ClientId:', id); });
   ```
4. Должно вывести строку вида:
   ```
   ClientId: 1234567890123456
   ```

5. Нажмите кнопку — в консоли должна появиться ссылка:
   ```
   [TG Bot] Открываем ссылку: https://t.me/ВАШ_БОТ?start=cid_1234567890123456
   ```

### Шаг 2: Проверка в боте

После перехода по deep link и нажатия START — посмотрите логи бота. Должна появиться запись:
```
INFO     ClientId из deep-link получен: 1234567890123456
```

Если бот сохраняет данные в БД — убедитесь, что в таблице пользователей поле `client_id` заполнено.

### Шаг 3: Проверка в Яндекс.Метрике

1. Откройте **Яндекс.Метрика** → ваш счётчик
2. Перейдите: **Настройки → Загрузка данных → Офлайн-конверсии**
3. В разделе «История загрузок» найдите последнюю загрузку
4. Статус должен быть **«Обработано»**, а не «Ошибка»

Если видите ошибки — выгрузите отчёт об ошибках (кнопка в интерфейсе) и посмотрите, какие ClientId отклонены.

### Частые ошибки и решения

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `ym is not defined` | Счётчик Метрики не загружен | Убедитесь, что код Метрики вставлен до скрипта кнопки |
| ClientId = `null` в консоли | `getClientID` вернул пустое значение | Проверьте правильность COUNTER_ID; дождитесь загрузки страницы |
| Бот не парсит ClientId | Параметр `start` не содержит `cid_` | Проверьте URL в консоли браузера — возможно префикс потерялся |
| Конверсии с ошибкой `CLIENT_ID_NOT_FOUND` | ClientId не найден в базе Метрики | Пользователь должен был посетить сайт со счётчиком; ClientId не может быть взят «из воздуха» |
| Конверсии не появляются в отчётах | Данные ещё не обработаны | Подождите 2–3 часа после загрузки |
| Deep link открывает веб-версию, а не приложение | Поведение Telegram на iOS/Android | Нормально, пользователь перенаправится в приложение |
| Блокировщик рекламы блокирует Метрику | Счётчик не инициализируется | Используйте запасной вариант через куку `_ym_uid` |

### Отладка с помощью DevTools Network

Если хотите убедиться, что Метрика получает хиты:

1. DevTools → вкладка **Network**
2. Отфильтруйте по `mc.yandex.ru`
3. Обновите страницу — должны появиться запросы к `https://mc.yandex.ru/watch/COUNTER_ID`

---

## 6. Важные ограничения Яндекс.Метрики

### Ограничение 1: ClientId должен существовать в Метрике

Оффлайн-конверсия будет принята **только если** пользователь с данным ClientId ранее посещал ваш сайт со счётчиком. Если передать произвольное число — Метрика вернёт ошибку `CLIENT_ID_NOT_FOUND`.

**Вывод:** бот не должен отправлять конверсию, если ClientId не был получен из deep link. Это нормальное поведение.

### Ограничение 2: Задержка обработки данных

После загрузки оффлайн-конверсий через API данные появляются в отчётах **через 2–3 часа**. Не ждите мгновенного результата.

### Ограничение 3: DateTime должен быть в прошлом

При отправке конверсии поле `DateTime` (Unix timestamp) должно указывать на момент в **прошлом**. Время конверсии, которое позже текущего момента, будет отклонено.

```python
import time

# Правильно: текущее время минус несколько секунд
conversion_time = int(time.time()) - 5

# Неправильно: время в будущем
# conversion_time = int(time.time()) + 3600  ← ошибка
```

### Ограничение 4: Формат загрузки конверсий

Метрика Management API принимает конверсии в формате CSV или JSON через метод `offline-conversions/upload`. Минимально необходимые поля:

| Поле | Описание | Пример |
|------|----------|--------|
| `ClientId` | ID браузерной сессии из Метрики | `1234567890123456` |
| `Target` | Идентификатор цели (из настроек счётчика) | `telegram_lead` |
| `DateTime` | Unix timestamp конверсии | `1740000000` |
| `Price` | Ценность конверсии (необязательно) | `0` |

### Ограничение 5: Если ClientId не передан — конверсия не отправляется

Это **намеренное поведение бота**: если пользователь написал в бот напрямую (не через deep link с сайта), то ClientId неизвестен и отправлять конверсию бессмысленно — она всё равно будет отклонена Метрикой.

В логах бота это выглядит так:
```
INFO  Пользователь 987654321 написал без ClientId — конверсия не отправляется
```

---

## Итоговый чеклист для веб-разработчика

- [ ] Счётчик Яндекс.Метрики установлен на странице с кнопкой
- [ ] ID счётчика (`COUNTER_ID`) прописан в скрипте кнопки
- [ ] Имя бота (`BOT_USERNAME`) прописано без символа `@`
- [ ] Скрипт кнопки вставлен **после** кода счётчика Метрики
- [ ] В консоли браузера `getClientID` возвращает непустое значение
- [ ] При клике на кнопку в консоли отображается корректная ссылка с `cid_`
- [ ] Переход по ссылке в боте → бот логирует полученный ClientId
- [ ] Тестовая конверсия отправлена и отображается в Метрике без ошибок
