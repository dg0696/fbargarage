# User OAuth via Python so eBay codes with ^ and # are not corrupted.
Set-Location (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
python scripts/ebay_user_oauth.py @args
