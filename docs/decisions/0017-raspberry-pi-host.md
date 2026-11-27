# 0017. Raspberry Pi host

- Status: accepted
- Date: 2026-11-26

## Context

The app runs unattended on a Raspberry Pi 4 (1.8 GB) with Raspberry Pi OS Lite 64-bit, booting from a SATA SSD in a
USB adapter. [0014](0014-docker-deployment.md) and [0015](0015-remote-access-and-backups.md) cover the containers,
remote access and backups, but not the machine around them. The previous installation lost its data to disk errors,
and its logs were on that same disk.

## Decision

These settings live on the host and are not applied by anything in this repository.

**Disk**

- Enable TRIM, which was off for this adapter: a `udev` rule sets `provisioning_mode=unmap` and limits
  `discard_max_bytes` to what the adapter accepts, and `fstrim.timer` is on. Without it, writes fell to 24 MiB/s with
  stalls of 8 s; with it they reached 162 MiB/s. A different adapter needs this checked again.

**Logs**

- A persistent journal, limited to 200 MB.
- Vector sends the whole journal to Axiom (a hosted log service, free plan), so the logs can be read if the disk
  fails. Its configuration holds a token that can only add data.
- The containers log to the journal, through
  [`docker-compose.journald.yml`](../../docker-compose.journald.yml), set with `COMPOSE_FILE` in `.env`.

**Network**

- A network cable, an address reserved in the router, and Wi-Fi off. On Wi-Fi, with its power saving already off, the
  Pi stopped answering for about six minutes while it kept running, and it logged no disconnection. An earlier,
  longer loss needed a power cycle.

**Access**

- SSH with a key only. The user is in the `docker` group.
- The repository is cloned with a read-only deploy key.

**Backups**

- `cron` runs `scripts/offsite-backup.sh` every night: a backup, then its copy to Google Drive with `rclone` (see the
  [deployment guide](../deployment.md#backups)). The result goes to the journal under the tag `tapo-backup`.
- `rclone` uses its own Google client ID, as its shared one is being retired, with the `drive.file` permission: it can
  reach only the files it created. The Google app must be published, or the authorisation expires after a week.
- Drive keeps 90 days of daily copies in one folder and the copy of the 1st of each month in another; the Pi keeps
  the last 14 days.

## Alternatives considered

- **Logs only on the Pi**: nothing leaves the house, but a failed disk takes the explanation of its failure with it.
- **Changing the log driver in `docker-compose.yml` with a variable**: no second file, but the size limits there are
  valid only for Docker's own log files.
- **Staying on Wi-Fi and watching the connection**: no cable, but it records the next loss instead of avoiding it.
- **Fetching the backups from a PC**: nothing leaves the house, but it works only while the PC is on.
- **Copying backups by hand**: nothing to set up, and easy to forget.

## Consequences

- Rebuilding the Pi means repeating these settings by hand.
- Logs and backups are stored by third parties. The backups are not encrypted and hold the plugs' names, local
  addresses and consumption history.
- A token for the Drive files is on the Pi.
- Membership of the `docker` group gives that user full control of the machine.
- If the cable is unplugged, the Pi cannot be reached.
- Docker marks everything a program writes to standard error as an error, including this app's `INFO` messages and
  nginx's notices. Searches for errors have to leave them out.
- Vector reads only the current boot with this version of `systemd`, so the last lines before a restart or a crash
  stay only on the disk (`journalctl -b -1`). Lines written during a short network loss did arrive afterwards.
- Nothing warns when the backup or the upload fails: the journal has to be read.
- Each backup includes up to 60 days of raw readings, so it is expected to level off near 22 MB (estimated from the
  growth of the first day). Keeping every copy would take about 8 GB a year.
- Damage noticed after 90 days can be undone only from a monthly copy.
- The cause of the Wi-Fi losses is unknown.
- Checked on the Pi: the first image build (3 minutes), a restore from a backup file, a restart of the machine, the
  nightly backup and upload running by themselves, a backup downloaded from Drive opened by a temporary container
  (its history matched the live one), and the tunnel with its login. Not yet seen: a monthly copy and the deletion
  of an old copy.
