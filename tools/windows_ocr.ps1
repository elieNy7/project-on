# Windows OCR (fr-FR), used by tools/import_books.py for scanned brochures.
# -ListFile: text file with one image path per line. Prints one JSON object
# per image (its lines and their pixel boxes), UTF-8.
param([string]$ListFile)
$ErrorActionPreference = 'Stop'
$Images = Get-Content -LiteralPath $ListFile -Encoding UTF8 | Where-Object { $_.Trim() }
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await($op, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait() | Out-Null
    $task.Result
}
$lang = New-Object Windows.Globalization.Language 'fr-FR'
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
foreach ($path in $Images) {
    $path = (Get-Item -LiteralPath $path).FullName
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $lines = @()
    foreach ($line in $result.Lines) {
        $words = @($line.Words)
        $x0 = ($words | ForEach-Object { $_.BoundingRect.X } | Measure-Object -Minimum).Minimum
        $y0 = ($words | ForEach-Object { $_.BoundingRect.Y } | Measure-Object -Minimum).Minimum
        $x1 = ($words | ForEach-Object { $_.BoundingRect.X + $_.BoundingRect.Width } | Measure-Object -Maximum).Maximum
        $y1 = ($words | ForEach-Object { $_.BoundingRect.Y + $_.BoundingRect.Height } | Measure-Object -Maximum).Maximum
        $lines += [pscustomobject]@{ text = $line.Text; x0 = $x0; y0 = $y0; x1 = $x1; y1 = $y1 }
    }
    $stream.Dispose()
    [pscustomobject]@{ image = $path; width = $bitmap.PixelWidth; height = $bitmap.PixelHeight; lines = $lines } |
        ConvertTo-Json -Depth 4 -Compress
}
