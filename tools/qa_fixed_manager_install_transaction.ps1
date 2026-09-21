# OPS-QA-SINGLE-BASE-GUARD-INSTALL-20260917. Function library, no top-level I/O.
function Invoke-FixedManagerInstallTransaction {
    param([hashtable]$Callbacks)
    $TaskTouched=$false
    $InstallAttempted=$false
    $Accepted=$false
    $OriginalEnabled=[bool](& $Callbacks.ReadEnabled)
    try {
        if ($OriginalEnabled) {
            # Take restoration responsibility before a possibly partial task mutation.
            $TaskTouched=$true
            & $Callbacks.Disable
        }
        & $Callbacks.Drain
        & $Callbacks.Preflight
        & $Callbacks.Backup
        $InstallAttempted=$true
        & $Callbacks.Install
        & $Callbacks.Verify
        $Accepted=$true
    } catch {
        if ($InstallAttempted) { & $Callbacks.Rollback }
        throw
    } finally {
        if ($TaskTouched) {
            if ($Accepted) { & $Callbacks.Enable }
            else {
                # Never reactivate the legacy switching manager after failed installation.
                & $Callbacks.Disable
            }
        }
        & $Callbacks.Finish $Accepted $OriginalEnabled
    }
}
