# Campaign points and immediate level-up

Raw REA exports are retained locally and excluded from the public repository.

Authorized 2026-10-09: +1/+10/+100 points to distribute, immediate Level up, and Player/Minion columns. The user explicitly requested immediate leveling. Inventory changes and XP multipliers were outside this original extension. The subsequently authorized gold award is documented separately in [saving and gold](saving-and-gold.md).

## Native operations

The supported executable hash remains `62c04002b98eee3f33d0f8c27030b1f5ea23d3ede56d62af9da6b1436a583962`. Analysis used the project-local executable copy through REA/Ghidra; the Steam installation was not modified.

| Operation | Address | Behavior |
|---|---|---|
| Add free points | `0x46ae00` | Add delta to both XOR-encoded copies at +0x16c/+0x188 |
| Read XP threshold | `0x46ada0` | Decode the current threshold |
| Set XP | `0x46ad80` | Update both XP copies at +0x160/+0x17c |
| Award XP and level | `0x46c8d0` | Normal level-up, points, healing and notification path |
| Character update entry | `0x46ef80` | Displaced eight bytes: `4156415541545553` |

Setting XP to the threshold alone does not trigger the normal level-up on the ordinary character update. The dispatcher reads the current threshold, sets XP through the game's setter and invokes XP award with delta 1. This enters the threshold comparison even when campaign scaling rounds that small award to zero. The game increments level and grants the usual difficulty-dependent points, healing and effects; its updates recalculate derived stats/thresholds. Residual XP follows the native award calculation. The campaign path contains a level 25 cap.

`FUN_004e0340` also checks allocated-point budgets. Its traced callers include network packet validation, save enumeration and custom-map/network initialization. The mode-zero story load in `FUN_00503ec0` skips the traced custom-map initialization call, while `FUN_00503480` branches separately for story mode. This supports the campaign-only scope; it does not prove that every possible save/load or skill-allocation path tolerates extra points. No validity checker, detection flag or penalty is disabled. Actual-game point spending and save/load must be checked separately.

## Request and hook lifecycle

The worker creates a verified save backup before the first mutation. With all threads stopped, it validates the process/build, living body, campaign mode, room, integrity flags, all four matching XOR pairs, signed balances, level cap and native function prefixes. It installs one reversible update-entry hook and writes a request with the expected body, room and level. No direct external progression-field write occurs.

On the next update of the selected hero, the hook atomically claims the request and repeats the context/integrity/balance checks. It calls native functions on that game thread. A changed body/room, incompatible mode, dead character, mismatched pair or invalid balance cancels the request. Foreign heroes and disabled hooks leave it untouched. Completion prevents replay on subsequent updates. A stale level-up request is cancelled rather than leveling a changed character.

The trampoline preserves general registers, flags, the SysV red zone and the x87/MMX/MXCSR/XMM context; calls use a 16-byte-aligned stack. A failed request write must be cleared while stopped; failed clearing retains unsafe state and restoration metadata. Disconnect cancels idle requests and restores the update entry before detaching. A request already claimed may finish in the retained cave. The cave stays mapped until target exit to let such a thread return safely.

The UI disables progression and gold controls while a character request or save is pending. Save game waits for pending character changes. Pause requires resuming the game. Completion is read through the existing live read-only view; no periodic GDB interruptions or refill writes were added. The update entry is also a checked allocation-stub fallback when HP/ENERGY sites are already patched.

## Controlled verification and remaining checks

Full suite: **435 passed, 6 skipped**, with all six skips due to sandbox ptrace denial. Tests cover +1/+10/+100, immediate native leveling without another XP reward, both XOR copies, one-shot behavior, campaign/body/room/level/integrity cancellation, overflow, patch coexistence, partial-write recovery, backup gating and shutdown of a pending request. Unicorn verifies GPRs, flags, MXCSR, all sixteen XMM registers, stack alignment and the red zone. A disposable native CPU process executes and restores the actual product dispatcher. The two-column English demo was rendered and inspected at `.work/progression-ui.png`.

Host integration command:

```bash
rtk proxy .venv/bin/python -m pytest tests/test_progression.py -q -rs
```

The new real-GDB integration test enables player/minion HP and ENERGY protection, adds points, levels immediately, verifies no replay and restores every hook. It cannot run inside this sandbox. In Unepic, verify each points increment, immediate level-up and normal level-up effects, the next XP threshold, spending added points, save/load and close/disconnect with the progression hook active. No actual-game result is claimed yet.

## Evidence

REA evidence bundle (`../rea-analysis/progression-evidence.json`, local export) contains 213 records; provider-neutral analysis snapshot (`../rea-analysis/progression-analysis.json`, local export) preserves the session. The session was closed after export. Native function prefix reads are retained alongside the analysis. Neither artifact is a native Ghidra project.

| Finding | Evidence ID |
|---|---|
| Paired points addition | `ev_f38958b7e8bcb1857d005dc240d38b3d29eabb0e3b3e88ae174bd8f2fa4d7e29` |
| Native XP and level-up | `ev_fe7db7007ed6e6c8515c1a0b93b6f25d4a7a573a054f1eb10761a7040f5821bd` |
| XP path assembly/cap | `ev_f79eb89098b2812554ff51cd02e525b60d5c6f428a56e7b539b08c763c99c129` |
| Update entry instructions | `ev_7b06d081c12d89ed13b602a5bcd70f5bcbd8b4d68a52bcea50b1e5e24368eb5b` |
| Validity-check callers | `ev_334ca37b5e5a85ca2372a48dc511c659da76b0cd7c174f326efd323b9d97f767` |
| Custom-map/network initialization | `ev_64769a8e455cbfe61681dab53c7e9199a1c6fd1a0548df47df136824718631cb` |
| Mode-specific main path | `ev_771ca7c14c55f740b19a76de2533fefe7794cbbf0f11c30427a4e2217926306f` |
| Mode-zero story reload | `ev_2cc5dd04a784e9c52818472bf59201222d37cf74babb004afdbc0b28f4afc442` |
