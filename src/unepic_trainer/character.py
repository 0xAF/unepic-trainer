from dataclasses import dataclass
import math
import struct

from .backend import BackendError


@dataclass(frozen=True)
class CharacterSnapshot:
    entity: int
    current_hp: float
    max_hp: int
    level: int
    xp: int
    free_points: int
    xp_threshold: int
    kill_points: int = 0  # Internal steps; five steps equal one displayed KP.
    kill_points_unlocked: bool = False


def _unpack(backend, address: int, kind: str):
    return struct.unpack('<' + kind, backend.read(address,struct.calcsize(kind)))[0]


def ensure_integrity(backend):
    profile = backend.profile
    if profile.penalty_flag == profile.detection_flag + 4:
        flags = struct.unpack('<II',backend.read(profile.detection_flag,8))
    else:
        flags = (_unpack(backend,profile.detection_flag,'I'),
                 _unpack(backend,profile.penalty_flag,'I'))
    if any(flags):
        raise BackendError('Game integrity flag is set; changes are disabled. Reload a clean save.')


def _read_character(backend) -> CharacterSnapshot | None:
    profile = backend.profile
    ensure_integrity(backend)
    entity = _unpack(backend,profile.entity_slot,'Q')
    if entity == 0:
        return None
    if entity < 0x10000 or entity > 0x7fffffffffff or entity % 4:
        raise BackendError('Invalid character pointer')
    if profile.current_hp_offset == profile.max_hp_offset + 4:
        maximum,current = struct.unpack('<if',backend.read(entity+profile.max_hp_offset,8))
    else:
        maximum = _unpack(backend,entity+profile.max_hp_offset,'i')
        current = _unpack(backend,entity+profile.current_hp_offset,'f')
    if not (0 < maximum <= 10000000 and math.isfinite(current) and 0 <= current <= maximum):
        raise BackendError('Invalid HP values; runtime addresses require verification')
    if profile.primary_key == profile.mirror_key + 4:
        key_b,key_a = struct.unpack('<II',backend.read(profile.mirror_key,8))
    else:
        key_a = _unpack(backend,profile.primary_key,'I')
        key_b = _unpack(backend,profile.mirror_key,'I')
    block = backend.read(profile.hero+0x160,0x2c)
    values = []
    for primary,mirror in ((0x160,0x17c),(0x164,0x180),(0x168,0x184),(0x16c,0x188)):
        a = struct.unpack_from('<I',block,primary-0x160)[0] ^ key_a
        b = struct.unpack_from('<I',block,mirror-0x160)[0] ^ key_b
        if a != b:
            raise BackendError('Inconsistent protected character values; changes are disabled')
        values.append(a)
    xp, threshold, level, points = values
    if not (1 <= level <= 1000 and 0 < threshold <= 0x7fffffff):
        raise BackendError('Invalid protected character values')
    kp,unlocked = struct.unpack_from('<ii',block,0x174-0x160)
    if not (0 <= kp <= 25 and unlocked in (0,1)):
        raise BackendError('Invalid Kill Points values')
    return CharacterSnapshot(entity,current,maximum,level,xp,points,threshold,kp,bool(unlocked))


def read_character(backend) -> CharacterSnapshot | None:
    with backend.stopped():
        return _read_character(backend)


def heal(backend) -> CharacterSnapshot:
    with backend.stopped():
        snapshot = _read_character(backend)
        if snapshot is None:
            raise BackendError('No character loaded')
        if snapshot.current_hp == 0:
            raise BackendError('Character is dead; healing does not reverse death')
        backend.write(snapshot.entity+backend.profile.current_hp_offset,
                      struct.pack('<f',snapshot.max_hp))
        return _read_character(backend)
