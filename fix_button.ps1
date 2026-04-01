$lines = Get-Content "c:\Users\kenda\OneDrive\Escritorio\filtros\frontend\planillas_ui.js"

# Insert the new button after line 1524 (index 1523)
$newLines = New-Object System.Collections.ArrayList

for ($i = 0; $i -lt $lines.Count; $i++) {
    [void]$newLines.Add($lines[$i])
    
    # After line 1524 (closing tag of Historial button), add new button
    if ($i -eq 1524) {
        [void]$newLines.Add("                        <button class=""vac-btn vac-btn-accent"" style=""font-size:0.78rem;"" onclick=""generarCartaPrestamo(`${p.id})"">")
        [void]$newLines.Add("                            <i class=""fa-solid fa-file-lines""></i> Carta")
        [void]$newLines.Add("                        </button>")
    }
}

# Save
$newLines | Set-Content "c:\Users\kenda\OneDrive\Escritorio\filtros\frontend\planillas_ui.js"

Write-Host "Done. Line count: $($newLines.Count)"
