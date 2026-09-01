# Paste Production eBay App ID, Dev ID, and Cert ID into Windows Credential Manager.
Set-Location (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
python scripts/store_ebay_secrets.py @args
