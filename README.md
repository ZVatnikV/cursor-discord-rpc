<p align="center">
  <img src="https://img.shields.io/badge/Cursor-Discord_RPC-3dd6c6?style=for-the-badge&labelColor=0b0f14" alt="Cursor Discord RPC">
  <img src="https://img.shields.io/badge/platform-Windows-8b9bb0?style=for-the-badge&labelColor=0b0f14" alt="Windows">
  <img src="https://img.shields.io/github/v/release/ZVatnikV/cursor-discord-rpc?style=for-the-badge&labelColor=0b0f14&color=4ecf8a" alt="release">
</p>

<h1 align="center">Cursor Discord RPC</h1>

<p align="center">
  <b>EN</b> Beautiful Discord Rich Presence for Cursor IDE<br>
  <b>RU</b> Красивый Discord Rich Presence для Cursor IDE
</p>

<p align="center">
  <a href="https://github.com/ZVatnikV/cursor-discord-rpc/releases/latest"><b>⬇ Download EXE</b></a>
  ·
  <a href="#english">English</a>
  ·
  <a href="#русский">Русский</a>
</p>

---

## English

Shows what the AI is doing in your **focused chat**, plus the chat name and workspace.

| Discord field | Example |
|---|---|
| **details** | `Editing ui.py` / `Idle` / `Writing a prompt` |
| **state** | `Discord RPC program · cursor-discord-rpc` |
| button | [GitHub](https://github.com/ZVatnikV/cursor-discord-rpc) *(friends only)* |

### Activity states

- **Idle** — AI is not working
- **Writing a prompt** — you are typing (prompt text is never shown)
- **Editing / Reading / Running commands / Searching / Thinking / Replying**

### Install

1. Download [`CursorDiscordRPC.exe`](https://github.com/ZVatnikV/cursor-discord-rpc/releases/latest)
2. Run it — Discord Client ID is built-in (`1562085628630540318`)
3. Optional: upload an Art Asset named `cursor` in the [Discord Developer Portal](https://discord.com/developers/applications)

### Run from source

```powershell
pip install -r requirements.txt
python run.py
```

### Build EXE

```powershell
.\scripts\build_exe.ps1
```

---

## Русский

Показывает, что делает AI в **активном чате**, плюс название чата и workspace.

| Поле Discord | Пример |
|---|---|
| **details** | `Редактирует ui.py` / `Простой` / `Пишет промпт` |
| **state** | `Discord RPC program · cursor-discord-rpc` |
| кнопка | [GitHub](https://github.com/ZVatnikV/cursor-discord-rpc) *(только друзьям)* |

### Состояния активности

- **Простой** — AI ничего не делает
- **Пишет промпт** — пользователь набирает текст (сам текст не показывается)
- **Редактирует / Читает / Выполняет команды / Ищет / Думает / Отвечает**

### Установка

1. Скачай [`CursorDiscordRPC.exe`](https://github.com/ZVatnikV/cursor-discord-rpc/releases/latest)
2. Запусти — Discord Client ID уже вшит (`1562085628630540318`)
3. Опционально: загрузи Art Asset с ключом `cursor` в [Discord Developer Portal](https://discord.com/developers/applications)

### Запуск из исходников

```powershell
pip install -r requirements.txt
python run.py
```

### Сборка EXE

```powershell
.\scripts\build_exe.ps1
```

В приложении можно переключить язык **RU / EN**.

---

## License / Лицензия

MIT © ZVatnikV
