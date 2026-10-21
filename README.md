# Cursor Discord RPC

Красивый Discord Rich Presence для Cursor IDE.

## Что видно в Discord

| Поле | Пример |
|------|--------|
| **details** | `Редактирует ui.py` |
| **state** | `Сделай RPC для Cursor… · cursor discord rpc` |
| кнопка | [GitHub](https://github.com/ZVatnikV/cursor-discord-rpc) |

Кнопку видят только друзья — ограничение Discord.

## Установка

1. Скачай [CursorDiscordRPC.exe](https://github.com/ZVatnikV/cursor-discord-rpc/releases/latest)
2. Запусти — Discord Client ID уже вшит
3. *(Опционально)* загрузи Art Asset с ключом `cursor` в [Developer Portal](https://discord.com/developers/applications)

## Запуск из исходников

```powershell
pip install -r requirements.txt
python run.py
```

## Сборка EXE

```powershell
.\scripts\build_exe.ps1
```

## Лицензия

MIT
