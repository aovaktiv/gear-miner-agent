# Deployment

This project can be hosted at `brand.search.getaktiv.org` with:

- the Gear Miner UI running in a Docker container
- Caddy terminating HTTPS and reverse proxying to the app
- a DNS record pointing `brand.search.getaktiv.org` at the server

## What This Setup Gives You

- HTTPS on `https://brand.search.getaktiv.org`
- automatic TLS certificate provisioning through Caddy
- persistent UI state, snapshots, and exports in `data/ui/`
- a simple single-host deployment path for the current MVP

## Prerequisites

- a Linux host or VPS with a public IPv4 address
- Docker and Docker Compose
- DNS access for `getaktiv.org`

## DNS

Create an `A` record for:

- Host: `brand.search`
- Value: `<your-server-ip>`

If your DNS provider supports AAAA and the server has IPv6, you can also add:

- Host: `brand.search`
- Value: `<your-server-ipv6>`

Wait until the record resolves publicly before starting Caddy, or TLS issuance can fail.

## Server Deploy Steps

1. Clone this repo onto the server.
2. From the repo root, start the stack:

```bash
docker compose up -d --build
```

3. Confirm the containers are healthy:

```bash
docker compose ps
docker compose logs -f app
docker compose logs -f caddy
```

4. Open:

```text
https://brand.search.getaktiv.org
```

## Updating The App

Pull the latest code and rebuild:

```bash
git pull
docker compose up -d --build
```

## Files In This Setup

- `Dockerfile`: runs the Python UI on port `8765`
- `docker-compose.yml`: launches the app and Caddy together
- `deploy/Caddyfile`: maps `brand.search.getaktiv.org` to the app

## Notes

- The current app stores run history and exported files on local disk under `data/ui/`.
- This deployment path assumes a single instance. If you later want multiple app instances, shared storage and job coordination will need to be added.
- The app exposes a lightweight health endpoint at `/healthz`.
