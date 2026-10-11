# Kill Points (KP)

Raw REA exports are retained locally and excluded from the public repository.

Supported input: Linux x86-64 `unepic64s`, SHA-256 `62c04002b98eee3f33d0f8c27030b1f5ea23d3ede56d62af9da6b1436a583962`. REA/Ghidra inspected the project-local copy; the Steam installation remained read-only. Static findings below are not actual-game execution evidence.

## Authoritative values and units

The campaign character stores a plain signed 32-bit counter at `hero+0x174` and its unlock flag at `hero+0x178`. These fields sit between the credits source counter and the protected progression mirrors. They are not an inventory stack or an extra skill-point pair.

The ordinary combat path in `0x48edf0` adds one internal step to qualifying characters in the same room, capped at 25. Its campaign increment is one step; a separate multiplayer branch may add a second. The trainer excludes multiplayer. Normal kill handling sets the character update flag at `+0x234`.

HUD `0x462390` reads the corresponding display-copy fields at `0x1001890`/`0x1001894`, draws a 25-step bar, and uses integer division by five for complete KP segments. Item descriptions in `0x45d180` likewise divide the resource/cost by five. Five internal steps therefore equal one displayed KP; the maximum is **5 KP**. The trainer additionally shows fractional progress, e.g. eight internal steps as **1.6 / 5 KP**.

The resource descriptor ID `0x1392` identifies KP requirements. Ordinary item/ability use in `0x48cf40` resolves the owning character, checks available steps, subtracts the cost and clamps at zero. The unlock path sets `+0x178` to one. The trainer changes neither the unlock flag nor those normal cost rules.

## Implementation

Player has a KP bar and **+1 / +10 / +100** buttons. Amounts refer to displayed KP; requests convert them to five internal steps each and saturate at 25. Consequently +10 and +100 both fill an eligible bar. Buttons are disabled for locked KP, a full bar, missing/dead characters, pending saves/character requests, busy operations and shutdown. Locked and unavailable states have distinct English labels.

The existing character-block read supplies both values without extra memory round trips. Reads reject counters outside 0–25 or flags outside 0/1. Automatic polling remains read-only and does not interrupt gameplay.

One-shot dispatcher action 5 reuses the existing reversible character-update hook. Queueing requires the backup gate, a living campaign hero, valid room/protected progression/function bytes, unlocked non-full KP, no custom map, exactly one active hero and a supported amount. Native execution repeats campaign/body/room/integrity/progression and KP context checks, atomically claims the request, clamps the increment and writes the source counter plus the normal update flag once. It preserves CPU state, never writes the derived HUD copy and leaves the unlock flag, Gold, Unepic Credits and challenge scores unchanged. Normal spending remains enabled. A paused game must resume to execute a request.

Completion reports **Kill Points updated · maximum 5 KP**, avoiding a false claim that a clamped +100 request added 100 points. Pending requests retain the existing cancellation, failed-write recovery and hook restoration behavior.

## Verification and remaining checks

Full suite: **898 passed, 6 skipped** in 4.96 seconds. Skips are existing sandbox ptrace refusals. New memory/worker/UI regressions failed for missing KP support before implementation; native CPU and valid/near-cap emulator cases also failed before the dispatcher extension.

The owned native CPU fixture executes all three increments through the product hook, checks one-shot behavior and the update flag, rejects locked/full/invalid counters and retains Gold/credits/challenge scores. Unicorn covers amounts, cap saturation, locked/invalid counters and changed body/room/campaign/custom-map/player/active-hero context, with register, flags, MXCSR, all sixteen XMM and red-zone checks. UI checks cover fractional KP, capped demo actions and pending/save/locked/unavailable controls. The English source demo was rendered and inspected at `.work/kp-ui.png`, 860×888.

Actual Unepic increments, bar units/animation, ordinary ability spending, room changes, disconnect and save/reload remain for host verification. Check +1 first with a partially filled unlocked bar, then +10 to fill it, spend KP normally and verify refill/disconnect. Save persistence is not established; the loader evidence retained from the earlier investigation shows reconstruction of the unlock flag from KP-using inventory, which alone does not establish persistence of the current counter. No current-game save result is claimed.

## Retained evidence

Evidence bundle (`../rea-analysis/kill-points-evidence.json`, local export): 271 records. Provider-neutral snapshot (`../rea-analysis/kill-points-analysis.json`, local export): retained evidence, empty separate cached-entry list. The REA session was closed after export.

| Finding | Evidence ID |
|---|---|
| HUD bar and complete-point segments | `ev_dd5cf610d9bd4c5e3b61d41e9a445e2cf0a6dab2285f629a50fbf102b4d36997` |
| HUD instruction confirmation | `ev_3178a124065c1a27099940b9740d2fd8d8e6dd5c245d58655773fab1d903853f` |
| Ordinary kill increment, 25-step cap and update flag | `ev_c9ecc8b9901dacae006b2c60d788cd40a8e1222f01965c3de79b02d5f9667c30` |
| Kill increment assembly | `ev_909eb005b62b1df41c9efdb755f207d6fba3e454f1721ccfd8c0dce9eb44f8f1` |
| Displayed resource/cost conversion | `ev_8307ea107bbdc88100de60588cc46a648787a481bc4c66eb8d295ac22e079f49` |
| Native KP consumption and unlock | `ev_d0fb26b6ea5b6a0535d9e992c29010cbcdea72201f8d0bccb34bccb60ded76d9` |
| Byte-to-counter character input | `ev_85758ad7d8182880ffcff0d8c776b1af7495bf48c655057c4d05137b0dffb84c` |
| Loader reconstructs KP unlock from resource-using items | `ev_6f9f62ad0f63d5909ec7b3dbb679ae21dbf1c6ab4e27e0afa0c8e83948104beb` |
