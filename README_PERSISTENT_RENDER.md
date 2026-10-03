# Persistent Render Telegram Python Hosting Bot

This version is designed for a Render Background Worker with a Persistent Disk.

## What is persistent

The following are stored under `/var/data`:
- hosted `.py` files
- hosting SQLite database
- bot logs
- pip cache
- dependency snapshots

After a Render worker restart/redeploy, the bot reads the database and automatically relaunches hosted scripts that were previously marked as running.

## Render setup

1. Push these files to GitHub:
   - `hosting_persistent.py`
   - `requirements.txt`
   - `render.yaml`

2. Render → New → Blueprint → select the GitHub repository.

3. `render.yaml` creates a Background Worker and a 1 GB Persistent Disk mounted at `/var/data`.

4. Set:
   - `BOT_TOKEN` = your Telegram bot token
   - `ADMIN_ID` = your numeric Telegram user/chat ID

5. Deploy.

## Important

A Render Persistent Disk is required for persistence. The disk is attached to the service and is not a replacement for backups.

Hosted scripts execute arbitrary Python code with the same permissions as the worker. Only allow trusted admin uploads.

## Runtime flow

Admin uploads `.py`
→ imports are detected
→ missing pip packages are installed
→ script starts
→ logs are captured
→ crash guard restarts stopped processes
→ after Render restart, previously running scripts are restored

## Local test

```bash
pip install -r requirements.txt
export BOT_TOKEN="YOUR_TOKEN"
export ADMIN_ID="YOUR_TELEGRAM_ID"
export STORAGE_DIR="./data"
python hosting_persistent.py
```
