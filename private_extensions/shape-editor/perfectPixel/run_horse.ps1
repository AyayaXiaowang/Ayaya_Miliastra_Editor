param(
    [string]$InputPath = "",
    [string]$OutputPath = ""
)

$Runner = Join-Path $PSScriptRoot "run_one.py"

if ([string]::IsNullOrWhiteSpace($InputPath)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path

    # Build folder/file names from Unicode code points to avoid script encoding issues.
    $FolderName = ([char]0x50CF) + ([char]0x7D20) # folder name
    $FileName = ([char]0x9A6C) + ([char]0x513F) + ".png" # file name

    $InputPath = Join-Path (Join-Path $ProjectRoot $FolderName) $FileName
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $InFile = Get-Item -LiteralPath $InputPath
    $OutputPath = Join-Path $InFile.DirectoryName ($InFile.BaseName + ".perfect" + $InFile.Extension)
}

python $Runner $InputPath -o $OutputPath

