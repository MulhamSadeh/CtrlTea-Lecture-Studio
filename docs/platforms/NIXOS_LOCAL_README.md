# Ctrl+Tea Lecture Studio — AQ-06 on NixOS

This folder retains the **original** `UPDATED_PROJECT_AQ06.zip` as the verified historical application release.

For a separate **local NixOS launch**, use `CtrlTea_AQ06_NixOS_Corrected.zip`. It is based on that original release, with:

- Added Nix Python dependencies (`psycopg`, `argon2-cffi`, `email-validator`, `pillow`, `sqlalchemy`, `alembic`).
- Updated the frontend's *visible* release label from `V1` to `AQ-06` (the API/package technical version remains `1.0.0`).
- Local launcher bound to `127.0.0.1:8766` to avoid confusion with an old server on port `8765`.
- Separate extraction folder (`ctrltea-studio-AQ06/`) and local data directory.

## Run

```bash
unzip CtrlTea_AQ06_NixOS_Corrected.zip
cd ctrltea-studio-AQ06
bash Run-NixOS-Local.sh
```

Visit `http://127.0.0.1:8766` in the browser.

To verify that the backend supports the new diagram schema:

```bash
curl -fsS http://127.0.0.1:8766/api/schema | grep -o 'control_diagram' | head
```

Local SQLite mode is for **personal, loopback-only use**, not public deployment. Existing data in another installation is not automatically migrated. Back it up; do not point two concurrent processes at the same data directory.

No source math/lecture export engine, new QA tests, or authorization logic was altered for this NixOS packaging. Native NixOS startup was not executed in the assistant environment; validate on your machine. AQ-05 Reviewer is a separate skill, and AQ-06 validators are available under `tools/academic_quality/`.

## Release provenance

Original `UPDATED_PROJECT_AQ06.zip` SHA-256:

`1eef8abada599394a98486f98a0c188ee75b5481e8d250e887ca73a6c17469a3`

The corrected archive has a different SHA-256 because of the added files and packaging changes. Refer to the separately recorded checksum for that archive; it does **not** replace the original release's checksum.
