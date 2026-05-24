#Requires -RunAsAdministrator
$ErrorActionPreference = 'Continue'
$ifAlias = 'Ethernet'
$ip      = '192.168.1.5'
$prefix  = 24

function Wait-Step($msg) {
    Write-Host ""
    Write-Host $msg -ForegroundColor Yellow
    Read-Host "Nacisnij Enter gdy bedzie gotowe"
}

Clear-Host
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  Huawei WS7200 - przygotowanie PC do flashowania (MUT)" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Ten skrypt:" -ForegroundColor Gray
Write-Host "  1) WYLACZY Wi-Fi i Tailscale (multicast musi isc tylko przez kabel)" -ForegroundColor Gray
Write-Host "  2) Poprosi Cie o wpiecie kabla i wlaczenie routera w tryb upgrade" -ForegroundColor Gray
Write-Host "  3) Sprawdzi czy karta Ethernet wstala" -ForegroundColor Gray
Write-Host "  4) Ustawi statyczny IP 192.168.1.5/24 na karcie Ethernet" -ForegroundColor Gray
Write-Host "  5) Pokaze co dalej zrobic w aplikacji HuaweiMUT.exe" -ForegroundColor Gray
Write-Host ""
Write-Host "Aby przywrocic internet po flashu uruchom: _restore_dhcp.ps1" -ForegroundColor DarkGray
Write-Host ""
$go = Read-Host "Kontynuowac? [T/n]"
if ($go -match '^[nN]') { Write-Host "Anulowano."; exit }

# =========================================================================
# KROK 1: WYLACZ WSZYSTKO POZA ETHERNET (PIERWSZA RZECZ!)
# =========================================================================
Write-Host ""
Write-Host "[1/5] Wylaczam Wi-Fi i Tailscale ..." -ForegroundColor Cyan
foreach ($n in 'Wi-Fi','Tailscale','Bluetooth Network Connection') {
    $a = Get-NetAdapter -Name $n -ErrorAction SilentlyContinue
    if ($a) {
        if ($a.Status -ne 'Disabled') {
            try {
                Disable-NetAdapter -Name $n -Confirm:$false -ErrorAction Stop
                Write-Host "  Wylaczono: $n" -ForegroundColor Green
            } catch {
                Write-Host "  Nie udalo sie wylaczyc $n : $_" -ForegroundColor Red
            }
        } else {
            Write-Host "  Juz wylaczone: $n" -ForegroundColor DarkGray
        }
    }
}
Start-Sleep -Seconds 2

# Wyswietl pozostale aktywne karty
Write-Host ""
Write-Host "Aktywne karty po wylaczeniu:" -ForegroundColor Gray
Get-NetAdapter | Where-Object { $_.Status -ne 'Disabled' } | Select-Object Name,Status,LinkSpeed | Format-Table -AutoSize

# =========================================================================
# KROK 2: INSTRUKCJA DLA UZYTKOWNIKA
# =========================================================================
Write-Host ""
Write-Host "[2/5] WYKONAJ FIZYCZNIE:" -ForegroundColor Cyan
Write-Host "  a) ODEPNIJ zasilanie routera." -ForegroundColor White
Write-Host "  b) Wepnij kabel z PC do portu LAN routera (NIE do WAN/Internet)." -ForegroundColor White
Write-Host "  c) WCISNIJ i TRZYMAJ przycisk H (AI Life) na routerze." -ForegroundColor White
Write-Host "  d) Trzymajac H wepnij zasilanie. Trzymaj H jeszcze ~2 sekundy. Puscic." -ForegroundColor White
Write-Host "  e) Dioda powinna byc STALA CZERWONA (nie pulsujaca jak w bootloopie)." -ForegroundColor White
Wait-Step ">>> Wykonaj kroki a-e, potem nacisnij Enter <<<"

