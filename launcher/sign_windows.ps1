param([Parameter(Mandatory=$true)][string[]]$Files)
$ErrorActionPreference = 'Stop'
# Optional real certificate from the current user's certificate store. No PFX files/passwords.
$Thumbprint = $env:GITHUB_AI_SIGN_THUMBPRINT
if ($Thumbprint) {
    $Cert = Get-Item "Cert:\CurrentUser\My\$Thumbprint"
    if (-not $Cert.HasPrivateKey) { throw 'Signing certificate has no accessible private key.' }
    foreach ($File in $Files) {
        $ArgsToSign = @{ FilePath=$File; Certificate=$Cert; HashAlgorithm='SHA256' }
        if ($env:GITHUB_AI_TIMESTAMP_URL) { $ArgsToSign.TimestampServer=$env:GITHUB_AI_TIMESTAMP_URL }
        $Result = Set-AuthenticodeSignature @ArgsToSign
        if ($Result.Status -ne 'Valid') { throw "Authenticode validation failed for $File" }
    }
}
foreach ($File in $Files) {
    $Result = Get-AuthenticodeSignature $File
    if ($Result.Status -notin @('Valid','NotSigned')) { throw "Unacceptable signing state: $($Result.Status)" }
    [pscustomobject]@{ File=(Split-Path -Leaf $File); Status=$Result.Status.ToString() }
}
