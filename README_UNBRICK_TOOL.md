# 🔧 Huawei MUT Unbrick Tool

> **Idiotoodporne** narzedzie do unbrick'a routerow Huawei przez protokol MUT (Multicast Upgrade Tool).
> **Open-source clone HuaweiMUT.exe** w czystym Pythonie z GUI Tkinter, pelnym RE protokolu i maksymalnymi zabezpieczeniami.

![Status](https://img.shields.io/badge/status-v1.0.0_release-brightgreen.svg)
![Python](https://img.shields.io/badge/python-3.7+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)
![Audit](https://img.shields.io/badge/audit-28%2F28_OK-brightgreen.svg)

## ⚡ **Co nowego w v1.0.0** (vs poprzednie wersje)

🚨 **CRITICAL FIX: `DEFAULT_INTERVAL_MS = 5`** (było 200ms = **100x za wolno!**)
- Z `conf.dat` oryginalnego MUT: `INTERVAL_TIME=5ms`
- Z Guide.txt 4PDA: *"put '2' for successful firmware!"*
- Wcześniejsze wersje wysyłały **100x za wolno** → bootloader timeout → flash failuje

✅ **11 modeli routerów** (WS7200, AX3, Honor R3, E5186, B315, B525, B535, HG630V2, HG633, HG659, Custom)
✅ **12 safety checks** (admin, firmware magic, INI CRC, WiFi block, link UP, router ping, secure boot warning...)
✅ **GUI Tkinter** + **CLI mode** (zero install, built-in tkinter)
✅ **Auto-disable WiFi/VPN** + restore tracking
✅ **Set 100Mbps Full Duplex** auto
✅ **Telnet `diag restore default`** post-flash button
✅ **LED state info** dialog z tabelą kolorów
✅ **ETA + bytes/sec** w progress bar
✅ **Auto-generate INI** po wyborze firmware'u
✅ **Network backup/restore** via PowerShell
✅ **Listen for router responses** (debugging)

## 🎯 Co to jest?

`unbrick_tool.py` to **community release** narzedzia replikujacego protokol Multicast Upgrade Tool (MUT) firmy Huawei. Pozwala odzyskac (unbrick) routery Huawei zlapane w bootloop, bez koniecznosci uzywania zamknietego `HuaweiMUT.exe` (389KB MFC binary z 2008 roku).

**Reverse-engineered** z `HuaweiMUT.exe` (IDA Pro + Hex-Rays) plus internet research:
- [blog.hqcodeshop.fi/289](https://blog.hqcodeshop.fi/archives/289-Huawei-E5186-Firmware-Upgrade-with-Multicast-Upgrade-Tool.html) (Jari Turkia, E5186)
- 4PDA forum threads (recovery procedures)
- XDA Forums (HG630V2)
- OpenWrt Forum (WS7200, B535 telnet)
- IDA Pro + Hex-Rays decompilation (`HuaweiMUT.exe`)

## 📋 Wspierane modele

| Model | SoC | Software recovery | Note |
|---|---|---|---|
| **WS7200 / AX3 Pro** | Hi5651T | ❌ secure boot | dla testow / edukacji |
| **WS7100 / AX3** | Hi5651T | ❌ secure boot | jw |
| **Honor Router 3 / XD-20** | Hi5651T | ❌ secure boot | jw |
| **E5186 LTE** | Balong | ✅ DZIALA | potwierdzone (Jari Turkia) |
| **B315 / B525 LTE** | Balong | ✅ DZIALA | potwierdzone (4PDA) |
| **B535 LTE** | Balong | ⚠️ uwaga na C-version | wymaga matching firmware |
| **HG630V2 DSL** | Broadcom | ✅ DZIALA | wymaga `multicast_restore_default_pack.bin` |
| **HG633 / HG659 DSL** | Lantiq/HiSi | ✅ DZIALA | sa UART recovery procedury |
| **Custom** | - | ⚠️ manual | konfigurujesz wszystko sam |

> **WAZNE**: WS7200/AX3/Honor R3 maja silicon-level RSA secure boot.
> Tool wysle pakiety, ale router je **odrzuci**. Patrz `_research/FINAL_REPORT.md`.
> Dla nich potrzebne jest **hardware recovery** (CH341A + NeoProgrammer + WSON-8 adapter).

## 🚀 Quick start

### Wymagania
- Python 3.7+ (built-in `tkinter`)
- Windows 10/11
- Administrator (dla `bind` portu 13456 + zmiany IP karty)
- Kabel Ethernet (NIE WiFi!)

### Instalacja

```powershell
git clone https://github.com/<your-repo>/huawei-mut-unbrick-tool
cd huawei-mut-unbrick-tool
# Zero install - dziala od razu!
python unbrick_tool.py
```

### GUI mode (zalecane)

```powershell
# PowerShell jako Administrator!
python unbrick_tool.py
```

Pojawi sie okno GUI:
1. **Wybierz model routera** (dropdown)
2. **Wskaz plik .bin** firmware'u
3. **Kliknij "Generate INI"** (lub uzyj wlasnego)
4. **Wybierz karte sieciowa** (auto-detect Ethernet)
5. **Pre-flight checklist** - 12 zielonych ✓
6. **Kliknij START** - wpisz "UNBRICK" do confirmation
7. **Czekaj** ~10-30 min az LED zmieni sie na zielony

### CLI mode (zaawansowane)

```powershell
# Lista kart sieciowych:
python unbrick_tool.py --cli --list-adapters

# Wygeneruj INI z FORCE-CFE:
python unbrick_tool.py --cli firmware.bin --gen-ini --force-cfe

# Flash z auto-detect IP:
python unbrick_tool.py --cli firmware.bin -v

# Flash z konkretnym IP:
python unbrick_tool.py --cli firmware.bin --pc-ip 192.168.1.5 -v

# Eksperyment - unicast:
python unbrick_tool.py --cli firmware.bin --unicast 192.168.1.1 -v

# Listen for router responses (debugging):
python unbrick_tool.py --cli firmware.bin --listen -v
```

## 🛡️ Zabezpieczenia (MAKSYMALNE)

Tool **BLOKUJE** start jezeli ktorykolwiek z 12 checków zwraca FAIL:

1. **Admin uprawnienia** – wymagane do bind portu
2. **Python 3.7+**
3. **Firmware file** – istnieje, > 1 MB
4. **Firmware magic** – `0x1AF00F1A` na offset 0x4 (Huawei format)
5. **INI file** – istnieje obok .bin (lub mozna wygenerowac)
6. **INI valid** – wszystkie pola obecne
7. **INI CRC32** – zgadza sie z firmware'm
8. **Karta wybrana** – pc_ip istnieje na karcie
9. **NIE WiFi!** – blokuje karte WiFi (default; expert mode override)
10. **Link UP** – kabel podlaczony
11. **PC IP w subnet routera** – ostrzezenie jak nie
12. **Router NIE odpowiada na ping** – blokuje jak ODPOWIADA (= dzialajacy router, nie cegla!)

Plus dodatkowe:
- **Confirmation modal** – wpisz dokladnie "UNBRICK" przed startem
- **Watchdog timer** – auto-stop po 30 min
- **Pass limit** – max 15 pelnych przejsc (zalecane Jari Turkia: "11 razy")
- **Network backup** – stan sieci zapisany przed (`_unbrick_network_backup.json`)
- **Atexit hook** – auto-stop engine on crash
- **Live link monitoring** – co 5s sprawdz czy karta UP
- **BIG STOP button** – zawsze widoczny, czerwony

## 🧠 Jak to dziala (protokol MUT)

Patrz [`_research/PROTOKOL.md`](_research/PROTOKOL.md) dla pelnej dokumentacji byte-by-byte.

W skrocie:
- **Multicast UDP `224.0.0.119:13456`** (oba ends - source i dest)
- **Packet 1086 bytes**: 62B header + 1024B chunk
- **3 opcode**: INIT (4), DATA (1), LAST (2)
- **Header**: control_word, seq, chunk_crc, total_size, fw_crc, PACKAGE_ID, PRODUCT_ID
- **Wymagany INI** z `IMAGE_NAME`, `IMAGE_SIZE`, `FIRMWARE_CRC_SUM`, `INI_CRC_SUM`, `PARTITIONS`

## 📁 Struktura projektu

```
.
├── unbrick_tool.py              # GLOWNY tool (GUI + CLI)
├── README_UNBRICK_TOOL.md       # ten plik
├── _research/
│   ├── PROTOKOL.md              # pelna dokumentacja MUT (byte-by-byte)
│   ├── MODELS.md                # tabela modeli z parametrami
│   ├── SAFETY.md                # lista zabezpieczen tool'a
│   ├── FINAL_REPORT.md          # analiza WS7200 (recovery niemozliwe)
│   ├── HARDWARE_FOUND.md        # hardware specs WS7200
│   ├── PLAN_A_UART_RECOVERY.md  # alternatywa dla cegly: UART
│   └── ...
├── mut_python.py                # poprzednia wersja (CLI only)
├── unbrick_all.ps1              # PowerShell wizard wrapper
├── _unbrick_wizard.ps1          # oryginalny wizard
├── generate_ini_file.py         # CLI INI generator (oryginal)
├── generate_ini_file_gui.py     # GUI INI generator (oryginal)
└── generate_ini_force_cfe.py    # CLI FORCE-CFE INI generator
```

## 🐛 Troubleshooting

### `WinError 10049: The requested address is not valid`
**Przyczyna**: IP karty nie pasuje do `--pc-ip`. Tool ma fallback na `0.0.0.0`, ale lepiej:
```powershell
python unbrick_tool.py --cli --list-adapters
# Wybierz IP z listy lub uzyj --auto-ip
```

### `Permission denied` przy bind
**Przyczyna**: nie jestes Administrator. Uruchom PowerShell jako Admin.

### Router nie reaguje (LED dalej czerwona)
- Sprawdz **Cover partitions** (uzyj `--force-cfe` dla CFE+kernelfs cover)
- Probuj **wieksze interval** (np. 500ms zamiast 200)
- Wyslij kilka razy (`--passes 15`)
- Sprawdz czy **kabel jest w LAN porcie routera (NIE WAN!)**
- **Powtorz tryb upgrade** routera (przycisk H + zasilanie)

### `WS7200 nie reaguje mimo wszystkiego`
**Przyczyna**: secure boot - software recovery NIEMOZLIWE.
**Rozwiazanie**: hardware recovery przez UART (Plan A) lub CH341A (Plan B). 
Patrz `_research/PLAN_A_UART_RECOVERY.md`.

### GUI sie nie otwiera
- Brakuje tkinter? Na Windows powinno byc built-in. Sprawdz:
  ```powershell
  python -c "import tkinter; tkinter._test()"
  ```
- Jezeli brakuje - instalator Python "Modify" -> "tcl/tk and IDLE"

## 🤝 Contributing

Pull requests welcome! Szczegolnie:
- Nowe modele Huawei do `MODELS` dict
- Nowe `PACKAGE_ID`/`PRODUCT_ID` z Wireshark capture
- Bug fixes
- Tlumaczenia (EN/PL/RU/CN)

## 📜 License

MIT License - free dla community use.

## 🙏 Credits

- **Jari Turkia** ([blog.hqcodeshop.fi](https://blog.hqcodeshop.fi)) - pierwszy publikowany E5186 unbrick guide
- **micha102** - oryginalny `generate_ini_file.py` na GitHub
- **4PDA community** - threads + recovery procedures dla wielu modeli
- **XDA Forums** - HG630V2 + B535 reports
- **OpenWrt forum** - WS7200/AX3 hardware analysis

## ⚠️ Disclaimer

Tool jest **community release** dla edukacji i odzyskiwania wlasnych routerow.
Uzywasz **na wlasna odpowiedzialnosc**. Autorzy nie odpowiadaja za:
- dalsze cegielenie routera,
- utrate gwarancji,
- konflikty z prawem (jezeli flash'ujesz cudzy sprzet bez zgody),
- inne szkody.

**WAZNE**: niektore routery (WS7200/AX3 z Hi5651T) maja secure boot i recovery jest **niemozliwa**. Tool nie naprawi tego - patrz `_research/FINAL_REPORT.md`.
