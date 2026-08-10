$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$process = Get-Process -Name 'aTrustTray' |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1
if (-not $process) {
    throw 'aTrust main window was not found.'
}

$root = [Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
$condition = [Windows.Automation.Condition]::TrueCondition
$scope = [Windows.Automation.TreeScope]::Descendants
$elements = $root.FindAll($scope, $condition)
$rows = foreach ($element in $elements) {
    $current = $element.Current
    if ($current.Name -or $current.AutomationId -or $current.ControlType.ProgrammaticName) {
        [PSCustomObject]@{
            Name = $current.Name
            AutomationId = $current.AutomationId
            ControlType = $current.ControlType.ProgrammaticName
            IsEnabled = $current.IsEnabled
            IsKeyboardFocusable = $current.IsKeyboardFocusable
        }
    }
}
$rows | ConvertTo-Json -Depth 4
