$status = Invoke-RestMethod http://127.0.0.1:8080/api/v1/data-status
$status | Where-Object { $_.static_state -eq 'active' } |
    Select-Object feed, active_version_id, last_successful_static_fetch_at