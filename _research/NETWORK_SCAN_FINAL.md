# 🌐 KOMPLETNY RAPORT Z GŁĘBOKIEGO SCANU SIECI

## Co przeszukałem (24.05.2026)

| Źródło | Status | Co znalezione |
|---|---|---|
| FCC photos PDF (Federal Comm. Commission) | ✅ pobrane | PCB top/bottom, brak UART headera |
| deviwiki.com (Honor Pro2 ten sam SoC) | ✅ | identyfikacja chipów |
| **acwifi.net/9665.html** (Chinese teardown WS7200) | ✅ przez webarchive | **W25N01GVZEIG NAND, NT5CC128M16JR RAM** |
| techinfodepot.shoutwiki.com (WS7200) | ✅ | tylko general specs |
| openwrt.org/toh/huawei/ws7200 | ⚠️ pusty szablon | nikt nie wpisał danych |
| OpenWrt Forum 1-8 + page 164 (Support for AX3 Pro) | ✅ | telnet on debug fw, signature reject |
| **4PDA Russian forum** (главный thread 989679) | ⚠️ posty blokowane, ale meta info | **3 recovery guide links** + NeoProgrammer.7z attached |
| elektroda.pl (polskie forum) | ⚠️ błąd HTTP/2 | "NeoProgrammer dla W25N01GV - najlepsze" |
| Winbond datasheet W25N01GVZEIG | ✅ | **WSON-8 package (8x6mm, no leads)** |
| Reddit, Snapeda, LCSC | ✅ | confirm WSON-8 |

## 🎯 NAJWAŻNIEJSZE ODKRYCIA

### 1. Chip NAND = Winbond W25N01GVZEIG
- **128 MB SPI NAND, 3.3V, 104 MHz**
- **Pakiet: WSON-8 (8x6 mm)** ← *bez nóżek!*, tylko pady od spodu
- Standardowy **klips SOIC-8 NIE zadziała** na ten chip
- CH341A z NeoProgrammer obsługuje ten chip

### 2. Shield nad SoC + NAND = PRZYLUTOWANY
- Dwa źródła (acwifi + dsouza @ OpenWrt) potwierdzają
- Trzeba zdjąć: hot-air gun (bezpiecznie) lub cążki (siłowo)

### 3. Software recovery NIEMOŻLIWA (potwierdzone z 3 forów)
- **Frifox @ OpenWrt**: "The router will refuse to flash"
- **4PDA users**: jedyna metoda recovery = **CH341A + NeoProgrammer**
- Wszystkie 8 firmware'ów ma RSA-2048 signature + AES enkrypcję
- MUT.exe to single-protocol multicast (port UDP 13456)

### 4. WAŻNE ostrzeżenie z 4PDA (CH341A topic):
> "Programowanie chipów SOP-8 klipsem **bez wylutowywania z PCB**
> daje absolutnie nieprzewidywalny wynik"

Czyli **klips na chip wlutowany w router = często NIE działa**, bo:
- Router ma kondensatory na linii zasilania chipa
- Inne komponenty na SPI bus przeszkadzają
- Trzeba albo wylutować chip, albo przerwać linię VCC chipa

### 5. NeoProgrammer.7z dostępny na 4PDA
- Link: `https://4pda.to/forum/dl/post/28208360/NeoProgrammer.7z`
- Wymaga konta 4PDA do pobrania (free)
- Alternatywa: https://github.com/Doniks-/NeoProgrammer-Mirror

## 🚨 OSTATECZNA OCENA TWOJEJ SYTUACJI

### Co masz:
- ✅ CH341A (czarna płytka)
- ✅ Klips SOIC-8 + adapter SOIC8→DIP8
- ❌ Adapter WSON-8 → DIP-8 (potrzebny dla W25N01GVZEIG)
- ❌ Hot-air gun (potrzebny do zdjęcia shieldu + wylutowania chipa)

### Czego brakuje:
| Sprzęt | Cena | Niezbędność |
|---|---|---|
| **Adapter WSON-8 → DIP-8** | 15-50 zł (Allegro) | KRYTYCZNE |
| **Hot-air gun** (Quick 858D / YIHUA 853D) | 150-300 zł | KRYTYCZNE |
| **Mikroskop USB** | 50-100 zł | bardzo zalecane |
| **Topnik + cyna 0.5mm** | 30 zł razem | KRYTYCZNE |
| Pinceta antystatyczna | 20 zł | zalecane |

### Realne ścieżki

**A) Pełna recovery (~300-500 zł sprzętu + 1-2 dni pracy)**
1. Otworzyć obudowę routera
2. Hot-air zdjąć shield z CPU/NAND
3. Hot-air wylutować W25N01GV
4. Klips lub adapter WSON-8 + CH341A dump
5. Modyfikacja dumpu (potrzebny clean NAND backup z OpenWrt forum)
6. Zapis chip + wlutowanie z powrotem
7. Złożenie + boot

**B) Półśrodek: lutowanie do test padów (jeśli istnieją)**
1. Otworzyć router
2. Sprawdzić wzrokowo - czy obok chipa NAND są test pady
3. Lutować cienkie kable do CS/MOSI/MISO/CLK/GND
4. Reszta jak w A) ale bez wylutowywania chipa

**C) Nowy router**
- WS7200 używany na Allegro/OLX: ~150-200 zł
- WS7100 (słabszy AX3): ~100-150 zł
- WS7206 (Qualcomm) lub inne AX1800: ~150-250 zł

**D) Zostaw cegłę, kup nowy**
- Najmniej ryzykowne
- Brak frustracji
- Stara cegła do recyklingu (lub jako pamiątka)

## 📌 KOŃCOWA REKOMENDACJA

**Trzeba podjąć decyzję:**

- Jeśli **lubisz elektronikę** i masz cierpliwość → recovery przez CH341A (opcja A/B). 
  Sprzęt: ~300 zł, czas: 1-2 dni, ryzyko: 30% że i tak się nie uda

- Jeśli **chcesz internet jak najszybciej** → kup nowy używany router (~200 zł)

- Jeśli **niezdecydowany** → zostaw cegłę, dokumentacja jest w `_research/`,
  możesz wrócić do tego za miesiąc/rok

## Pliki źródłowe w `_research/`
- `FINAL_REPORT.md` - software-only analysis
- `HARDWARE_FOUND.md` - hardware components 
- `NETWORK_SCAN_FINAL.md` - this file
- `mut_strings.txt` - MUT.exe strings dump
- `pe_analysis.txt` - PE analysis MUT.exe
- `firmware_deep_analysis.txt` - binary analysis .bin
- `compare_firmwares.txt` - all 8 firmware compared
- `cli_context.txt` - MUT.exe disassembly context
- `final_software_checks.txt` - hidden features search
- `native_images/` - 3 PCB photos (FCC native)
