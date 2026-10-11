param([switch]$Build)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot
try {
    if (-not (Test-Path '.local/codabench/.env')) {
        throw 'Local installation is missing. Follow deploy/README.md to prepare source and credentials.'
    }
    $composeArgs = @('compose', '--env-file', '.local/codabench/.env', '-f', 'deploy/compose.yaml')
    if ($Build) {
        & docker @composeArgs build django compute_worker
        if ($LASTEXITCODE -ne 0) { throw 'Image build failed.' }
        & docker @composeArgs build scoring_image
        if ($LASTEXITCODE -ne 0) { throw 'Scoring image build failed.' }
        & docker @composeArgs run --rm frontend
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    }
    & docker @composeArgs up -d --wait --wait-timeout 180 db rabbit redis minio createbuckets django site_worker compute_worker web
    if ($LASTEXITCODE -ne 0) { throw 'Service startup failed.' }
    & docker @composeArgs cp deploy/bootstrap_admin.py django:/tmp/bootstrap_admin.py
    if ($LASTEXITCODE -ne 0) { throw 'Administrator script copy failed.' }
    & docker @composeArgs exec -T django python manage.py shell -c "exec(open('/tmp/bootstrap_admin.py').read())"
    if ($LASTEXITCODE -ne 0) { throw 'Administrator initialization failed.' }
    Write-Host 'Codabench: http://localhost:8080'
    Write-Host 'Credentials: .local/admin-credentials.txt'
} finally {
    Pop-Location
}
