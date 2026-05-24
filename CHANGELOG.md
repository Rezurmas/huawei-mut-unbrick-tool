# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.0] - 2026-05-24

### 🎉 Initial community release

#### Added
- Pełna replika protokołu MUT w czystym Pythonie (`unbrick_tool.py`)
- Tkinter GUI z 4 panelami konfiguracyjnymi + status + log
- 11 model presets: WS7200, WS7100, Honor R3, E5186, B315, B525, B535,
  HG630V2, HG633, HG659, Custom
- 12 safety checks (admin, firmware magic, INI CRC, WiFi block, link UP,
  router ping, secure boot warning, PC IP subnet, etc.)
- CLI mode (`--cli` flag) z pełną kompatybilnością z mut_python.py
- Auto-detect karty Ethernet (preferuje wired, NIE WiFi)
- INI file generator (normal + FORCE-CFE modes)
- Network backup/restore via PowerShell
- Disable/enable WiFi/VPN auto + tracking
- Set 100Mbps Full Duplex (lepszy multicast)
- Telnet `diag restore default` post-flash
- LED state info dialog
- Post-flash dialog z instrukcjami
- ETA + bytes/sec speed w progress
- About dialog
- Auto-generate INI po wyborze firmware'u (z confirmation)

#### Documentation
- `_research/PROTOKOL.md` - kompletny opis MUT byte-by-byte
- `_research/MODELS.md` - tabela 11 modeli z parametrami
- `_research/SAFETY.md` - lista 30+ zabezpieczeń
- `_research/FINAL_REPORT.md` - analiza WS7200 (secure boot)
- `README_UNBRICK_TOOL.md` - community README
- `CONTRIBUTING.md` - guide dla kontrybutorów
- `CHANGELOG.md` - ten plik

#### Critical bug fixes (vs mut_python.py)
- **DEFAULT_INTERVAL_MS = 5** (było 200ms = 100x za wolno!)
  Zgodne z `conf.dat` MUT'a oryginalnego: `INTERVAL_TIME=5ms`
  Guide.txt z 4PDA: "put '2' for successful firmware!"
- WiFi adapter detection + block
- Router-alive ping check (blokuje jak NIE jest cegłą)
- Bind fallback na 0.0.0.0 zamiast crash przy WinError 10049
- Auto-detect IP karty
- Listen mode z `select()` zamiast `settimeout` (nie psuje sendto)

#### Tested
- Syntax check (`py_compile`) ✓
- pyflakes static analysis ✓
- Custom audit script (28 OK, 0 errors) ✓
- GUI smoke test (otwiera+zamyka bez crashy) ✓
- CLI list-adapters ✓
- CLI gen-ini --force-cfe ✓

#### Known issues
- WS7200/AX3/Honor R3 mają **silicon-level secure boot** - software recovery
  niemożliwa. Tool wysle pakiety, router je odrzuci. Patrz FINAL_REPORT.md.
- Status karty `Unknown` jeśli PowerShell `Get-NetAdapter` failuje
- `app` variable unused w `main()` - intended (mainloop trzyma referencje
  przez `root`)

#### Acknowledgments
- Jari Turkia ([blog.hqcodeshop.fi](https://blog.hqcodeshop.fi)) - E5186 unbrick guide
- micha102 - oryginalny `generate_ini_file.py`
- 4PDA forum (thread 989679) - recovery procedures + Guide.txt
- XDA Forums - HG630V2 + B535 reports
- OpenWrt Forum - WS7200 hardware analysis
