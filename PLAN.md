# Unepic Trainer implementation plan

> Use `superpowers:executing-plans` for task-by-task implementation in this session. Track progress here and in `progress.md`. Do not delegate without user authorization.

**Goal:** A standalone Linux single-player trainer with player/minion HP, healing, independent god modes and owned-minion ENERGY locked at its maximum, extra campaign points, immediate level-up, gold, Unepic Credits, Kill Points and manual saving.

**Architecture:** Python with PySide6/Qt Widgets and a separate GDB/MI backend. A worker handles memory operations; Qt widgets stay in the main thread. Python generates the x86-64 damage trampoline. REA/Ghidra supports analysis; PINCE and scanners are optional research tools.

**Design:** [DESIGN.md](DESIGN.md).

Updated 2026-10-09. The user has verified connection, damage readings, healing, player-only protection against ordinary attacks and restoration after disabling. Eight host backend/hook tests passed; backup hashes were verified. The user clarified that player HP decreases while burning and reported poisoning too. A second periodic-damage hook now passes controlled checks; game verification of the fix is pending. Minion HP/ENERGY, healing, independent god mode and maximum-energy lock are implemented; actual-game verification is pending. Public release checks remain open.

## Constraints

- Project root: `/home/af/devel/games/unepic`.
- Steam installation `/home/af/.local/share/Steam/steamapps/common/Unepic` is read-only.
- Keep code, analysis, logs, fixtures, builds and backups in the project.
- Support the analyzed Linux x86-64 `unepic64s` hash: `62c04002b98eee3f33d0f8c27030b1f5ea23d3ede56d62af9da6b1436a583962`.
- Revalidate executable and process identity before using addresses or writing.
- Authorized campaign points, immediate level-up and Gold +100/+1000/+10000 use native game routines. Unepic Credits +100/+1000/+10000 change the saved campaign source counter once, followed by the normal native item rebuild. Other inventory changes remain excluded. Keep integrity checks active. Manual saving queues the normal game request.
- Restore original instructions when disabling or normally disconnecting.
- Do not require PINCE or scanners in the distributed initial version.
- Use English for the application and publishable files; use Bulgarian in user conversation.

## Review focus

Reject unsupported executables without writes. Invalidate expired or reused PIDs. Disable changes for an unavailable character. Read the current entity pointer dynamically. Keep enemy damage working. Report patch/restore errors precisely and never report successful detach before restoration succeeds.

## Preparation

- [x] Relocated `rea-analysis/` into the project and verified the three original hashes.
- [x] Saved the design and read-only Steam rule in project documentation.
- [x] Selected a standalone trainer; a PINCE table is not the product.

## Files

| File | Responsibility |
|---|---|
| `pyproject.toml` | Dependencies and entry point |
| `src/unepic_trainer/profiles.py` | Supported hash, offsets and original instruction bytes |
| `src/unepic_trainer/processes.py` | Discovery and process identity |
| `src/unepic_trainer/backend.py` | GDB/MI, all-stop, memory access, allocation and detach |
| `src/unepic_trainer/character.py` | Character reads and healing |
| `src/unepic_trainer/hooks.py` | Trampoline, patch and restoration |
| `src/unepic_trainer/progression.py` | One-shot points, native level-up, Gold, credits and KP dispatch |
| `src/unepic_trainer/gold.py` | Currency descriptors, inventory pairs/capacity and credits source validation |
| `src/unepic_trainer/saving.py` | Normal campaign save requests and cancellation/recovery |
| `src/unepic_trainer/ui.py` | Qt window and worker |
| `tests/fixtures/` | Owned synthetic process; no game files |
| `tests/` | Backend, character, hooks, backup and UI checks |
| `runtime-notes/` | Runtime evidence, investigations and limits |
| `backups/`, `dist/` | Local save copies and packages |

## Task 1: Supported build and process

Interfaces: `ProcessIdentity`, `find_candidates()`, `validate_target(identity)`.

