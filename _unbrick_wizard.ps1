#Requires -RunAsAdministrator
<#
 Huawei WS7200 / AX3 - Unbrick Wizard
 Backup, wybor firmware, walidacja CRC, regeneracja .ini, telnet, firewall,
 wylaczenie WiFi/Tailscale, statyczny IP, uruchomienie MUT, monitoring,
 telnet diag restore, restore DHCP - wszystko interaktywnie.
#>
$ErrorActionPreference = 'Continue'
$ProgressPreference    = 'SilentlyContinue'

# Konfig
$ifAlias       = 'Ethernet'
$staticIP      = '192.168.1.5'
$staticPrefix  = 24
$routerIP      = '192.168.1.1'
$multicastIP   = '224.0.0.119'
$multicastPort = 13456
$scriptDir     = $PSScriptRoot
$mutPath       = Join-Path $scriptDir 'WS7200---WS1000-Firmware-Bins-and-Tools-main\MUT\HuaweiMUT.exe'
$iniGen        = Join-Path $scriptDir 'generate_ini_file.py'
$backupFile    = Join-Path $scriptDir '_network_backup.json'
$logFile       = Join-Path $scriptDir ("_wizard_log_{0}.txt" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

# Logger
function Write-Log([string]$Msg,[string]$Color='Gray') {
    $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $Msg
    Write-Host $line -ForegroundColor $Color
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}
function Write-Section($title) {
    $bar = '=' * 70
    Write-Host "" ; Write-Host $bar -ForegroundColor Cyan
    Write-Host "  $title" -ForegroundColor Cyan ; Write-Host $bar -ForegroundColor Cyan
    Add-Content -Path $logFile -Value "`n=== $title ===" -Encoding UTF8
}
function Read-YN($prompt,[bool]$default=$true) {
    $hint = if ($default) { '[T/n]' } else { '[t/N]' }
    while ($true) {
        $a = (Read-Host "$prompt $hint").Trim().ToLower()
        if ($a -eq '') { return $default }
        if ($a -in @('t','tak','y','yes')) { return $true }
        if ($a -in @('n','nie','no'))      { return $false }
    }
}
function Wait-Enter($msg='>>> Nacisnij Enter aby kontynuowac <<<') {
    Write-Host "" ; Write-Host $msg -ForegroundColor Yellow ; [void](Read-Host)
}
function Get-Crc32File([string]$Path) {
    # Liczymy CRC32 przez Python - szybko (<1s dla 27MB) i bez problemow z uint32 w PS 5.1
    $py = (Get-Command python -ErrorAction Stop).Source
    $code = "import sys,zlib;print(zlib.crc32(open(sys.argv[1],'rb').read()) & 0xFFFFFFFF)"
    $out = & $py -c $code $Path 2>&1
    if ($LASTEXITCODE -ne 0) { throw "CRC32 failed: $out" }
    return [uint64]($out.ToString().Trim())
}

Clear-Host
Write-Section 'Huawei WS7200 - Unbrick Wizard'
Write-Log "Log: $logFile" 'DarkGray'
Write-Log "Folder: $scriptDir" 'DarkGray'

if (-not (Test-Path $iniGen)) { Write-Log "BLAD: brak $iniGen" 'Red'; Wait-Enter; exit 1 }
if (-not (Test-Path $mutPath)) { Write-Log "UWAGA: brak HuaweiMUT.exe pod $mutPath" 'Yellow' }
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { Write-Log "BLAD: brak python.exe w PATH." 'Red'; Wait-Enter; exit 1 }
Write-Log "Python: $($python.Source)" 'DarkGray'

Write-Host ""
Write-Host "Co bedzie zrobione (z potwierdzeniem na kazdym etapie):" -ForegroundColor White
@(
 '1. Backup obecnej konfiguracji sieci',
 '2. Wybor firmware + walidacja .bin/.ini (CRC)',
 '3. Sprawdzenie Klient Telnet + reguly Zapory',
 '4. Wylaczenie WiFi / Tailscale / Bluetooth NCP',
 '5. Wprowadzenie routera w tryb upgrade',
 '6. Statyczny IP + 100 Mbps Full Duplex',
 '7. Uruchomienie HuaweiMUT.exe',
 '8. Monitoring + telnet diag restore default',
 '9. Przywrocenie DHCP / WiFi / Tailscale'
) | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
Write-Host ""
if (-not (Read-YN 'Zaczynamy?')) { Write-Log 'Anulowano.' 'Yellow'; exit }

# ===== KROK 1: BACKUP =====
Write-Section '[1/9] Backup konfiguracji sieci'
$backup = @{ timestamp=(Get-Date).ToString('o'); adapters=@() }
foreach ($a in Get-NetAdapter) {
    # SilentlyContinue + 2>$null bo adaptery Disabled rzucaja niegrozne ostrzezenia
    $cfg = Get-NetIPConfiguration -InterfaceAlias $a.Name -ErrorAction SilentlyContinue 2>$null
    $ip4 = $cfg.IPv4Address | Select-Object -First 1
    $dhcp = (Get-NetIPInterface -InterfaceAlias $a.Name -AddressFamily IPv4 -ErrorAction SilentlyContinue 2>$null).Dhcp
    $dns  = (Get-DnsClientServerAddress -InterfaceAlias $a.Name -AddressFamily IPv4 -ErrorAction SilentlyContinue 2>$null).ServerAddresses
    $backup.adapters += @{
        Name=$a.Name; Status="$($a.Status)"; IPv4=$ip4.IPAddress; Prefix=$ip4.PrefixLength
        Gateway=($cfg.IPv4DefaultGateway | Select-Object -First 1).NextHop
        Dhcp="$dhcp"; Dns=$dns
    }
}
$backup | ConvertTo-Json -Depth 5 | Set-Content -Path $backupFile -Encoding UTF8
Write-Log "Backup zapisany: $backupFile" 'Green'
foreach ($adp in $backup.adapters) {
    Write-Log ("  {0,-30} {1,-12} IPv4={2,-16} Gw={3,-15} DHCP={4}" -f $adp.Name,$adp.Status,$adp.IPv4,$adp.Gateway,$adp.Dhcp) 'DarkGray'
}

# ===== KROK 2: WYBOR FIRMWARE =====
Write-Section '[2/9] Wybor firmware'
$bins = Get-ChildItem -Path $scriptDir -Filter 'WS7200-20_*.bin' | Sort-Object Name
if (-not $bins) { Write-Log 'BLAD: brak plikow .bin WS7200.' 'Red'; Wait-Enter; exit 1 }
$rec = $bins | Where-Object { $_.Name -match 'debug|recovery' } | Select-Object -First 1
if (-not $rec) { $rec = $bins | Where-Object { $_.Name -match '10\.0\.5\.17|10\.0\.5\.26' } | Select-Object -First 1 }
if (-not $rec) { $rec = $bins[0] }

Write-Host "Dostepne firmware:" -ForegroundColor White
for ($i=0; $i -lt $bins.Count; $i++) {
    $mark = if ($bins[$i].Name -eq $rec.Name) { ' <-- ZALECANE (recovery)' } else { '' }
    $mb = [math]::Round($bins[$i].Length/1MB,2)
    Write-Host ("  [{0}] {1,-50} {2} MB{3}" -f ($i+1), $bins[$i].Name, $mb, $mark) -ForegroundColor Gray
}
$pick = Read-Host "Numer [Enter = zalecane]"
$binFile = if ([string]::IsNullOrWhiteSpace($pick)) { $rec } else {
    $idx = ([int]$pick)-1
    if ($idx -lt 0 -or $idx -ge $bins.Count) { Write-Log 'Zly numer.' 'Red'; exit 1 }
    $bins[$idx]
}
Write-Log "Wybrano: $($binFile.Name)" 'Green'
if ($binFile.Length -lt 10MB) {
    Write-Log "OSTRZEZENIE: plik <10MB - moze byc uszkodzony!" 'Red'
    if (-not (Read-YN 'Mimo to kontynuowac?' $false)) { exit 1 }
}

# Walidacja .ini
$iniFile = [System.IO.Path]::ChangeExtension($binFile.FullName, '.ini')
$regen = $false
if (-not (Test-Path $iniFile)) { Write-Log "Brak .ini - regeneruje" 'Yellow'; $regen = $true }
else {
    $iniText = Get-Content $iniFile -Raw
    if ($iniText -match 'FIRMWARE_CRC_SUM=(\d+)') {
        $iniCrc = [uint64]$matches[1]
        Write-Log "Licze CRC32 pliku .bin (~$([math]::Round($binFile.Length/1MB))MB) przez Python..." 'DarkGray'
        try {
            $real = Get-Crc32File $binFile.FullName
            if ($real -ne $iniCrc) { Write-Log "CRC niezgodne ($real vs $iniCrc) - regeneruje .ini" 'Yellow'; $regen = $true }
            else { Write-Log "CRC OK: $real" 'Green' }
        } catch {
            Write-Log "Nie udalo sie policzyc CRC ($_) - regeneruje .ini na wszelki wypadek" 'Yellow'
            $regen = $true
        }
    } else { $regen = $true }
}
if ($regen) {
    Push-Location $scriptDir
    try { & python $iniGen $binFile.Name | ForEach-Object { Write-Log "  $_" 'Green' } }
    finally { Pop-Location }
    if (-not (Test-Path $iniFile)) { Write-Log 'BLAD regeneracji .ini' 'Red'; exit 1 }
}
Write-Log "INI: $iniFile" 'DarkGray'

# ===== KROK 3: TELNET + FIREWALL =====
Write-Section '[3/9] Telnet Client + reguly Zapory'
$tf = Get-WindowsOptionalFeature -Online -FeatureName TelnetClient -ErrorAction SilentlyContinue
if ($tf -and $tf.State -ne 'Enabled') {
    Write-Log 'Wlaczam Klient Telnet...' 'Yellow'
    Enable-WindowsOptionalFeature -Online -FeatureName TelnetClient -NoRestart | Out-Null
    Write-Log '  OK' 'Green'
} else { Write-Log 'Klient Telnet OK' 'Green' }

$rules = @(
    @{ N='HuaweiMUT-UDP13456-In';  D='Inbound'  },
    @{ N='HuaweiMUT-UDP13456-Out'; D='Outbound' }
)
foreach ($r in $rules) {
    if (-not (Get-NetFirewallRule -DisplayName $r.N -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $r.N -Direction $r.D -Protocol UDP -LocalPort $multicastPort -Action Allow -Profile Any | Out-Null
        Write-Log "  Dodano: $($r.N)" 'Green'
    } else { Write-Log "  Istnieje: $($r.N)" 'DarkGray' }
}
if (Test-Path $mutPath) {
    foreach ($d in 'Inbound','Outbound') {
        $n = "HuaweiMUT-App-$d"
        if (-not (Get-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -DisplayName $n -Direction $d -Program $mutPath -Action Allow -Profile Any | Out-Null
            Write-Log "  Dodano per-app: $n" 'Green'
        }
    }
}

# ===== KROK 4: WYLACZ INNE INTERFEJSY =====
Write-Section '[4/9] Wylaczanie innych interfejsow'
$disabled = @()
foreach ($n in 'Wi-Fi','Tailscale','Bluetooth Network Connection') {
    $a = Get-NetAdapter -Name $n -ErrorAction SilentlyContinue
    if ($a -and $a.Status -ne 'Disabled') {
        try { Disable-NetAdapter -Name $n -Confirm:$false -ErrorAction Stop; $disabled += $n; Write-Log "  Wylaczono: $n" 'Green' }
        catch { Write-Log "  BLAD wylaczania $n : $($_.Exception.Message)" 'Red' }
    } elseif ($a) { Write-Log "  Juz off: $n" 'DarkGray' }
}
foreach ($a in (Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.Name -ne $ifAlias -and $_.InterfaceDescription -match 'VMware|Hyper-V|VirtualBox|TAP|OpenVPN|WireGuard' })) {
    try { Disable-NetAdapter -Name $a.Name -Confirm:$false; $disabled += $a.Name; Write-Log "  Wylaczono wirtualny: $($a.Name)" 'Green' } catch {}
}
$disabled | Set-Content -Path (Join-Path $scriptDir '_disabled_adapters.txt') -Encoding UTF8

# ===== KROK 5: TRYB UPGRADE + ETHERNET UP =====
Write-Section '[5/9] Wprowadzenie routera w tryb upgrade'
Write-Host @"
WYKONAJ FIZYCZNIE TERAZ:
  a) ODEPNIJ zasilanie routera
  b) Wepnij kabel z PC do dowolnego portu LAN routera (NIE WAN!)
  c) WCISNIJ i TRZYMAJ przycisk H / AI Life
  d) Trzymajac H wepnij zasilanie
  e) Trzymaj H jeszcze 2-3 sekundy, potem PUSC
  f) Dioda powinna byc STALA (czerwona/pomaranczowa, NIE pulsujaca)

