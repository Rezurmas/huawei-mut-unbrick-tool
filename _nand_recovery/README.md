# NAND Recovery WS7200 - CH341A

## Co bedziemy robic

Bootloader (CFE) routera **odrzuca kazdy firmware** przez multicast - prawdopodobnie z powodu
uszkodzonego CFE w NAND lub fail-safe locku. Multicast nie potrafi tego naprawic.

**Rozwiazanie**: programatorem **CH341A z klipsem SOIC8** czytamy/zapisujemy NAND flash **bezposrednio**,
pomijajac CFE/signature. Dzialamy na poziomie surowych bajtow chipa.

## Workflow

```
[1] Otworz router + zidentyfikuj NAND chip (zdjecie + odczyt napisu)
                              |
                              v
[2] Podlacz klips SOIC8 na chip (orientacja: pin1 = kropka, czerwony przewod)
                              |
                              v
[3] NeoProgrammer -> Detect chip -> Read -> ZAPISZ ja "nand_original_backup_01.bin"
                              |
                              v
[4] Read PONOWNIE -> ZAPISZ "nand_original_backup_02.bin"
    Porownaj (fc /b backup_01.bin backup_02.bin) - MUSZA byc identyczne
                              |
                              v
[5] Analiza dumpu - znajdujemy offset CFE, kernelfs, nvram
                              |
                              v
[6] Wstrzykujemy DOBRE firmware do dumpu (offset kernelfs)
    + czyscimy nvram (offset partycji nvram = 0xFF)
                              |
                              v
[7] Erase + Write + Verify chip
                              |
                              v
[8] Zlozenie routera + start
```

## Plik checklisty

Patrz `checklist.md` w tym folderze.

## Plik wskazowek dla otwarcia routera

Patrz `01_open_router.md`.

## Plik instrukcji CH341A

Patrz `02_dump_nand.md`.

## Analiza dumpu

Patrz `03_analyze_dump.md`.

## Tworzenie naprawionego obrazu

Patrz `04_build_fixed_image.md`.

## Zapis chipa

Patrz `05_write_chip.md`.
