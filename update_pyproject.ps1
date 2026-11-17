 = Get-Content pyproject.toml -Encoding UTF8 -Raw;  = .Replace(" version = \1.2.0\\, \version = \1.2.0-beta\\); Set-Content pyproject.toml -Value -Encoding UTF8; Write-Host \OK\
