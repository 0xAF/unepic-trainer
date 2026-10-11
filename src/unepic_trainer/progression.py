"""Campaign progression requests executed once by the game's update thread."""
import struct

from .backend import BackendError
from .character import read_character, _unpack
from .hooks import GodMode, relative_jump
from .gold import validate_gold, validate_credits


def build_progression_hook(cave, return_to, profile, config):
    p = profile
    if p.progression_original != bytes.fromhex('4156415541545553'):
        raise BackendError('Unsupported character update prologue')
    code = bytearray()
    labels, branches = {}, []

    def emit(hexadecimal):
        code.extend(bytes.fromhex(hexadecimal))

    def branch(opcode,label):
        emit(opcode); branches.append((len(code),label)); code.extend(b'\0'*4)

    def imm64(opcode,value):
        emit(opcode); code.extend(struct.pack('<Q',value))

    def call(address):
        emit('4c 89 e7')  # RDI = saved character
        imm64('48 b8',address); emit('ff d0')

    # Preserve flags, all GPRs and the SysV red zone, including idle updates.
    emit('48 8d 64 24 80 9c 50 51 52 53 55 56 57')
    emit('41 50 41 51 41 52 41 53 41 54 41 55 41 56 41 57')
    imm64('48 b8',p.hero); emit('48 39 c7'); branch('0f 85','restore')
    emit('49 89 fc'); imm64('49 bd',config)
    emit('41 f6 45 00 08'); branch('0f 84','restore')
    # Claim atomically: reentrant/concurrent updates cannot repeat a request.
    emit('b8 01 00 00 00 ba 04 00 00 00 f0 41 0f b1 55 0c')
    branch('0f 85','restore')
    for address in (p.campaign_mode,p.simulation_flag,p.detection_flag,p.penalty_flag):
        imm64('48 b8',address); emit('83 38 00'); branch('0f 85','cancel')
    imm64('48 b8',p.entity_slot); emit('4c 8b 30 4d 85 f6'); branch('0f 84','cancel')
    emit('4d 3b 75 10'); branch('0f 85','cancel')
    emit('41 8b 86'); code.extend(struct.pack('<i',p.current_hp_offset))
    emit('85 c0'); branch('0f 8e','cancel')
    emit('3d 00 00 80 7f'); branch('0f 83','cancel')
    emit('4d 8b bc 24 c0 97 01 00 4d 85 ff'); branch('0f 84','cancel')
    emit('4d 3b 7d 20'); branch('0f 85','cancel')
    imm64('48 b8',p.primary_key); emit('44 8b 10')
    imm64('48 b8',p.mirror_key); emit('44 8b 18')
    for primary,mirror in ((0x160,0x17c),(0x164,0x180),(0x168,0x184),(0x16c,0x188)):
        emit('41 8b 84 24'); code.extend(struct.pack('<i',primary)); emit('44 31 d0')
        emit('41 8b 8c 24'); code.extend(struct.pack('<i',mirror)); emit('44 31 d9 39 c8')
        branch('0f 85','cancel')
        emit('85 c0'); branch('0f 88','cancel')
    # Last decoded value is the free-point balance.
    emit('41 89 c0 41 8b 45 04 83 f8 01'); branch('0f 84','points')
    emit('83 f8 03'); branch('0f 84','gold')
    emit('83 f8 04'); branch('0f 84','gold')
    emit('83 f8 05'); branch('0f 84','kill-points')
    emit('83 f8 02'); branch('0f 85','cancel')
    emit('41 8b 84 24 68 01 00 00 44 31 d0 85 c0'); branch('0f 8e','cancel')
    emit('83 f8 18'); branch('0f 87','cancel')
    emit('41 3b 45 18'); branch('0f 85','cancel')
    emit('41 81 f8 f8 ff ff 7f'); branch('0f 87','cancel')
    emit('41 8b 84 24 64 01 00 00 44 31 d0 85 c0'); branch('0f 8e','cancel')
    emit('3d 00 ca 9a 3b'); branch('0f 87','cancel')  # threshold <= 1e9
    branch('e9','execute')
    labels['points'] = len(code)
    emit('41 8b 75 08 83 fe 01'); branch('0f 84','points-valid')
    emit('83 fe 0a'); branch('0f 84','points-valid')
    emit('83 fe 64'); branch('0f 85','cancel')
    labels['points-valid'] = len(code)
    emit('44 01 c6'); branch('0f 88','cancel')
    branch('e9','execute')
    labels['kill-points'] = len(code)
    imm64('48 b8',p.custom_map); emit('83 38 00'); branch('0f 85','cancel')
    imm64('48 b8',p.player_count); emit('83 38 01'); branch('0f 85','cancel')
    imm64('48 b8',p.active_hero); emit('4c 39 20'); branch('0f 85','cancel')
    emit('41 83 bc 24 78 01 00 00 01'); branch('0f 85','cancel')
    emit('41 8b 84 24 74 01 00 00 83 f8 18'); branch('0f 87','cancel')
    emit('41 8b 4d 08 83 f9 01'); branch('0f 84','kp-amount')
    emit('83 f9 0a'); branch('0f 84','kp-amount')
    emit('83 f9 64'); branch('0f 85','cancel')
    labels['kp-amount'] = len(code)
    # Match the normal counter's 25-step cap and five steps per displayed KP.
    emit('6b c9 05 01 c8 83 f8 19'); branch('0f 86','kp-store')
    emit('b8 19 00 00 00')
    labels['kp-store'] = len(code)
    emit('41 89 84 24 74 01 00 00 41 c7 84 24 34 02 00 00 01 00 00 00')
    emit('41 c7 45 0c 02 00 00 00'); branch('e9','restore')
    labels['gold'] = len(code)
    imm64('48 b8',p.custom_map); emit('83 38 00'); branch('0f 85','cancel')
    imm64('48 b8',p.player_count); emit('83 38 01'); branch('0f 85','cancel')
    imm64('48 b8',p.active_hero); emit('4c 39 20'); branch('0f 85','cancel')
    emit('41 8b 45 08 83 f8 64'); branch('0f 84','gold-amount')
    emit('3d e8 03 00 00'); branch('0f 84','gold-amount')
    emit('3d 10 27 00 00'); branch('0f 85','cancel')
    labels['gold-amount'] = len(code)
    imm64('49 bf',p.item_table)
    emit('41 8b 8f 00 94 0b 00 85 c9'); branch('0f 8e','cancel')
    emit('81 f9 80 06 00 00'); branch('0f 87','cancel')
    emit('89 c8 48 69 c0 c8 01 00 00 49 8d 2c 07 49 8b 5d 28')
    emit('4c 39 fb'); branch('0f 82','cancel')
    emit('48 39 eb'); branch('0f 83','cancel')
    emit('48 89 d8 4c 29 f8 31 d2 bf c8 01 00 00 48 f7 f7 48 85 d2')
    branch('0f 85','cancel')
    emit('41 83 7d 04 04'); branch('0f 84','credit-descriptor')
    emit('81 3b 8d 23 00 00'); branch('0f 85','cancel')
    branch('e9','currency-descriptor-valid')
    labels['credit-descriptor'] = len(code)
    emit('81 3b 8e 23 00 00'); branch('0f 85','cancel')
    labels['currency-descriptor-valid'] = len(code)
    emit('83 bb e8 00 00 00 00'); branch('0f 85','cancel')
    emit('f6 83 ad 00 00 00 80'); branch('0f 85','cancel')
    emit('83 7b 58 01'); branch('0f 84','cancel')
    emit('80 7b 04 00'); branch('0f 84','cancel')
    emit('48 8d 73 04 b9 40 00 00 00')
    labels['gold-name'] = len(code)
    emit('80 3e 00'); branch('0f 84','gold-capacity')
    emit('48 ff c6 ff c9'); branch('0f 85','gold-name')
    branch('e9','cancel')
    labels['gold-capacity'] = len(code)
    emit('8b 73 70 85 f6'); branch('0f 88','cancel')
    emit('41 83 7d 04 04'); branch('0f 84','credit-slot')
    emit('41 8b 45 08 85 f6'); branch('0f 85','gold-divide')
    emit('b8 01 00 00 00'); branch('e9','gold-slots')
    labels['credit-slot'] = len(code)
    emit('b8 01 00 00 00'); branch('e9','gold-slots')
    labels['gold-divide'] = len(code)
    emit('01 f0 ff c8 31 d2 f7 f6')
    labels['gold-slots'] = len(code)
    emit('41 8b 8c 24 0c 14 00 00 81 f9 ff 01 00 00'); branch('0f 87','cancel')
    emit('01 c8 3d 00 02 00 00'); branch('0f 87','cancel')
    emit('49 8d b4 24 18 14 00 00 45 31 c9 85 c9'); branch('0f 84','gold-total')
    labels['gold-record'] = len(code)
    emit('48 8b 16 4c 39 fa'); branch('0f 82','cancel')
    emit('48 39 ea'); branch('0f 83','cancel')
    emit('48 89 d0 4c 29 f8 31 d2 bf c8 01 00 00 48 f7 f7 48 85 d2')
    branch('0f 85','cancel')
    for primary,mirror in ((8,0x34),(0x10,0x38),(0x18,0x3c),(0x24,0x40)):
        emit('8b 46'); code.append(primary); emit('44 31 d0 8b 56'); code.append(mirror)
        emit('44 31 da 39 d0'); branch('0f 85','cancel')
        if primary == 8:
            emit('85 c0'); branch('0f 88','cancel')
            emit('48 39 1e'); branch('0f 85','gold-other')
            emit('41 01 c1'); branch('0f 80','cancel')
            labels['gold-other'] = len(code)
    emit('48 81 c6 b8 00 00 00 ff c9'); branch('0f 85','gold-record')
    labels['gold-total'] = len(code)
    emit('45 03 4d 08'); branch('0f 80','cancel')
    emit('41 83 7d 04 04'); branch('0f 85','execute')
    # Credits = type-2 challenge scores minus the saved per-hero spent
    # counter. Change that source once; normal update code rebuilds the
    # protected inventory quantity. Achievement scores/types stay untouched.
    imm64('48 be',p.credit_scores); imm64('48 bf',p.credit_types)
    emit('83 7e 3c ff'); branch('0f 85','cancel')
    emit('b9 0f 00 00 00 45 31 c9')
    labels['credit-score'] = len(code)
    emit('83 3f 02'); branch('0f 85','credit-next')
    emit('8b 06 85 c0'); branch('0f 88','cancel')
    emit('41 01 c1'); branch('0f 80','cancel')
    labels['credit-next'] = len(code)
    emit('48 83 c6 04 48 83 c7 04 ff c9'); branch('0f 85','credit-score')
    emit('41 8b 84 24 70 01 00 00 44 89 ca 29 c2'); branch('0f 80','cancel')
    emit('85 d2'); branch('0f 88','cancel')
    emit('41 03 55 08'); branch('0f 80','cancel')
    emit('41 2b 45 08'); branch('0f 80','cancel')
    emit('41 89 84 24 70 01 00 00 41 c7 45 0c 02 00 00 00')
    branch('e9','restore')
    labels['execute'] = len(code)
    # Native calls may clobber the entire FP/SSE context. FXSAVE64 includes
    # x87/MMX, MXCSR and all sixteen XMM registers. Keep the call stack aligned.
    emit('48 89 e5 48 81 ec 10 02 00 00 48 83 e4 f0 48 0f ae 04 24 fc')
    emit('41 83 7d 04 01'); branch('0f 84','call-points')
    emit('41 83 7d 04 03'); branch('0f 84','call-gold')
    call(p.xp_cap_store); emit('89 c6'); call(p.xp_set_store)
    emit('be 01 00 00 00'); call(p.xp_award_store)
    branch('e9','complete')
    labels['call-points'] = len(code)
    emit('41 8b 75 08'); call(p.points_add_store)
    branch('e9','complete')
    labels['call-gold'] = len(code)
    emit('49 8d bc 24 00 14 00 00 49 8b 75 28 48 83 c6 04 31 d2 31 c9 45 8b 45 08')
    imm64('48 b8',p.item_add_store); emit('ff d0 48 85 c0'); branch('0f 84','call-failed')
    labels['complete'] = len(code)
    emit('48 0f ae 0c 24 48 89 ec 41 c7 45 0c 02 00 00 00')
    branch('e9','restore')
    labels['call-failed'] = len(code)
    emit('48 0f ae 0c 24 48 89 ec')
    labels['cancel'] = len(code)
    emit('41 c7 45 0c 03 00 00 00')
    labels['restore'] = len(code)
    emit('41 5f 41 5e 41 5d 41 5c 41 5b 41 5a 41 59 41 58')
    emit('5f 5e 5d 5b 5a 59 58 9d 48 8d a4 24 80 00 00 00')
    code.extend(p.progression_original)
    code.extend(relative_jump(cave+len(code),return_to))
    for offset,label in branches:
        struct.pack_into('<i',code,offset,labels[label]-offset-4)
    if len(code) >= 2048:
        raise BackendError('Progression dispatcher exceeds code space')
    return bytes(code)


