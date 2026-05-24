# SAFETY CHECKS - lista zabezpieczen unbrick_tool.py

> Wszystkie checki sa **BLOKUJACE** chyba ze user wlaczy "Expert mode" w GUI.
> Status: zielony [V] / zolty [!] / czerwony [X].

## Kategoria 1: Pre-flight (zanim user kliknie START)

### 1.1 Admin uprawnienia
- **Co**: Sprawdz czy proces jest uruchomiony jako Administrator
- **Dlaczego**: bind port 13456 wymaga uprawnien (port < 1024 nie jest problemem ale niektore Windowsy traktuja inne porty tez)
- **Test**: `ctypes.windll.shell32.IsUserAnAdmin()`
- **Jezeli FAIL**: blokuje + przycisk "Restart as Admin"

### 1.2 Python version
- **Co**: Python >= 3.7
- **Dlaczego**: f-strings, dataclasses
- **Test**: `sys.version_info >= (3, 7)`
- **Jezeli FAIL**: blokuje + komunikat "Update Python"

### 1.3 Firmware file
- **Co**: Plik .bin istnieje, > 1 MB, nie pusty
- **Test**: `os.path.isfile()`, `os.path.getsize() > 1024*1024`
- **Jezeli FAIL**: blokuje, komunikat

### 1.4 Firmware magic header
- **Co**: bytes [4:8] == `0x1A F0 0F 1A` (Huawei magic)
- **Dlaczego**: zeby user nie wyslal przypadkiem .exe albo random pliku
- **Test**: `with open(...) as f: f.seek(4); f.read(4) == b'\x1a\xf0\x0f\x1a'`
- **Jezeli FAIL**: ostrzezenie (mozna kontynuowac dla nietypowych modeli)

### 1.5 INI file
- **Co**: Plik .ini istnieje obok .bin lub mozna wygenerowac
- **Test**: `os.path.isfile(bin.replace('.bin', '.ini'))`
- **Jezeli BRAK**: oferta wygenerowania (button "Generate INI")

### 1.6 INI valid
- **Co**: INI ma wszystkie wymagane pola
- **Test**: parsuj, sprawdz IMAGE_NAME, IMAGE_SIZE, FIRMWARE_CRC_SUM, INI_CRC_SUM, PARTITIONS
- **Jezeli FAIL**: pokazuje co brakuje + button "Regenerate"

### 1.7 INI CRC zgodne z firmware
- **Co**: FIRMWARE_CRC_SUM z INI == zlib.crc32(open(bin).read())
- **Test**: oblicz CRC i porownaj
- **Jezeli FAIL**: ostrzezenie + button "Regenerate INI"

### 1.8 INI_CRC_SUM zgodne z INI
- **Co**: INI_CRC_SUM == zlib.crc32(content_without_crc)
- **Test**: parsuj content do "INI_CRC_SUM=", oblicz CRC, porownaj
- **Jezeli FAIL**: blokuje (router odrzuci)

## Kategoria 2: Network (interfejsy)

### 2.1 Karta sieciowa wybrana
- **Co**: User wybral adapter w GUI (lub auto-detect zadzialal)
- **Test**: `pc_ip is not None and pc_ip in [a.ip for a in adapters]`
- **Jezeli FAIL**: blokuje, dropdown z adapterami

### 2.2 Karta to NIE WiFi
- **Co**: wybrany adapter NIE jest typu wireless
- **Dlaczego**: WiFi multicast = problemy + pakiety ida do domowej sieci
- **Test**: `not adapter.is_wifi`
- **Jezeli WiFi**: BLOKUJE w default. Tylko expert mode + dodatkowy "Tak, na pewno WiFi" checkbox.

### 2.3 Link UP
- **Co**: Karta ma "MediaConnectState=Connected"
- **Test**: PowerShell `Get-NetAdapter -Name X | select MediaConnectState`
- **Jezeli FAIL**: blokuje, "Podlacz kabel Ethernet"

