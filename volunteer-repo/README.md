# PingLuma Iran-Side Reference Publisher

This is a **template** for the small companion repo that produces the
`iran-ref.json` file PingLuma's bot consumes via `IRAN_REFERENCE_URL`.

It is meant to run on a device whose internet connection is routed
through Iran (a friend's home PC, an old Android phone with Termux, a
Raspberry Pi behind an Iranian ISP, etc.). The device acts as a
**self-hosted GitHub Actions runner**, runs the probe every 30 minutes
on a schedule, and commits the resulting JSON back to this repo.

The bot then fetches the JSON via:

```
https://raw.githubusercontent.com/<OWNER>/<REPO>/main/iran-ref.json
```

`raw.githubusercontent.com` serves arbitrary files from any public repo
for free, with rate limits well above what the bot needs (the bot fetches
once per `IRAN_REFERENCE_TTL_S`, default ~4 times/day).

---

## Architecture

```
┌──────────────────────────────────────────┐
│  Volunteer's device (in Iran)            │
│  ─────────────────────────────────────   │
│  • OS: Linux/macOS/Windows or Android    │
│         + Termux                         │
│  • Self-hosted GH Actions runner         │
│    registered to THIS repo only          │
│                                          │
│  Every 30 min the runner:                │
│    1. checkout this repo                 │
│    2. pip install ping-luma              │
│    3. python -m ping_luma                │
│         .publish_iran_reference          │
│         --output iran-ref.json           │
│    4. git commit & push                  │
└──────────────────────────────────────────┘
                      │
                      ▼ git push
┌──────────────────────────────────────────┐
│  GitHub: <OWNER>/<REPO> (public)         │
│  ─────────────────────────────────────   │
│  iran-ref.json (refreshed every 30 min)  │
└──────────────────────────────────────────┘
                      │
                      ▼ HTTPS GET (cached on bot side)
┌──────────────────────────────────────────┐
│  PingLuma bot                            │
│  IRAN_REFERENCE_URL=                     │
│    https://raw.githubusercontent.com/    │
│    <OWNER>/<REPO>/main/iran-ref.json     │
└──────────────────────────────────────────┘
```

---

## Setup — Operator side (one-time)

### 1. Create the public repo

```
gh repo create <YOUR_USER>/pingluma-iran-ref --public \
    --description "Iran-side reference for PingLuma bot" \
    --confirm
```

Or via the GitHub web UI — name doesn't matter, just keep it public.

### 2. Copy this template into the new repo

From the root of your local `ping-luma` checkout:

```bash
cd ../   # one level above ping-luma
git clone https://github.com/<YOUR_USER>/pingluma-iran-ref.git
cp -r ping-luma/volunteer-repo/. pingluma-iran-ref/
cd pingluma-iran-ref
```

Edit `requirements.txt` and replace `YOUR_GITHUB_OWNER` with your actual
GitHub username/org so the file looks like:

```
ping-luma @ git+https://github.com/<YOUR_USER>/ping-luma.git@main
```

Commit and push:

```bash
git add .
git commit -m "Initial volunteer-repo from template"
git push
```

### 3. Harden the repo's Action settings (CRITICAL)

In the GitHub web UI for `pingluma-iran-ref`:

1. **Settings → Actions → General → Actions permissions**:
   - Choose **"Allow YOUR_USER and select actions and reusable workflows"**
   - In the allow-list, add only:
     - `actions/checkout@*`
     - `actions/setup-python@*`

2. **Settings → Actions → General → Workflow permissions**:
   - Choose **"Read and write permissions"**
   - Tick **"Allow GitHub Actions to create and approve pull requests"**: leave it OFF.

3. **Settings → Actions → General → Fork pull request workflows from outside collaborators**:
   - Choose **"Require approval for all outside collaborators"**.

4. **Settings → Actions → General → Workflow runs in private forks of public repositories**:
   - Leave at default (no allow).

5. **Settings → Branches**:
   - Add a branch protection rule for `main`:
     - **Require status checks to pass before merging**: OFF (so the
       bot's own commit can land).
     - **Restrict who can push to matching branches**: only you and the
       runner's identity (the workflow uses `${{ github.actor }}` which
       resolves to the workflow itself).

These four settings collectively prevent any outside contributor from
making the self-hosted runner execute their code via a PR.

### 4. (When the volunteer is ready) Register the self-hosted runner

In the GitHub web UI for `pingluma-iran-ref`:

