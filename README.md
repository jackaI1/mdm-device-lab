# mdm-device-lab

I built a lab for managing Android phones and tablets from one place, using a free open-source server, because I wanted to learn how device management works without paying for Microsoft Intune.

This project is not Microsoft Intune. It uses **Headwind MDM**, an open-source mobile device management (MDM) server. MDM is the software that lets someone in charge of a set of phones set Wi-Fi, install apps, require passwords, lock a lost phone, or wipe one. Intune is Microsoft's paid version of the same idea. Headwind does the same job for free, and I can run it on my own computer.

## What it does, in plain terms

1. **Enrolls phones.** A phone is "enrolled" when it has joined the MDM server and checks in with it. I use Android emulators (phone simulators on the computer) as the test phones.
2. **Pushes settings from a spreadsheet.** I list device groups in a CSV file (a spreadsheet saved as plain text). Each row says which phones belong to a group, and what Wi-Fi, apps and password rules they should get. A script sends those rules to every phone in the group.
3. **Locks or wipes one phone.** If a phone is lost, one command locks it. A wipe erases it, and the script refuses to wipe unless I add `--yes`.
4. **Reports on every phone.** One command writes a CSV showing whether each phone is enrolled, when it last checked in, and whether that check-in is recent (within 24 hours), stale, or never.

## How to use it

You need Python 3.11 or newer and Docker (a tool that runs the server in a box so it works the same on any computer).

**1. Start the MDM server**

```bash
docker compose up -d
```

This starts Headwind and its database on your own computer. The admin panel is at http://127.0.0.1:8080 and only your computer can reach it. Before the first start, set `HMDM_IMAGE` to the Headwind image version you want, and change the passwords in `docker-compose.yml`. I did not verify the image name against a running server (see the limitations below).

**2. Enroll an Android emulator**

Create an emulator in Android Studio, start it, and follow the Headwind enrollment steps in the admin panel to point it at the server. Each enrolled phone gets a device ID. You will need those IDs for the groups file.

**3. Install this tool**

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

**4. Set your login (kept out of files)**

```bash
export HMDM_URL=http://127.0.0.1:8080
export HMDM_LOGIN=admin
export HMDM_PASSWORD='your-admin-password'
```

**5. Write your groups and check them**

Copy `groups.example.csv` to `groups.csv` and put your real device IDs in it. Then run a dry run, which shows what would be sent and changes nothing:

```bash
python -m mdm_lab push groups.csv
```

If a row has a mistake, the tool lists every problem with its line number and sends nothing.

**6. Send the settings**

```bash
python -m mdm_lab push groups.csv --apply
```

**7. Lock, wipe, or report**

```bash
python -m mdm_lab lock 1
python -m mdm_lab wipe 1 --yes
python -m mdm_lab report --out device-report.csv
```

## How it is built

- `mdm_lab/groups.py` reads and checks the CSV. It collects all the problems first, then stops, so a bad row never half-applies.
- `mdm_lab/policy.py` turns one group into the settings payload. A group only sends the settings it fills in. Blank cells mean "leave it alone".
- `mdm_lab/client.py` talks to the server's REST API (the web address the server answers on for scripts). It uses only the Python standard library, so there is nothing extra to install to run it. It logs in once, then sends a token with each request.
- `mdm_lab/report.py` builds the enrollment and check-in report, and writes CSV or a Markdown table.
- `mdm_lab/cli.py` is the command line, with the dry-run default and the `--yes` guard on wipes.
- `tests/` has 17 tests. They run against a small fake server in the same process, so they need no Docker and no emulator.
- `docker-compose.yml` starts the server and its MariaDB database.
- `.github/workflows/ci.yml` runs lint and tests on Python 3.11 and 3.13 on every push, and checks the Docker file.

## Limitations

- **The REST paths are my best reading of Headwind's API, not checked against a live server.** I could not find Headwind's API reference from the tools I had. All the paths are in one block at the top of `mdm_lab/client.py`. Before using this on real phones, compare them with your server's API and change them there.
- **The emulator enrollment step has not been run in CI.** Android emulators need a Linux machine with hardware virtualization. The tests cover the code, not a live enrollment.
- The settings payload fields (`wifi`, `apps`, `password`) are a plain shape of my own. They need to be mapped to the exact configuration fields your Headwind version expects.
