"""Reversible, independently selected player and owned-minion protection."""
import struct

from .backend import BackendError
from .character import read_character
from .minions import read_minions, refill_energy


def relative_jump(source: int, destination: int) -> bytes:
    displacement = destination - source - 5
    if not -(1 << 31) <= displacement < (1 << 31):
        raise BackendError('Code cave is outside rel32 jump range')
    return b'\xe9' + struct.pack('<i',displacement)


def build_hook(cave: int, return_to: int, entity_slot: int, original: bytes) -> bytes:
    if original not in (bytes.fromhex('f30f1193ec040000'),
                        bytes.fromhex('f30f119bec040000')):
        raise BackendError('Unsupported displaced instruction')
    # LEA preserves flags. Save below the 128-byte SysV red zone.
    prefix = bytes.fromhex('48 8d 64 24 80 9c 50 48 b8')
    prefix += struct.pack('<Q',entity_slot)
    prefix += bytes.fromhex('48 8b 00 48 39 c3')
    restore = bytes.fromhex('58 9d 48 8d a4 24 80 00 00 00')
    # JNE: non-player goes to the original MOVSS; player skips the store.
    code = prefix + b'\x75' + bytes([len(restore)+5]) + restore
    code += relative_jump(cave+len(code),return_to)
    code += restore + original
    code += relative_jump(cave+len(code),return_to)
    return code


def build_protection_hook(cave, return_to, entity_slot, original, config, energy=False):
    hp_stores = (bytes.fromhex('f30f1193ec040000'), bytes.fromhex('f30f119bec040000'))
    energy_stores = (bytes.fromhex('f30f118308060000'),
                     bytes.fromhex('f30f118708060000'), bytes.fromhex('f30f118f08060000'))
    if original not in (energy_stores if energy else hp_stores):
        raise BackendError('Unsupported displaced instruction')
    rdi = original in energy_stores[1:]
    memory = b'\x87' if rdi else b'\x83'
    compare = b'\xbf' if rdi else b'\xbb'
    code = bytearray(bytes.fromhex('48 8d 64 24 80 9c 50 51 48 b8'))
    code += struct.pack('<Q',entity_slot) + bytes.fromhex('48 8b 00 48 b9')
    code += struct.pack('<Q',config)
    labels, branches = {}, []

    def branch(opcode, label):
        code.extend(bytes.fromhex(opcode)); branches.append((len(code),label)); code.extend(b'\0'*4)

    code += bytes.fromhex('48 85 c0'); branch('0f 84','original')
    code += bytes.fromhex('48 39 c7' if rdi else '48 39 c3')
    branch('0f 85','pet')
    if energy:
        branch('e9','original')
    else:
        code += bytes.fromhex('f6 01 01'); branch('0f 85','protected'); branch('e9','original')
    labels['pet'] = len(code)
    code += b'\xf6\x01' + bytes([4 if energy else 2]); branch('0f 84','original')
    code += b'\x81'+compare+struct.pack('<ii',0x170,4); branch('0f 85','original')
    code += bytes.fromhex('8b 80 8c 05 00 00 85 c0'); branch('0f 84','original')
    code += b'\x39'+memory+struct.pack('<i',0x64c); branch('0f 85','original')
    for state in (0x73,0x76):
        code += b'\x81'+compare+struct.pack('<ii',0x5c8,state); branch('0f 84','original')
    # Positive finite HP excludes already-dead pets without using SSE flags.
    code += b'\x8b'+memory+struct.pack('<i',0x4ec)+b'\x85\xc0'; branch('0f 8e','original')
    code += b'\x3d'+struct.pack('<I',0x7f800000); branch('0f 83','original')
    labels['protected'] = len(code)
    if energy:
        code += b'\x8b'+memory+struct.pack('<i',0x178)+b'\x85\xc0'; branch('0f 8e','original')
        code += b'\x3d'+struct.pack('<I',10000000); branch('0f 87','original')
        # Preserve all 128 bits of XMM0 while converting the integer cap.
        code += bytes.fromhex('48 8d 64 24 f0 f3 0f 7f 04 24 f3 0f 2a')+memory+struct.pack('<i',0x178)
        code += bytes.fromhex('f3 0f 11')+memory+struct.pack('<i',0x608)
        code += bytes.fromhex('f3 0f 6f 04 24 48 8d 64 24 10')
    restore = bytes.fromhex('59 58 9d 48 8d a4 24 80 00 00 00')
    code += restore+relative_jump(cave+len(code)+len(restore),return_to)
    labels['original'] = len(code)
    code += restore+original
    code += relative_jump(cave+len(code),return_to)
    for offset,label in branches:
        struct.pack_into('<i',code,offset,labels[label]-offset-4)
    return bytes(code)


