#Requires -RunAsAdministrator
$ErrorActionPreference = 'Continue'
$ifAlias = 'Ethernet'

Write-Host "=== Przywracanie DHCP po flashowaniu ===" -ForegroundColor Cyan

Get-NetIPAddress -InterfaceAlias $ifAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
Get-NetRoute -InterfaceAlias $ifAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' } | Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
Set-NetIPInterface -InterfaceAlias $ifAlias -Dhcp Enabled
Set-DnsClientServerAddress -InterfaceAlias $ifAlias -ResetServerAddresses

foreach ($n in 'Wi-Fi','Tailscale') {
    $a = Get-NetAdapter -Name $n -ErrorAction SilentlyContinue
    if ($a -and $a.Status -eq 'Disabled') {
        Enable-NetAdapter -Name $n -Confirm:$false
        Write-Host "Wlaczono karte: $n" -ForegroundColor Green
    }
}

ipconfig /renew | Out-Null
Write-Host "Przywrocono DHCP na $ifAlias." -ForegroundColor Green
Read-Host "Nacisnij Enter aby zamknac"
