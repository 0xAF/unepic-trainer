"""Disposable native CPU execution; never attaches to the game."""
import ctypes
from dataclasses import replace
import mmap
from pathlib import Path
import struct
import sys

from unepic_trainer.profiles import Profile
from unepic_trainer.progression import build_progression_hook
from unepic_trainer.hooks import relative_jump

lib = ctypes.CDLL(sys.argv[1])
libc = ctypes.CDLL(None)
libc.mprotect.argtypes = [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]
libc.mprotect.restype = ctypes.c_int
def address(name): return ctypes.addressof((ctypes.c_char*1).in_dll(lib,name))
hero,entity,room = address('hero'),address('player'),address('room')
entry = ctypes.cast(lib.character_update,ctypes.c_void_p).value
p = replace(Profile(),hero=hero,entity_slot=address('entity_slot'),
    primary_key=address('key_a'),mirror_key=address('key_b'),
    detection_flag=address('detection'),penalty_flag=address('penalty'),
    campaign_mode=address('campaign_mode'),simulation_flag=address('simulation_flag'),
    custom_map=address('custom_map'),player_count=address('player_count'),active_hero=address('active_hero'),
    progression_store=entry,item_table=address('item_table'),item_add_store=ctypes.cast(lib.item_add,ctypes.c_void_p).value,
    credit_scores=address('credit_scores'),credit_types=address('credit_types'),
    **{name+'_store':ctypes.cast(getattr(lib,name),ctypes.c_void_p).value
                               for name in ('points_add','xp_cap','xp_set','xp_award')})
memory = mmap.mmap(-1,4096,prot=mmap.PROT_READ|mmap.PROT_WRITE|mmap.PROT_EXEC)
cave = ctypes.addressof(ctypes.c_char.from_buffer(memory)); config=cave+2048
# Place a tiny executable fixture wrapper near the cave if rel32 to the DSO
# is unavailable. On standard Linux mmap and the DSO are neighbors.
code = build_progression_hook(cave,entry+8,p,config)
ctypes.memmove(cave,code,len(code))
original = ctypes.string_at(entry,8); assert original == p.progression_original
page = entry & ~4095
assert libc.mprotect(page,4096,7) == 0
patch = relative_jump(entry,cave)+b'\x90'*3
ctypes.memmove(entry,patch,8)
ctypes.c_uint32.from_address(config).value = 8
lib.character_update.argtypes = [ctypes.c_void_p]
def decoded(offset): return ctypes.c_uint32.from_address(hero+offset).value^ctypes.c_uint32.from_address(p.primary_key).value
def mirrors():
    keyb=ctypes.c_uint32.from_address(p.mirror_key).value
    for a,b in ((0x160,0x17c),(0x164,0x180),(0x168,0x184),(0x16c,0x188)):
        assert decoded(a) == ctypes.c_uint32.from_address(hero+b).value^keyb
def submit(action,amount=0):
    descriptor=p.item_table+(0x1c8 if action==4 else 0) if action in (3,4) else 0
    request=struct.pack('<IIIQI4xQQ',action,amount,1,entity,decoded(0x168),room,descriptor)
    ctypes.memmove(config+4,request,len(request))
