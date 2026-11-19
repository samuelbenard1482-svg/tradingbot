# Deploying the XAUUSD Paper Trading Bot Online

This gets `server/app.py` running on a free cloud server that stays on
whether or not your own PC/phone is — visit its address from any
browser, anytime, to see the live chart and paper-trading performance.

We'll use **Oracle Cloud's "Always Free" tier**, because it's genuinely
free forever (not a trial) and includes enough resources for this.

## 1. Create the free VM

1. Sign up at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/)
   (needs a credit card for identity verification, but the Always Free
   tier itself never charges you).
2. In the Oracle Cloud Console: **Compute → Instances → Create Instance**.
3. Choose an **Ampere (ARM) "Always Free"** shape, or a
   **VM.Standard.E2.1.Micro "Always Free"** shape — both are labeled
   "Always Free" directly in the shape picker.
4. Choose **Canonical Ubuntu** as the image.
5. Under "Add SSH keys," either upload a public key you already have,
   or let Oracle generate one and download the private key file.
6. Click **Create**, wait a few minutes, then copy the instance's
   **public IP address** from its details page.

## 2. Open the port

1. On the instance details page, click the **Virtual Cloud Network**
   link, then the **Security List** for its subnet.
2. Add an **Ingress Rule**: Source CIDR `0.0.0.0/0`, Protocol `TCP`,
   Destination Port `5000`.
3. Once logged into the server itself (step 4), also open Ubuntu's own
   firewall for that port.

## 3. Connect to the server

From your own PC's terminal (PowerShell works fine on Windows too):

```bash
ssh -i /path/to/your-private-key.key ubuntu@YOUR_SERVER_IP
```

## 4. Set up the server

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv
sudo iptables -I INPUT -p tcp --dport 5000 -j ACCEPT
sudo netfilter-persistent save
```

## 5. Upload the bot

From your OWN PC, in a new terminal:

```bash
scp -i /path/to/your-private-key.key -r ict_wing_pipeline ubuntu@YOUR_SERVER_IP:~/
```

## 6. Install and run

Back in your SSH session:

```bash
cd ict_wing_pipeline
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # paste your real Twelve Data API key, Ctrl+O to save, Ctrl+X to exit
python3 server/app.py
```

Visit `http://YOUR_SERVER_IP:5000` from any browser, anywhere — the
dashboard keeps running even after you close that tab or turn off your
own PC.

## 7. Keep it running after you disconnect

```bash
sudo apt install -y screen
screen -S bot
python3 server/app.py
```
Press **Ctrl+A then D** to detach — it keeps running after you close
your SSH session. Reattach later with `screen -r bot`.

### Survive a server reboot too

Create `/etc/systemd/system/ict-bot.service`:

```ini
[Unit]
Description=ICT Wing XAUUSD Paper Trading Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/ict_wing_pipeline
ExecStart=/home/ubuntu/ict_wing_pipeline/venv/bin/python3 server/app.py
Restart=always
EnvironmentFile=/home/ubuntu/ict_wing_pipeline/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable ict-bot
sudo systemctl start ict-bot
```

## What this bot actually does — and doesn't do

- **It simulates trades with fake money only.** No real orders are
  ever placed with any broker. `engine/strategy.py` is an unvalidated
  starter template, not a proven system.
- **It's for personal use, unsecured.** No login screen, no HTTPS.
  Fine for your own viewing; don't expose anything sensitive behind it.
- **Twelve Data's free-tier rate limit (8 req/min) still applies** —
  same as every other script in this project.
- Before ever considering real capital, run `backtest_thresholds.py`
  against real historical XAUUSD data (see `pull_historical_data.py`)
  and validate the strategy's actual edge over a meaningful sample —
  days of live paper-trading results aren't enough evidence either way.
