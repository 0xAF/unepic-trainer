# Manual saving and campaign gold

Raw REA exports are retained locally and excluded from the public repository.

Authorized 2026-10-09: Save game for Hard/Hard++ as well as Easy/Medium, and Gold +100/+1000/+10000. Gold was the only authorized inventory modification in this extension; the later [Unepic Credits extension](credits.md) also changes its campaign balance. The application and documentation use English.

## Save request

The campaign frame at `0x503ec0` consumes four flags at `0x7e1930`: exit, room reload, game load and save. A manual save sets the last flag (`0x7e193c`) to 2. The consumer calls the normal writer at `0x504d20` with the current slot from `0x7c4bb8`, handles failure through the game's dialogue and emits the native confirmation for manual requests. It then clears the flag. Neither traced consumer nor writer has a difficulty gate. The automatic request generator separately depends on a difficulty-derived flag. These are static findings, not a verified Hard/Hard++ save.

The writer serializes complete character/world state with the existing difficulty and calls `0x504cb0`, which constructs `save/game_%d.sav`. The adapter at `0x4088b0` uses SteamRemoteStorage's normal write path. The trainer queues the in-memory request; the game handles serialization/storage. No trainer file write in the read-only Steam installation, difficulty change, player movement or GDB serializer call is used.

SaveGame validates fresh stopped data: living character, integrity pairs/flags, campaign mode, no simulation/custom map, one active hero, slot 0–8, a valid room, no pending exit/load/save, function prefixes and the game's save-block flag. A verified backup is required first. Polling is read-only. Disconnect clears an unprocessed trainer request while preserving a later game-owned automatic request. Failed write/clear recovery retains unsafe state and keeps the target paused.

Flag consumption does not prove successful storage. The status says **Save request processed · check the game confirmation**; check the game's own notification or error. The writer retains its normal restrictions. Resume a paused game to process the request.

## Gold award

Gold is inventory item ID `0x238d` (9101). The HUD uses a derived inventory at `0xff5060`; that display copy is not modified. The authoritative inventory is inline at character `+0x1400`, with count at `+0x140c` and `0xb8`-byte records beginning at `+0x1418`. Each record has four XOR pairs: `+0x08/+0x34` (quantity), `+0x10/+0x38`, `+0x18/+0x3c` and `+0x24/+0x40`, using the character's two keys.

The item table at `0x20b4840` has count at `+0xb9400`, capacity 1664 and descriptor stride `0x1c8`. The unique gold descriptor is located by ID; its internal name at `+4` is passed to the normal award function `0x417030`. That function resolves the descriptor through `0x41b120`, creates a temporary record through `0x514620` and merges/appends through `0x416ba0` until the requested quantity is consumed. Native operations update protected copies and inventory metadata/cache. No external quantity-pair writes or integrity-check bypasses are used.

Gold shares the one-shot character-update dispatcher at `0x46ef80`. Queueing validates a single active campaign hero, descriptor/name/type, all protected pairs for every inventory entry, descriptor pointer bounds/alignment, quantities, signed total overflow and four native function prefixes. Enough slots are reserved conservatively for the entire amount without relying on existing stack space. Full 512-slot inventory is rejected: the native adder can otherwise discard its last slot before adding an item. The dispatcher repeats campaign/body/room/integrity, descriptor, inventory-pair, overflow and capacity checks immediately before calling the native function. It handles an existing gold stack and no gold entry. Invalid/stale requests cancel; repeated updates cannot replay them.

Calls preserve GPRs, flags, the SysV red zone and x87/MMX/MXCSR/all sixteen XMM registers. A native null return reports failure; native failure may have partially changed state, so check the game. Restoration and retained cave lifetime follow the progression controller. Gold, points and level-up share one pending request. The UI and worker serialize these requests with saving, so a pending mutation is processed before Save game can be requested. No periodic GDB stops or writes were added.

## Verification and host checks

Full suite: **589 passed, six real-GDB tests skipped** because the sandbox denies ptrace. Controlled checks cover request-only saving, backups, pending actions, invalid context, partial writes, recovery and cleanup. Native CPU execution verifies all gold increments with existing/initially empty inventory, one-shot behavior, changed/full-inventory rejection and entry restoration. Unicorn verifies the award ABI, CPU context, empty/unlimited stacks, bounds, pairs, capacity, overflow and native failure. The English 860×846 demo was inspected at `.work/saving-gold-ui.png`.

