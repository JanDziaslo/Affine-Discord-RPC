# AFFiNE Discord RPC

Osobna aplikacja Python, która wyświetla [Discord Rich Presence](https://discord.com/rich-presence) podczas korzystania z [AFFiNE](https://affine.pro/) na Linuksie (testowane na EndeavourOS / KDE Plasma Wayland).

```
Discord pokazuje:
  📝 Moja notatka          ← tytuł aktywnego dokumentu
  Edytowanie notatek       ← status
  [logo AFFiNE]  AFFiNE    ← obraz + czas od uruchomienia
```

---

## Wymagania

- Python 3.10+
- AFFiNE (wersja stable, zainstalowana jako AppImage lub `.deb`)
- Discord (aplikacja desktopowa uruchomiona w tle)
- `xdotool` **lub** `wmctrl` — do odczytu tytułu okna

```bash
sudo pacman -S xdotool   # zalecane
```

> **KDE Plasma Wayland:** AFFiNE (Electron) domyślnie działa przez XWayland,
> więc `xdotool` działa bez żadnych dodatkowych ustawień.
> Jeśli uruchamiasz AFFiNE z flagą `--ozone-platform=wayland`,
> skrypt spróbuje użyć KWin D-Bus jako fallbacku.

---

## Krok 1 — Utwórz Discord Application i zdobądź Client ID

1. Otwórz [discord.com/developers/applications](https://discord.com/developers/applications)
2. Kliknij **New Application** → wpisz nazwę (np. `AFFiNE`) → **Create**
3. Skopiuj **Application ID** z sekcji *General Information*
4. Wklej go do `config.yaml` jako `client_id`

## Krok 2 — Utwórz Bot Token (do auto-uploadu logo)

1. W tej samej aplikacji: zakładka **Bot** → **Add Bot** → **Yes, do it!**
2. Kliknij **Reset Token** → skopiuj token
3. Wklej go do `config.yaml` jako `bot_token`

> Token jest potrzebny **tylko raz** — przy pierwszym uruchomieniu skrypt
> automatycznie uploaduje `affine.webp` jako asset do Twojej aplikacji Discord
> i zapisuje flagę w `~/.cache/affine-discord-rpc/asset_uploaded`.
> Przy kolejnych startach token nie jest używany.

---

## Instalacja

```bash
# 1. Sklonuj repozytorium
git clone https://github.com/twoj-nick/Affine-Discord-RPC.git
cd Affine-Discord-RPC

# 2. Uzupełnij config.yaml
nano config.yaml   # wpisz client_id i bot_token

# 3. Uruchom instalator
chmod +x install.sh
./install.sh
```

Instalator:
- tworzy środowisko wirtualne Python w `.venv/`
- instaluje zależności (`pypresence`, `psutil`, itp.)
- tworzy i włącza **systemd user service** (auto-start po zalogowaniu)

### Zarządzanie serwisem

```bash
systemctl --user status  affine-discord-rpc.service   # stan
systemctl --user restart affine-discord-rpc.service   # restart
systemctl --user stop    affine-discord-rpc.service   # zatrzymanie
journalctl --user -u affine-discord-rpc.service -f    # logi na żywo
```

### Uruchomienie ręczne (testowanie)

```bash
.venv/bin/python -m affine_rpc.main
```

---

## Konfiguracja (`config.yaml`)

| Klucz | Opis | Domyślnie |
|---|---|---|
| `client_id` | Discord Application ID | **wymagane** |
| `bot_token` | Discord Bot Token (jednorazowy upload logo) | **wymagane** |
| `poll_interval` | Jak często sprawdzać stan AFFiNE (sekundy) | `5` |
| `large_image_key` | Nazwa assetu obrazu w Discord | `affine` |
| `details_prefix` | Prefiks przed tytułem dokumentu | `📝` |
| `state_text` | Tekst statusu gdy dokument jest otwarty | `Edytowanie notatek` |
| `idle_text` | Tekst gdy AFFiNE otwarte bez wykrytego dokumentu | `Otwarte` |

---

## Jak to działa

```
AFFiNE (Electron/XWayland)
        │
        │  xdotool / wmctrl / KWin D-Bus
        ▼
[affine_rpc/monitor.py]  — wykrywa proces, odczytuje tytuł okna
        │
        │  parsuje "Dokument · AFFiNE" → "Dokument"
        ▼
[affine_rpc/rpc.py]      — pypresence → Discord IPC socket
        │                  (~/.run/user/1000/discord-ipc-0)
        ▼
   Discord Client         — wyświetla Rich Presence
```

Przy starcie `rpc.py` sprawdza przez Discord REST API czy asset `affine`
już istnieje. Jeśli nie — uploaduje `affine.webp` automatycznie (wymaga `bot_token`).

---

## Rozwiązywanie problemów

**Discord nie pokazuje presence:**
- Upewnij się że Discord jest uruchomiony
- Sprawdź logi: `journalctl --user -u affine-discord-rpc.service -f`
- Upewnij się że `client_id` w `config.yaml` jest poprawny

**Logo nie zostało uploadowane:**
- Sprawdź czy `bot_token` jest poprawny i czy bot jest dodany do aplikacji
- Usuń flagę i uruchom ponownie: `rm ~/.cache/affine-discord-rpc/asset_uploaded`

**Tytuł dokumentu nie jest wykrywany:**
- Zainstaluj `xdotool`: `sudo pacman -S xdotool`
- Jeśli AFFiNE działa w trybie natywnego Wayland: usuń flagę `--ozone-platform=wayland`
  z uruchomienia AFFiNE (XWayland działa lepiej z tym skryptem)

**Serwis się nie startuje:**
- `systemctl --user status affine-discord-rpc.service`
- Sprawdź czy `graphical-session.target` jest aktywny po zalogowaniu

---

## Struktura projektu

```
Affine-Discord-RPC/
├── affine_rpc/
│   ├── __init__.py
│   ├── config.py    # ładowanie i walidacja config.yaml
│   ├── monitor.py   # detekcja procesu + odczyt tytułu okna
│   ├── rpc.py       # pypresence wrapper + upload logo
│   └── main.py      # główna pętla + obsługa sygnałów
├── affine.webp      # logo uploadowane do Discord
├── config.yaml      # konfiguracja użytkownika
├── requirements.txt
└── install.sh       # instalator (venv + systemd service)
```

## Licencja

MIT