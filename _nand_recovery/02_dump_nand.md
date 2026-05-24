# Krok 2: PEŁNY backup NAND przez CH341A + NeoProgrammer

## Co potrzebne

- CH341A czarna plytka + USB
- Klips SOIC8 (czerwony/zielony) + adapter SOIC8->DIP8
- Sterownik CH341PAR zainstalowany (pobierz: https://www.wch-ic.com/downloads/CH341PAR_EXE.html)
- NeoProgrammer zainstalowany
- Otwarty router z odslonietym chipem NAND

## ZASADY BEZPIECZENSTWA - CZYTAJ ZANIM PODLACZYSZ KLIPSA

### 1. Router MUSI byc CALKOWICIE odlaczony od zasilania
- Wyciagnij wtyczke z gniazdka **i** kabel zasilacza z routera
- **Zaczekaj 30 sekund** zeby kondensatory sie rozladowaly
- Sprawdz multimetrem napiecie na chipie - **musi byc 0V**

### 2. Orientacja klipsa - KRYTYCZNA
- Pin 1 chipa = **kropka/marker laserowy** w jednym z rogow
- Czerwony przewod klipsa = pin 1
- Klips musi sciskac chip rownomiernie z obu stron - sprawdz wzrokowo

### 3. Plyta CH341A wlozona DO USB - **TYLKO po podlaczeniu klipsa do chipa**
Inaczej moze podac napiecie na luzne pinki klipsa = zwarcie

### 4. Niektore chipy 1.8V - **CH341A czarna podaje 3.3V**
Jesli oznaczenie chipa zawiera `LF` (Macronix), lub jest **GD5F** seria - mozliwe ze
chip potrzebuje 1.8V VCC. Wtedy CH341A czarna **uszkodzi** chip.
**Sprawdz datasheet** chipa zanim podasz napiecie.

## Procedura dump

### Krok A: Test bez zasilania routera

1. Wpinasz CH341A do USB
2. Otwierasz NeoProgrammer.exe (jako Administrator)
3. Menu **Hardware -> Select hardware -> CH341a**
4. Klikasz **Detect** (lub `Read ID`)
5. Jesli chip wykryty - **idziesz dalej**. Jesli "Unknown chip" - patrz troubleshooting nizej

### Krok B: Pierwszy backup

1. **File -> Save as -> `nand_backup_01.bin`** (zapisz na pulpicie albo w `_nand_recovery/dumps/`)
2. **Action -> Read** (lub przyciskRead)
3. Czekaj az NeoProgrammer skonczy czytanie (moze trwac 5-30 min, NAND ma 128 MB)
4. Po skonczeniu **File -> Save** (do tego samego pliku)
5. Sprawdz wielkosc pliku - powinna byc **rowna pojemnosci NAND**:
   - 128 MB chip -> 128 MB plik = 134217728 bajtow (lub 137363456 z OOB)
   - 256 MB chip -> 256 MB plik = 268435456 bajtow

### Krok C: WERYFIKACJA - drugi backup

**Bez wyciagania klipsa** zrob drugi dump:

1. **File -> Save as -> `nand_backup_02.bin`**
2. **Action -> Read**
3. Zapisz

### Krok D: Porownanie dwoch backupow

```powershell
fc /b nand_backup_01.bin nand_backup_02.bin
```

- Output `FC: no differences encountered` -> **OK, mozemy isc dalej**
- Output zawiera offsety -> klips ma **slaby kontakt**, sprobuj ponownie

## Troubleshooting "Unknown chip" / Detect failed

### Problem: NeoProgrammer pokazuje "0x00 0x00 0x00" lub "0xFF 0xFF 0xFF" jako ID

To znaczy ze klips **NIE ma kontaktu** z chipem. Przyczyny:

1. **Zla orientacja** - pin 1 klipsa po zlej stronie chipa (czerwony przewod musi byc na pin 1)
2. **Klips luzny** - chip moze byc lekko gruby, sprawdz czy klipsy sciskaja
3. **Brudne piny** chipa - przetrzyj alkoholem izopropylowym (IPA)
4. **NAND wymaga osobnego zasilania** - niektore chipy potrzebuja zasilania routera (delikatnie!)
5. **NAND nie jest SPI** - mozliwe ze to parallel/eMMC. Sprawdz typ.

### Problem: "ID jest 0x9F 0x?? 0x??" ale chip "Unknown"

ID jest odczytane prawidlowo, ale NeoProgrammer nie zna tego chipa. Mozesz:

1. **Powiedziec mi konkretne ID** (3 bajty) - sprawdze co to za chip
2. **Recznie dodac** chip do NeoProgrammer'a (Settings -> Chip Database -> Add)
3. **Sprobowac inny tool** - flashrom z patchami SPI NAND

## Status

[ ] CH341A wpiety, NeoProgrammer wykrywa chip
[ ] Backup #1 zrobiony (rozmiar: _________ bajtow)
[ ] Backup #2 zrobiony (rozmiar: _________ bajtow)
[ ] fc /b - **NO DIFFERENCES**
[ ] Backupy skopiowane do bezpiecznej lokalizacji (Google Drive, USB stick)
