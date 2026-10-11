from pathlib import Path
import os


def proc_fixture(tmp_path):
    from unepic_trainer.processes import identify
    executable = tmp_path / 'unepic64s'
    executable.write_bytes(b'abc')
    proc = tmp_path / 'proc'
    entry = proc / '42'
    entry.mkdir(parents=True)
    (entry / 'exe').symlink_to(executable)
    # stat fields 3..22, with spaces and parentheses in comm.
    (entry / 'stat').write_text('42 (game (name)) S ' + '0 ' * 18 + '123 0\n')
    return proc, entry, executable, identify(42, proc)


def test_supported_hash_and_changed_binary(tmp_path):
    from unepic_trainer.processes import validate_target
    from unepic_trainer.profiles import Profile
    proc, entry, exe, identity = proc_fixture(tmp_path)
    profile = Profile(sha256='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
    assert identity.start_time == 123
    assert validate_target(identity, profile, proc)
    exe.write_bytes(b'wrong build')
    assert not validate_target(identity, profile, proc)


def test_pid_reuse_and_exec_replacement(tmp_path):
    from unepic_trainer.processes import is_current
    proc, entry, exe, identity = proc_fixture(tmp_path)
    assert is_current(identity, proc)
    (entry / 'stat').write_text('42 (game) S ' + '0 ' * 18 + '124 0\n')
    assert not is_current(identity, proc)
    (entry / 'stat').write_text('42 (game) S ' + '0 ' * 18 + '123 0\n')
    replacement = tmp_path / 'replacement'
    replacement.write_bytes(b'abc')
    os.replace(replacement, exe)
    assert not is_current(identity, proc)


def test_candidate_discovery_ignores_other_executables(tmp_path):
    from unepic_trainer.processes import find_candidates
    proc, entry, exe, identity = proc_fixture(tmp_path)
    (proc / '99').mkdir()
    (proc / '99' / 'exe').symlink_to('/bin/bash')
    assert find_candidates(proc) == [identity]
