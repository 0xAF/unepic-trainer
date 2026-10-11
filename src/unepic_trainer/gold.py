"""Validate campaign currency descriptors and their protected inventory."""
import struct

from .backend import BackendError
from .character import _unpack


def validate_gold(backend,amount,currency='gold'):
    p = backend.profile
    item_id,title = {'gold':(0x238d,'Gold'),'credits':(0x238e,'Unepic Credits')}[currency]
    if (_unpack(backend,p.custom_map,'I') or _unpack(backend,p.player_count,'I') != 1 or
            _unpack(backend,p.active_hero,'Q') != p.hero):
        raise BackendError(f'{title} controls require one active campaign hero')
    count = _unpack(backend,p.item_table+0xb9400,'I')
    slots = _unpack(backend,p.hero+0x140c,'I')
    if not 1 <= count <= 1664 or not 0 <= slots < 512:
        raise BackendError('Invalid item table or full inventory')
    table = backend.read(p.item_table,count*0x1c8)
    matches = [i for i in range(count) if struct.unpack_from('<I',table,i*0x1c8)[0] == item_id]
    if len(matches) != 1:
        raise BackendError(f'{title} descriptor unavailable')
    index = matches[0]; descriptor = p.item_table+index*0x1c8
    item = table[index*0x1c8:(index+1)*0x1c8]
    name = item[4:68]
    cap = struct.unpack_from('<i',item,0x70)[0]
    if (not name[0] or b'\0' not in name or cap < 0 or
            struct.unpack_from('<I',item,0xe8)[0] or item[0xad]&0x80 or
            struct.unpack_from('<I',item,0x58)[0] == 1):
        raise BackendError(f'Unsupported {title} descriptor')
    # Reserve enough new slots without relying on existing stack space.
    required = (amount+cap-1)//cap if cap and currency == 'gold' else 1
    if slots+required > 512:
        raise BackendError(f'Insufficient inventory capacity for {title}')
    key_a = _unpack(backend,p.primary_key,'I')
    key_b = _unpack(backend,p.mirror_key,'I')
    records = backend.read(p.hero+0x1418,slots*0xb8) if slots else b''
    total = 0
    for offset in range(0,len(records),0xb8):
        pointer = struct.unpack_from('<Q',records,offset)[0]
        if not p.item_table <= pointer < p.item_table+count*0x1c8 or (pointer-p.item_table)%0x1c8:
            raise BackendError('Invalid inventory descriptor pointer')
        values = []
        for primary,mirror in ((8,0x34),(0x10,0x38),(0x18,0x3c),(0x24,0x40)):
            a = struct.unpack_from('<I',records,offset+primary)[0]^key_a
            b = struct.unpack_from('<I',records,offset+mirror)[0]^key_b
            if a != b:
                raise BackendError('Inconsistent protected inventory values')
            values.append(a)
        if values[0] > 0x7fffffff:
            raise BackendError('Invalid inventory quantity')
        if pointer == descriptor:
            total += values[0]
    if total > 0x7fffffff-amount:
        raise BackendError(f'{title} balance would overflow')
    for function in ('item_add','item_merge','item_create','item_lookup'):
        original = getattr(p,function+'_original')
        if backend.read(getattr(p,function+'_store'),len(original)) != original:
            raise BackendError(f'{title} function bytes mismatch')
    return descriptor


def validate_credits(backend,amount):
    descriptor = validate_gold(backend,amount,'credits'); p = backend.profile
    scores = struct.unpack('<16i',backend.read(p.credit_scores,64))
    types = struct.unpack('<15i',backend.read(p.credit_types,60))
    earned = sum(score for score,kind in zip(scores,types) if kind == 2)
    spent = _unpack(backend,p.hero+0x170,'i')
    if (scores[-1] != -1 or any(score < 0 for score,kind in zip(scores,types) if kind == 2)
            or not 0 <= earned <= 0x7fffffff or not 0 <= earned-spent <= 0x7fffffff-amount
            or spent-amount < -0x80000000):
        raise BackendError('Invalid Unepic Credits source balance or overflow')
    return descriptor