- [x] Test exact hash acceptance, wrong hash rejection, changed start time and executable identity.
- [x] Implement `/proc` discovery and clear access errors.
- [x] Process tests pass.

## Task 2: Backend on an owned process

Interfaces: `Backend.attach`, `pause`, `resume`, `read`, `write`, `detach`.

- [x] Implement the synthetic process and the 100-to-80 read/write integration check.
- [x] Check process exit, GDB errors, pause/resume and token-correlated MI notifications.
- [x] Implement timeouts and process identity checks before each operation.
- [x] Host verification: backend/hooks subset passed all eight tests without skips. Sandbox skips remain an environment restriction.

## Task 3: Character and healing

Interfaces: `CharacterSnapshot`, `read_character(backend)`, `heal(backend)`.

- [x] Test float32 HP, int32 maximum, XOR decoding and invalid pointers.
- [x] Read character `0x0142d620`, body pointer `+0x197b8`, maximum `+0x4e8`, current HP `+0x4ec`.
- [x] Character tests verify healing to the current maximum and no protected-value changes.
- [x] User screenshot confirms connection and level 16; subsequent report confirms HP decreases when damaged.
- [x] Verify six backup file sizes/hashes against `backups/20261008T215445Z-98e804e3/manifest.json`.
- [x] User confirms Full heal restores health in Unepic.
- [ ] Independently observe integrity flags/progression after changes; check room transitions and save/load.

Exact in-game numeric HP, the gold HUD marker and restore-from-backup remain unverified.

## Task 4: Reversible player god mode

Interfaces: `GodMode.enable`, `disable`, `active`; backend supplies all-stop patching and near allocation.

- [x] Require the eight original bytes `f3 0f 11 93 ec 04 00 00` at `0x004caf49`.
- [x] Verify executable allocation, relative jumps and instruction restoration on an owned process through GDB.
- [x] Verify registers, flags and the SysV red zone in Unicorn and behavior on a native CPU.
- [x] Compare against the current player entity; execute original damage for other objects.
- [x] Test repeated enable/disable, partial patch recovery and unsafe instruction pointers.
- [x] Host hook tests pass with original bytes restored after disabling.
- [x] User confirms protection from ordinary attacks, enemy damage and normal player damage after disabling.
- [x] Trace the second ongoing-effect HP store at `0x004cb2ad` and cover it with a player-only trampoline.
- [x] Verify both stores, register/flag preservation, transaction rollback and restoration on owned fixtures.
- [x] Reproduce a shared-PC allocation refusal and add a verified unoccupied instruction fallback without weakening occupancy checks.
- [x] User reports successful host tests and activation without the earlier allocation error; exact counts/output were not supplied.
- [ ] Repeat host backend/hook tests after the extension; verify burning and poisoning in Unepic with protection on and off.
- [ ] Game checks: disconnect/close with an active hook, room transitions, save/load, traps and scripted/direct HP-zero paths.

## Task 5: Interface and distribution

Interfaces: worker signals for snapshots, status, errors, connection and hook state.

- [x] Implement a compact Qt window, backup selection and responsive worker operations.
- [x] Offscreen checks cover demo healing/toggling, missing characters and worker shutdown/recovery.
- [x] User confirms the basic game combat cycle through enable and disable.
- [ ] Verify disconnect/close with an active game hook and normal continuation.
- [ ] Install and launch with dependencies in a clean Python environment.
- [ ] Verify a Linux distribution package and a second Linux environment.

## Owned-minion extension

Accepted controls: separate HP and ENERGY bars, Heal minion, independent Minion god mode and Lock energy at maximum. Details and evidence: [runtime-notes/minion.md](runtime-notes/minion.md).

