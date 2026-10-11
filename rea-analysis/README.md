# Unepic: data integrity and trainer analysis

Raw REA exports are retained locally and excluded from the public repository.

Analyzed input: `unepic64s`, Linux ELF x86-64, Ghidra 12.1.2 through REA 6.0.0.
SHA-256: `62c04002b98eee3f33d0f8c27030b1f5ea23d3ede56d62af9da6b1436a583962`.
The original findings below come from static analysis of this executable. These operations did not run or modify the game. Addresses have not been checked against other Linux variants or Windows releases. Subsequent user-reported game checks are recorded separately in [runtime notes](../runtime-notes/god-mode.md).

## Integrity mechanism

Several character and inventory values have two 32-bit copies, each XOR-encoded with a different global key:

```c
primary = value ^ *(uint32_t *)0x009f43b4;
mirror  = value ^ *(uint32_t *)0x009f43b0;
```

`FUN_004e0320` decodes both copies and compares them. A mismatch sets `context + 0xd18` to 1. With the global context at `0x007c5000`, this is `0x007c5d18`. This function does not clear the flag when a later comparison matches. [E01]

Character update `FUN_0046ef80` checks the four pairs below. `FUN_00419050` also checks four pairs in each inventory record. [E02, E07]

| Value | Primary character offset | Mirror offset | Setter |
|---|---:|---:|---:|
| XP toward the next level | +0x160 | +0x17c | 0x0046ad80 |
| Next-level XP threshold | +0x164 | +0x180 | 0x0046adb0 |
| Level | +0x168 | +0x184 | 0x0046ad50 |
| Available skill points | +0x16c | +0x188 | 0x0046ade0 |

Field names are analyst interpretations based on XP awards, leveling, point allocation and threshold calculation. The setters update both copies. [E08, E09]

Initialization `FUN_005027d0` sets the primary key to zero and the mirror key to the low 32 bits of `DAT_02378bc8`. A primary field may therefore look like a plain number during scanning. The trainer must read keys from the live process. [E10]

## Response to a mismatch

`FUN_0046fd90` first updates characters, then processes a nonzero `0x007c5d18`:

1. Clear that flag and set the persistent penalty flag `0x007c5d1c = 1`.
2. Call `FUN_004caed0(entity, max_hp * 2, 0, 0, 0)`.
3. Reset level to 1, XP and free points to 0, and the XP threshold to 1,000,000.
4. Clear inventory entries, change skills and add the base items `camiseta` and `zippo` again.
5. On later updates, the penalty flag sets `entity + 0x644 = 11`. Its meaning across all game subsystems has not been traced.

Twice the maximum HP is sufficient to reduce normally bounded current HP to zero. Assembly confirms that `0x0046fe64` doubles maximum HP and `0x0046fe67` calls the damage function. This supports the user's recollection of immediate death, but the penalty also changes progression and inventory. [E03, E04]

## HP and direct damage

| Data or code | Address or offset | Type |
|---|---|---|
| First character record | 0x0142d620 | Structure |
| Character record size | 0x19b60 | Bytes |
| Body pointer | Character +0x197b8; first slot 0x01446dd8 | 64-bit pointer |
| Maximum HP | Entity +0x4e8 | int32 |
| Current HP | Entity +0x4ec | float32 |
| Direct damage function | 0x004caed0 | Shared by game objects |
| Reduced-HP store | 0x004caf49 | MOVSS [RBX+0x4ec], XMM2 |

The function subtracts damage and clamps the result to zero. Store bytes are `f3 0f 11 93 ec 04 00 00`, at file offset `0x000caf49`. [E05, E06]

Maximum HP is recalculated from level, skill and equipment; current HP is then clamped to that maximum. HP is not one of the four duplicated values in the described character check. This does not establish the absence of other HP checks. [E09]

## Additional checks

- Inventory records are 0xb8 bytes. Pairs +0x08/+0x34, +0x10/+0x38, +0x18/+0x3c and +0x24/+0x40 use the same two XOR keys. [E07]
- `FUN_004e0450` compares item IDs against a separate array on a conditional multiplayer path in `FUN_00502980`. Mismatches set the same penalty flag. [E11]
- `FUN_004e0340` checks valid items and skill allocations, including per-skill limits against level and the total point budget. Matching XOR copies alone do not guarantee a valid character. [E12]
- `FUN_004e0560`, reached through a multiplayer path, adds skill-level, point-budget and progression-consistency checks. These are separate from immediate punishment in the current scene. [E13]
- `Memoria checksum error! %s` comes from allocator check `FUN_0052af90`, checking 0x1d before a block and 0x45 after it. Its handler `FUN_0052d110` is empty in this build. This path does not explain the punitive death. [E14]

## Implications for the single-player trainer

The direct damage store can be conditionally skipped for the selected character's current body. Its function also serves enemies; unconditional removal would protect them too. A timer that refills HP may miss a lethal hit between updates. Conditional damage hooks give more precise control, but do not establish coverage of every scripted or direct HP change.

Protected progression requires consistent primary and mirror copies. Game setters preserve that relationship. External paired writes would need to stop the game check from running between the writes, and must satisfy the additional skill and inventory validity checks. The progression extension now uses the native points-adder and XP/level-up path from a one-shot character-update hook, restricted to campaign mode. It preserves both XOR copies and leaves integrity checks active. See [progression evidence and limitations](../runtime-notes/progression.md).

