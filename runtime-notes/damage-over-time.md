# Periodic damage investigation and fix

Raw REA exports are retained locally and excluded from the public repository.

On 2026-10-09 the user reported working protection from hits but continued loss while burning, and clarified that the player's HP decreases in the trainer. The user subsequently reported the same loss while poisoned. The previous hook only covered the direct-damage store at `0x004caf49`.

## Static evidence

For the supported executable hash, `FUN_004cb250` subtracts damage from current HP, clamps to zero and stores at `0x004cb2ad`. The displaced instruction is eight bytes: `f3 0f 11 9b ec 04 00 00`, or `MOVSS [RBX+0x4ec], XMM3`. The continuation is `0x004cb2b5`. The following conditional branch uses existing flags, so the trampoline must preserve them.

`FUN_00489350` calls this function from ongoing-effect timer/damage loops, including entity timer fields around +0x750 and +0x760. Other callers are `0x0040a8f0` and `0x00491900`. This establishes a separate ongoing-effect damage path. Individual timer slots have not been mapped conclusively to named fire and poison effects. The user reports motivate testing both effects after the fix; they do not prove that every variant uses this path.

The executable SHA-256 and both instruction byte sequences were independently rechecked against the read-only Steam file. No game file was changed.

## Implementation

Player God mode installs two conditional trampolines in one nearby page. Both reread the current player body pointer and skip only that body's HP store. Other entities execute their original MOVSS, using XMM2 for direct damage and XMM3 for periodic damage. Registers, flags and the SysV red zone are preserved.

Both sites are validated before writes. Partial installation restores every affected site. Disabling validates both tracked patches before restoration; failed restoration retains the remaining patch state and leaves the target paused for recovery. Both original instructions are restored and verified through the backend. The cave remains mapped and is reused.

## Verification

New regression tests failed against the original implementation: XMM3 was rejected, periodic damage remained unpatched, and secondary-site validation/recovery was absent. After the fix, the full suite passed 44 tests with three explicit sandbox ptrace skips.

Unicorn checks player/enemy branches for both instruction variants, preserving registers, flags and red-zone bytes. A disposable native CPU process executes both damage paths, checks player-only protection, follows a replaced player pointer and verifies normal damage after both instructions are restored. Controlled-memory tests cover secondary-site mismatches, thread instruction pointers, partial writes, failed rollback and retrying restoration.

Actual Unepic burning and poisoning with the updated trainer remain **unverified**. The previous eight host backend/hook passes predate this extension. Repeat the host tests, then launch the updated trainer and check both effects with God mode enabled and disabled. Blue EN, direct HP-zero writes, scripted deaths and other special paths are outside this verified coverage. Minion protection is separate pending work.

## Evidence ledger

Bundle: damage-over-time-evidence.json (`../rea-analysis/damage-over-time-evidence.json`, local export), 121 retained records. Snapshot: damage-over-time-analysis.json (`../rea-analysis/damage-over-time-analysis.json`, local export), provider-neutral analysis data.

| Evidence ID | Observation |
|---|---|
| ev_e95075ee77683c4adb617e6556e51e3773e6db54104d69911fc9a30d25db9437 | Pseudocode of 0x4cb250 |
| ev_9db65db9a6a2f800ccb55752508e65111781a8ad50ec064b71f7b468abae3ba8 | Assembly and XMM3 HP store |
| ev_45e9e6c297e403edfe1b24e0c90f364dee2ca1460943f430d4a87eec283aa045 | Callers of 0x4cb250 |
| ev_496236645c31f0ca9ec635d2352619d803d394c8d62104ccba0abd721b644bbe | Ongoing-effect damage in 0x489350 |
