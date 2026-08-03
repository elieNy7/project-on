param(
    [Parameter(Mandatory = $true)]
    [string]$Manifest
)

$ErrorActionPreference = 'Stop'
$items = Get-Content -Raw -Encoding UTF8 -LiteralPath $Manifest | ConvertFrom-Json
$powerpoint = $null
$presentation = $null

function Start-PowerPointApplication {
    $application = New-Object -ComObject PowerPoint.Application
    $application.Visible = -1
    $application.DisplayAlerts = 1
    return $application
}

function Stop-PowerPointApplication($application) {
    if ($null -eq $application) { return }
    try { $application.Quit() } catch {}
    try { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($application) } catch {}
}

try {
    $powerpoint = Start-PowerPointApplication
    $index = 0

    foreach ($item in $items) {
        $index += 1
        $source = [string]$item.source
        $output = [string]$item.output
        $presentation = $null
        $restartPowerPoint = $false
        try {
            $parent = Split-Path -Parent $output
            [IO.Directory]::CreateDirectory($parent) | Out-Null
            $presentation = $powerpoint.Presentations.Open(
                $source,
                $true,
                $false,
                $false
            )
            # 24 = ppSaveAsOpenXMLPresentation
            $presentation.SaveAs($output, 24)
            $failureMarker = "$output.failed.txt"
            if (Test-Path -LiteralPath $failureMarker) {
                Remove-Item -LiteralPath $failureMarker -Force
            }
            Write-Output "CONVERTED $index/$($items.Count) $([IO.Path]::GetFileName($source))"
        }
        catch {
            Write-Warning "FAILED $index/$($items.Count) $source :: $($_.Exception.Message)"
            Set-Content -Encoding UTF8 -LiteralPath "$output.failed.txt" -Value $_.Exception.Message
            $restartPowerPoint = $true
        }
        finally {
            if ($null -ne $presentation) {
                try { $presentation.Close() } catch {}
                [void][Runtime.InteropServices.Marshal]::ReleaseComObject($presentation)
                $presentation = $null
            }
        }
        if ($restartPowerPoint) {
            Stop-PowerPointApplication $powerpoint
            $powerpoint = $null
            Start-Sleep -Milliseconds 300
            try {
                $powerpoint = Start-PowerPointApplication
            }
            catch {
                Write-Warning "PowerPoint restart failed: $($_.Exception.Message)"
                Start-Sleep -Seconds 2
                $powerpoint = Start-PowerPointApplication
            }
        }
    }
}
finally {
    Stop-PowerPointApplication $powerpoint
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
