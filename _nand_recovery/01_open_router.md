# Krok 1: Otwarcie routera WS7200 + identyfikacja NAND

## Narzedzia

- Sruboktet **Phillips PH1**
- Plastikowa spatulka / stara karta kredytowa (do podwazania zaczepow)
- Pinceta antystatyczna (opcjonalne)
- Mata antystatyczna (opcjonalne, mozna polozyc kartkE papieru)
- Dobra lampa + telefon (do zdjecia chipow)

## ZASADA BEZPIECZENSTWA

- **Wyciagnij wtyczke zasilania PRZED otwarciem**
- **Dotknij obudowy komputera** lub kaloryfera zeby rozladowac statycznosc cialo
- **Nie dotykaj chipow palcami** - tylko PCB krawedzie

## Otwarcie obudowy

1. Polozk router do gory dnem na mietkiej powierzchni
2. Pod **4 gumowymi nozkami** sa schowane srubki PH1
3. Podwaz gumki ostrym przedmiotem (paznokciem, plastikowa spatulka) i wyjmij
4. Wykrec **4 srubki** PH1 (sa krotkie, ~5mm)
5. Plastikowa spatulka wsun w szczeline pomiedzy gorna a dolna czesc obudowy - od strony przedniej (gdzie LED)
6. Powolutku **przesuwaj wokol obudowy** - sa tam plastikowe zaczepy ktore trzeba rozpinac
7. Beware: u gory sa **anteny przykklejone do gornej obudowy** - kable nie naciagac

## Po otwarciu

PCB jest dostepne. Mozesz zobaczyc:
- 4 zlote anteny po bokach (zwykle 2.4G x2 + 5G x2)
- Cztery porty LAN + WAN (RJ45) po jednej stronie
- Glowny SoC w srodku PCB (duzy BGA, czarny) - to **HiSilicon Hi5651T RBCV100**
- **Pod glownym SoC** - male chipy BGA/SOIC - tu jest **NAND flash + DDR RAM**

## Identyfikacja NAND chip

NAND flash to **mniejszy chip** kolo glownego SoC. Wyglada tak:

```
[NAND 8-pin SOIC]      [DDR3 RAM BGA]      [WiFi front-end]
       8 nozek            kwadratowy             maly
       po bokach           BGA                   chip

      _________
     |  pin1 . | <- kropka identyfikujaca pin 1
     |        |
     |  NAND  |
     |        |
     |________|
     |8 nozek po lewej, 8 po prawej?

```

### Co odczytac z chipa

Na chipie sa napisy **graweracyjne** - male, czasami trudne do odczytania bez lupy.
Najlepiej **swiatlo z boku** (kierunek pod katem) - litery sa lepiej widoczne.

Przyklady oznaczen NAND ktore moga byc na WS7200:

| Producent | Oznaczenia (przyklady) |
|---|---|
| **Winbond** | `W25N01GV`, `W25N02JV`, `W25N512KV` |
| **GigaDevice** | `GD5F1GQ4UB`, `GD5F2GQ5UE` |
| **Macronix** | `MX35LF1GE4AB`, `MX35LF2GE4AB` |
| **Toshiba/Kioxia** | `TC58CVG0S3HRAIG`, `TC58CVG1S3HRAIG` |
| **ESMT/Etron** | `F50L1G41A`, `F50L2G41XA` |
| **Micron** | `MT29F1G01ABAFD`, `MT29F2G01ABAGD` |

### Co zrobic z odczytanym oznaczeniem

1. **Zrob zdjecie** chipa z bliska (telefonem, z dobra ostroscia)
2. **Zapisz** dokladny napis (z myslnikiem, prefiksami, sufiksami - wszystko)
3. **Wyslij mi** zdjecie + tekst napisu, ja zweryfikuje:
   - Czy to SPI NAND (CH341A wystarczy) czy parallel NAND (potrzeba RT809H)
   - Jaki pinout (8-pin czy 16-pin SOIC)
   - Jakie napiecie (3.3V czy 1.8V)
   - Czy NeoProgrammer ma support dla tego chipa

## Co JESLI NAND to BGA (bez nozek po bokach)

Wtedy CH341A z klipsem SOIC8 **NIE zadziala** - chip jest pod plata BGA, niemozliwy do zlapania klipsem.

Wtedy mamy 2 opcje:
- **Wylutowanie chipa** + adapter BGA->SOIC + zaprogramowanie + wlutowanie z powrotem (TRUDNE)
- **Kup nowy router** WS7200 lub WS7100 (sa za ~150-200 zl uzywane)

Ale to malo prawdopodobne - Hi5651T routery uzywaja SPI NAND SOIC8 w 95% przypadkow.

## Co JESLI NAND to TSOP-48 (parallel)

Duzy prostokat z 24 nozkami po dwoch bokach. CH341A **NIE umie** parallel NAND.
Tylko z **RT809H**, **T48**, lub **TL866II Plus + adapter TSOP-48**.

W tym przypadku - musisz kupic dodatkowy programator (~200-300 zl) lub odpuscic.

## Status

[ ] Router otwarty
[ ] PCB widoczne
[ ] NAND chip zidentyfikowany - oznaczenie: __________________
[ ] Zdjecie chipa zrobione
[ ] Pin1 oznaczony (kropka, znacznik laserowy) - widoczny