Jesli dioda dalej miga w bootloopie -> odepnij zasilanie i powtorz c-e.
"@ -ForegroundColor White
Wait-Enter '>>> Gdy dioda jest stala, nacisnij Enter <<<'

Write-Log "Czekam na karte $ifAlias = Up (max 15s)..." 'Cyan'
$linkOk = $false; $a = $null
for ($i=1; $i -le 15; $i++) {
    $a = Get-NetAdapter -Name $ifAlias -ErrorAction SilentlyContinue
    if ($a -and $a.Status -eq 'Up') { Write-Log "  UP po $i s, link: $($a.LinkSpeed)" 'Green'; $linkOk=$true; break }
    Write-Host ("  proba {0}/15 - {1}" -f $i, ($a.Status)) -ForegroundColor DarkGray
    Start-Sleep -Seconds 1
}
if (-not $linkOk) {
    Write-Log "Karta nie wstala (status: $($a.Status))" 'Red'
    Write-Host "Sprawdz: kabel, port LAN (nie WAN), tryb upgrade routera." -ForegroundColor Yellow
    if (-not (Read-YN 'Kontynuowac mimo to?' $false)) { exit 1 }
}

# ===== KROK 6: 100Mbps + STATYCZNY IP =====
Write-Section '[6/9] Konfiguracja karty Ethernet'
try {
    $sp = Get-NetAdapterAdvancedProperty -Name $ifAlias -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'Speed.*Duplex|Speed.*and.*Duplex|Predkosc' } | Select-Object -First 1
    if ($sp) {
        Write-Log "  Speed/Duplex (przed): $($sp.DisplayValue)" 'DarkGray'
        $tgt = $sp.ValidDisplayValues | Where-Object { $_ -match '100\s*Mbps.*Full|100.*Pelny' } | Select-Object -First 1
        if ($tgt -and $sp.DisplayValue -ne $tgt) {
            Set-NetAdapterAdvancedProperty -Name $ifAlias -DisplayName $sp.DisplayName -DisplayValue $tgt
            Start-Sleep -Seconds 2
            Write-Log "  Ustawiono: $tgt (lepsze dla multicast)" 'Green'
        }
    }
} catch { Write-Log "  Speed/Duplex skip: $($_.Exception.Message)" 'DarkGray' }

