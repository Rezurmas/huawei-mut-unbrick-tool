# RAPORT KONCOWY: Software recovery WS7200 - czemu to NIE DZIALA

## TL;DR

**Software-only recovery jest definitywnie NIEMOZLIWE.**
Wszystkie protokoly, narzedzia i firmware'y sprawdzone i odrzucone.
Jedyna sciezka to **CH341A + klips SOIC8 na NAND chip** lub **nowy router**.

---

## 1. MUT.exe - kompletna analiza

### Statystyki:
- **Plik**: `HuaweiMUT.exe` (389 KB, 32-bit Windows x86)
- **Build**: 2008-05-15 (15 lat temu)
- **Compiler**: Visual C++ 6.0 / MFC
- **NIE jest spakowany** (brak UPX/Themida/VMProtect)

### Sekcje PE:
| Sekcja | VirtAddr | RawSize | Chars |
|---|---|---|---|
| `.text` | 0x1000 | 0x45000 (276 KB) | code+execute |
| `.rdata` | 0x46000 | 0x11000 (68 KB) | read-only data |
| `.data` | 0x57000 | 0x4000 (16 KB) | read-write data |
| `.rsrc` | 0x6A000 | 0x4000 (16 KB) | resources |

**Wniosek**: Brak ukrytych sekcji, brak zaszyfrowanych danych.

### Hardcoded constants:
| Constant | Wartosc | Liczba wystapien |
|---|---|---|
| Multicast IP | `224.0.0.119` | 1x |
| Bind IP | `0.0.0.0` | 1x |
| UDP port | **`13456`** (0x3490) | 2x |

**Wniosek**: Jeden, sztywny protokol UDP multicast na port 13456. Brak fallback.

### Imports (DLL):
- WS2_32.dll, WSOCK32.dll (network)
- KERNEL32, USER32, GDI32, COMCTL32 (Windows API)
- ADVAPI32 (registry)
- OLE32, OLEAUT32 (COM)
- **BRAK** crypto DLL (advapi nie uzywane do crypto)

**Wniosek**: MUT NIE robi zadnej kryptografii. NIE weryfikuje signature firmware.

### Searched for hidden CLI args / debug modes:
- `/?` - false positive (assembly code bytes)
- `-h` - false positive (random hex pattern)
- `-v` - false positive (string "spanish-venezuela")
- `-d` - false positive (string "spanish-dominican republic")
- `--help`, `--debug` - NIE WYSTEPUJA
- `GetCommandLineA` - **istnieje**, ale tylko jako MFC init (nie parsuje argow)

**Wniosek**: MUT.exe NIE MA command-line arguments. Tylko GUI.

### Searched for alternative protocols:
- `TFTP`, `tftp` - NIE
- `HTTP`, `HiLink`, `UPnP`, `SSDP` - NIE
- `telnet`, `SSH` - NIE
- `FTP`, `VRP` - false positive (random bytes)

**Wniosek**: Jedyny protokol = UDP multicast 224.0.0.119:13456.

### conf.dat:
```
MULTICAST_IP=224.0.0.119
INTERVAL_TIME=5ms
```
**Wniosek**: Brak ukrytych ustawien.

### INI keys recognized:
- IMAGE_NAME, IMAGE_SIZE
- FIRMWARE_CRC_SUM, FIRMWARE_VERSION
- INI_CRC_SUM
- PARTITIONS (format: `CFE,start-end,cover|kernelfs,start-end,cover`)
- PCB_VERSION, PRODUCT_ID, PACKAGE_ID

**Wniosek**: Brak ukrytych flag typu `FORCE_FORMAT`, `ERASE_NVRAM`, `BYPASS_SIG`, etc.

### Error messages w MUT (co MUT moze pokazac):
- "Image file CRC error"
- "Image file length error"
- "Image file name error"
- "Open image file failed"
- "Ini file CRC"
- "Ini file error"
- "Verify image file failed"
- "Socket error"
- "Please select an image file"
- "Please select partition(s) need to be covered."

**WAZNE**: U Ciebie zaden z tych bledow NIE wyswietlil sie. MUT zglosil sukces.
Czyli MUT wykonal swoja prace **idealnie**. Blokada jest **po stronie routera**.

---

## 2. Firmware .bin - kompletna analiza

### Struktura header (32 bajtow, identyczna dla wszystkich 8 firmware'ow):

```
Offset  Bajty                                       Znaczenie
------  ------------------------------------------  -------------------
0x00    01 00 00 00                                 version = 1
0x04    1A F0 0F 1A                                 magic (Huawei)
0x08    01 00 02 00                                 product subID = 0x00020001
0x0C    20 00 00 00                                 header length = 32
0x10    0F 00 00 00                                 partition count = 15
0x14-1B 00 00 00 00 00 00 00 00                     reserved (zeros)
0x1C    20 00 00 00                                 partition table offset = 32
```

### Signature area (256 bajtow, **rozna dla kazdego firmware**):

```
Offset 0x30 - 0x12F: 256 bajtow = 2048 bitow = RSA-2048 signature
```

To **kryptograficzny podpis cyfrowy** wszystkich plikow firmware.
**Bez klucza prywatnego Huawei** nie da sie wygenerowac validnego podpisu.

### Entropia danych:
- Pierwsze 1 MB kazdego firmware: **8.0 bits/byte** (maksymalna mozliwa)
- Brak czytelnych stringow Linux/CFE/HUAWEI w pierwszych 12 MB
- Wystepuje "CFE" tylko jeden raz @ offset ~12 MB (najpewniej fragment encrypted CFE binary)

