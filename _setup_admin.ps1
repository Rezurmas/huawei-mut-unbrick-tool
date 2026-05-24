$ErrorActionPreference = 'Continue'
Write-Host "=== Huawei MUT - przygotowanie systemu (jako Admin) ===" -ForegroundColor Cyan
Write-Host ""

# 1) Klient Telnet
Write-Host "[1/3] Instaluje Klient Telnet..." -ForegroundColor Yellow
try {
    $feat = Get-WindowsOptionalFeature -Online -FeatureName TelnetClient
    if ($feat.State -eq 'Enabled') {
        Write-Host "  Juz wlaczony." -ForegroundColor Green
    } else {
        Enable-WindowsOptionalFeature -Online -FeatureName TelnetClient -NoRestart | Out-Null
        Write-Host "  Wlaczony." -ForegroundColor Green
    }
} catch {
    Write-Host "  BLAD: $_" -ForegroundColor Red
}

# 2) Regula firewalla - UDP 13456
Write-Host ""
Write-Host "[2/3] Dodaje reguly Zapory Windows (UDP 13456)..." -ForegroundColor Yellow
$rules = @(
    @{ Name='HuaweiMUT-UDP13456-In';  Direction='Inbound';  Protocol='UDP'; LocalPort=13456 },
    @{ Name='HuaweiMUT-UDP13456-Out'; Direction='Outbound'; Protocol='UDP'; LocalPort=13456 }
)
foreach ($r in $rules) {
    $existing = Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "  Regula '$($r.Name)' juz istnieje - pomijam." -ForegroundColor DarkGray
    } else {
        New-NetFirewallRule -DisplayName $r.Name -Direction $r.Direction -Protocol $r.Protocol -LocalPort $r.LocalPort -Action Allow -Profile Any | Out-Null
        Write-Host "  Dodano: $($r.Name)" -ForegroundColor Green
    }
}

# 3) Regula firewalla per-aplikacja (HuaweiMUT.exe)
Write-Host ""
Write-Host "[3/3] Dodaje reguly per-aplikacja (HuaweiMUT.exe)..." -ForegroundColor Yellow
$mutPath = "c:\Users\rezur\Desktop\ini-firmware-ws7100-ws7200-xd20-main\WS7200---WS1000-Firmware-Bins-and-Tools-main\MUT\HuaweiMUT.exe"
if (Test-Path $mutPath) {
    foreach ($dir in @('Inbound','Outbound')) {
        $name = "HuaweiMUT-App-$dir"
        $existing = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Host "  Regula '$name' juz istnieje - pomijam." -ForegroundColor DarkGray
        } else {
            New-NetFirewallRule -DisplayName $name -Direction $dir -Program $mutPath -Action Allow -Profile Any | Out-Null
            Write-Host "  Dodano: $name" -ForegroundColor Green
        }
    }
} else {
    Write-Host "  Nie znaleziono HuaweiMUT.exe pod sciezka: $mutPath" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== ZAKONCZONO ===" -ForegroundColor Cyan
Write-Host "Mozesz zamknac to okno." -ForegroundColor Gray
Read-Host "Nacisnij Enter aby zamknac"
