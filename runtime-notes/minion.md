# Owned minion HP and maximum ENERGY

Raw REA exports are retained locally and excluded from the public repository.

The English MINION section provides HP and ENERGY displays, Heal, independent God mode and Lock energy controls. Lock energy fills the resource to its current maximum and keeps it there. Controlled tests pass; the companion in the actual game still needs verification.

## Static identity and resources

Supported executable SHA-256: `62c04002b98eee3f33d0f8c27030b1f5ea23d3ede56d62af9da6b1436a583962`.

The first character is at `0x0142d620`, with body pointer +0x197b8 and room pointer +0x197c0. Room count is +0xbef0 and its inline 64-bit object-pointer array starts at +0xbef8. Pet spawn `0x0047a2d0` copies player ID +0x58c into pet owner +0x64c. Recall `0x0047a260` selects owned type-4 entities (+0x170) and sets state +0x5c8 to 0x73. State 0x76 and nonpositive HP are also excluded.

Maximum HP is an integer at +0x4e8; current HP is a float at +0x4ec. The reader bounds the room count to 4096, validates pointers and resource values, deduplicates entities and selects living owned pets. Writes reread ownership and resources while all threads are stopped. Multiple qualifying pets are displayed as totals and controlled together. Healing does not resurrect dead pets.

`FUN_00488dc0` reads maximum ENERGY as an integer at +0x178 and current ENERGY as a float at +0x608. Ability cost is +0x174. It regenerates ENERGY, clamps it to the cap, and subtracts ability cost. Template fields copied to entity +0x38 explain the cap offset. `FUN_004daf60` serializes pet ENERGY +0x608, HP +0x4ec and ownership +0x64c. The HUD function `0x00462390` uses client copies: HP +0x80, ENERGY +0x8c and template caps +0xe8/+0x140. The trainer uses authoritative entity resources rather than HUD copies. A zero ENERGY cap makes the energy control unavailable while HP controls remain available.

## Verified patch sites

| Resource path | Store address | Original bytes |
|---|---|---|
| Direct HP damage, RBX/XMM2 | 0x004caf49 | f30f1193ec040000 |
| Periodic HP damage, RBX/XMM3 | 0x004cb2ad | f30f119bec040000 |
| ENERGY spending, RBX/XMM0 | 0x0048907b | f30f118308060000 |
| ENERGY regeneration, RDI/XMM0 | 0x00488e0c | f30f118708060000 |
| ENERGY cap update, RDI/XMM1 | 0x00489170 | f30f118f08060000 |

The executable hash and three ENERGY instructions were checked directly against the read-only Steam binary. Static instruction evidence alone does not establish the identity of the user's current companion.

## Protection and restoration

Two HP trampolines share independent player/minion configuration bits. Three ENERGY trampolines use a separate allocation and configuration bit. Each follows the current player and owned living pet identity; other entities execute the original instruction. ENERGY protection writes the current positive cap rather than retaining a possibly depleted value. It preserves XMM0, general registers, flags and the red zone. Activation refills valid pets. The dynamic store hooks fill replacement pets on their next ENERGY update and use changing maxima; periodic displays never refill or stop the game.

Turning off either minion control leaves the other enabled. HP instructions are restored when neither player nor minion HP protection is active. ENERGY instructions are restored when its lock is disabled. Disconnect restores all five installed sites before detaching. A failed restoration retains recovery state and leaves the target stopped.

Remote allocation can use a verified ENERGY instruction when both HP stores are already patched. Every fallback requires matching original bytes, no stopped instruction pointers in its full instruction range and no overlap with a tracked patch. No game stepping or privilege change is used.

## Verification and remaining game checks

Full suite: **376 passed, 5 skipped**. All skips are real-GDB attach checks denied by sandbox ptrace restrictions. Unicorn verifies eight toggle masks, seven actor cases and five stores, including register/flag/XMM/red-zone preservation. A disposable native process executes the product trampolines for all masks and restores all five stores. Worker tests cover backups, independent controls and disconnect; UI tests and an inspected English demo cover displays and controls.

Run the host integration checks:

```bash
rtk proxy .venv/bin/python -m pytest tests/test_backend.py tests/test_hooks.py tests/test_minion_integration.py -q -rs
```

In Unepic, compare the companion's HP and ENERGY with the display; test healing, each toggle independently, ability spending, recall/resummon, room changes and disconnect. Also verify player burning/poisoning. Protection covers the identified damage stores; scripted lethal paths and direct zero assignments remain unverified. The minion controls do not change progression or inventory. Separate authorized player points/level-up actions are described in [progression notes](progression.md).

## Evidence ledger

Earlier bundle: minion-evidence.json (`../rea-analysis/minion-evidence.json`, local export), 116 records. Updated bundle: minion-energy-evidence.json (`../rea-analysis/minion-energy-evidence.json`, local export), 200 records. Updated snapshot: minion-energy-analysis.json (`../rea-analysis/minion-energy-analysis.json`, local export), provider-neutral analysis data. REA analyzed a project-local executable copy; the session was exported and closed.

| Evidence ID | Observation |
|---|---|
| ev_1d9c9a1edb7b4ce1422b5e442e87440461076bab8a11d9c924203c67ee0a8f19 | Pet spawn, owner ID and HP initialization at 0x47a2d0 |
| ev_159f25ee6eb0c9966b30bd10d369d9023440a343e6eaa9737326f786a159562d | Recall, room list and owned type-4 predicate at 0x47a260 |
| ev_37827fb5b5f598c2e64ce390687f36d0b00842160c1030728e1f18554b95ff8e | Pet dispatch at 0x46d690 |
| ev_af9d5c764b32beba04c7cec86d2c2239bde87308ee08a7fc4d0d3f4b1138e11c | Character update and room binding at 0x46ef80 |
| ev_15f5f087dcdcaae3020c75aa3ef8b994b4d5581149c64c8f8bbeec9bb73b7622 | Authoritative ENERGY, cap and cost in 0x488dc0 pseudocode |
| ev_0d6f030e6545037b8635eca6f1921beb36cad24ddb5596c69b0a5e377b71a77a | Assembly and all three ENERGY stores in 0x488dc0 |
| ev_874e26bb7838da5b4877230b814010201e37272dc763d95e67ac9a6a3e71fc79 | Pet resource serialization at 0x4daf60 |
| ev_dd5cf610d9bd4c5e3b61d41e9a445e2cf0a6dab2285f629a50fbf102b4d36997 | Companion HUD resource copies at 0x462390 |
