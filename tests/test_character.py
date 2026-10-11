from contextlib import contextmanager
import struct
import pytest


class Memory:
    def __init__(self):
        from unepic_trainer.profiles import UNEPIC
        self.profile = UNEPIC
        self.data = {}
        self.writes = []
        self.reads = []
        self.data.update({self.profile.hero+i:0 for i in range(0x160,0x18c)})
        self.put(self.profile.entity_slot,'Q',0x100000)
        self.put(0x1004e8,'i',100)
        self.put(0x1004ec,'f',75.5)
        self.put(self.profile.primary_key,'I',0xabcdef01)
        self.put(self.profile.mirror_key,'I',0x12345678)
        self.put(self.profile.detection_flag,'I',0)
        self.put(self.profile.penalty_flag,'I',0)
        for primary,mirror,value in ((0x160,0x17c,250),(0x164,0x180,1000),
                                     (0x168,0x184,3),(0x16c,0x188,5)):
            self.put(self.profile.hero+primary,'I',value^0xabcdef01)
            self.put(self.profile.hero+mirror,'I',value^0x12345678)

    def put(self,address,format,value):
        for i,b in enumerate(struct.pack('<'+format,value)):
            self.data[address+i]=b

    def read(self,address,size):
        from unepic_trainer.backend import BackendError
        self.reads.append((address,size))
        try: return bytes(self.data[address+i] for i in range(size))
        except KeyError: raise BackendError('Unmapped test address')

    def write(self,address,data):
        self.writes.append((address,data))
        for i,b in enumerate(data): self.data[address+i]=b

    @contextmanager
    def stopped(self):
        yield self


def test_snapshot_uses_few_memory_round_trips():
    from unepic_trainer.character import read_character
    memory = Memory()
    assert read_character(memory).current_hp == 75.5
    assert len(memory.reads) <= 6


def test_snapshot_and_heal_only_hp():
    from unepic_trainer.character import read_character, heal
    memory = Memory()
    snapshot = read_character(memory)
    assert (snapshot.current_hp,snapshot.max_hp,snapshot.level,snapshot.xp,
            snapshot.free_points) == (75.5,100,3,250,5)
    assert heal(memory).current_hp == 100.0
    assert memory.writes == [(0x1004ec,bytes.fromhex('0000c842'))]


@pytest.mark.parametrize('hp',[float('nan'),float('inf'),-1,101])
def test_invalid_hp_cannot_be_healed(hp):
    from unepic_trainer.character import heal
    from unepic_trainer.backend import BackendError
    memory = Memory()
    memory.put(0x1004ec,'f',hp)
    with pytest.raises(BackendError): heal(memory)
    assert memory.writes == []


def test_null_pointer_and_inconsistent_protected_values():
    from unepic_trainer.character import read_character, heal
    from unepic_trainer.backend import BackendError
    memory = Memory()
    memory.put(memory.profile.entity_slot,'Q',0)
    assert read_character(memory) is None
    with pytest.raises(BackendError): heal(memory)
    memory = Memory()
    memory.put(memory.profile.hero+0x184,'I',99)
    with pytest.raises(BackendError,match='protected'): read_character(memory)
    assert memory.writes == []


def test_penalty_flag_blocks_changes():
    from unepic_trainer.character import heal
    from unepic_trainer.backend import BackendError
    memory = Memory()
    memory.put(memory.profile.penalty_flag,'I',1)
    with pytest.raises(BackendError,match='integrity'): heal(memory)
    assert memory.writes == []
