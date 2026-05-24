# 🎯 PEŁNY ROZKŁAD HARDWARE WS7200 (Huawei AX3 Pro)

Źródło: chiński teardown acwifi.net/9665.html (przez webarchive)
+ datasheet Winbond + 4PDA Russian forum + OpenWrt forum

## Komponenty (potwierdzone fizycznie)

| Komponent | Konkretny chip | Pakiet | Notatki |
|---|---|---|---|
| **CPU** | HiSilicon **Hi5651T** RBCV100 | BGA pod shieldem | Quad-core ARM Cortex-A53 1.4 GHz |
| **RAM** | Nanya **NT5CC128M16JR** | BGA | 256 MB DDR3-1866 |
| **🔥 NAND FLASH** | Winbond **W25N01GVZEIG** | **WSON-8 (8x6mm)** | **128 MB SPI NAND, 3.3V, 104 MHz** |
| **WiFi SoC** | HiSilicon **Hi1152** | BGA pod shieldem | 2.4G+5G dual band, single chip |
| **2.4G PA (front-end)** | 2x Skyworks **SKY85333-11** | LGA-24 (3x5mm) | +28 dBm output |
| **5G PA (front-end)** | 2x Richwave **RTC7676** | – | 5GHz only |
| **Gigabit PHY** | Realtek **RTL8211F** | – | 1Gbps Ethernet |
| **NFC** | **FM11NC08** | – | Tap-to-connect |

## ⚠️ KRYTYCZNE: pakiet NAND chipa

**`W25N01GVZEIG`** suffix `ZEIG` oznacza **WSON-8 package** (8x6 mm).

**WSON-8 ≠ SOIC-8!**

```
SOIC-8 (200mil):              WSON-8 (8x6mm):
  ___________                  __________
 |1●  ___  8|                 |1●        |
 |2 |   | 7|                  |2         |
 |3 |   | 6|  <- nóżki po bokach     <- BRAK nóżek po bokach
 |4 |___| 5|                  |   PADS   |
  -----------                  | OD SPODU |
                               |8________5|
```

**Klips SOIC-8** standardowy **NIE chwyci** chipa WSON-8 (nie ma za co).

## Dostępne opcje recovery NAND

### Opcja A: Sprawdzić wzrokowo (FIRST!)
Otwórz router, sprawdź **fizycznie**:
- Czy chip ma wystające nóżki po bokach (4+4) -> SOIC-8, klips zadziała
- Czy chip jest gładki kwadracik bez nóżek -> WSON-8, klips NIE zadziała
- Może w Twojej rev. PCB jest inny package (Winbond czasem używa SOIC-8 dla tego chipa)

### Opcja B: Wylutować chip (jeśli WSON-8)
Sprzęt:
- **Hot-air gun** (np. Quick 858D, ~150 zł, lub stacja typu YIHUA 853D)
- **Adapter WSON-8 → DIP-8** (~10-30 zł na Allegro: "adapter WSON8 DIP8 programator")
- Cyna 0.5mm + topnik (kwiatowy lub kalafonia)

Procedura:
1. Hot-air ~370°C, dyszka 5mm, ostrożnie podgrzej tylko obszar chipa
2. Pinceta - delikatnie podnoś chip kiedy cyna się stopi
3. Wyczyść pady na PCB z resztek cyny (oplot + topnik)
4. Włóż chip do adaptera WSON-8→DIP-8
5. Adapter włóż do CH341A (do socketu DIP-8)

Po skończonej recovery - chip wlutowujesz z powrotem na PCB
(hot-air + cyna + topnik, podstawa pad-to-pad alignment)

### Opcja C: Lutowanie do test padów na PCB
Trudne ale możliwe. Przy chipie są zwykle test pady CS/MOSI/MISO/CLK/GND.
Trzeba znaleźć je multimetrem (continuity test do pinów chipa).

Wymaga:
- Lutownica z **bardzo cienkim grotem** (1mm lub mniejszy)
- Drut nawojowy 0.2mm (kynar wire 30 AWG)
- Mikroskop USB (~50 zł)
- Multimetr

