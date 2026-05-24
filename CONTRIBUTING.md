# Contributing to Huawei MUT Unbrick Tool

Thanks for your interest in helping! Tool jest open-source dla społeczności –
PR'y mile widziane.

## Czego najbardziej brakuje

### 1. Nowe modele Huawei
Edytuj `MODELS` dict w `unbrick_tool.py`. Potrzebne:
- Nazwa modelu (np. "B315s-936")
- SoC (HiSilicon Balong / Broadcom / etc)
- Default router IP (np. 192.168.8.1)
- PC IP zalecane (np. 192.168.8.100)
- Tryb upgrade (np. "Reset+WPS 10s + power")
- PACKAGE_ID / PRODUCT_ID (z Wireshark capture lub INI Huawei)
- Default partitions (z fabrycznego INI)
- Secure boot (TAK/NIE)

### 2. Wireshark captures
Jeśli masz **działający router** który MOŻESZ poddać upgrade'owi:
1. Zainstaluj Wireshark
2. Capture filter: `udp port 13456`
3. Uruchom oryginalny HuaweiMUT.exe + flash
4. Save .pcapng
5. Wrzuć anonymizowany capture do issues

To pozwoli **zweryfikować nasz protokół byte-by-byte** i znaleźć `unknown_word`
@ offset 40-41 (w packet) który nie jest jeszcze w pełni rozkodowany.

### 3. Tłumaczenia
Tool jest po polsku. Potrzebne tłumaczenia EN/RU/DE/CN.
Plik z tekstami: na razie inline w `unbrick_tool.py`, w przyszłości `i18n/*.json`.

### 4. Testy regresji
- Test framework: pytest + tkinter
- CI: GitHub Actions (`.github/workflows/test.yml`)
- Mock: `subprocess.run` żeby testować bez Windows'owych komend

### 5. Bug reports
Jeśli znalazłeś bug:
- Sprawdź `_research/FINAL_REPORT.md` (może to known issue dla WS7200)
- Otwórz issue z:
  - Wersja Pythona (`python --version`)
  - Wersja Windows
  - Model routera + LED state
  - Pełny `_unbrick_log_*.txt`
  - Screenshot GUI / błędu

## Setup developerski

```powershell
git clone https://github.com/<your-repo>/huawei-mut-unbrick-tool
cd huawei-mut-unbrick-tool
# Zero install - tylko Python 3.7+ z built-in tkinter
python unbrick_tool.py
```

## Linting

```powershell
pip install pyflakes ruff
python -m pyflakes unbrick_tool.py
python -m ruff check unbrick_tool.py
```

## Test smoke

```powershell
python _test_audit.py     # static analysis + import test (28 checks)
python _test_gui_smoke.py # GUI launch + auto-close (sanity)
```

## PR guidelines

1. **Fork + branch** (`feature/your-thing`)
2. **Test zmian** (powyższe scripty)
3. **PR description** z:
   - Co zmieniłeś (i czemu)
   - Jak testowałeś (z którym routerem)
   - Czy są breaking changes

## Code style

- PEP 8 (line < 100 chars OK, < 88 lepiej)
- Docstring dla każdej publicznej funkcji
- Type hints dla wszystkich argumentów
- Polski w komentarzach OK (oryginalny user's code base po polsku)
- Angielski w docstrings (community release)

## Architektura

```
unbrick_tool.py (~2700 linii):
  1. Constants + MODELS dict
  2. Helpers (CRC, INI gen, packet build)
  3. Network adapter helpers
  4. SafetyChecker (12+ checks)
  5. NetworkManager (PowerShell wrappers)
  6. MutEngine (threaded send loop)
  7. UnbrickGUI (Tkinter)
  8. CLI mode
  9. Main entry

Documentation:
  _research/PROTOKOL.md   - byte-by-byte MUT protocol
  _research/MODELS.md     - 12 supported models
  _research/SAFETY.md     - 30+ safety checks
  _research/FINAL_REPORT.md - WS7200 secure boot analysis
```

## License

MIT - patrz LICENSE.
