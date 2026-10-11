# God mode implementation and limits

For the supported hash, the eight bytes of MOVSS at `0x004caf49` (direct damage, XMM2) and `0x004cb2ad` (periodic damage, XMM3) are replaced with a rel32 JMP and three NOPs. Mismatched bytes or a stopped thread inside the patch range reject installation.

The trampoline rereads the current entity pointer from `0x01446dd8` and compares it with RBX. Player damage skips the original store; other entities execute MOVSS. Each trampoline returns after its displaced instruction, at `0x004caf51` or `0x004cb2b5`. RAX and flags are saved below the SysV red zone; RSP and other registers are unchanged.

A nearby executable page is allocated with Linux mmap syscall 9 and MAP_FIXED_NOREPLACE. Temporary syscall/int3 instructions execute in a stopped thread with scheduler-locking; original code, registers and scheduler settings are restored. Unconfirmed restoration leaves the target stopped. This GDB path passed against an owned process in the host terminal; the agent sandbox denies ptrace.

Unicorn verifies both branches, registers, flags and the red zone. A disposable native CPU process verifies player 100-to-100, enemy 100-to-75, protection following a replaced entity pointer and normal damage after restoring original code.

Disabling restores and verifies the eight original bytes at both sites. The code cave remains mapped until process exit because a stopped thread may be inside it; subsequent enable operations reuse it. Unexpected foreign patch bytes are not overwritten blindly, and failed restoration cannot be reported as a successful detach.

## Host verification

On 2026-10-09 the first live hook test stopped before mmap or instruction modification: GDB rejected an integer cast of `$eflags`. Reading flags now discovers the register number and uses numeric MI register reads. A synthetic ELF core reproduces the failure and verifies the fix with real GDB.

The host backend/hooks repeat passed all eight tests in 0.93 seconds. With the hook enabled, player HP stays at 100 and enemy HP drops to 75; after disabling, player HP drops to 75 and enemy HP to 50. This covers allocation, conditional hook and restoration on the owned fixture.

## Unepic verification

The user confirmed working god mode, then explicitly confirmed both follow-up checks: enemies take damage while protection is enabled, and the player loses HP again after disabling it. Basic player-only protection and restoration work in the reported game scenario. Attack types/counts were not supplied; detach/close was not separately reported. No address log or independent game patch-byte capture was provided.

The user later clarified that burning reduces the player's HP in the trainer and reported poisoning too. The original hook missed the separate ongoing-effect damage store. The updated implementation covers both stores with player-only trampolines and transactional restoration. Controlled-memory, Unicorn and native CPU checks pass; burning/poisoning in Unepic with the new code remain unverified. See [periodic damage evidence and verification](damage-over-time.md).

## Initial-allocation collision fix

The user reported `Another thread or patch occupies syscall stub range` on first activation, followed by successful activation after moving the player. The original allocator temporarily placed syscall/int3 at the selected thread's current instruction pointer. Multiple waiting threads can share that address, so the occupancy check correctly refused it.

The allocator now retains that check and falls back to the profile's verified direct-damage instruction when the current location is occupied. It requires the complete original eight-byte sequence, no stopped thread anywhere within that instruction and no overlapping tracked patch. Only the selected thread is redirected there under scheduler-locking; the three temporarily changed bytes, all saved registers including the waiting RIP, and scheduler settings are restored before normal execution. If the fallback is also occupied or unverified, activation still fails without writes.

Controlled-kernel tests reproduced the original refusal and now verify successful allocation through the fallback, recovery after an unexpected stop, byte mismatches and overlapping patches. The full suite passes 50 tests with four sandbox ptrace skips. A new real-GDB test reserves the waiting PC to force the same fallback and checks allocation, code/register restoration and subsequent ordinary damage. It cannot run inside the agent sandbox and awaits host verification. Actual first-click activation while idle in Unepic also remains pending.

Host command:

```bash
rtk proxy .venv/bin/python -m pytest tests/test_backend.py tests/test_hooks.py tests/test_remote.py -q -rs
```

## Remaining checks

Disconnect/close with an active hook, room transitions, save/load, burning/poisoning with the update, lethal traps, scripted deaths and side effects after the skipped HP store remain open. Skipping two known stores does not establish coverage of direct HP-zero paths. The HP protection itself does not change XP, level or inventory; the penalty update is not bypassed. Separate authorized points/level-up actions are described in [progression notes](progression.md).

## Subsequent host report

The user reports that the requested tests passed and that enabling God mode now works without the initial allocation error. No test count or terminal output was supplied. This supports the corrected activation path; it does not independently verify fire/poison coverage or minion features.