- [x] Trace owned-pet identity, current room, HP, ENERGY and its maximum using REA.
- [x] Validate bounded room lists, pointers and resource values; exclude foreign, dead and recalled pets.
- [x] Heal living owned pets; display totals and count when several are present.
- [x] Add independent player/minion enable bits to both HP trampolines.
- [x] Fill and maintain ENERGY at its current cap through spending/regeneration hooks, with independent control.
- [x] Keep enemy/foreign-pet damage and resource spending intact; restore all hooks at disconnect.
- [x] Verify CPU context, toggle combinations, partial patch recovery, UI and worker shutdown on controlled fixtures.
- [x] Export REA evidence/snapshot and visually inspect the English interface.
- [ ] Run the new GDB minion integration test on the host; sandbox ptrace restrictions skip it here.
- [ ] Compare actual-game minion HP/ENERGY bars, heal, separate toggles, recall/replacement, room changes and disconnect.

XP multipliers and further protected-value modifications require separate designs; the authorized points/level-up design is recorded below. Add scanmem/libmemscan integration only when a concrete feature needs scanning.

## Polling and shutdown correction

The user reported periodic game stalls and a hidden trainer window with a surviving process; Ctrl-C did not stop it.

- [x] Reproduce excessive stopped polling with a 100-object controlled room and a modeled 5 ms GDB response latency.
- [x] Replace timer reads with live read-only memory access; remove timer ENERGY writes.
- [x] Keep all changes stopped and freshly validated; use manual Refresh when live access is denied.
- [x] Route window close and SIGINT/SIGTERM through verified cleanup, then explicitly quit and join the worker.
- [x] Verify live reads on a running native process, permission denial, identity changes, descriptor closure, CLI termination, debugger reaping and recovery retry.
- [x] User reports that everything now works after the correction; the reported periodic stalls and lingering process are resolved in the session.
- [ ] Independently verify individual close/Ctrl-C paths with every hook active and ordinary damage/ENERGY spending restored afterward; check recall and room transitions.

Details: [polling and shutdown notes](runtime-notes/performance-and-shutdown.md).

## Campaign progression and two-column interface

Accepted by the user: +1/+10/+100 points to distribute, immediate Level up without waiting for a kill, Player on the left and Minion on the right. This supersedes the initial progression read-only scope; the separately authorized gold extension below is an authorized inventory change; the later Unepic Credits extension is documented below. Design and evidence: [progression notes](runtime-notes/progression.md).

- [x] Trace the native paired points-adder, XP setter and normal level-up path with REA; restrict controls to campaign mode.
- [x] Queue one-shot requests under all-stop validation and execute native calls on the game's own character-update thread.
- [x] Recheck living body, room, campaign, integrity pairs, level and balances in the dispatcher; cancel stale requests and prevent replay.
- [x] Preserve CPU context, retain partial-write recovery, restore the update entry on detach and coexist with all HP/ENERGY hooks.
- [x] Add +1/+10/+100 and immediate Level up to Player, with pending/cap states and an XP bar; arrange Minion on the right.
- [x] Verify emulator/native CPU execution, backups, lifecycle, allocation fallback and the rendered English UI.
- [x] Export 213 REA records and snapshot; close the analysis session.
- [ ] Run the added real-GDB integration test on the host; the sandbox denies ptrace.
- [ ] Verify Unepic point changes/spending, immediate level-up effects, XP threshold, save/load and disconnect/close after progression changes.

## Manual saving and gold extension

Authorized: Save game in the current slot without changing difficulty, plus Gold +100/+1000/+10000. See [saving and gold notes](runtime-notes/saving-and-gold.md).

- [x] Trace native manual save consumption, restrictions, confirmation and Steam storage.
- [x] Queue the native request after backup/context checks; use read-only completion polling and preserve recovery.
- [x] Trace gold item identity and authoritative inventory award; validate descriptor, all XOR pairs, bounds, overflow and capacity.
- [x] Extend the one-shot update dispatcher with a native gold award and runtime revalidation.
- [x] Add Save game and three Gold buttons to Player; serialize character requests with saving.
- [x] Verify controlled requests, native CPU/emulator context, recovery, the English UI and offline wheel installation.
- [x] Export 247 REA records/snapshot and close the analysis session.
- [ ] Verify actual Unepic gold increments, spending, zero-gold inventory and active-hook disconnect.
- [ ] Verify manual save/reload in Hard/Hard++ with unchanged difficulty, position and gold.

