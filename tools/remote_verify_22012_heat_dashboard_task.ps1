$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
& schtasks.exe /query /tn "\BlastFurnaceServices\StandaloneHeatDashboard8891" /fo LIST /v 2>&1 |
    Select-String -Pattern "TaskName|Status|Task To Run|Schedule Type|Start Time|Last Run Time|Last Result"
