# HTTPS Setup for the Boat API

The boat's Pi 5 API is exposed over cellular internet and **must** use HTTPS.
Caddy handles this automatically with zero-config TLS.

## Prerequisites

1. A domain name (e.g., `boat.yourdomain.com`)
2. DNS A record pointing to the Pi 5's public IP (from the SIM7600 modem)
3. Port 443 reachable from the internet (check with your cellular provider)

## Install Caddy on Pi 5

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

## Configure

1. Edit `deploy/Caddyfile` — replace `boat.yourdomain.com` with your domain
2. Copy to system config:
   ```bash
   sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
   ```
3. Build the dashboard and copy to serve path:
   ```bash
   cd dashboard && npm run build
   sudo mkdir -p /home/pi/boat/dashboard
   sudo cp -r dist /home/pi/boat/dashboard/
   ```

## Start

```bash
sudo systemctl enable caddy
sudo systemctl start caddy
```

Caddy will automatically:
- Request a TLS certificate from Let's Encrypt
- Redirect HTTP → HTTPS
- Renew the certificate before it expires

## Verify

```bash
curl https://boat.yourdomain.com/api/status -H "X-API-Key: your-key"
```

## If you don't have a domain

For testing with a self-signed certificate, change the Caddyfile to:

```
:443 {
    tls internal
    # ... rest of config
}
```

Then trust the Caddy root CA on your phone/computer, or accept the browser warning.

## Security checklist

- [x] HTTPS via Caddy auto-TLS
- [x] Rate limiting in FastAPI middleware (60 req/min default, 10/min for ESTOP/RTH)
- [x] WebSocket auth via `?key=` query parameter
- [x] API key auth via `X-API-Key` header (constant-time comparison)
- [x] HSTS header (Strict-Transport-Security)
- [x] Request body size limit (1MB)
- [ ] Set `BOAT_API_KEY` to a strong random value:
  ```bash
  export BOAT_API_KEY=$(openssl rand -hex 32)
  ```
