param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$ImagePath
)

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.FileAccessMode, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]

function Wait-WindowsRuntimeOperation {
    param(
        [Parameter(Mandatory = $true)]$Operation,
        [Parameter(Mandatory = $true)][Type]$ResultType
    )

    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq 'AsTask' -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1
        } |
        Select-Object -First 1
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

$stream = $null
$bitmap = $null
try {
    $resolvedPath = (Resolve-Path -LiteralPath $ImagePath).Path
    $file = Wait-WindowsRuntimeOperation `
        ([Windows.Storage.StorageFile]::GetFileFromPathAsync($resolvedPath)) `
        ([Windows.Storage.StorageFile])
    $stream = Wait-WindowsRuntimeOperation `
        ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) `
        ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Wait-WindowsRuntimeOperation `
        ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) `
        ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Wait-WindowsRuntimeOperation `
        ($decoder.GetSoftwareBitmapAsync()) `
        ([Windows.Graphics.Imaging.SoftwareBitmap])
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) {
        throw 'Windows OCR language engine is unavailable.'
    }
    $result = Wait-WindowsRuntimeOperation `
        ($engine.RecognizeAsync($bitmap)) `
        ([Windows.Media.Ocr.OcrResult])
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    [Console]::Write($result.Text)
}
finally {
    if ($null -ne $bitmap) {
        $bitmap.Dispose()
    }
    if ($null -ne $stream) {
        $stream.Dispose()
    }
}
