# MODELE HUAWEI z MUT - tabela presetow

> Wszystkie zmienne na model. Tool ma wybor modelu z dropdown'a + auto-fill defaultow.

## A. Routery domowe (CFE bootloader)

### WS7200-20 / AX3 Pro (HiSilicon Hi5651T)
- **Default router IP**: `192.168.3.1` (normal mode), bez IP w upgrade mode
- **PC IP zalecane**: `192.168.1.5/24` (subnet 192.168.1.x)
- **Secure boot**: TAK (RSA-2048 sig + AES enc) - **software recovery NIEMOZLIWE**
- **Tryb upgrade**: trzymaj **przycisk H/AI Life** + zasilanie -> stala dioda czerwona
- **Format firmware**: `.bin` raw (28MB)
- **PACKAGE_ID/PRODUCT_ID**: `fnt-HGW`
- **Partycje**: `CFE,0x0-0xFFFF | kernelfs,0x10000-0x3FFFFF`
- **LED states**: red blink fast = transfer, red blink slow = NAND write, green = OK
- **Telnet po flash**: TAK (jezeli debug fw) port 23, login: shell, su

### WS7100-20 / AX3 (slabsza wersja)
- Identyczne jak WS7200 ale slabszy CPU
- Software recovery NIEMOZLIWE

### WS7100-10 (Chinese)
- Identyczne ustawienia, inne firmware'y

### Honor Router 3 / XD-20
- HiSilicon Hi5651T (jak WS7200)
- Identyczne ustawienia

## B. LTE Modems (slabszy bootloader)