Save-slot correction: native selection/enumeration confirms nine slots (0–8). Fixed the off-by-one rejection of slot 8; all nine queue/consumption checks pass. Full suite: 589 passed, six sandbox ptrace skips. Actual-game saving remains pending. See the ninth-slot correction in [saving notes](runtime-notes/saving-and-gold.md).

## Unepic Credits extension

User-authorized currency buttons use the full name Unepic Credits and +100/+1000/+10000 amounts, matching Gold.

- [x] Trace item 0x238e, score-minus-counter rebuilding, native spending and raw save/load.
- [x] Validate the source, descriptor and inventory; execute a one-shot counter adjustment with runtime rechecks.
- [x] Add the separate currency row and retain pending/backup/save/lifecycle guards.
- [x] Verify native CPU repeated rebuild/spending/raw-counter round trip, emulator context and the compact English UI.
- [x] Export 258 REA records and snapshot, then close the session.
- [ ] Verify actual Unepic increments, subsequent updates, purchases, save/reload and disconnect.

Full suite: 698 passed, six sandbox ptrace skips. Details: [credits](runtime-notes/credits.md).

## Kill Points extension

User authorized buttons for the newly available Kill Points (KP) bar. Add +1/+10/+100 displayed KP, clamped to the native maximum of 5 KP (25 internal steps). The controls require the game's existing unlock flag and never unlock the feature themselves.

- [x] Retain REA evidence for the authoritative counter, HUD units/cap and ordinary consumption.
- [x] Read KP from the existing character block and display its current/max bar.
- [x] Extend the one-shot dispatcher with a checked, capped KP increment and normal dirty flag.
- [x] Preserve backup, pending/save serialization, runtime context guards and read-only polling.
- [x] Verify native CPU and emulator execution, context/cap/invalid/locked cases and UI; build, install and verify the wheel.
- [ ] Verify actual-game increments, spending, full bar, save/load and disconnect.

Full suite: 898 passed, six sandbox ptrace skips. Evidence and limits: [Kill Points](runtime-notes/kill-points.md).


## AppImage and GitHub distribution (2026-10-12)

User authorized a public `0xAF/unepic-trainer` repository with MIT licensing, a downloadable AppImage, English README and tag-triggered releases.

- [x] Prepare user documentation, original icon and demo screenshot.
- [x] Add a writable XDG data root for frozen applications and an isolated system GDB launcher; source behavior remains unchanged.
- [x] Add a pinned Debian 12/Python 3.12 build container, PyInstaller/AppDir packaging and checksum generation.
- [x] Add test/build/smoke checks and a tag-only release job using GITHUB_TOKEN.
- [x] Exclude game artifacts, backups, raw REA exports and caches; retain curated evidence notes.
- [x] Complete container/AppImage verification, license collection and host smoke checks.
- [x] Initialize Git, review staged files, create/push the public repository.
- [x] Push v0.1.0, verify the hosted build and downloadable release assets.

The Steam installation remains read-only. Actual-game checks and cross-distribution coverage remain limited as recorded in README/runtime notes.

Distribution verification: full host suite 914 passed (9.51s); Debian/Python 3.12 suite 914 passed (10.83s), no skips. AppImage system GDB/MI, offscreen and X11/Xvfb demo/normal startup and graceful shutdown pass. Host Arch smoke checks pass. Mismatched version tags are rejected before building. Public GitHub repo and v0.1.0 release are published. Both hosted workflows succeeded; the downloaded AppImage matches its checksum and GitHub digest and passes host smoke checks.