class GodMode:
    default_feature = 'player'
    bits = {'player':1,'minion':2}

    def __init__(self):
        self._mask = 0
        self.cave: int | None = None
        self.patch: bytes | None = None
        self._patches: dict[int, bytes] = {}
        self._owner = None

    @property
    def active(self):
        return bool(self._mask & self.bits[self.default_feature]) or bool(
            self._patches and self._owner and self._owner.unsafe)

    @property
    def minion_active(self):
        return bool(self._mask & 2)

    @property
    def config(self):
        return self.cave+2048

    def _check_owner(self, backend):
        if self._owner is not None and self._owner is not backend:
            raise BackendError('Hook belongs to a different backend session')

    @staticmethod
    def _sites(backend):
        profile = backend.profile
        return ((profile.damage_store, profile.original),
                (profile.dot_damage_store, profile.dot_original))

    @classmethod
    def _check_instruction_pointers(cls, backend):
        ips = backend.instruction_pointers()
        if any(site < ip < site+len(original)
               for site, original in cls._sites(backend) for ip in ips):
            raise BackendError('Thread is inside patch range; retry after it advances')

    def _restore(self, backend):
        errors = []
        for site, original in self._sites(backend):
            if site not in self._patches:
                continue
            try:
                backend.write(site, original)
            except Exception as error:
                errors.append(str(error))
            else:
                backend.active_patches.pop(site, None)
                del self._patches[site]
        if errors:
            backend.unsafe = True
            raise BackendError('Original instructions could not be restored; '
                               'target remains stopped: ' + '; '.join(errors))
        backend.unsafe = False
        self._mask = 0

    def _validate(self, backend, feature):
        character = read_character(backend)
        if character is None or character.current_hp <= 0:
            raise BackendError('No living character loaded')
        if feature != 'player' and not read_minions(backend):
            raise BackendError('No living owned minion loaded')

    def _update_mask(self, backend, mask):
        try:
            backend.write(self.config,bytes([mask]))
        except Exception:
            backend.unsafe = True
            raise
        self._mask = mask

    def _build_code(self, backend, cave, site, original):
        return build_protection_hook(cave, site+len(original),
            backend.profile.entity_slot, original, self.config,
            self.default_feature == 'energy')

    def enable(self, backend, feature=None):
        feature = feature or self.default_feature
        bit = self.bits[feature]
        self._check_owner(backend)
        if backend.unsafe:
            raise BackendError('Hook recovery required before enabling')
        if self._mask & bit:
            return
        with backend.stopped():
            self._validate(backend,feature)
            if self._patches:
                self._verify_patches(backend)
                self._update_mask(backend,self._mask|bit)
                return
            sites = self._sites(backend)
            for site, original in sites:
                if backend.read(site, len(original)) != original:
                    raise BackendError('Hook bytes mismatch; unsupported code or existing patch')
            self._check_instruction_pointers(backend)
            self._owner = backend
            if self.cave is None:
                self.cave = backend.allocate_near(sites[0][0], 4096)
            patches = {}
            for index, (site, original) in enumerate(sites):
                cave = self.cave + index*512
                code = self._build_code(backend,cave,site,original)
                patches[site] = relative_jump(site, cave) + b'\x90'*3
                backend.write(cave, code)
            backend.write(self.config,bytes([bit]))
            self.patch = patches[sites[0][0]]
            self._check_instruction_pointers(backend)
            try:
                for site, original in sites:
                    # Track before writing: even a failed write can change bytes.
                    self._patches[site] = patches[site]
                    backend.active_patches[site] = original
                    backend.write(site, patches[site])
            except Exception:
                self._restore(backend)
                raise
            self._mask = bit

    def _verify_patches(self, backend):
        for site, original in self._sites(backend):
            if site not in self._patches:
                continue
            if backend.read(site,len(original)) not in (self._patches[site],original):
                backend.unsafe = True
                raise BackendError('Unexpected hook bytes; recovery required before detaching')

    def disable(self, backend, feature=None):
        feature = feature or self.default_feature
        bit = self.bits[feature]
        self._check_owner(backend)
        if not self._patches:
            return
        with backend.stopped():
            self._check_instruction_pointers(backend)
            self._verify_patches(backend)
            remaining = self._mask & ~bit
            if remaining and not backend.unsafe:
                self._update_mask(backend,remaining)
                return
            self._restore(backend)
            # Leave the page mapped until process exit: a stopped thread might
            # still be inside a trampoline. Reuse it on subsequent enables.

    def disable_all(self, backend):
        self._check_owner(backend)
        if self._patches:
            with backend.stopped():
                self._check_instruction_pointers(backend)
                self._verify_patches(backend)
                self._restore(backend)


class EnergyLock(GodMode):
    default_feature = 'energy'
    bits = {'energy':4}

    @staticmethod
    def _sites(backend):
        p = backend.profile
        return ((p.energy_store,bytes.fromhex('f30f118308060000')),
                (p.energy_regen_store,bytes.fromhex('f30f118708060000')),
                (p.energy_cap_store,bytes.fromhex('f30f118f08060000')))

    def _validate(self, backend, feature):
        pets = read_minions(backend)
        if not any(p.max_energy for p in pets):
            raise BackendError('No living owned minion with energy loaded')

    def enable(self, backend, feature=None):
        with backend.stopped():
            super().enable(backend,feature)
            refill_energy(backend)