# =========================================================================
# KROK 3: SPRAWDZ ETHERNET
# =========================================================================
Write-Host ""
Write-Host "[3/5] Sprawdzam karte Ethernet ..." -ForegroundColor Cyan
$attempts = 0
while ($attempts -lt 10) {
    $a = Get-NetAdapter -Name $ifAlias -ErrorAction SilentlyContinue
    if ($a -and $a.Status -eq 'Up') {
        Write-Host "  Ethernet UP, link: $($a.LinkSpeed)" -ForegroundColor Green
        break
    }
    $attempts++
    Write-Host "  Status: $($a.Status) - czekam 2s (proba $attempts/10)..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 2
}
if (-not $a -or $a.Status -ne 'Up') {
    Write-Host ""
    Write-Host "  UWAGA: Karta Ethernet nadal $($a.Status)." -ForegroundColor Yellow
    Write-Host "  Mozliwe przyczyny:" -ForegroundColor Yellow
    Write-Host "    - kabel nie wpiety lub uszkodzony" -ForegroundColor Yellow
    Write-Host "    - kabel w porcie WAN zamiast LAN" -ForegroundColor Yellow
    Write-Host "    - router nie wszedl w tryb upgrade (powtorz: trzymaj H + wepnij zasilanie)" -ForegroundColor Yellow
    Write-Host "    - router calkowicie martwy" -ForegroundColor Yellow
    $cont = Read-Host "Kontynuowac mimo to? [t/N]"
    if ($cont -notmatch '^[tT]') { Write-Host "Przerwano."; Read-Host "Enter"; exit }
}

# =========================================================================
# KROK 4: USTAW STATYCZNY IP
# =========================================================================
Write-Host ""
Write-Host "[4/5] Ustawiam statyczny IP $ip/$prefix na $ifAlias ..." -ForegroundColor Cyan
try {
    Set-NetIPInterface -InterfaceAlias $ifAlias -Dhcp Disabled -ErrorAction Stop
    Get-NetIPAddress -InterfaceAlias $ifAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
    Get-NetRoute -InterfaceAlias $ifAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' } | Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    New-NetIPAddress -InterfaceAlias $ifAlias -IPAddress $ip -PrefixLength $prefix -ErrorAction Stop | Out-Null
    Write-Host "  OK - karta ma teraz IP: $ip/$prefix" -ForegroundColor Green
} catch {
    Write-Host "  BLAD: $_" -ForegroundColor Red
    Write-Host "  Sprobuj recznie: Set-NetIPInterface -InterfaceAlias Ethernet -Dhcp Disabled; New-NetIPAddress -InterfaceAlias Ethernet -IPAddress 192.168.1.5 -PrefixLength 24" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Aktualne IP na Ethernet:" -ForegroundColor Gray
Get-NetIPAddress -InterfaceAlias $ifAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object IPAddress,PrefixLength,PrefixOrigin | Format-Table -AutoSize

# =========================================================================
# KROK 5: CO ROBIC W MUT
# =========================================================================
Write-Host ""
Write-Host "[5/5] CO TERAZ W APLIKACJI HuaweiMUT.exe:" -ForegroundColor Cyan
Write-Host "  1. Otworz HuaweiMUT.exe (jako Admin) z folderu:" -ForegroundColor White
Write-Host "     $PSScriptRoot\WS7200---WS1000-Firmware-Bins-and-Tools-main\MUT\" -ForegroundColor DarkGray
Write-Host "  2. Kliknij 'Refresh' obok pola Netcard." -ForegroundColor White
Write-Host "  3. Wybierz: 'Realtek Gaming GbE Family Controller ... IP:192.168.1.5'" -ForegroundColor White
Write-Host "     (jesli widzisz IP:0.0.0.0 -> cos nie poszlo z IP, sprawdz powyzej)" -ForegroundColor DarkGray
Write-Host "  4. Multicast IP: 224.0.0.119 (juz jest)" -ForegroundColor White
Write-Host "  5. Interval: 2" -ForegroundColor White
Write-Host "  6. Image file: WS7200-20_10.0.5.26_main_debug.bin" -ForegroundColor White
Write-Host "     (.ini juz lezy obok w folderze)" -ForegroundColor DarkGray
Write-Host "  7. Cover partitions: ZAZNACZ OBA (CFE + kernelfs)" -ForegroundColor White
Write-Host "  8. Kliknij Start" -ForegroundColor White
Write-Host ""
Write-Host "Po pomyslnym flashu (zielona dioda):" -ForegroundColor Cyan
Write-Host "  - wylacz/wlacz router (zostawia kabel wpiety)" -ForegroundColor White
Write-Host "  - dioda bedzie pomaranczowo-czerwona = OK" -ForegroundColor White
Write-Host "  - cmd jako Admin: telnet 192.168.1.1" -ForegroundColor White
Write-Host "  - polecenie: diag restore default" -ForegroundColor White
Write-Host "  - poczekaj 5s, wylacz/wlacz router" -ForegroundColor White
Write-Host "  - uruchom _restore_dhcp.ps1 zeby wrocic do normalnego internetu" -ForegroundColor White
Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  PC jest gotowy. Mozesz teraz uruchomic HuaweiMUT.exe" -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Cyan
Read-Host "Nacisnij Enter aby zamknac okno"