try {
    Set-NetIPInterface -InterfaceAlias $ifAlias -Dhcp Disabled -ErrorAction Stop
    Get-NetIPAddress -InterfaceAlias $ifAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
    Get-NetRoute -InterfaceAlias $ifAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' } | Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    New-NetIPAddress -InterfaceAlias $ifAlias -IPAddress $staticIP -PrefixLength $staticPrefix -ErrorAction Stop | Out-Null
    Write-Log "  Statyczny IP $staticIP/$staticPrefix nadany (bez bramy)" 'Green'
} catch { Write-Log "BLAD IP: $($_.Exception.Message)" 'Red'; exit 1 }

try { Disable-NetAdapterBinding -Name $ifAlias -ComponentID 'ms_tcpip6' -ErrorAction SilentlyContinue; Write-Log '  IPv6 wylaczone na karcie' 'DarkGray' } catch {}

$ipNow = (Get-NetIPAddress -InterfaceAlias $ifAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress
Write-Log "  Karta '$ifAlias' IP: $ipNow" 'Cyan'

# ===== KROK 7: URUCHOM MUT =====
Write-Section '[7/9] Uruchamianie HuaweiMUT.exe'
Write-Host @"
###########################################################################
##                                                                       ##
##   UWAGA KRYTYCZNA - przeczytaj zanim klikniesz w MUT:                 ##
##                                                                       ##
##   W sekcji 'Cover partitions' MUSZA byc zaznaczone OBA checkboxy:    ##
##                                                                       ##
##      [X] CFE        0x00000000-0x0000ffff                            ##
##      [X] kernelfs   0x00010000-0x003fffff                            ##
##                                                                       ##
##   Jesli zaznaczysz TYLKO kernelfs:                                    ##
##   - bootloader (CFE) zostanie nieuszkodzony popsuty                   ##
##   - router dalej bedzie w bootloopie po flashu (zielona dioda klamie) ##
##                                                                       ##
##   Domyslnie MUT zaznacza tylko kernelfs - kliknij CFE samodzielnie!  ##
##                                                                       ##
###########################################################################

Co kliknac w HuaweiMUT.exe (po kolei):
  1) Netcard -> Refresh -> wybierz wpis z 'IP:$staticIP'
                          (NIE wpis z IP:0.0.0.0!)
  2) Multicast IP: $multicastIP        (juz powinno byc)
  3) Interval:     2                   (jak nie zadziala - zmien na 5)
  4) Image file -> Open -> wskaz:
        $($binFile.FullName)
     (.ini juz lezy obok, MUT zaladuje automatycznie)
  5) Cover partitions: ZAZNACZ OBA --> CFE i kernelfs (BARDZO WAZNE!)
  6) Times of sending image: zostaw domyslne (1)
  7) Kliknij Start