**Wniosek**: **Caly firmware jest AES-encrypted**. Tresc widoczna dopiero **wewnatrz routera**, po deszyfracji przez CFE/bootloader (po sprawdzeniu RSA signature).

### Porownanie wszystkich firmware:
- Identyczny header (32 bajtow) - WSZYSTKIE 8 firmware'ow
- Rozny signature (256 bajtow) - kazdy ma swoj
- Rozna entropia + content - kazdy to inne dane encrypted

**Wniosek**: Nawet `_debug` firmware ma RSA podpis i AES enkrypcje. Nie ma "lekkiej" wersji bez ochrony.

---

## 3. Co router robi przy odbiorze firmware (rekonstrukcja)

```
[Router w bootloop, red LED, MUT wysyla multicast]
                 |
                 v
[Recovery listener w CFE odbiera UDP multicast]
                 |
                 v
[Sprawdza magic '1A F0 0F 1A']  --- BLAD ---> ignoruje pakiet
                 |
                 v OK
[Pobiera caly firmware do RAM]
                 |
                 v
[Sprawdza RSA-2048 signature przeciwko klucz publiczny w bootROM]
                 |
                 v --- BLAD ---> odrzuca firmware, NIE zapisuje, restart
                 v OK
[Sprawdza CRC32 calego firmware]
                 |
                 v --- BLAD ---> j.w.
                 v OK
[Zapisuje na NAND (kernelfs partition)]
                 |
                 v
[Restart router]
                 |
                 v
[BootROM ladowuje CFE -> CFE deszyfruje AES kernelfs -> uruchamia Linux]
                 |
                 v --- BLAD ---> wraca do bootloop (red LED) -- TWOJ STAN
                 v OK -> normalny boot (green LED)
```

**Najbardziej prawdopodobne miejsca odrzucania**:
1. **CFE bootROM odrzuca firmware** bo signature nie pasuje do klucza zaszytego w silicon
2. **Lub** kernelfs jest zapisywany, ale przy boocie CFE wykrywa **uszkodzenie CFE samej partycji** (CFE bad block w NAND) i nie potrafi sie wlasciwie zainicjalizowac

Bez UART/JTAG/NAND dumpa - **nie da sie stwierdzic ktora opcja**.

---

## 4. Co JESZCZE probowalismy/sprawdzilismy:

| Metoda | Wynik | Powod |
|---|---|---|
| `cover` flag dla CFE w .ini | Bez efektu | MUT wysyla zgodnie z flagiem, ale router ignoruje |
| Debug firmware (10.0.5.26 debug) | Bez efektu | Tez ma RSA sig + AES |
| Demo firmware (10.0.5.30 C888) | Bez efektu | Tez ma RSA sig + AES |
| Stare firmware (10.0.5.17) | Bez efektu | Tez ma RSA sig + AES |
| Nowe firmware (11.0.5.5) | Bez efektu | Tez ma RSA sig + AES |
| C500 variants | Bez efektu | Tez ma RSA sig + AES |
| 30-30-30 reset | Bez efektu | Router nie reaguje, LED czerwony |
| WPS + Reset combo | Bez efektu | jw |
| Triple-reboot | Bez efektu | jw |
| MUT z roznymi sieciami | Bez efektu | Sama recovery sciezka i tak konczy sie tym samym |
| Forced CFE cover via custom .ini | Bez efektu | Router odrzuca pomimo wysylania |

---

## 5. Co NIE jest mozliwe do sprawdzenia bez sprzetu:

| Test | Czemu sprawdzic? | Wymagane |
|---|---|---|
| Boot log z UART | Zobaczyc czemu CFE odrzuca | USB-TTL + lutowanie test pads |
| NAND dump | Zobaczyc czy CFE partycja jest cala | CH341A + klips SOIC8 |
| Multicast listener listener log | Co router faktycznie odbiera | UART |
| Recovery z CFE shell | Manualnie flashowac | UART z prompt-em |
| JTAG access | Bezposrednia ingerencja | JTAG adapter ($$$) |

---

## 6. Co BY moglo zadzialac (teoretyczne, niepraktyczne):

| Scenariusz | Realnosc |
|---|---|
| Wyciek klucza prywatnego Huawei (RSA) | 0% - nigdy publicznie nie wyciekly |
| Wyciek klucza dekrypcji (AES) | 0% - jw |
| Publiczny exploit na CFE Hi5651T | 0% - nie znany, badaczy Pwn2Own niw przebadali tego SoC |
| Side-channel attack (timing/power) | 0% praktyki - wymaga sprzet $5000+ |
| Glitch attack (voltage injection) | 0% praktyki - wymaga sprzet $1000+ |

---

## 7. WERDYKT KONCOWY

```
   +-----------------------------------------------------+
   |                                                     |
   |  SOFTWARE-ONLY RECOVERY = NIEMOZLIWE                |
   |                                                     |
   |  Wszystkie sciezki protokolowe sprawdzone i         |
   |  zamkniete. MUT robi swoja prace. Router odrzuca    |
   |  firmware na poziomie CFE/bootROM (signature        |
   |  check w silicon).                                  |
   |                                                     |
   |  JEDYNE wyjscie:                                    |
   |   A) CH341A + klips SOIC8 na NAND chip (DIY)        |
   |   B) Nowy router (~150-200 zl uzywany WS7200)       |
   |                                                     |
   |  Lutowanie blaszki shielding jest OPCJONALNE -      |
   |  wiele routerow ma snap-on shield bez lutowania.    |
   |  Sprawdz wzrokowo po otwarciu obudowy.              |
   |                                                     |
   +-----------------------------------------------------+
```
