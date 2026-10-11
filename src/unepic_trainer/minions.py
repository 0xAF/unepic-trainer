"""Current-room pets owned by the selected character."""
from dataclasses import dataclass
import math
import struct

from .backend import BackendError
from .character import read_character, _unpack


@dataclass(frozen=True)
class MinionSnapshot:
    entity: int
    current_hp: float
    max_hp: int
    energy: float
    max_energy: int


def _pointer(value):
    if not (0x10000 <= value <= 0x7fffffffffff and value % 4 == 0):
        raise BackendError('Invalid minion or room pointer')
    return value


def read_minions(backend) -> tuple[MinionSnapshot, ...]:
    with backend.stopped():
        player = read_character(backend)
        if player is None or player.current_hp <= 0:
            return ()
        profile = backend.profile
        owner = _unpack(backend,player.entity+0x58c,'I')
        room = _unpack(backend,profile.hero+0x197c0,'Q')
        if not owner or not room:
            return ()
        _pointer(room)
        count = _unpack(backend,room+0xbef0,'i')
        if not 0 <= count <= 4096:
            raise BackendError('Invalid room entity count')
        pointers = struct.unpack('<'+'Q'*count,backend.read(room+0xbef8,count*8)) if count else ()
        pets = []
        for entity in dict.fromkeys(pointers):
            if not entity or entity == player.entity:
                continue
            _pointer(entity)
            block = backend.read(entity+0x170,0x4e0)
            unpack = lambda kind,offset: struct.unpack_from('<'+kind,block,offset-0x170)[0]
            if unpack('i',0x170) != 4 or unpack('I',0x64c) != owner:
                continue
            if unpack('i',0x5c8) in (0x73,0x76):
                continue
            maximum, hp = unpack('i',0x4e8), unpack('f',0x4ec)
            if not (0 < maximum <= 10000000 and math.isfinite(hp) and 0 <= hp <= maximum):
                raise BackendError('Invalid minion HP values')
            if hp == 0:
                continue
            cap, energy = unpack('i',0x178), unpack('f',0x608)
            if not (0 <= cap <= 10000000 and (cap == 0 or
                    (math.isfinite(energy) and 0 <= energy <= cap))):
                raise BackendError('Invalid minion energy values')
            pets.append(MinionSnapshot(entity,hp,maximum,energy if cap else 0,cap))
        return tuple(pets)


def heal_minions(backend):
    with backend.stopped():
        pets = read_minions(backend)
        if not pets:
            raise BackendError('No living owned minion loaded')
        for pet in pets:
            backend.write(pet.entity+backend.profile.current_hp_offset,struct.pack('<f',pet.max_hp))
        return read_minions(backend)


def refill_energy(backend):
    with backend.stopped():
        pets = tuple(p for p in read_minions(backend) if p.max_energy)
        if not pets:
            raise BackendError('No living owned minion with energy loaded')
        for pet in pets:
            if pet.energy != pet.max_energy:
                backend.write(pet.entity+0x608,struct.pack('<f',pet.max_energy))
        return read_minions(backend)
