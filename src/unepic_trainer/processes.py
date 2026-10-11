from dataclasses import dataclass
from pathlib import Path
import hashlib

from .profiles import Profile, UNEPIC


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    start_time: int
    executable: str
    device: int
    inode: int


def identify(pid: int, proc_root: Path = Path('/proc')) -> ProcessIdentity:
    entry = proc_root / str(pid)
    stat = (entry / 'stat').read_text()
    tail = stat[stat.rfind(')') + 2:].split()
    executable = entry / 'exe'
    info = executable.stat()
    return ProcessIdentity(pid, int(tail[19]), str(executable.resolve(strict=True)),
                           info.st_dev, info.st_ino)


def is_current(identity: ProcessIdentity, proc_root: Path = Path('/proc')) -> bool:
    try:
        return identify(identity.pid, proc_root) == identity
    except (OSError, ValueError, IndexError):
        return False


def validate_target(identity: ProcessIdentity, profile: Profile = UNEPIC,
                    proc_root: Path = Path('/proc')) -> bool:
    if not is_current(identity, proc_root):
        return False
    try:
        with (proc_root / str(identity.pid) / 'exe').open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        return digest == profile.sha256 and is_current(identity, proc_root)
    except OSError:
        return False


def find_candidates(proc_root: Path = Path('/proc')) -> list[ProcessIdentity]:
    result = []
    for entry in proc_root.iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            identity = identify(int(entry.name), proc_root)
            if Path(identity.executable).name == 'unepic64s':
                result.append(identity)
        except (OSError, ValueError, IndexError):
            continue
    return sorted(result, key=lambda item: item.pid)
