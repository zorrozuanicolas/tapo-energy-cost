# Deployment

Running the app with Docker on a machine that stays on, such as a Raspberry Pi. To install and start it, see the
[quick start](../README.md#quick-start).

## Day to day

```sh
docker compose ps                # is it running and healthy?
docker compose logs --since 24h backend
docker compose down              # stop it; the data stays in ./data
```

## After a change

| After changing | Run |
|---|---|
| `.env` | `docker compose up -d` |
| `TIMEZONE`, or the code (after `git pull`) | `docker compose up -d --build` |
| A file in `config/` | `docker compose restart backend` |

Only the dashboard's port is published, and **there is no login**: keep it on your home network, or add one as
described in [Remote access](#remote-access). The reasoning behind this setup is in
[0014](decisions/0014-docker-deployment.md).

## Logs

Docker keeps the last 30 MB of each container's log, and discards it when the container is recreated, for example on
an update. On Linux the logs can go to the systemd journal instead, with the rest of the machine's logs. Add this to
`.env` and run `docker compose up -d`:

```
COMPOSE_FILE=docker-compose.yml:docker-compose.journald.yml
```

`docker compose logs` works as before. `journalctl CONTAINER_NAME=tapo-energy-cost-backend-1` reads the same lines,
including those of earlier containers. How long they are kept depends on the journal's settings, and they survive a
reboot only if the journal is persistent.

## Remote access

Optional: reach the dashboard from outside your home through a Cloudflare Tunnel, without opening a router port. You
need a Cloudflare account and a domain whose DNS Cloudflare manages. `energy.example.com` stands for your address,
and the names in Cloudflare's dashboard may differ slightly.

1. **Add the login first.** In Zero Trust, create a self-hosted **Access** application for `energy.example.com`,
   with an *Allow* policy that includes only your email address (a one-time PIN by email works as the login method).
2. Create a **Tunnel** (cloudflared) and give it a public hostname: `energy.example.com`, with the service
   `http://frontend:8080`.
3. In `.env`, set the tunnel's token (it is a secret) and enable the tunnel:

   ```
   TUNNEL_TOKEN=<the token>
   COMPOSE_PROFILES=tunnel
   ```

4. Run `docker compose up -d`.
5. **Check it:** open the address in a private browser window, for example on a phone using mobile data. It must ask
   you to log in before showing anything. If it does not, run `docker compose stop cloudflared` and review step 1.

If the tunnel does not connect, see `docker compose logs cloudflared`.

## Backups

With the app running:

```sh
scripts/backup.sh                    # on Windows: docker compose exec backend python -m app.backup
scripts/backup.sh --keep-days 30     # the default is 14
```

It writes `data/backups/tapo-<date and time in UTC>.db.gz`, safely while the app keeps running, checks it, and deletes
older backups.

**Every day,** on Linux, add one of these lines with `crontab -e`, with your own paths.

To keep the backups on this machine only:

```
15 3 * * * /home/<user>/tapo-energy-cost/scripts/backup.sh 2>&1 | logger -t tapo-backup
```

To also copy them elsewhere, which is safer, as a disk failure takes the database and its backups together:

1. Install [rclone](https://rclone.org/drive/) and set up a remote called `gdrive`, for example for Google Drive
   (create your own Google client ID, and choose the `drive.file` scope, which reaches only the files rclone created).
2. Use this line:

   ```
   15 3 * * * /home/<user>/tapo-energy-cost/scripts/offsite-backup.sh 2>&1 | logger -t tapo-backup
   ```

[`offsite-backup.sh`](../scripts/offsite-backup.sh) makes a backup and copies it to `tapo-backups`, where the last 90
days are kept. Backups dated the 1st of each month also go to `tapo-monthly`, permanently. Old daily copies are
deleted for good, without going to the trash. A month with no backup on the 1st (UTC) has no monthly copy. For
another rclone remote, set `RCLONE_REMOTE`.

`journalctl -t tapo-backup` shows the results. Look at it now and then: nothing else reports a failed backup.

Without rclone you can copy them by hand, for example from your PC:

```sh
scp -r <user>@<address>:tapo-energy-cost/data/backups .
```

**Restore** a backup (change the file name). The current database is renamed to `old-tapo.db`, with its `-wal` and
`-shm` files, replacing the one kept by an earlier restore. Leaving those two files next to a restored database could
damage it.

```sh
docker compose stop backend
docker compose run --rm --no-deps -e BACKUP=tapo-20261125-061500Z.db.gz backend sh -ec '
  cd /srv/data
  gzip -t "backups/$BACKUP"
  for f in tapo.db tapo.db-wal tapo.db-shm; do [ ! -e "$f" ] || mv "$f" "old-$f"; done
  gunzip -c "backups/$BACKUP" > tapo.db'
docker compose start backend
```

With real plugs, the app then recovers up to a week of the hours recorded after the backup.

**Moving to another machine:** stop the app on the old one, back up, and copy the file to `data/backups/` on the new
one. Restore it there **without the last command**, as a backend with no `.env` uses fake plugs and would add their
readings to your history. Set the real plugs in `.env`, then run `docker compose up -d`.

Without Docker, `uv run python -m app.backup` in `backend/` backs up the database set there. The reasoning behind
backups and remote access is in [0015](decisions/0015-remote-access-and-backups.md), and the setup of a
Raspberry Pi host in [0017](decisions/0017-raspberry-pi-host.md).
