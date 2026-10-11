"""Execute a trampoline in this disposable process, without ptrace."""
import ctypes as c
from pathlib import Path
import sys

from unepic_trainer.backend import find_near_gap
from unepic_trainer.hooks import build_hook, build_protection_hook, relative_jump

library = c.CDLL(sys.argv[1])
libc = c.CDLL(None,use_errno=True)
libc.mmap.argtypes = [c.c_void_p,c.c_size_t,c.c_int,c.c_int,c.c_int,c.c_long]
libc.mmap.restype = c.c_void_p
libc.mprotect.argtypes = [c.c_void_p,c.c_size_t,c.c_int]
libc.munmap.argtypes = [c.c_void_p,c.c_size_t]


class Entity(c.Structure):
    _fields_ = [('pad',c.c_char*0x4e8),('max_hp',c.c_int),('hp',c.c_float)]


player = Entity.in_dll(library,'player')
enemy = Entity.in_dll(library,'enemy')
slot = c.c_void_p.in_dll(library,'entity_slot')
site = c.addressof(c.c_char.in_dll(library,'damage_store'))
dot_site = c.addressof(c.c_char.in_dll(library,'dot_damage_store'))
original = c.string_at(site,8)
dot_original = c.string_at(dot_site,8)
assert dot_original == bytes.fromhex('f30f119bec040000')
assert original == bytes.fromhex('f30f1193ec040000')
maps = []
for line in Path('/proc/self/maps').read_text().splitlines():
    start,end = line.split()[0].split('-')
    maps.append((int(start,16),int(end,16)))
candidate = find_near_gap(site,maps,4096)
cave = libc.mmap(candidate,4096,7,0x100022,-1,0)
assert cave == candidate,(cave,c.get_errno())
for address, destination, displaced in ((site,cave,original),
                                        (dot_site,cave+256,dot_original)):
    assert libc.mprotect(address&~4095,4096,7) == 0
    code = build_hook(destination,address+8,c.addressof(slot),displaced)
    c.memmove(destination,code,len(code))
    patch = relative_jump(address,destination)+b'\x90'*3
    c.memmove(address,patch,8)
for name in ('damage','burn'):
    function = getattr(library,name)
    function.argtypes = [c.c_void_p,c.c_float]
    function.restype = None
    function(c.addressof(player),25)
    function(c.addressof(enemy),25)
    assert (player.hp,enemy.hp) == ((100,75) if name == 'damage' else (100,50))
slot.value = c.addressof(enemy)
for name in ('damage','burn'):
    function = getattr(library,name)
    function(c.addressof(player),10)
    function(c.addressof(enemy),10)
    assert (player.hp,enemy.hp) == ((90,50) if name == 'damage' else (80,50))
for address, displaced in ((site,original),(dot_site,dot_original)):
    c.memmove(address,displaced,8)
    assert c.string_at(address,8) == displaced
library.damage(c.addressof(player),10)
library.burn(c.addressof(player),10)
assert player.hp == 60
# Exercise the exact product trampolines on a native CPU for every toggle mask.
pet = Entity.in_dll(library,'minion')
foreign = Entity.in_dll(library,'foreign_minion')
slot.value = c.addressof(player)
c.c_uint32.from_address(c.addressof(player)+0x58c).value = 42
stores = [(site,original,False),(dot_site,dot_original,False)]
for symbol,expected in (('energy_store','f30f118308060000'),
                        ('energy_regen_store','f30f118708060000'),
                        ('energy_cap_store','f30f118f08060000')):
    address = c.addressof(c.c_char.in_dll(library,symbol))
    displaced = c.string_at(address,8)
    assert displaced == bytes.fromhex(expected)
    stores.append((address,displaced,True))
config = cave+3072
for i,(address,displaced,energy) in enumerate(stores):
    destination = cave+i*512
    assert libc.mprotect(address&~4095,4096,7) == 0
    code = build_protection_hook(destination,address+8,c.addressof(slot),displaced,config,energy)
    c.memmove(destination,code,len(code))
    c.memmove(address,relative_jump(address,destination)+b'\x90'*3,8)
for mask in range(8):
    c.c_ubyte.from_address(config).value = mask
    for actor,is_pet,is_player in ((player,False,True),(pet,True,False),(foreign,False,False)):
        pointer = c.addressof(actor)
        for name in ('damage','burn'):
            actor.hp = 80
            getattr(library,name)(pointer,25)
            assert actor.hp == (80 if ((is_player and mask&1) or (is_pet and mask&2)) else 55)
        for name in ('drain','regen','energy_cap'):
            function = getattr(library,name)
            function.argtypes = [c.c_void_p,c.c_float]; function.restype = None
            actor.hp = 80
            c.c_float.from_address(pointer+0x608).value = 100
            function(pointer,25)
            assert c.c_float.from_address(pointer+0x608).value == (100 if is_pet and mask&4 else (75 if name == 'drain' else 25))
for address,displaced,_ in stores:
    c.memmove(address,displaced,8)
    assert c.string_at(address,8) == displaced
library.drain(c.addressof(pet),10)
assert c.c_float.from_address(c.addressof(pet)+0x608).value == 90
libc.munmap(cave,4096)
print('native trampolines: player/minion HP, maximum energy, independent masks, restore PASS')
