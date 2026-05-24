#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$ifAlias = 'Ethernet'
$ip      = '192.168.1.5'
$prefix  = 24

Write-Host "=== Ustawianie statycznego IP dla flashowania Huawei ===" -ForegroundColor Cyan

# Stan karty
$adapter = Get-NetAdapter -Name $ifAlias -ErrorAction SilentlyContinue
if (-not $adapter) { Write-Host "Brak karty $ifAlias" -ForegroundColor Red; exit 1 }
Write-Host ("Karta {0}: status={1}" -f $adapter.Name, $adapter.Status) -ForegroundColor Gray
if ($adapter.Status -ne 'Up') {
    Write-Host "UWAGA: karta jest $($adapter.Status). Wepnij kabel do routera (port LAN) i wlacz zasilanie routera dopiero pozniej." -ForegroundColor Yellow
}

# Wylaczam Wi-Fi i Tailscale zeby multicast szedl przez Ethernet
foreach ($n in 'Wi-Fi','Tailscale') {
    $a = Get-NetAdapter -Name $n -ErrorAction SilentlyContinue
    if ($a -and $a.Status -eq 'Up') {
        Disable-NetAdapter -Name $n -Confirm:$false
        Write-Host "Wylaczono karte: $n" -ForegroundColor Green
    }
}

# DHCP off + czyszczenie
Set-NetIPInterface -InterfaceAlias $ifAlias -Dhcp Disabled
Get-NetIPAddress -InterfaceAlias $ifAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
Get-NetRoute -InterfaceAlias $ifAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' } | Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue

# Nadaj statyczny
New-NetIPAddress -InterfaceAlias $ifAlias -IPAddress $ip -PrefixLength $prefix | Out-Null
Write-Host "Ustawiono IP: $ip/$prefix (bez bramy - nie potrzebna do multicastu) na $ifAlias" -ForegroundColor Green

Write-Host ""
Write-Host "Aktualna konfiguracja:" -ForegroundColor Cyan
Get-NetIPAddress -InterfaceAlias $ifAlias -AddressFamily IPv4 | Select-Object IPAddress,PrefixLength,InterfaceAlias | Format-Table -AutoSize
Read-Host "Nacisnij Enter aby zamknac"
