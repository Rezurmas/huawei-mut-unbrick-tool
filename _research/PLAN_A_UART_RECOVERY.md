# 🟢 PLAN A: UART Console Recovery (najtańszy + najbezpieczniejszy)

## DLACZEGO TO ZADZIAŁA:

1. WS7200 ma U-Boot (potwierdzone z 4PDA boot loga: "DRAM: 256 MiB Check spi flash controller v350")
2. U-Boot to standardowy bootloader z consolą szeregową
3. U-Boot ma komendy `tftpboot`, `nand write` które OMIJAJĄ signature check
4. Signature check jest w userspace (po boot'cie kernela), NIE w U-Boot
5. Twój router jest w bootloop = U-Boot DZIAŁA, tylko kernel się crash'uje

## BARIERY:

1. **UART pady są nieoznaczone na PCB** - trzeba znaleźć multimetrem
2. **Pady mogą być przylutowane high-melt-point solder** (jak w Huawei HG633 - jcjc-dev.com)
3. **Trzeba znać baudrate** (najpewniej 115200, ale może być inny)
4. **Anteny 2.4G są przylutowane do PCB** - ostrożnie z wyciąganiem mainboardu

## SPRZĘT POTRZEBNY (Allegro - Polska):

| Sprzęt | Model | Cena |
|---|---|---|
| USB-UART adapter | CP2102 / FT232RL / CH340 | 5-15 zł |
|   *(masz już CH341A - ma piny UART też)* | | – |
| Przewody Dupont F-F (5 sztuk wystarczy) | – | 3-5 zł |
| Lutownica (TYLKO jeśli pady przez-otworowe wymagają lutowania pinów) | dowolna 30W | – |
| **Razem minimum** | | **~10 zł** |

## OPROGRAMOWANIE:

| Software | Po co | Link |
|---|---|---|
| **Putty** lub **TeraTerm** | Terminal serial | putty.org / teratermproject.github.io |
| **Tftpd64** | TFTP server na PC | bitbucket.org/phjounin/tftpd64 |
| (CH341PAR driver jeśli używasz CH341A) | UART przez CH341A | wch-ic.com |

## PROCEDURA:

### Krok 1: Otwarcie routera (5 min)

1. Postaw router do góry nogami
2. Odklej 4 gumki w narożnikach spodu (paznokciem)
3. Wykręć 4 śrubki Philips PH1 pod gumkami
4. Plastikową kartą podważ od strony portów Ethernet (zatrzaski)
5. Górna obudowa odejdzie - widzisz PCB
6. Pamiętaj: **NIE wyciągaj PCB** - anteny 2.4G są przylutowane!

### Krok 2: Znajdowanie UART pads (15-30 min)

Szukaj:
- **4-6 nieużywanych pinów/padów w rzędzie** blisko CPU (HiSilicon Hi5651T)
- Często oznaczone jako TP1, TP2, J1, J2 albo bez oznaczenia
- Pady mogą być **through-hole** (z dziurkami) lub **SMD** (płaskie)

Identyfikacja:
1. **Multimetrem** - tryb continuity (sygnał dźwiękowy)
2. Znajdź **GND** - dotknij multimetrem korpus portu Ethernet (to GND), 
   drugą sondą szukaj pinu który pisknie (continuity = ten pad to GND)
3. Znajdź **Vcc** - włącz router (uważaj!), 
   multimetrem na DC volt 20V, czerwoną sonda na pad, czarną na GND
   - 3.3V = Vcc ← **NIE PODŁĄCZAJ DO TEGO!**
4. **Tx** - na włączonym routerze, multimetrem DC volt:
   - Pad który ma chwilę 3.3V, chwilę 0V, fluktuuje = **Tx routera** (data sending)
5. **Rx** - pad który zostaje na ~0V (floating, czeka na connection) = **Rx routera**

Alternatywnie: **logic analyzer** ($5-10 sztuka analizator USB) pokaże od razu
który pad ma signal a który nie.

### Krok 3: Podłączenie (5 min)

```
Router PCB        USB-UART adapter (np. CP2102)
---------         --------------------------------
GND       <-->   GND
Tx (rout) <-->   Rx (adapter)
Rx (rout) <-->   Tx (adapter)
Vcc       <-->   NIE PODŁĄCZAJ! (router ma swoje zasilanie 12V z zasilacza)
```

USB-UART adapter włóż do USB komputera. W Device Manager pojawi się
nowy port COM (np. COM3 / COM5).

### Krok 4: Boot do U-Boot (5 min)

1. Putty:
   - Connection type: **Serial**
   - Serial line: **COM3** (lub jaki masz)
   - Speed: **115200** (jeśli nie zadziała: 57600, 38400, 9600)
   - Open

2. **Zasilij router** (nie podłączony jeszcze)

3. W Putty zobaczysz boot log:
   ```
   U-Boot 2010.06 (Apr 28 2020 - ...)
   DRAM: 256 MiB
   Check spi flash controller v350
   spi nand id table version 1.42
   Hit any key to stop autoboot: 3
   ```

4. **Naciśnij ENTER szybko** (w 3 sekundach!)

5. Powinieneś zobaczyć prompt:
   ```
   hisilicon #
   ```

### Krok 5: Recovery flash przez TFTP (15 min)

**Na PC**:
1. Uruchom Tftpd64
2. Ustaw "Current Directory" na folder z firmware (np. `WS7200-20_10.0.5.30(C888)_demo.bin`)
3. Server interface: ustaw na sieć Ethernet (192.168.x.x)

**Połącz Ethernet PC <-> Router (do dowolnego portu LAN routera)**

**W U-Boot (Putty)**:

```bash
# Sprawdź jakie są obecne env
hisilicon # printenv

# Ustaw IP routera i serverIP (PC)
hisilicon # setenv ipaddr 192.168.1.100
hisilicon # setenv serverip 192.168.1.10
hisilicon # setenv ethact eth0     # albo eth1, sprawdź help

# Test sieci
hisilicon # ping 192.168.1.10
# Powinno: "host 192.168.1.10 is alive"

# Pobierz firmware do RAM
hisilicon # tftpboot 0x82000000 WS7200-20_10.0.5.30_demo.bin
# Powinno: "Bytes transferred = 19659xxx"

# Spóźrz partycje NAND
hisilicon # mtdparts
# albo:
hisilicon # nand info

# Wymaż partycje (UWAGA: NIEODWRACALNE!)
hisilicon # nand erase 0x... 0x...

# Zapisz
hisilicon # nand write 0x82000000 0x... 0x...

# Reset
hisilicon # reset
```

**ALE**: Format firmware `.bin` user'a jest **enkryptowany** AES. Nie można go bezpośrednio zapisać do NAND. Trzeba mieć **rozszyfrowany** firmware lub kompletny **dump NAND** od działającego identycznego routera.

### Krok 6: Alternatywa - boot z RAM bez flashowania

```bash
# Załaduj firmware do RAM
hisilicon # tftpboot 0x82000000 firmware.bin

# Boot bez zapisu (TRYB TESTOWY!)
hisilicon # bootm 0x82000000
```

Jeśli to działa, masz potwierdzenie że firmware jest dobry przed flashowaniem.

## ⚠️ POTENCJALNE PROBLEMY:

### Problem 1: Brak okienka "Hit any key"
- Znaczy że U-Boot ma `bootdelay=0` (bardzo short)
- Spróbuj **trzymać ENTER wciśnięty PODCZAS WŁĄCZANIA** routera
- Spróbuj **Ctrl+C** zamiast Enter
- Spróbuj **Ctrl+B** (Huawei enterprise convention)

### Problem 2: U-Boot poprosi o hasło
- Default Huawei password: `Admin@huawei.com`
- Lub: `huawei`, `admin`, pusty enter

### Problem 3: Router odrzuca firmware (signature check w U-Boot)
- WS7200 może mieć **secure boot** w U-Boot - to potwierdzilibyśmy podczas próby
- Wtedy musisz wrócić do Planu B (CH341A NAND)

### Problem 4: Komendy NAND są zablokowane
- Niektóre Huawei U-Boot mają wyłączone `nand write` jako security
- Sprawdź: `hisilicon # help` - wylistuje dostępne komendy
- Jeśli brak `nand write` - jest `sf write` (SPI flash) lub `mtd`

## SZANSE POWODZENIA:

- **70%** że uda się znaleźć UART pady (jcjc-dev.com pokazał że na Huawei jest możliwe)
- **80%** że uda się wejść w U-Boot prompt (jeśli pady działają)
- **40%** że uda się flashować firmware z encrypted .bin (zależy czy U-Boot deszyfruje, czy zostawia to userspace'owi)
- **70%** że TFTP load + bootm bez flash zadziała (pokazałby nam "trustchain")

**Ogólna szansa pełnego recovery przez UART: ~30-40%**

## CO ZROBIĆ JEŚLI ZADZIAŁA:

1. Przed flash - **ZRÓB BACKUP** całego NAND'a
   ```
   hisilicon # nand dump 0x0 0x8000000 > backup.bin
   ```
2. Wrzuć **debug firmware** (10.0.5.26_main_debug) - ten ma OTWARTY TELNET!
3. Po boot: `telnet 192.168.3.1`, `shell`, `su` = root shell!
4. Z root: można robić wszystko (zapisać dobrą oryginalną firmware, wyłączyć OTA, etc.)

## CO ZROBIĆ JEŚLI NIE ZADZIAŁA:

→ Plan B (CH341A NAND dump + write)
→ lub Plan C (nowy router)