Co bedzie sie dzialo na routerze:
  - Czerwona dioda zacznie SZYBKO migac           (transfer multicast trwa)
  - Po kilku/kilkunastu min: WOLNE miganie czerw. (zapis na flash NAND)
  - WAZNE: w tej fazie NIE WYLACZAJ ZASILANIA!
  - Dioda zaswieci na ZIELONO                     (transmisja+zapis OK)

Jesli problem - dioda swieci STALE czerwono (nie miga w ogole):
  - multicast nie dochodzi do routera
  - sprawdz: czy MUT pokazuje IP:$staticIP (nie 0.0.0.0)?
  - zwieksz Interval do 5
  - kliknij Start jeszcze raz
  - jak nie pomoze - powtorz tryb upgrade (kabel + H + zasilanie)
"@ -ForegroundColor White

if (Test-Path $mutPath) {
    if (Read-YN 'Uruchomic teraz HuaweiMUT.exe?') {
        Start-Process -FilePath $mutPath -WorkingDirectory (Split-Path $mutPath)
        Write-Log "  Uruchomiono MUT" 'Green'
    }
}
Wait-Enter '>>> Po pomyslnym flashu (zielona dioda), nacisnij Enter <<<'

# ===== KROK 8: MONITORING + TELNET diag restore default =====
Write-Section '[8/9] Po-flashowy reset routera + telnet'
Write-Host @"
Teraz:
  1) Wyciagnij i wepnij zasilanie routera (kabel zostaw wpiety)
  2) Dioda powinna byc pomaranczowo-czerwona (debug firmware) - to OK