### Opcja D: BGA pogo-pin adapter
Specjalny adapter ze sprężynowymi pinami który dotyka padów chipa:
- "WSON-8 socket adapter" lub "DFN-8 spring loaded socket"
- Ceny ~150-400 zł na Aliexpress

## Konfiguracja CH341A + NeoProgrammer

### Software:
- **NeoProgrammer 1.2.1.10+** - obsługuje W25N01GV out-of-the-box
- **Driver CH341PAR** (NIE CH341SER!) - wersja parallel/SPI
  Pobierz: https://www.wch-ic.com/downloads/CH341PAR_EXE.html

### Konfiguracja w NeoProgrammer:
1. Hardware -> Select Hardware -> **CH341A**
2. Chip -> Select Chip -> **Winbond -> W25N01GV** (1Gbit SPI NAND)
3. Detect ID - powinno odczytać `EFh AAh 21h`
4. Read - dump'uje cały chip (~5-10 min dla 128 MB)

## Software-only recovery NIEMOŻLIWE - dlaczego (potwierdzone z 4PDA + OpenWrt)

1. **Frifox @ OpenWrt forum**: "The router will refuse to flash" non-Chinese firmware
2. **Dsouza @ OpenWrt forum**: "the RF metal shields seemed to be soldered"
3. **4PDA: "Инструкция по восстановлению кирпича"** - oficjalna procedura
   wykorzystuje CH341A + NeoProgrammer + dump NAND

Procedura zatem JEDNA:
1. Otwórz router (4 śrubki pod gumkami)
2. Zdejmij shield z CPU/NAND (siłowo cążkami lub hot-air gun)
3. Identyfikuj package NAND chipa (SOIC-8 vs WSON-8)
4. Klips lub wylutowanie chipa
5. CH341A + NeoProgrammer = backup pełnego flash
6. Modyfikacja dumpu (czyszczenie nvram + wstrzyknięcie dobrego firmware)
7. Zapis chip + reboot
8. Router powinien się uruchomić

## Telnet recovery (TYLKO jeśli flash debug firmware się uda)

Z OpenWrt forum:
> "debug & demo versions boost wifi power and have open 23 (Telnet) and 3333 ports,
>  type shell and after su for enter"

Procedura na DZIAŁAJĄCYM debug firmware (po recovery):
```
telnet 192.168.3.1
shell           # wejście w sh
su              # root
# pełen kontrol nad routerem
```

Pliki które router ma w /etc/firmware/:
- cfg_ws7200_r_hisi.ini    (26970 B)
- cfg_ws7200_hisi.ini      (26402 B)
- phy_patch_hi5651.bin     (6480 B)
- cfg_ws7200_20_h_hisi.ini (32694 B)
- cfg_ws7200_20_hisi.ini   (32584 B)
- WCPU_ROM.bin             (1144 B)  <- WiFi CPU ROM
- cfg_ws7200_30_hisi.ini   (44404 B)
- cfg_device_hisi.ini      (232 B)
- FIRMWARE.bin             (918640 B) <- WiFi firmware

Komendy żeby zamknąć debug ports po dostaniu się do shell'a (security):
```
killall app_sdt   # zamyka port 3333
killall app_acs
killall app_nlc
```

## Podsumowanie sytuacji TWOJEGO routera

✅ Wiemy WSZYSTKO o hardware (chipy, package, voltages)
✅ Wiemy że MUT.exe robi swoją pracę poprawnie  
✅ Wiemy że router odrzuca firmware przez signature check w CFE
✅ Wiemy że masz CH341A + klips SOIC-8 (ALE chip może być WSON-8!)
✅ Wiemy że NeoProgrammer obsługuje W25N01GV
❓ Nie wiemy fizycznego pakietu chipa (sprawdź zdjęciem!)
❓ Nie wiemy czy shield jest snap-on czy lutowany u Ciebie

**KOLEJNY KROK**: otwórz tylko OBUDOWĘ (NIE zdejmuj shieldów),
sfotografuj PCB, sprawdź wzrokowo NAND chip.
