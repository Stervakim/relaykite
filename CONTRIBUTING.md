# Contributing to RelayKite

Useful contributions include reproducible bug reports, device compatibility checks, English documentation improvements and focused pull requests.

Before changing code, read the relevant Android, Windows or relay guide. Keep existing module IDs, tool names, installation paths and pairing formats compatible unless a migration is explicitly designed. Test the component you change with the checks in `.github/workflows/check.yml`.

For a bug, include the version, OS/device, component, steps, expected result and actual result. Remove credentials and personal data from logs. For compatibility reports, separate what you actually tested from expectations. A working host test is not proof of a working physical-device installation.

Documentation pull requests should explain the task in plain English and use the current public name, RelayKite. Release ZIPs and internal identifiers still use legacy names. Do not rename those as a documentation cleanup.

Use GitHub issues for public discussion. To report an access-control flaw, share a minimal description first and do not post working credentials or other users' data. This repository does not promise a dedicated private vulnerability intake channel.