### 2.4 Link speed wystarczajacy
- **Co**: Link speed >= 10 Mbps (idealnie 100/1000)
- **Test**: `Get-NetAdapter -Name X | select LinkSpeed`
- **Jezeli FAIL**: ostrzezenie (nieslyszane = duplex problem)

### 2.5 IP karty zgodny z subnet routera
- **Co**: pc_ip in router_subnet (np. 192.168.1.0/24 dla routera 192.168.1.1)
- **Test**: `ipaddress.ip_interface(pc_ip + '/24') in network`
- **Jezeli FAIL**: ostrzezenie + button "Auto-set IP" (wymaga admin + powershell New-NetIPAddress)

### 2.6 Tylko JEDNA karta UP
- **Co**: Inne karty (Wi-Fi, Tailscale, Hyper-V, VMware, virtual) sa Disabled
- **Dlaczego**: multicast routing problem
- **Test**: `len([a for a in adapters if a.status == 'Up']) == 1`
- **Jezeli FAIL**: ostrzezenie + button "Disable other adapters" (wymaga admin)

### 2.7 Ping 192.168.1.1 (lub model_default_router_ip)
- **Co**: Test czy router odpowiada
- **Dlaczego**: 
  - Router-cegla w upgrade mode **NIE** odpowiada na ping (nie ma TCP/IP stack)
  - Jezeli router ODPOWIADA = nie jest w upgrade mode (lub to inny router!)
- **Test**: `subprocess.run(['ping', '-n', '1', '-w', '500', router_ip])`
- **Jezeli ODPOWIADA**: BLOKUJE w default. Pokaz "Twoj router dziala normalnie - nie potrzebujesz MUT" lub "Jestes podpiety do INNEGO routera".

### 2.8 Firewall rules
- **Co**: Sa reguly UDP 13456 in/out
- **Test**: `Get-NetFirewallRule -DisplayName "HuaweiMUT*"`
- **Jezeli BRAK**: button "Add firewall rules" (wymaga admin)

### 2.9 IPv6 wylaczone na karcie
- **Co**: ms_tcpip6 binding disabled
- **Dlaczego**: zmniejsza chaos
- **Test**: `Get-NetAdapterBinding -Name X -ComponentID ms_tcpip6`
- **Jezeli ON**: ostrzezenie + button "Disable IPv6"

### 2.10 Telnet client
- **Co**: TelnetClient feature enabled
- **Dlaczego**: po flash trzeba `telnet 192.168.1.1` + `diag restore default`
- **Test**: `Get-WindowsOptionalFeature -FeatureName TelnetClient`
- **Jezeli OFF**: ostrzezenie + button "Enable Telnet"

## Kategoria 3: Confirmation (na klikniecie START)

### 3.1 "Wpisz UNBRICK aby kontynuowac"
- **Co**: Modalne okno z Entry'em - musi wpisac dokladnie "UNBRICK"
- **Dlaczego**: zeby nie kliknal Enter przypadkiem
- **Pokazuje sie**: KAZDY raz przed startem (nie zapamietuje)

### 3.2 Final summary modal
- Wyswietla:
  - Model wybrany
  - Firmware path + size + CRC
  - INI path + content preview
  - Karta + IP
  - Multicast IP + port + interval
  - Estimated time
- Buttons: [Cancel] [START FLASH]

## Kategoria 4: Runtime (podczas flash)

### 4.1 Watchdog timer (30 min)
- **Co**: Auto-stop po 30 minutach
- **Dlaczego**: jezeli sukces nie nastapil w 30 min - prawdopodobnie cos zle
- **Implementacja**: timer.cancel() w GUI thread

### 4.2 Pass limit (default 15)
- **Co**: Auto-stop po 15 pelnych przejsciach (1 pass = caly firmware wyslany raz)
- **User configurable**: 1-100 passes lub infinite
- **Default**: 15 (zalecone z Jari Turkia: "11 razy musialem wyslac")

### 4.3 Live link monitoring
- **Co**: co 5s sprawdzaj czy karta nadal UP
- **Jezeli DOWN**: STOP + alert "Kabel odpiety"

