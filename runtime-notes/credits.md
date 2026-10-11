# Unepic Credits

Raw REA exports are retained locally and excluded from the public repository.

Authorized by the user: separate Unepic Credits buttons in Player. The user clarified the full currency name; +100/+1000/+10000 match the existing Gold amounts. Implementation and documentation use English. The Steam installation remains read-only.

## Authoritative source

The campaign HUD at `0x462390` counts item `0x238e` (9102), distinct from Gold `0x238d`. The ordinary character update at `0x46ef80` rebuilds that item every update: sum the fifteen challenge scores at `0x772640` whose corresponding types at `0x7882a0` equal 2, then subtract the signed per-hero counter at `+0x170`. The score-list sentinel at `0x77267c` is -1. If the item is missing, the update creates it with the normal item factory and then uses paired quantity setter `0x41a660`. Changing only the protected inventory quantity would be overwritten.

The item-exchange path in `0x46d690` consumes item 0x238e and adds the cost to the hero's +0x170 counter. The writer `0x504d20` stores that counter as four raw bytes inside the LOGR section. Loader `0x5064b0` reads it into uint32-indexed character field 0x5c (+0x170) for supported modern saves. No negative-value clamp appears in that traced read. This establishes the saved source representation; actual Unepic save/reload remains unverified.

## Request behavior

The existing one-shot update-entry dispatcher accepts action 4 for credits. Before queueing, the worker requires a verified backup. Validation checks a living campaign hero, body/room/integrity, the unique currency descriptor and internal name, all inventory XOR pairs, descriptor pointer bounds/alignment, capacity, original native function prefixes, score sentinel, nonnegative type-2 scores, signed score sum/current balance and arithmetic overflow.

On the selected hero's next update, the dispatcher atomically claims the request, repeats context and inventory checks, recomputes the score sum and current balance, then subtracts the amount from the source counter once. Negative source counters intentionally represent extra credits beyond earned scores. The normal displaced update subsequently creates/rebuilds the credit item and its matching XOR quantity copies. Achievement score/type arrays are unchanged. Credits remain spendable through the ordinary cost-counter path, and later updates recompute the remaining balance. Gold uses its existing native award independently.

No periodic stop/refill or additional protection hook is added. Requests share the existing patch/configuration, pending state, restoration and retained cave lifetime with points, level-up and Gold. CPU context is preserved. Changed context, invalid source/inventory or overflow cancels without changing the counter. Credits and saves wait for one another. A paused game must resume to execute the request. The raw source counter remains changed after detach; native rebuilding maintains the derived item without the trainer.

## Verification and limits

Full suite: **698 passed, 6 skipped**; all skips are existing sandbox ptrace refusals. Tests cover backups, request-only queueing, all amounts, invalid score/sentinel/balance/pairs and source overflow. Unicorn executes the product dispatcher, checking GPRs/flags/red zone/MXCSR/all XMM registers, one-shot behavior, stale-context/inventory rejection, source checks and no native Gold call for credits. An owned native CPU fixture executes all amounts through the product hook and ordinary rebuild, checks both quantity copies, repeated updates, normal spending, raw four-byte source save/load and unchanged Gold/challenge scores. That controlled raw round trip is not a game serializer or Steam Cloud test.

The English Player/Minion demo was inspected at `.work/credits-ui.png`, 860×842. Gold and Unepic Credits occupy separate compact rows. Actual Unepic currency/HUD behavior, purchases, save/reload and disconnect after credits changes require host verification. Check +100 first, move/wait to confirm it survives updates, spend some credits, then save and reload. Native failure paths and all scene transitions have not been exhaustively audited.

## Evidence

REA bundle (`../rea-analysis/credits-evidence.json`, local export) retains 258 records; provider-neutral snapshot (`../rea-analysis/credits-analysis.json`, local export) retains their evidence with an empty separate cached-entry list. The session was closed after export. The analyzed project copy matches the supported executable hash.

| Finding | Evidence ID |
|---|---|
| HUD item identity | `ev_dd5cf610d9bd4c5e3b61d41e9a445e2cf0a6dab2285f629a50fbf102b4d36997` |
| Native score-minus-counter rebuild | `ev_af9d5c764b32beba04c7cec86d2c2239bde87308ee08a7fc4d0d3f4b1138e11c` |
| Credit item exchange and cost accounting | `ev_37827fb5b5f598c2e64ce390687f36d0b00842160c1030728e1f18554b95ff8e` |
| Saved source counter | `ev_f9d7e21af177e0f158bef8e6e8565b85d78891ab1439afcaf8b0e0ef74cd2e96` |
| Modern counter loading | `ev_6f9f62ad0f63d5909ec7b3dbb679ae21dbf1c6ab4e27e0afa0c8e83948104beb` |
| Raw four-byte integer serialization | `ev_3c10fdbaadc1554ab57134b826df35d126766dd13dc6722211d542235e576b13` |
| Paired native quantity setter | `ev_0e630b86f9c23f5755c308a2d7a3f08357f4fb6300c2215a92108ee8ab1af96a` |
| LOGR/logr section strings | `ev_023037c25a15386abed58d82674ac70672741f2fd0991be34063846b9afecce9` |

Static pseudocode is not original source or proof of actual execution. Raw source-counter behavior is documented explicitly because this differs from Gold's native award.