"@ -ForegroundColor White
Wait-Enter '>>> Po podaniu zasilania nacisnij Enter <<<'

Write-Log "Pinguje $routerIP (max 30s)..." 'Cyan'
$pingOk = $false
for ($i=1; $i -le 30; $i++) {
    if (Test-Connection -ComputerName $routerIP -Count 1 -Quiet -ErrorAction SilentlyContinue) {
        Write-Log "  Router odpowiada na ping (po $i s)" 'Green'; $pingOk=$true; break
    }
    Start-Sleep -Seconds 1
}
if (-not $pingOk) { Write-Log "Router NIE odpowiada na ping. Sprawdz dioda + kabel." 'Yellow' }

Write-Host @"
Otworze automatycznie nowe okno cmd z telnet $routerIP.
Po polaczeniu wpisz polecenie:
  diag restore default
i nacisnij Enter. Poczekaj ~5s, zamknij okno.
"@ -ForegroundColor White
if ($pingOk -and (Read-YN "Otworzyc telnet $routerIP teraz?")) {
    Start-Process cmd -ArgumentList "/k","title TELNET $routerIP - wpisz: diag restore default && telnet $routerIP"
    Wait-Enter '>>> Po wykonaniu diag restore default w drugim oknie nacisnij Enter <<<'
}
Write-Host "Wylacz i wlacz zasilanie routera. Powinien wstac z fabryczna konfiguracja." -ForegroundColor White
Wait-Enter '>>> Po restarcie routera nacisnij Enter, zeby przywrocic Twoj internet <<<'

