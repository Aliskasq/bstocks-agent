# Установка на VPS — по шагам

Инструкция для чистого сервера Ubuntu/Debian. Копируй команды по одной.

Значок `$` писать не надо — это просто приглашение терминала.

---

## Шаг 0. Подключиться к серверу

Со своего компьютера:

```bash
ssh root@ТВОЙ_IP
```

Если пользователь не root — подставь своё имя. Дальше все команды выполняются
уже **на сервере**.

---

## Шаг 1. Обновить систему и поставить нужные пакеты

```bash
apt update
apt install -y python3 python3-pip python3-venv git
```

Почему `python3-venv` отдельно: на Ubuntu он не входит в python3, и без него
следующий шаг падает с ошибкой «ensurepip is not available». Я это проверил.

Если ты не root, добавляй `sudo` в начало: `sudo apt update` и т.д.

Проверка:

```bash
python3 --version    # должно быть 3.10 или выше
git --version
```

---

## Шаг 2. Скачать проект с GitHub

```bash
cd /opt
git clone https://github.com/Aliskasq/bstocks-agent.git
cd bstocks-agent
```

Теперь ты внутри папки проекта. Проверка — должны увидеть `app`, `frontend`,
`requirements.txt`:

```bash
ls
```

Репозиторий публичный, пароль не спросит.

---

## Шаг 3. Создать виртуальное окружение

Это отдельная песочница для библиотек, чтобы не сломать системный Python.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

После второй команды в начале строки появится `(.venv)`. Это значит, что
окружение включено.

Важно: `(.venv)` пропадает при новом заходе по SSH. Тогда снова:
`cd /opt/bstocks-agent && source .venv/bin/activate`

---

## Шаг 4. Установить библиотеки

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Проверка:

```bash
python -c "import fastapi, uvicorn, httpx; print('всё на месте')"
```

---

## Шаг 5. Создать файл настроек `.env`

```bash
cp .env.example .env
nano .env
```

Откроется простой редактор. Нужно заполнить две строки:

```
OPENROUTER_API_KEY=sk-or-v1-твой_ключ
BINANCE_OAUTH_CLIENT_ID=https://aliskasq.github.io/bstocks-agent/oauth-client.json
```

Ключ OpenRouter берётся на https://openrouter.ai/keys

Как выйти из nano: `Ctrl+O`, затем `Enter` (сохранить), потом `Ctrl+X` (выйти).

Проверка, что ключ подхватился:

```bash
python -c "from app.config import OPENROUTER_API_KEY as k; print('ключ найден' if k else 'ПУСТО')"
```

`.env` в `.gitignore` — он никогда не попадёт на GitHub. Так и должно быть.

---

## Шаг 6. Запустить и проверить, что работает

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Должна появиться строка `Uvicorn running on http://127.0.0.1:8000`.

Оставь это окно как есть и проверь из **второго** SSH-окна:

```bash
curl -s http://127.0.0.1:8000/api/state
```

Если вернулся JSON — сервер живой. Остановить: `Ctrl+C` в первом окне.

---

## Шаг 7. Посмотреть дашборд в браузере

Сервер слушает только сам себя (`127.0.0.1`), наружу он не открыт — это
намеренно, дашборд пока без пароля. Пробрось порт со своего компьютера:

```bash
# выполнять НА СВОЁМ компьютере, не на сервере
ssh -L 8000:127.0.0.1:8000 root@ТВОЙ_IP
```

Не закрывая это окно, открой в браузере: http://localhost:8000

Увидишь дашборд. В карточке «Model» выбери бесплатную модель — тогда клацание
кнопок не тратит платные токены.

---

## Шаг 8. Логин в Binance Agent OS

На сервере (с включённым `.venv`):

```bash
python3 -m app.cli_auth login-manual "market:read"
```

1. Скрипт напечатает длинную ссылку — открой её в браузере на своём телефоне
   или ноутбуке, войди в Binance, подтверди доступ.
2. Браузер попробует перейти на `http://127.0.0.1:8765/callback?code=...` и
   покажет **ошибку «сайт недоступен» — это нормально и ожидаемо**.
3. Скопируй **всю строку из адресной строки браузера** и вставь в терминал.
4. Нажми Enter.

Проверка:

```bash
python3 -m app.cli_auth status   # has_token: true
python3 -m app.cli_auth tools    # список инструментов Binance
```

Код из ссылки живёт около минуты и одноразовый. Замешкалась — просто запусти
команду заново.

---

## Шаг 9. Сделать так, чтобы работало постоянно

Пока ты запускаешь вручную, всё умирает при закрытии SSH. Systemd это исправит.

```bash
cat > /etc/systemd/system/bstocks.service <<'EOF'
[Unit]
Description=bStocks AI Agent
After=network.target

[Service]
WorkingDirectory=/opt/bstocks-agent
ExecStart=/opt/bstocks-agent/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now bstocks
systemctl status bstocks --no-pager
```

Полезные команды на будущее:

```bash
systemctl restart bstocks       # перезапустить
systemctl stop bstocks          # остановить
journalctl -u bstocks -f        # смотреть логи живьём
```

---

## Обновить проект, когда я что-то поменяю

```bash
cd /opt/bstocks-agent
git pull
source .venv/bin/activate
pip install -r requirements.txt
systemctl restart bstocks
```

`git pull` не тронет твой `.env` и токен — они не в репозитории.

---

## Если что-то не так

| Симптом | Причина и лечение |
|---|---|
| `ensurepip is not available` | `apt install -y python3-venv`, потом заново шаг 3 |
| `ModuleNotFoundError: fastapi` | не включён venv → `source .venv/bin/activate` |
| `OPENROUTER_API_KEY is not set` | пустой или неверный `.env`, см. шаг 5 |
| `HTTP 429` в логах | бесплатная модель занята; агент сам подождёт и переключится |
| `command not found: git` | шаг 1 не выполнен |
| `Address already in use` | порт занят: `fuser -k 8000/tcp` |
| Дашборд не открывается | не запущен туннель из шага 7 |
| `no token stored` | шаг 8 не пройден |

Не пиши ключи и токены в чат — если нужно проверить, присылай только текст ошибки.