Actual Unepic saving and gold remain unverified. On the host, check each increment, ordinary spending/HUD refresh, no replay, zero-gold inventory, and disconnect with the dispatcher active. Request Save game in Hard and Hard++, confirm the game notification, reload and check position, gold and unchanged difficulty. Keep the existing backup; backup restoration and Steam Cloud behavior remain unverified.

## Evidence

REA bundle (`../rea-analysis/saving-and-gold-evidence.json`, local export) contains 247 records; provider-neutral snapshot (`../rea-analysis/saving-and-gold-analysis.json`, local export) retains evidence with an empty separate cached-entry list. The session was closed after export. The project-local copy and read-only Steam executable retain the supported SHA-256. Original artifact strings remain unchanged.

| Finding | Evidence ID |
|---|---|
| Campaign save consumer | `ev_2cc5dd04a784e9c52818472bf59201222d37cf74babb004afdbc0b28f4afc442` |
| Native serializer and restrictions | `ev_f9d7e21af177e0f158bef8e6e8565b85d78891ab1439afcaf8b0e0ef74cd2e96` |
| Difficulty-derived automatic-save setup | `ev_771ca7c14c55f740b19a76de2533fefe7794cbbf0f11c30427a4e2217926306f` |
| Automatic request generator | `ev_810a2bdc66dbd8c10f374017bffe0ae06f6aadecb368328766dc9b6e118077ec` |
| Native confirmation queue | `ev_f841c2e6bcb28c1c8cf261ec70611446ce92e4417cc76cf7abd79a8fd26d2541` |
| Save filename wrapper | `ev_07516c2c2cc3d638aaf4812e230232f5ae17b83528241e28d123dc07e89dcca9` |
| Steam storage adapter | `ev_6f3cfd7b77347708e5a6f680e418fd22d279059f4994954efa45f805d3c5d3be` |
| Gold HUD identification | `ev_dd5cf610d9bd4c5e3b61d41e9a445e2cf0a6dab2285f629a50fbf102b4d36997` |
| Authoritative quantity sum | `ev_7941f4d8fc5947e872a207a0ec7e5013cff2f05881b2f71ca80cade998d08c1e` |
| Internal-name descriptor lookup | `ev_742be1d4432dc5a46b23df29bceccd2d5a2318d6dff91c895b9d536faf0982f8` |
| Native award wrapper | `ev_ccba82d97d144f5df3e184ad9d251be8441b434879a3d7d882fe7073e75c0acc` |
| Merge/append/capacity/cache | `ev_ccd72bc3bb518570fafed521a23095cb6360e5ff0579739f73c143351fec8713` |
| Protected item factory | `ev_fa2efa32d863fdc6823a1ee1b123e474ff78b7f0c7920bf71bd05dc16958d584` |

Native-prefix byte reads are retained alongside analysis. Decompiled symbols are analysis labels, not original source names.


## Ninth-slot correction

The user reported `Invalid current save slot` when pressing Save game. The initial trainer boundary excluded index 8. Native selector `0x4531e0` uses unsigned `CMP ESI, 8` / `JBE` and accepts 0–8 inclusive; enumerator `0x4536d0` visits exactly nine slots. Validation now accepts the ninth slot, still rejects negative indices and 9+, and includes the observed value in invalid-slot diagnostics. Controlled request/consumption checks cover all nine indices. Slot 8 reproduced the reported error before the fix; the full suite now passes 589 checks with the same six sandbox ptrace skips. Actual-game saving still requires host confirmation.

Slot evidence bundle (`../rea-analysis/save-slot-evidence.json`, local export) retains 251 records and snapshot (`../rea-analysis/save-slot-analysis.json`, local export) retains their evidence; the REA session is closed.

| Finding | Evidence ID |
|---|---|
| Native slot selection | `ev_11fcda8216c1349691a8eb745055f762a786662bde8c4dda5b16c5c292ed3df4` |
| Inclusive unsigned boundary assembly | `ev_d484703b6be90a5b3898b1739e34948c0ccc77689bcc9b6585c971224e8e41df` |
| Nine-slot enumeration | `ev_0f1c701a3dae4501e41799474bad17c1f27b26ccf2869990da42e33195f3ed80` |
