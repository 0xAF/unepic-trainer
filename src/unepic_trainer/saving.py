"""Queue the game's ordinary campaign save request for its main loop."""
import struct

from .backend import BackendError
from .character import _unpack, read_character


class SaveGame:
    def __init__(self):
        self.pending = False
        self.slot = None
        self._owner = None
        self._unsafe = False

    def _check_owner(self,backend):
        if self._owner is not None and self._owner is not backend:
            raise BackendError('Save request belongs to a different backend session')

    def submit(self,backend):
        self._check_owner(backend)
        if self.pending:
            raise BackendError('A save request is pending; resume the game')
        with backend.stopped():
            if backend.unsafe:
                raise BackendError('Recovery required before requesting a save')
            p = backend.profile
            character = read_character(backend)
            if character is None or character.current_hp <= 0:
                raise BackendError('No living character loaded')
            if any(_unpack(backend,address,'I') for address in
                   (p.campaign_mode,p.simulation_flag,p.custom_map)):
                raise BackendError('Save game requires a single-player campaign')
            if _unpack(backend,p.save_blocked,'I'):
                raise BackendError('The game currently blocks saving')
            if (_unpack(backend,p.player_count,'i') != 1 or
                    _unpack(backend,p.active_hero,'Q') != p.hero):
                raise BackendError('No single active campaign hero loaded')
            slot = _unpack(backend,p.save_slot,'i')
            # Native selection accepts unsigned indices <= 8; enumeration
            # visits nine saves. Slot 8 is the ninth valid campaign slot.
            if not 0 <= slot <= 8:
                raise BackendError(f'Invalid current save slot: {slot} (expected 0..8)')
            if any(struct.unpack('<4I',backend.read(p.save_actions,16))):
                raise BackendError('The game has a pending save, load or exit request')
            room = _unpack(backend,p.hero+0x197c0,'Q')
            if room < 0x10000 or room > 0x7fffffffffff or room % 4:
                raise BackendError('No valid campaign room loaded')
            backend.read(room+0x24af4,12)
            for name in ('save_dispatch','save_writer'):
                original = getattr(p,name+'_original')
                if backend.read(getattr(p,name+'_store'),len(original)) != original:
                    raise BackendError('Save function bytes mismatch')
            self._owner = backend
            self.slot = slot
            self.pending = True  # A failed write may already change the flag.
            try:
                backend.write(p.save_actions+12,struct.pack('<I',2))
            except Exception:
                self._unsafe = backend.unsafe = True
                self.cancel(backend)
                raise

    def poll(self,reader):
        if not self.pending:
            return None
        if _unpack(reader,reader.profile.save_actions+12,'I'):
            return None
        self.pending = False
        # Consumption is not proof of successful storage. The game reports
        # its native writer result through its normal notification/dialog.
        return self.slot

    def cancel(self,backend):
        self._check_owner(backend)
        if not self.pending:
            return
        with backend.stopped():
            address = backend.profile.save_actions+12
            value = _unpack(backend,address,'I')
            if value == 2 or (self._unsafe and value == 0):
                backend.write(address,b'\0'*4)
            elif self._unsafe:
                raise BackendError('Save request recovery required; game remains paused')
            # Preserve a subsequent game-owned automatic request (value 1).
            if self._unsafe:
                backend.unsafe = self._unsafe = False
            self.pending = False
