<p align="center">
  <img src="assets/banner.png" alt="Cursor Discord RPC" width="100%">
</p>

<h1 align="center">Cursor Discord RPC</h1>

<p align="center">
  Простой Discord Rich Presence для Cursor — один EXE, минимум настроек.
</p>

<p align="center">
  <img alt="platform" src="https://img.shields.io/badge/platform-Windows-0b0f14?style=flat-square">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-8b9bb0?style=flat-square&labelColor=0b0f14">
</p>

## Как выглядит

Discord официально даёт **только 2 строки**:

| Поле | Пример |
|------|--------|
| details | `Редактирует файл · rpc_client.py` |
| state | `Создай прогу для RPC… · cursor discord rpc` |

+ таймер + кнопка GitHub (**кнопку видят только другие**, не ты сам — ограничение Discord).

## Установка

1. Скачай [CursorDiscordRPC.exe](https://gitlab.com/artembucka382/cursor-discord-rpc/-/releases)
2. Закрой старые копии (трей → Выход)
3. Запусти EXE — Client ID уже вшит
4. *(Опционально)* в [Developer Portal](https://discord.com/developers/applications) у приложения загрузи Art Asset с ключом `cursor`

## Настройки

- Вкл/выкл RPC одной кнопкой
- Файл / чат / проект / таймер / кнопка / автозапуск
- Трей: настройки, отключить, выход

## Сборка

```powershell
.\scripts\build_exe.ps1
```

## Лицензия

MIT