def run(): lib.character_update(hero)
try:
    for amount in (1,10,100):
        before=decoded(0x16c); submit(1,amount); run(); run()
        assert decoded(0x16c) == before+amount
        assert ctypes.c_uint32.from_address(config+12).value == 2
        mirrors()
    before=decoded(0x168); points=decoded(0x16c)
    submit(2); run(); run()
    assert decoded(0x168) == before+1 and decoded(0x160) == 0
    assert decoded(0x164) == 2000 and decoded(0x16c) == points+5
    assert ctypes.c_uint32.from_address(address('progression_calls')).value == 4
    mirrors()
    for empty in (False,True):
        if empty: ctypes.c_uint32.from_address(hero+0x140c).value=0
        balance=250 if not empty else 0
        for amount in (100,1000,10000):
            submit(3,amount); run(); run(); balance+=amount
            assert decoded(0x1420) == balance
            assert ctypes.c_uint32.from_address(hero+0x144c).value^ctypes.c_uint32.from_address(p.mirror_key).value == balance
            assert ctypes.c_uint32.from_address(config+12).value == 2
            mirrors()
    assert ctypes.c_uint32.from_address(address('gold_calls')).value == 6
    # Change inventory after queueing: the native dispatcher must reject it.
    submit(3,100); ctypes.c_uint32.from_address(hero+0x140c).value=512; run()
    assert ctypes.c_uint32.from_address(config+12).value == 3
    ctypes.c_uint32.from_address(hero+0x140c).value=1
    ctypes.c_int32.from_address(address('credits_fixture_enabled')).value=1
    ctypes.c_int32.from_address(hero+0x170).value=250
    gold_balance=decoded(0x1420); credit_balance=250
    scores_before=ctypes.string_at(p.credit_scores,64)
    for amount in (100,1000,10000):
        submit(4,amount); run(); run(); credit_balance+=amount
        assert decoded(0x1420+0xb8)==credit_balance
        assert decoded(0x1420)==gold_balance
        assert ctypes.c_int32.from_address(hero+0x170).value==500-credit_balance
        assert ctypes.c_uint32.from_address(config+12).value==2
        assert ctypes.string_at(p.credit_scores,64)==scores_before
        mirrors()
    # Native spending and raw four-byte save/load preserve the extra balance.
    ctypes.c_int32.from_address(hero+0x170).value+=75
    saved_counter=ctypes.string_at(hero+0x170,4)
    ctypes.c_int32.from_address(hero+0x170).value=0
    ctypes.memmove(hero+0x170,saved_counter,4); run()
    assert decoded(0x1420+0xb8)==credit_balance-75
    assert ctypes.c_uint32.from_address(hero+0x1418+0xb8+0x34).value^ctypes.c_uint32.from_address(p.mirror_key).value==credit_balance-75
    assert decoded(0x1420)==gold_balance
    for amount,expected in ((1,13),(10,25),(100,25)):
        ctypes.c_int32.from_address(hero+0x174).value=8
        ctypes.c_int32.from_address(hero+0x178).value=1
        ctypes.c_uint32.from_address(hero+0x234).value=0
        submit(5,amount); run(); run()
        assert ctypes.c_int32.from_address(hero+0x174).value==expected
        assert ctypes.c_uint32.from_address(hero+0x234).value==1
        assert ctypes.c_uint32.from_address(config+12).value==2
        assert decoded(0x1420)==gold_balance and decoded(0x1420+0xb8)==credit_balance-75
        assert ctypes.string_at(p.credit_scores,64)==scores_before
        mirrors()
    # A pending request cannot unlock KP or write above the native cap.
    for balance,unlocked in ((8,0),(25,1),(26,1),(-1,1)):
        ctypes.c_int32.from_address(hero+0x174).value=balance
        ctypes.c_int32.from_address(hero+0x178).value=unlocked
        ctypes.c_uint32.from_address(hero+0x234).value=0
        submit(5,1); run()
        assert ctypes.c_int32.from_address(hero+0x174).value==balance
        assert ctypes.c_uint32.from_address(hero+0x234).value==0
        assert ctypes.c_uint32.from_address(config+12).value==3
    ctypes.c_int32.from_address(hero+0x174).value=0
    ctypes.c_int32.from_address(hero+0x178).value=0
    submit(1,100); ctypes.c_uint32.from_address(p.campaign_mode).value=1; run()
    assert ctypes.c_uint32.from_address(config+12).value == 3
    assert decoded(0x16c) == points+5
    ctypes.c_uint32.from_address(p.campaign_mode).value=0
    submit(1,10); lib.character_update(hero+4)
    assert ctypes.c_uint32.from_address(config+12).value == 1
    ctypes.c_uint32.from_address(config).value=0; run()
    assert decoded(0x16c) == points+5
finally:
    ctypes.memmove(entry,original,8)
assert ctypes.string_at(entry,8) == original
run(); assert decoded(0x16c) == points+5
print('native progression: points, immediate level, one-shot, cancellation, restoration passed')