class Progression(GodMode):
    default_feature = 'progression'
    bits = {'progression':8}

    def __init__(self):
        super().__init__()
        self.pending = False
        self._request = None

    @staticmethod
    def _sites(backend):
        p = backend.profile
        return ((p.progression_store,p.progression_original),)

    def _validate(self,backend,feature):
        snapshot = read_character(backend); p = backend.profile
        if snapshot is None or snapshot.current_hp <= 0:
            raise BackendError('No living character loaded')
        if _unpack(backend,p.campaign_mode,'I') or _unpack(backend,p.simulation_flag,'I'):
            raise BackendError('Progression controls require a single-player campaign')
        if snapshot.xp > 0x7fffffff or snapshot.free_points > 0x7fffffff:
            raise BackendError('Invalid progression balance')
        room = _unpack(backend,p.hero+0x197c0,'Q')
        if room < 0x10000 or room > 0x7fffffffffff or room % 4:
            raise BackendError('No valid campaign room loaded')
        backend.read(room+0x24af4,12)
        for name in ('points_add','xp_cap','xp_set','xp_award'):
            original = getattr(p,name+'_original')
            if backend.read(getattr(p,name+'_store'),len(original)) != original:
                raise BackendError('Progression function bytes mismatch')
        return snapshot,room

    def _check_cave(self,backend):
        if self.cave is not None and any(self.cave <= ip < self.cave+4096
                                        for ip in backend.instruction_pointers()):
            raise BackendError('Thread is inside progression dispatcher; retry after it advances')

    def _build_code(self,backend,cave,site,original):
        self._check_cave(backend)
        backend.write(self.config+4,b'\0'*44)
        return build_progression_hook(cave,site+len(original),backend.profile,self.config)

    def submit(self,backend,action,amount=0):
        if action not in ('points','level-up','gold','credits','kill-points') or (action in ('points','gold','credits','kill-points') and
                (type(amount) is not int or amount not in ((1,10,100) if action in ('points','kill-points') else (100,1000,10000)))):
            raise BackendError('Unsupported progression request')
        self._check_owner(backend)
        if self.pending:
            raise BackendError('A progression request is pending; resume the game')
        with backend.stopped():
            snapshot,room = self._validate(backend,self.default_feature)
            if action == 'points' and snapshot.free_points > 0x7fffffff-amount:
                raise BackendError('Point balance would overflow')
            if action == 'kill-points':
                if not snapshot.kill_points_unlocked or snapshot.kill_points >= 25:
                    raise BackendError('Kill Points are locked or already at maximum (5 KP)')
                p = backend.profile
                if (_unpack(backend,p.custom_map,'I') or _unpack(backend,p.player_count,'I') != 1 or
                        _unpack(backend,p.active_hero,'Q') != p.hero):
                    raise BackendError('Kill Points require one active campaign hero')
            if action == 'level-up' and (not 1 <= snapshot.level < 25 or
                    snapshot.xp_threshold > 1000000000 or snapshot.free_points > 0x7fffffff-7):
                raise BackendError('Campaign level cap reached or progression balance invalid')
            descriptor = (validate_gold(backend,amount) if action == 'gold' else
                          validate_credits(backend,amount) if action == 'credits' else 0)
            self._check_cave(backend)
            self.enable(backend)
            self._verify_patches(backend)
            self._check_cave(backend)
            data = struct.pack('<IIIQI4xQQ',{'points':1,'level-up':2,'gold':3,'credits':4,'kill-points':5}[action],
                               amount,1,snapshot.entity,snapshot.level,room,descriptor)
            try:
                backend.write(self.config+4,data)
            except Exception:
                backend.unsafe = True
                # Clear any partially written request before permitting resume.
                backend.write(self.config+4,b'\0'*44)
                backend.unsafe = False
                raise
            self._request = (action,amount)
            self.pending = True

    def poll(self,reader):
        if not self.pending:
            return None
        status = _unpack(reader,self.config+12,'I')
        if status in (1,4):
            return None
        self.pending = False
        if status != 2:
            raise BackendError('Character request cancelled or native operation failed; check the game state')
        return self._request

    def disable_all(self,backend):
        # Stop/cancel idle requests before removing the entry. A thread that
        # already claimed a request may finish safely in the retained mapping.
        if self._patches:
            with backend.stopped():
                self._verify_patches(backend)
                self._update_mask(backend,0)
                super().disable_all(backend)
        self.pending = False