1. **Settings → Actions → Runners → New self-hosted runner**.
2. Pick the volunteer's OS — GitHub will show 6–8 commands tailored to
   it. Send those commands to the volunteer over a private channel
   (the registration token in those commands is single-use and short-
   lived, so don't post it publicly).
3. The volunteer follows the **Volunteer side** instructions below.
4. Once the runner appears as **Idle** in the GitHub UI, you're done.

### 5. Configure the bot

In the bot's `.env` (the deployment that runs `python -m ping_luma.bot`):

```dotenv
IRAN_REFERENCE_URL=https://raw.githubusercontent.com/<YOUR_USER>/pingluma-iran-ref/main/iran-ref.json
# IRAN_REFERENCE_TOKEN= (leave empty — public repo, no auth needed)
IRAN_REFERENCE_TIMEOUT_S=10
# Cache the result for 30 min to match the publisher cadence.
IRAN_REFERENCE_TTL_S=1800
```

Restart the bot. It will log:

```
Iran reference enabled: ASN(N hosts) + OONI(...) + Crowd(...)
                      + HTTP(https://raw.githubusercontent.com/.../iran-ref.json)
```

Done. The HTTP override now wins over every other source where it has
data.

---

## Setup — Volunteer side (one-time, on the device in Iran)

### Option 1 — Linux / macOS / Windows PC

#### 1. Install Python 3.11

* **Linux (Debian/Ubuntu)**: `sudo apt install python3.11 python3.11-venv git`
* **macOS** (Homebrew): `brew install python@3.11 git`
* **Windows**: install the official 3.11 installer from python.org and
  Git for Windows.

#### 2. Download and register the GitHub Actions runner

Use the commands the operator sent you (these come from
GitHub → repo → Settings → Actions → Runners → New self-hosted runner).
They look like:

```bash
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64-2.X.Y.tar.gz -L \
    https://github.com/actions/runner/releases/download/v2.X.Y/actions-runner-linux-x64-2.X.Y.tar.gz
tar xzf ./actions-runner-linux-x64-2.X.Y.tar.gz
./config.sh --url https://github.com/<OWNER>/pingluma-iran-ref --token <SHORT_LIVED_TOKEN>
```

When `config.sh` asks for a runner name, just press Enter for the
default. When it asks for additional labels, leave it empty (the
workflow uses the default `self-hosted` label).

#### 3. Run the runner as a background service

* **Linux**: `sudo ./svc.sh install && sudo ./svc.sh start`
* **macOS**: `./svc.sh install && ./svc.sh start`
* **Windows**: run `./run.cmd` and add a shortcut to startup; or use
  `./svc.cmd install`.

That's it. The runner now polls GitHub every few seconds. Within 30
minutes the first scheduled run will execute on your device.

#### 4. Verify

* On GitHub, repo → Actions: you should see a recent run titled
  `iran-reference-probe`, and `iran-ref.json` should be updated in the
  repo root.
* On your device, the runner logs are at
  `actions-runner/_diag/Runner_*.log`.

### Option 2 — Old Android phone with Termux

This is the cheapest, lowest-power option. Any Android 7+ phone works.

#### 1. Install Termux from F-Droid

The Play Store version is unmaintained. Use F-Droid:
<https://f-droid.org/packages/com.termux/>.

#### 2. Bootstrap

```bash
pkg update -y
pkg install -y python-3.11 git curl tar
termux-wake-lock          # prevents Android from sleeping the runner
```

#### 3. Download the runner (ARM64)

```bash
mkdir actions-runner && cd actions-runner
curl -o runner.tar.gz -L \
    https://github.com/actions/runner/releases/download/v2.X.Y/actions-runner-linux-arm64-2.X.Y.tar.gz
tar xzf runner.tar.gz
./config.sh --url https://github.com/<OWNER>/pingluma-iran-ref --token <SHORT_LIVED_TOKEN>
```

#### 4. Keep it alive

Termux's background-running guide:
<https://wiki.termux.com/wiki/Termux:Boot>. Install the **Termux:Boot**
add-on (also from F-Droid), then create
`~/.termux/boot/start-runner.sh`:

```bash
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
cd ~/actions-runner
./run.sh
```

`chmod +x` it. Reboot the phone — the runner will start automatically
on boot.

Plug the phone into power, leave it in a window with WiFi. Done.

---

## Maintenance & Troubleshooting

### "The bot says HTTP override fetch failed"

* Check that the workflow has run at least once: GitHub → repo →
  Actions tab.
* Open `iran-ref.json` directly in the browser via the
  `raw.githubusercontent.com` URL — confirm it loads and parses.
* If the file exists but the bot still fails, increase
  `IRAN_REFERENCE_TIMEOUT_S` (raw.githubusercontent.com is sometimes
  slow from poorly-routed VPSes).

### "The runner shows Offline"

The volunteer's device is offline (rebooted, lost WiFi, lost power).
The workflow will silently skip while the runner is offline — the bot
will keep using the last cached `iran-ref.json` until its TTL, then
fall back to OONI/ASN. No outage.

### "I want to refresh manually right now"

GitHub → repo → Actions → `iran-reference-probe` → "Run workflow" button.
Or, on the volunteer's device:

```bash
cd actions-runner
./run.sh   # runs the next queued job and exits
```

### "The volunteer wants to stop"

* Operator: GitHub → Settings → Actions → Runners → remove the runner.
* Volunteer: `cd actions-runner && ./svc.sh stop && ./svc.sh uninstall`
  (or, on Termux, just delete `~/actions-runner/`).

The bot keeps working — without a fresh `iran-ref.json`, the existing
ASN/OONI/Crowd layers take over.

### "Updating ping-luma"

The `requirements.txt` pins `@main` by default. Each scheduled run
re-installs from `main`, so any push to your `ping-luma` repo's `main`
branch propagates to the volunteer's device on the next run. For
production stability, replace `@main` with `@v1.0.0` (a tag) and bump
manually.

---

## Privacy notes for the volunteer

* The script ONLY runs the same network probes that the bot's WebApp
  performs in users' browsers. It does NOT scrape, log, or transmit
  anything about the device's owner.
* The committed `iran-ref.json` contains only per-messenger boolean
  reachability — no IP addresses, no DNS history, no timing data
  beyond the latest verdict.
* The runner's outbound traffic goes to: the messenger origins listed
  in `ping_luma/messengers.py`, GitHub's API, and PyPI.
* If you're uncomfortable running the GitHub runner directly on your
  daily-driver phone, dedicate an old phone or a $35 Raspberry Pi.

---

## License

Same as PingLuma — MIT.
