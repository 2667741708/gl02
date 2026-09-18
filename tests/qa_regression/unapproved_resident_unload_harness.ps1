[CmdletBinding()]
param([Parameter(Mandatory)][string]$Controller,[Parameter(Mandatory)][string]$Mode)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8=[Text.UTF8Encoding]::new($false,$true)
[Console]::InputEncoding=$Utf8
[Console]::OutputEncoding=$Utf8
$OutputEncoding=$Utf8
$PSDefaultParameterValues['*:Encoding']='utf8'
Set-StrictMode -Version Latest
$Tokens=$null
$Errors=$null
$Ast=[Management.Automation.Language.Parser]::ParseFile($Controller,[ref]$Tokens,[ref]$Errors)
if ($Errors.Count) { throw 'Controller syntax failed' }
$Functions=@($Ast.FindAll({param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst] -and $Node.Name -ceq 'Assert-UnapprovedResidentUnloadBoundary'},$true))
if ($Functions.Count -ne 1) { throw 'Boundary function inventory changed' }
# Load the single pure assertion only; no source top-level statements are evaluated.
. ([scriptblock]::Create($Functions[0].Extent.Text))
function Invoke-RestMethod { throw 'Synthetic boundary forbids network' }
function Invoke-WebRequest { throw 'Synthetic boundary forbids network' }
function Get-ScheduledTask { throw 'Synthetic boundary forbids tasks' }
function Get-FileHash { throw 'Synthetic boundary forbids controller file I/O' }
$Approved='e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
$Unapproved='9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb'
$ManagerHash='1f871a8bbbaa553233d318b3d019a5a63e68be38d0f0caa7d29cca731d44434f'
$CatalogHash='723c4f2c6e5c2093060db8beaf5338dc857477a5b10d5db9f95ec79dfdc2f57a'
$Tags=@([pscustomobject]@{name='chiqiongblastfuenace:1';digest=$Approved},
        [pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$Unapproved})
$Resident=@([pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$Unapproved})
$TaskEnabled=$false
$TaskState='Disabled'
switch ($Mode) {
    'tags_null' { $Tags=$null }
    'tags_empty' { $Tags=@() }
    'tags_string' { $Tags='unknown' }
    'tags_dictionary' { $Tags=@{name='chiqiongblastfuenace:latest';digest=$Unapproved} }
    'tags_single_object' { $Tags=$Tags[0] }
    'tags_missing_fixed' { $Tags=@($Tags[1]) }
    'tags_missing_public' { $Tags=@($Tags[0]) }
    'tags_duplicate_fixed' { $Tags+=@($Tags[0]) }
    'tags_duplicate_public' { $Tags+=@($Tags[1]) }
    'fixed_name_case' { $Tags[0].name='CHIQIONGBLASTFUENACE:1' }
    'fixed_wrong_tag' { $Tags[0].name='chiqiongblastfuenace:0' }
    'fixed_wrong_digest' { $Tags[0].digest=$Unapproved }
    'fixed_digest_upper' { $Tags[0].digest=$Approved.ToUpperInvariant() }
    'fixed_digest_short' { $Tags[0].digest=$Approved.Substring(0,12) }
    'public_name_case' { $Tags[1].name='CHIQIONGBLASTFUENACE:LATEST' }
    'public_wrong_digest' { $Tags[1].digest=$Approved }
    'public_digest_upper' { $Tags[1].digest=$Unapproved.ToUpperInvariant() }
    'public_digest_short' { $Tags[1].digest=$Unapproved.Substring(0,12) }
    'tags_missing_name' { $Tags=@([pscustomobject]@{digest=$Approved},$Tags[1]) }
    'tags_missing_digest' { $Tags=@([pscustomobject]@{name='chiqiongblastfuenace:1'},$Tags[1]) }
    'resident_null' { $Resident=$null }
    'resident_empty' { $Resident=@() }
    'resident_string' { $Resident='unknown' }
    'resident_dictionary' { $Resident=@{name='chiqiongblastfuenace:latest';digest=$Unapproved} }
    'resident_single_object' { $Resident=$Resident[0] }
    'resident_multiple' { $Resident+=@([pscustomobject]@{name='chiqiongblastfuenace:1';digest=$Approved}) }
    'resident_duplicate' { $Resident+=@($Resident[0]) }
    'resident_wrong_name' { $Resident[0].name='chiqiongblastfuenace:1' }
    'resident_name_case' { $Resident[0].name='CHIQIONGBLASTFUENACE:LATEST' }
    'resident_wrong_digest' { $Resident[0].digest=$Approved }
    'resident_digest_upper' { $Resident[0].digest=$Unapproved.ToUpperInvariant() }
    'resident_digest_short' { $Resident[0].digest=$Unapproved.Substring(0,12) }
    'resident_missing_name' { $Resident=@([pscustomobject]@{digest=$Unapproved}) }
    'resident_missing_digest' { $Resident=@([pscustomobject]@{name='chiqiongblastfuenace:latest'}) }
    'manager_wrong' { $ManagerHash='0'*64 }
    'manager_upper' { $ManagerHash=$ManagerHash.ToUpperInvariant() }
    'manager_short' { $ManagerHash=$ManagerHash.Substring(0,12) }
    'catalog_wrong' { $CatalogHash='0'*64 }
    'catalog_upper' { $CatalogHash=$CatalogHash.ToUpperInvariant() }
    'catalog_short' { $CatalogHash=$CatalogHash.Substring(0,12) }
    'task_enabled' { $TaskEnabled=$true }
    'task_null_enabled' { $TaskEnabled=$null }
    'task_string_enabled' { $TaskEnabled='false' }
    'task_numeric_enabled' { $TaskEnabled=0 }
    'task_running' { $TaskState='Running' }
    'task_running_case' { $TaskState='running' }
    'task_ready' { $TaskState='Ready' }
    'task_queued' { $TaskState='Queued' }
    'task_unknown' { $TaskState='Unknown' }
    'task_empty' { $TaskState='' }
    'task_null_state' { $TaskState=$null }
    'task_disabled_case' { $TaskState='disabled' }
    'task_numeric_state' { $TaskState='1' }
    'task_numeric_unknown' { $TaskState='0' }
    'task_numeric_queued' { $TaskState='2' }
    'task_numeric_ready' { $TaskState='3' }
    'task_numeric_running' { $TaskState='4' }
    'task_numeric_invalid' { $TaskState='01' }
    'extra_registered_tag' { $Tags+=@([pscustomobject]@{name='synthetic:unused';digest='0'*64}) }
    'healthy' {}
    default { throw 'Unknown synthetic fixture mode' }
}
$Failed=$false
$ErrorType=$null
try {
    Assert-UnapprovedResidentUnloadBoundary -Tags $Tags -Resident $Resident -ManagerHash $ManagerHash -CatalogHash $CatalogHash -TaskEnabled $TaskEnabled -TaskState $TaskState
} catch { $Failed=$true;$ErrorType=$_.Exception.GetType().FullName }
@{failed=$Failed;error_type=$ErrorType;extracted_functions=@($Functions[0].Name);top_level_executed=$false;network_calls=0;model_operations=0;task_operations=0} | ConvertTo-Json -Depth 4
