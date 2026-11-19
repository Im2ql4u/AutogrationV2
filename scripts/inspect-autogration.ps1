[CmdletBinding()]
param(
    [ValidateSet(
        "Status",
        "Runs",
        "Task",
        "Bundle",
        "ResultsJson",
        "ResultsParquet",
        "Assumptions",
        "Logs",
        "CdfAssets"
    )]
    [string]$Mode = "Status",

    [string]$TaskId,

    [ValidateRange(1, 1000)]
    [int]$Limit = 100,

    [string]$ApiBaseUrl = $(
        if ($env:AUTOGRATION_API_URL) {
            $env:AUTOGRATION_API_URL
        } else {
            "http://localhost:5201/api/v1"
        }
    ),

    [string]$OutDirectory = (Join-Path $PSScriptRoot "..\artifacts\autogration")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$apiBase = $ApiBaseUrl.TrimEnd("/")

function Require-TaskId {
    if ([string]::IsNullOrWhiteSpace($TaskId)) {
        throw "-TaskId is required for mode $Mode."
    }
}

function Invoke-ReadOnlyJson {
    param([string]$Path)

    $uri = "$apiBase$Path"
    try {
        return Invoke-RestMethod -Method Get -Uri $uri -Headers @{ Accept = "application/json" }
    } catch {
        throw "Read-only request failed: GET $uri. Start the backend or set -ApiBaseUrl. $($_.Exception.Message)"
    }
}

function Save-ReadOnlyDownload {
    param(
        [string]$Path,
        [string]$FileName
    )

    $uri = "$apiBase$Path"
    New-Item -ItemType Directory -Path $OutDirectory -Force | Out-Null
    $destination = Join-Path $OutDirectory $FileName

    try {
        Invoke-WebRequest -Method Get -Uri $uri -OutFile $destination
    } catch {
        throw "Read-only download failed: GET $uri. $($_.Exception.Message)"
    }

    Get-Item $destination | Select-Object FullName, Length, LastWriteTime
}

function Write-JsonResult {
    param($Value)
    $Value | ConvertTo-Json -Depth 32
}

switch ($Mode) {
    "Status" {
        $runs = Invoke-ReadOnlyJson "/runs/?limit=1"
        [pscustomobject]@{
            ApiBaseUrl = $apiBase
            Reachable = $true
            ReturnedRuns = @($runs.runs).Count
            NextContinuationToken = $runs.continuation_token
        } | Format-List
    }
    "Runs" {
        Write-JsonResult (Invoke-ReadOnlyJson "/runs/?limit=$Limit")
    }
    "Task" {
        Require-TaskId
        $encodedTaskId = [uri]::EscapeDataString($TaskId)
        Write-JsonResult (Invoke-ReadOnlyJson "/tasks/?task_id=$encodedTaskId")
    }
    "Bundle" {
        Require-TaskId
        Save-ReadOnlyDownload "/runs/$TaskId" "$TaskId-data-exchange.json"
    }
    "ResultsJson" {
        Require-TaskId
        Save-ReadOnlyDownload "/runs/$TaskId/results" "$TaskId-results.json"
    }
    "ResultsParquet" {
        Require-TaskId
        Save-ReadOnlyDownload "/runs/$TaskId/results/parquet" "$TaskId-results.parquet"
    }
    "Assumptions" {
        Require-TaskId
        Save-ReadOnlyDownload "/runs/$TaskId/assumptions" "$TaskId-assumptions.json"
    }
    "Logs" {
        Require-TaskId
        Write-JsonResult (Invoke-ReadOnlyJson "/tasks/$TaskId/logs")
    }
    "CdfAssets" {
        Write-JsonResult (Invoke-ReadOnlyJson "/assets/")
    }
}