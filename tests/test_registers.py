"""Use real GDB on a synthetic ELF core; no ptrace or live target needed."""
import json
import os
import shutil
import struct

import pytest
from pygdbmi.gdbcontroller import GdbController


def write_register_core(path):
    descriptor = bytearray(336)  # Linux x86-64 elf_prstatus, NT_PRSTATUS.
    struct.pack_into('<i',descriptor,0,11)
    struct.pack_into('<h',descriptor,12,11)
    struct.pack_into('<i',descriptor,32,123)
    registers = [0]*27
    registers[10] = 0x1122334455667788  # rax
    registers[15] = 0xffffffffffffffff  # orig_rax
    registers[16] = 0x400000  # rip
    registers[17] = 0x33  # cs
    registers[18] = 0x246  # eflags
    registers[19] = 0x7fffffffe000  # rsp
    registers[20] = 0x2b  # ss
    struct.pack_into('<27Q',descriptor,112,*registers)
    note = struct.pack('<III',5,len(descriptor),1)+b'CORE\0\0\0\0'+descriptor
    ident = b'\x7fELF'+bytes([2,1,1,0])+bytes(8)
    header = struct.pack('<16sHHIQQQIHHHHHH',ident,4,62,1,0,64,0,0,64,56,1,0,0,0)
    program = struct.pack('<IIQQQQQQ',4,0,120,0,0,len(note),len(note),4)
    path.write_bytes(header+program+note)


@pytest.fixture
def core_backend(tmp_path):
    if not shutil.which('gdb'):
        pytest.skip('GDB required for synthetic core register test')
    from unepic_trainer.backend import Backend
    from unepic_trainer.processes import identify
    path = tmp_path/'registers.core'
    write_register_core(path)
    backend = Backend()
    # The transport reads only our core. This identity satisfies the session
    # liveness guard; GDB is never attached to this Python process.
    backend.identity = identify(os.getpid())
    backend._gdb = GdbController(command=['gdb','--nx','--quiet','--interpreter=mi3',
        '-iex','set auto-load off','-iex','set debuginfod enabled off'],
        time_to_check_for_additional_output_sec=0.005)
    try:
        backend._command('-gdb-set architecture i386:x86-64')
        # Older GDB versions keep target-select filename quotes literally.
        # Set a properly quoted working directory and use a simple basename.
        backend._command('-environment-cd '+json.dumps(str(tmp_path)))
        backend._command('-target-select core registers.core')
        yield backend
    finally:
        backend.identity = None
        backend.detach()


def test_flags_register_reads_without_integer_cast(core_backend):
    assert core_backend.evaluate('$eflags') == 0x246


def test_unsigned_register_widths_are_preserved(core_backend):
    assert core_backend.evaluate('$rax') == 0x1122334455667788
    assert core_backend.evaluate('$orig_rax') == 0xffffffffffffffff
    assert core_backend.evaluate('$rip') == 0x400000
