# JSON-lines RPC over stdin/stdout. Credentials arrive only via stdin.
# TCP is opened on the bridge within a persistent PSSession; no listener/firewall change.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$taskEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $taskEncoding
[Console]::OutputEncoding = $taskEncoding
$taskSession = $null
try {
    $taskInit = [Console]::ReadLine() | ConvertFrom-Json
    $taskSecure = ConvertTo-SecureString $taskInit.password -AsPlainText -Force
    $taskCredential = New-Object System.Management.Automation.PSCredential($taskInit.user, $taskSecure)
    $taskOptions = New-PSSessionOption -OpenTimeout ($taskInit.timeout * 1000) -OperationTimeout ($taskInit.timeout * 1000)
    $taskParams = @{
        ComputerName = $taskInit.bridge
        Credential = $taskCredential
        Authentication = 'Negotiate'
        SessionOption = $taskOptions
    }
    if ($taskInit.https) { $taskParams.UseSSL = $true }
    $taskSession = New-PSSession @taskParams
    $taskInit.password = $null
    Invoke-Command -Session $taskSession -ArgumentList $taskInit.host, $taskInit.port, $taskInit.timeout -ScriptBlock {
        param($targetHost, $targetPort, $connectTimeout)
        $script:bridgeTcp = New-Object System.Net.Sockets.TcpClient
        $pendingConnect = $script:bridgeTcp.BeginConnect($targetHost, $targetPort, $null, $null)
        try {
            if (-not $pendingConnect.AsyncWaitHandle.WaitOne($connectTimeout * 1000)) {
                throw 'Target TCP connect timed out'
            }
            $script:bridgeTcp.EndConnect($pendingConnect)
            $script:bridgeStream = $script:bridgeTcp.GetStream()
            $script:bridgeStream.WriteTimeout = $connectTimeout * 1000
        } catch {
            $script:bridgeTcp.Close()
            throw
        } finally { $pendingConnect.AsyncWaitHandle.Close() }
    } | Out-Null
    [Console]::WriteLine('{"ok":true}')
    while ($null -ne ($taskLine = [Console]::ReadLine())) {
        $taskRequest = $taskLine | ConvertFrom-Json
        if ($taskRequest.op -eq 'close') { break }
        $taskReply = Invoke-Command -Session $taskSession -ArgumentList $taskRequest.op, $taskRequest.data, $taskRequest.size -ScriptBlock {
            param($operation, $payload, $size)
            if ($operation -eq 'send') {
                $bytes = [Convert]::FromBase64String($payload)
                $script:bridgeStream.Write($bytes, 0, $bytes.Length)
                return @{ok=$true; count=$bytes.Length}
            }
            if ($operation -ne 'recv') { throw 'Invalid operation' }
            if (-not $script:bridgeStream.DataAvailable) {
                if ($script:bridgeTcp.Client.Poll(0, [System.Net.Sockets.SelectMode]::SelectRead)) {
                    return @{ok=$true; eof=$true; data=''}
                }
                return @{ok=$true; eof=$false; data=''}
            }
            $bytes = New-Object byte[] ([Math]::Min([int]$size, 65536))
            $count = $script:bridgeStream.Read($bytes, 0, $bytes.Length)
            return @{ok=$true; eof=($count -eq 0); data=[Convert]::ToBase64String($bytes, 0, $count)}
        }
        [Console]::WriteLine(($taskReply | ConvertTo-Json -Compress))
    }
} catch {
    # Emit an actionable error without returning credentials or request payload.
    $taskError = $_.Exception.Message
    if ($taskInit.password) { $taskError = $taskError.Replace([string]$taskInit.password, '[redacted]') }
    [Console]::WriteLine((@{ok=$false; error=$taskError} | ConvertTo-Json -Compress))
} finally {
    if ($taskSession) {
        try {
            Invoke-Command -Session $taskSession -ScriptBlock {
                if ($script:bridgeTcp) { $script:bridgeTcp.Close() }
            } -ErrorAction SilentlyContinue | Out-Null
        } finally { Remove-PSSession $taskSession -ErrorAction SilentlyContinue }
    }
}