### E5186 / E5186s-22a
- **Default router IP**: `192.168.8.1`
- **PC IP zalecane**: `192.168.8.100/24`
- **Secure boot**: SLABE (Jari Turkia odzyskal cegle przez MUT!)
- **Tryb upgrade**: WPS + Wi-Fi button + power switch (window 0.85-1.89s)
- **Format firmware**: `.gz.bin` (**wymaga WinRAR'a**)
- **PACKAGE_ID/PRODUCT_ID**: rozne (sprawdz INI)
- **LED states**: blue stale = upgrade mode, wifi blink = transfer, slow blink = done
- **Czas flash**: ~10 min, czasem trzeba przeslac 5-15 razy

### B310As-852 (LTE indoor)
- **Default router IP**: `192.168.1.1`
- **Tryb upgrade**: needle method (small reset hole)
- **Format firmware**: `.bin`
- **Secure boot**: NIE (z 4PDA potwierdzone unbrick)

### B315
- **Default router IP**: `192.168.8.1`
- **PC IP zalecane**: `192.168.8.100/24`
- **Tryb upgrade**: trzymaj Reset+WPS przez 10s + power up
- **Format firmware**: `.bin`
- **Secure boot**: prawdopodobnie NIE

### B525
- Podobne do B315
- **Tryb upgrade**: identyczny

### B535-232
- **Default router IP**: `192.168.8.1`
- **Tryb upgrade**: Reset+WPS przez 10s
- **WAZNE**: wymaga matching signed firmware (modem + WebUI pair)
- **C-version mismatch** = brick

## C. DSL Modems

### HG630V2 / HG630 V2-12
- **Default router IP**: `192.168.1.1`
- **PC IP zalecane**: `192.168.1.5/24`
- **Format firmware**: `multicast_restore_default_pack.bin` (specjalny recovery pack)
- **Secure boot**: NIE
- **Recovery**: znany na XDA - dziala
- **PACKAGE_ID/PRODUCT_ID**: rozne, sprawdz INI

### HG633 / HG659
- **Default router IP**: `192.168.1.1`
- **PC IP zalecane**: `192.168.1.5/24`
- **Format firmware**: `.bin`
- **UART recovery**: dokumentowane na jcjc-dev.com

### HG863 (GPON)
- **Default router IP**: `192.168.100.1`
- **PC IP zalecane**: `192.168.100.10/24`
- **Format firmware**: `.bin`

## D. Tabela porownawcza (do GUI dropdown)

| Model | Router IP | PC IP | Subnet | Upgrade trigger | Firmware | Secure boot |
|---|---|---|---|---|---|---|
| WS7200/AX3 Pro | 192.168.3.1 | 192.168.1.5 | /24 | przycisk H + power | `.bin` | **TAK** |
| WS7100/AX3 | 192.168.3.1 | 192.168.1.5 | /24 | przycisk H + power | `.bin` | **TAK** |
| Honor R3 / XD-20 | 192.168.3.1 | 192.168.1.5 | /24 | przycisk H + power | `.bin` | **TAK** |
| E5186 | 192.168.8.1 | 192.168.8.100 | /24 | WPS+WiFi+power | `.gz.bin` | NIE |
| B310As | 192.168.1.1 | 192.168.1.100 | /24 | needle reset | `.bin` | NIE |
| B315 | 192.168.8.1 | 192.168.8.100 | /24 | Reset+WPS 10s | `.bin` | NIE |
| B525 | 192.168.8.1 | 192.168.8.100 | /24 | Reset+WPS 10s | `.bin` | NIE |
| B535 | 192.168.8.1 | 192.168.8.100 | /24 | Reset+WPS 10s | `.bin` | weak |
| HG630V2 | 192.168.1.1 | 192.168.1.5 | /24 | – | `multicast_restore_default_pack.bin` | NIE |
| HG633 | 192.168.1.1 | 192.168.1.5 | /24 | – | `.bin` | NIE |
| HG659 | 192.168.1.1 | 192.168.1.5 | /24 | – | `.bin` | NIE |
| HG863 (GPON) | 192.168.100.1 | 192.168.100.10 | /24 | – | `.bin` | NIE |

## E. PACKAGE_ID / PRODUCT_ID per model

Te wartosci ida do header MUT packet i ROUTER weryfikuje czy pasuja.

| Model | PACKAGE_ID | PRODUCT_ID | Source |
|---|---|---|---|
| WS7200/AX3 Pro | `fnt-HGW` | `fnt-HGW` | INI plików user'a (potwierdzone) |
| WS7100/AX3 | `fnt-HGW` | `fnt-HGW` | jw |
| Honor R3 | `fnt-HGW` | `fnt-HGW` | jw (ten sam SoC) |
| E5186 | `mbb-CPE` (?) | `mbb-CPE` (?) | spekulacja, sprawdz INI |
| B315 | `mbb-CPE` (?) | jw | spekulacja |
| HG630V2 | `dsl-IAD` (?) | jw | spekulacja |

> **WAZNE**: jezeli nie wiesz - **wyciagnij INI z oryginalnego firmware'u producenta** lub **uruchom Wireshark + oryginalny MUT** zeby zobaczyc co wysyla.

## F. Default partitions per model

### WS7200/AX3/Honor R3:
```
CFE,0x00000000-0x0000FFFF,uncover|kernelfs,0x00010000-0x003FFFFF,cover
```
(64KB CFE + ~4MB kernelfs)

### E5186 (zmiana - 4PDA):
```
CFE,0x00000000-0x0001FFFF,uncover|kernelfs,0x00020000-0x01FFFFFF,cover|...
```
(128KB CFE + 32MB kernelfs - wiekszy)

### HG630V2:
```
boot,0x00000000-0x00007FFF,uncover|firmware,0x00008000-0x00FFFFFF,cover
```

> **NIE WIEM dokladnie** - kazdy model ma INI dostarczane przez Huawei.
> Tool ma **importowac partycje z istniejacego INI** + pozwalac edycje przez UI.

## G. Workflow per model (kroki user'a)

### WS7200 (czerwona dioda, bootloop)
1. Odepnij zasilanie
2. Trzymaj przycisk H, podlacz power, trzymaj 2-3s, pusc
3. **Stala czerwona dioda** = upgrade mode active
4. PC: ustaw 192.168.1.5/24 na Ethernet
5. Uruchom MUT (tool) z firmware
6. Czekaj ~10-30 min (transfer + NAND write)
7. **Zielona dioda** = sukces

### E5186 (cegla po nieudanym update)
1. Odlacz Ethernet, USB, kable
2. **Trzymaj WPS + Wi-Fi buttons**
3. Wlacz zasilanie
4. **Po 1-1.5 sekundy puscic Wi-Fi** (dokladnie window 0.85-1.89s)
5. **Stala niebieska dioda** = upgrade mode
6. PC: ustaw 192.168.8.100/24 na Ethernet
7. Uruchom MUT
8. Czekaj ~10 min (czasem 5-15 retries)
9. **Slow blink WiFi LED** = sukces

### HG630V2 (czerwona dioda)
1. Odepnij zasilanie
2. Trzymaj **Reset** przez 30s, jednoczesnie wlacz zasilanie
3. PC: 192.168.1.5/24
4. Uruchom MUT z **multicast_restore_default_pack.bin**
5. Czekaj
