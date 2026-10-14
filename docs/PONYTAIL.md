# Ponytail plugin (pinned v5.2.0, disabled by default)

Pin: tag `v5.2.0`, commit `2961b52fc1fe6a5a87c7a959a79512e5c2f3ffe5`. A tag does not pin code, so the installed commit and every installed file are verified against that commit. Auto-update is off.

## What is guaranteed, and what is not

| Claim | Basis |
|---|---|
| The plugin is **disabled** after the Setup script, so none of its hooks can run. | The script runs `claude plugin disable` immediately after install, before any verification and before any Claude session exists. If the disable fails the plugin is uninstalled. |
| The script never enables the plugin. | It contains no `enable` call. |
| Verification runs no plugin code. | It reads `installed_plugins.json`, then compares the SHA-256 of every file in the pinned commit (`git show`) with the installed copy and rejects extra files. |
| A mismatch removes the plugin; a missing network or CLI leaves it uninstalled. | Both exit 0 so the Cloud session still starts. |
| `.claude/settings.json` keeps `ponytail@ponytail` at `false` and sets `PONYTAIL_DEFAULT_MODE=off`, `PONYTAIL_MAP=0`. | Project settings override user settings. The `env` route is documented but **not observed** in a running hook. |
| Not verified: whether `~/.claude/plugins` survives the Cloud environment snapshot. | Docs say files the Setup script writes carry over. If it does not survive, the plugin is simply absent (safe). Re-run the script to reinstall. |
| Not verified: the exact `installed_plugins.json` field names (`gitCommitSha`, `installPath`) in a real install. | Tested only against a synthetic record. If they differ the script reports `UNVERIFIED` and the plugin stays disabled. |

The verification logic was tested offline against the real v5.2.0 tree (202 files, all match) and against a tampered copy (mismatch detected and removed). The install path itself has not been run, per the no-install rule.

## Files

* `infra/ponytail_setup.sh`: the Cloud Setup script. Paste its full contents into the environment's Setup script field (the repo may not be cloned when it runs, so it cannot be called by path). `ponytail_setup.sh verify` re-checks an existing install without installing or enabling anything.
* `.claude/settings.json`: marketplace pinned to `v5.2.0` with `autoUpdate: false`, `enabledPlugins` `ponytail@ponytail: false`, env safeguards. Cloud sessions do **not** install declared plugins, so this file never installs anything.

Scope: the script installs at **user** scope because it cannot rely on the repo existing. The project file is the master switch: it overrides the user scope, so the plugin stays off until `.claude/settings.json` is changed.

Persistence limits: the install lives in the environment snapshot (rebuilt after about 7 days or when the Setup script changes) and in no committed file. `~/.config/ponytail/config.json` (`{"defaultMode":"off"}`) is written by the script and is outside the repo.

## Activation (explicit, manual)

1. Confirm the verdict: `bash infra/ponytail_setup.sh verify`, last line must start with `STATUS: VERIFIED commit=2961b52f`. Anything else: do not activate.
2. Set `"ponytail@ponytail": true` in `.claude/settings.json` (or `claude plugin enable ponytail@ponytail --scope project`), then start a new session or run `/reload-plugins`.
3. The mode stays `off`; switch it on with `/ponytail` when wanted.

## Disable and uninstall

* Disable: set the settings value back to `false`, or `claude plugin disable ponytail@ponytail --scope project`.
* Uninstall: `claude plugin uninstall ponytail@ponytail --scope user`, then `claude plugin marketplace remove ponytail`; delete `~/.config/ponytail/config.json`.

## Rollback (repo)

Remove the Setup script text from the environment, run the uninstall commands, then `git rm infra/ponytail_setup.sh docs/PONYTAIL.md .claude/settings.json` (if `.claude/settings.json` holds other keys by then, remove only the three Ponytail keys) and delete the E5 row in `docs/DECISIONS.md`. Nothing else is touched.

## Fail-open / fail-closed

* Availability failures (no network, no CLI): fail-open, no plugin, session starts.
* Integrity failures (commit or file mismatch): fail-closed, plugin removed, session starts.
* Unknown record format: stays disabled, reported `UNVERIFIED`.
