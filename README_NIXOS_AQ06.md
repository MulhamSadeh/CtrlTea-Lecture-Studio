# Ctrl+Tea AQ-06 — NixOS local launch

This archive contains the AQ-06 application (original verified code, with a visual release-label correction), plus a local NixOS launcher.

## Steps

1. Extract this ZIP in a NEW directory; it creates `ctrltea-studio-AQ06/` (not the older `ctrltea-studio/` folder).
2. `cd ctrltea-studio-AQ06`
3. `bash Run-NixOS-Local.sh`
4. Open http://127.0.0.1:8766 (NOT port 8765).

The UI label now reads AQ-06; the upstream Python package and API technical version remain 1.0.0 because upstream did not increment them.

The default local data directory is this new folder's `data/`. Existing projects in another app folder are NOT automatically imported or deleted. Back up old data and stop the old process before migrating or reusing it. Do not point two concurrent app servers at the same SQLite data directory.

If the new port is occupied, stop the conflicting process; do not assume the app you see at 8765 is from this release.

This local profile uses SQLite and disables account authentication; never expose it to the public network.

Changes relative to `CtrlTea_AQ06_NixOS_Local.zip`: archive root changed to `ctrltea-studio-AQ06/` to avoid extracting over old files; visible UI version label changed from V1 to AQ-06 in source and referenced built JS; launcher uses port 8766. No lecture engine, math, figure, or QA validator changes.

The environment is not executed on real NixOS in this environment. Actual Nix deployment should be tested on the target system.