Blocking the penalty's lethal damage would leave progression and inventory resets active. Skipping all of `FUN_0046fd90` would also skip normal character updates. The trainer does neither.

Validate executable hash, process identity, mappings, character pointer and original bytes before runtime writes. The penalty changes inventory and progression; whether these changes automatically reach a save file has not been established.

## Follow-up investigations

The original direct-damage hook was confirmed working against ordinary attacks by the user. Burning and poisoning exposed incomplete coverage. A separate periodic damage store at `0x004cb2ad` has now been added to the player hook, with fixture/emulator verification; game verification remains pending. See [periodic damage](../runtime-notes/damage-over-time.md) and its REA evidence (`damage-over-time-evidence.json`, local export).

Owned-minion identity was traced separately. See [minion investigation and proposed controls](../runtime-notes/minion.md) and its REA evidence (`minion-evidence.json`, local export). Minion HP, healing, independent god mode and maximum-energy locking are now implemented and verified on controlled fixtures. The actual game still needs verification. ENERGY evidence is retained in minion-energy-evidence.json (`minion-energy-evidence.json`, local export).

Original evidence is retained in unepic64s-evidence.json (`unepic64s-evidence.json`, local export). JSON analysis snapshots are provider-neutral records, not native Ghidra projects. FUN_/DAT_ symbols and field names are analysis output, not recovered original names. Original artifact strings retain their original language.

Integrity flag observations, special lethal/scripted paths and save/load checks remain open. Anti-debug behavior and executable-code checksums have not been exhaustively audited.

## Original evidence ledger

| Code | Evidence ID | Source |
|---|---|---|
| E01 | ev_09006262df82f348636536e34afe3d67fb9fa5ae86070402da04ee427a4d32cf | Assembly at 0x4e0320 |
| E02 | ev_af9d5c764b32beba04c7cec86d2c2239bde87308ee08a7fc4d0d3f4b1138e11c | Pseudocode at 0x46ef80 |
| E03 | ev_e8f9ba3a1c301e05e681d84d8e7672b906cabcd0e701b93b2494aa2994136af3 | Pseudocode at 0x46fd90 |
| E04 | ev_fa4b9fc20496e303aadcd020ec68350a4312c3dbaed57dcbf05863bf11d3b38c | Assembly at 0x46fd90 |
| E05 | ev_dd38324a5df3113230948bd3d537d94fab6e505292d76e5055fc90321586bb91 | Pseudocode at 0x4caed0 |
| E06 | ev_42f7c5d9a7433e57d3c18ea2df4afcd5b0f079a2bf5593dddd455c487d88ded3 | Assembly at 0x4caed0 |
| E07 | ev_037c697ccc9fb6f5476bcaf64bf4f19028c148820762ce5f349a4276ec95e799 | Pseudocode at 0x419050 |
| E08 | ev_fe7db7007ed6e6c8515c1a0b93b6f25d4a7a573a054f1eb10761a7040f5821bd | XP and leveling at 0x46c8d0 |
| E09 | ev_7224b0b25fa2337de0b65a42d510a2fc179f22520277776f0fceeff93b714e12 | Stat recalculation at 0x46b800 |
| E10 | ev_2aff12f551d464d48bb71dff29c906ec87d79c70cea38162cd2b49c057261d59 | Key initialization at 0x5027d0 |
| E11 | ev_64c79bfdf143b61fc741e69888354c9f81368fdb3585d37c040ece0a7c824c94 | Main update at 0x502980 |
| E12 | ev_b130c81fc8d12dd6ef004acac4bf99efb44ffc607088ebaa25313c90d7e430a6 | Character validity at 0x4e0340 |
| E13 | ev_61b4a285c15f15a09694b4831f15c9e8bdfa442ec44ffc9502513c896a2c49f6 | Additional progression checks at 0x4e0560 |
| E14 | ev_91982ace54708862401968995d6d31a108e5c1e929e34a04aa74ab37030c449a | Allocator markers at 0x52af90 |

## Manual saving and gold

The manual save consumer has no difficulty gate; automatic save generation is conditional. Gold is protected inventory item 0x238d, with a native award wrapper that maintains quantities and metadata. Implementation, evidence ledger and remaining host checks are in [saving and gold](../runtime-notes/saving-and-gold.md). REA bundle (`saving-and-gold-evidence.json`, local export) retains 247 records and snapshot (`saving-and-gold-analysis.json`, local export) retains evidence; the session is closed. Static findings do not establish actual-game save or gold success.

## Unepic Credits

Item 0x238e is rebuilt on character update from challenge scores minus the hero counter at +0x170; modifying its inventory quantity alone would be overwritten. The trainer changes the saved source counter once and retains the normal paired native rebuild. Evidence and host limits: [credits notes](../runtime-notes/credits.md), 258-record bundle (`credits-evidence.json`, local export), snapshot (`credits-analysis.json`, local export). The REA session is closed.

## Kill Points

KP is the character counter at +0x174, enabled by +0x178. Native kills cap it at 25 steps; HUD/cost displays divide by five, giving a maximum of 5 KP. Ordinary ability use consumes this source counter. The trainer adds checked capped KP through its one-shot dispatcher and retains unlock/cost rules. Findings and pending actual-game checks: [KP notes](../runtime-notes/kill-points.md), 271-record bundle (`kill-points-evidence.json`, local export), snapshot (`kill-points-analysis.json`, local export). The REA session is closed.
