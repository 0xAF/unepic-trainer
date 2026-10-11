# HP verification status

Implemented: current entity pointer, float32 current HP, int32 maximum HP, XOR decoding using live keys, mirror comparisons and checks of both integrity flags.

Healing stops the target, rereads the current character and writes only current HP. It does not resurrect a character at zero HP. Invalid, NaN or implausible HP and active integrity flags reject changes. Controlled-data and owned-process tests exercise these operations.

## Game evidence

On 2026-10-09 the user supplied a screenshot showing a connected trainer, PID 2703759 and a loaded character. Level 16 matches the game HUD. The trainer reports 450/450 HP, XP 28770/127917 and 16 points. God mode is off and no error is visible. The original screenshot is archived locally in `.work/first-connection.png` and excluded from publication.

The red game health gauge ends at a gold marker before the right edge. An earlier full-gauge interpretation was premature and was corrected after the user questioned it. The remaining segment's meaning is unknown. The screenshot does not independently establish numeric HP, XP or points.

Retained REA E09 (`ev_7224b0b25fa2337de0b65a42d510a2fc179f22520277776f0fceeff93b714e12`, `FUN_0046b800`) and the trainer code were rechecked: current HP is entity `+0x4ec`; the current calculated maximum is `+0x4e8`. The game recalculates the cap from progression, skill and equipment, then clamps current HP. This cap is not a fixed lifetime maximum. HUD scaling and the gold marker have not been traced.

The user subsequently confirmed that taking damage decreases the trainer HP reading and pressing Full heal restores health in the game. This verifies the basic read/write behavior in that session. Exact before/after values, separate integrity-flag readings and progression observations were not supplied.

## Backup evidence

`backups/20261008T215445Z-98e804e3/manifest.json` identifies a Steam userdata App ID 233980 `remote` source. It contains four `save/game_*.sav` files, `retos.bin` and `config.cfg`. All six copied file sizes and SHA-256 hashes match the manifest. Save restoration and which slot belongs to the current character have not been checked.

## Remaining checks

Exact numeric HP against the game, HUD scaling, equipment-induced maximum changes, room transitions, save/load and backup restoration remain open. The agent sandbox denies ptrace even for owned children and GDB launching `/bin/true`; host connection is established by user evidence. No agent privilege elevation or Yama policy change was attempted.

Player protection against ordinary attacks, enemy damage and normal player damage after disabling have been reported working. The user clarified that player HP decreases while burning, then reported poisoning as well. A separate periodic-damage store is now hooked; actual-game verification of that update remains pending. Minion HP and protection are separate follow-up work. Record new results before making broader coverage claims.
