from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    sha256: str = '62c04002b98eee3f33d0f8c27030b1f5ea23d3ede56d62af9da6b1436a583962'
    hero: int = 0x0142D620
    entity_slot: int = 0x01446DD8
    primary_key: int = 0x009F43B4
    mirror_key: int = 0x009F43B0
    detection_flag: int = 0x007C5D18
    penalty_flag: int = 0x007C5D1C
    damage_store: int = 0x004CAF49
    original: bytes = bytes.fromhex('f3 0f 11 93 ec 04 00 00')
    dot_damage_store: int = 0x004CB2AD
    dot_original: bytes = bytes.fromhex('f3 0f 11 9b ec 04 00 00')
    max_hp_offset: int = 0x4E8
    current_hp_offset: int = 0x4EC
    energy_store: int = 0x0048907B
    energy_regen_store: int = 0x00488E0C
    energy_cap_store: int = 0x00489170
    progression_store: int = 0x0046EF80
    progression_original: bytes = bytes.fromhex('4156415541545553')
    points_add_store: int = 0x0046AE00
    points_add_original: bytes = bytes.fromhex('8b15ae9558008b876c01000031d001f0')
    xp_cap_store: int = 0x0046ADA0
    xp_cap_original: bytes = bytes.fromhex('8b050e965800338764010000c3906690')
    xp_set_store: int = 0x0046AD80
    xp_set_original: bytes = bytes.fromhex('8b052e96580031f03335229658008987')
    xp_award_store: int = 0x0046C8D0
    xp_award_original: bytes = bytes.fromhex('448b0585bd19014585c00f8503010000')
    campaign_mode: int = 0x009F1EDC
    simulation_flag: int = 0x0160865C
    item_table: int = 0x020B4840
    credit_scores: int = 0x00772640
    credit_types: int = 0x007882A0
    item_add_store: int = 0x00417030
    item_add_original: bytes = bytes.fromhex('41554589c541544989fcbf40480b0255')
    item_merge_store: int = 0x00416BA0
    item_merge_original: bytes = bytes.fromhex('41564589c641554189cd41544189d455')
    item_create_store: int = 0x00514620
    item_create_original: bytes = bytes.fromhex('415441b8b80000004189d45589cd5348')
    item_lookup_store: int = 0x0041B120
    item_lookup_original: bytes = bytes.fromhex('41564989fe415541544989f45553448b')
    save_actions: int = 0x007E1930
    save_slot: int = 0x007C4BB8
    player_count: int = 0x014FB120
    active_hero: int = 0x014FB140
    custom_map: int = 0x020B42D8
    save_blocked: int = 0x007C5910
    save_dispatch_store: int = 0x00503EC0
    save_dispatch_original: bytes = bytes.fromhex('5331d231f64889fbbfa09d38024881ec')
    save_writer_store: int = 0x00504D20
    save_writer_original: bytes = bytes.fromhex('415741564155415455534881ecd80400')


UNEPIC = Profile()