# ===== KROK 9: RESTORE =====
Write-Section '[9/9] Przywracanie internetu na PC'
try {
    Get-NetIPAddress -InterfaceAlias $ifAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
    Get-NetRoute -InterfaceAlias $ifAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' } | Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    Set-NetIPInterface -InterfaceAlias $ifAlias -Dhcp Enabled -ErrorAction Stop
    Set-DnsClientServerAddress -InterfaceAlias $ifAlias -ResetServerAddresses -ErrorAction SilentlyContinue
    Enable-NetAdapterBinding -Name $ifAlias -ComponentID 'ms_tcpip6' -ErrorAction SilentlyContinue
    Write-Log "  $ifAlias przywrocony do DHCP" 'Green'
} catch { Write-Log "  Restore IP: $($_.Exception.Message)" 'Red' }

$disabledList = if (Test-Path (Join-Path $scriptDir '_disabled_adapters.txt')) {
    Get-Content (Join-Path $scriptDir '_disabled_adapters.txt')
} else { @('Wi-Fi','Tailscale','Bluetooth Network Connection') }
foreach ($n in $disabledList) {
    $a = Get-NetAdapter -Name $n -ErrorAction SilentlyContinue
    if ($a -and $a.Status -eq 'Disabled') {
        try { Enable-NetAdapter -Name $n -Confirm:$false -ErrorAction Stop; Write-Log "  Wlaczono: $n" 'Green' }
        catch { Write-Log "  Nie udalo sie wlaczyc $n : $($_.Exception.Message)" 'Red' }
    }
}
ipconfig /renew | Out-Null

Write-Section 'GOTOWE'
Write-Host "Skrypt zakonczony. Log: $logFile" -ForegroundColor Green
Write-Host "Backup sieci (na wypadek problemow): $backupFile" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Co dalej z routerem:" -ForegroundColor White
Write-Host "  - Sprawdz czy widzisz siec WiFi 'HUAWEI-...'" -ForegroundColor Gray
Write-Host "  - Konfiguracja: http://192.168.3.1" -ForegroundColor Gray
Write-Host "  - Po skonfigurowaniu mozesz w GUI zaktualizowac na nowszy firmware" -ForegroundColor Gray
Wait-Enter 'Nacisnij Enter aby zamknac okno'