### 4.4 BIG STOP button
- **Co**: zawsze widoczny, czerwony, ogromny
- **Akcja**: 
  1. Zatrzymaj send loop (set running=False)
  2. Close socket
  3. Restore network state (DHCP back, enable other adapters)

### 4.5 Ctrl+C handler
- **Co**: KeyboardInterrupt -> graceful stop
- **Implementacja**: `signal.signal(SIGINT, handler)`

### 4.6 Atexit hook
- **Co**: w razie crash'a -> przywroc DHCP automatycznie
- **Implementacja**: `atexit.register(restore_network)`

### 4.7 Crash logging
- **Co**: jezeli wyjatek - zapisz traceback do `crash_TIMESTAMP.log`
- **Plus**: pokaz user'owi gdzie znalezc

## Kategoria 5: Cleanup

### 5.1 Restore IP karty
- **Co**: po flash przywroc DHCP
- **Test**: `Set-NetIPInterface -Dhcp Enabled`
- **Akcja**: button "Restore network" lub auto na Ctrl+C

### 5.2 Re-enable disabled adapters
- **Co**: WiFi, Tailscale, Bluetooth - przywroc je
- **Test**: `Get-NetAdapter | where Status -eq Disabled` -> Enable

### 5.3 Restore IPv6
- **Co**: enable ms_tcpip6 binding
- **Test**: `Enable-NetAdapterBinding -ComponentID ms_tcpip6`

### 5.4 Backup network state
- **Co**: PRZED rozpoczeciem - zapisz JSON ze stanem sieci
- **Plik**: `_network_backup_TIMESTAMP.json`
- **Format**: lista adapter -> {name, status, ip, dhcp, dns}

## Kategoria 6: Logging

### 6.1 Log rotacyjny
- **Co**: kazdy run -> nowy plik `_unbrick_log_TIMESTAMP.txt`
- **Format**: `[HH:MM:SS] LEVEL message`
- **Levels**: INFO, WARN, ERROR, DEBUG, PACKET (verbose)

### 6.2 Live log w GUI
- **Co**: Text widget z ostatnimi N=500 linii
- **Auto-scroll**: tak (chyba ze user scroll'uje)
- **Filter**: dropdown level (INFO/WARN/ERROR/PACKET)

### 6.3 Crash dump
- **Co**: na exception zapisz: traceback, network state, ostatnie 100 packetow
- **Plik**: `crash_TIMESTAMP.json`

## Kategoria 7: Expert mode override

User w GUI moze wlaczyc "Expert mode" checkbox -> wylacza:
- 2.2 (WiFi block)
- 2.7 (router ping block)
- 3.1 (UNBRICK confirmation)

ALE dalej blokuje:
- 1.1 (admin)
- 1.4 (firmware magic - bo firmware nie-Huawei to bug)
- 1.6/1.8 (INI valid + CRC - bo router je odrzuci anyway)

## Kategoria 8: Edge cases

### 8.1 No adapters at all
- **Co**: zero IPv4 adapter
- **Akcja**: blokuje, instrukcja "Podlacz kabel"

### 8.2 Multiple WiFi adapters
- **Co**: 2+ WiFi up (laptop ma WiFi + Mobile Hotspot)
- **Akcja**: ostrzezenie, dropdown wyboru

### 8.3 VPN active
- **Co**: Tailscale/OpenVPN/WireGuard adapter Up
- **Akcja**: ostrzezenie, button "Disable VPN"

### 8.4 Antivirus blocks UDP
- **Co**: niektore AV (Avast, Norton) blokuja port 13456
- **Akcja**: ostrzezenie po `bind` failure z radzeniem disable AV

### 8.5 Firmware secure-boot router
- **Co**: model wybrany = WS7200/AX3/Honor R3
- **Akcja**: pre-flight WARNING "Ten model ma secure boot - flash moze nie zadzialac. Sprawdz `_research/FINAL_REPORT.md`."
