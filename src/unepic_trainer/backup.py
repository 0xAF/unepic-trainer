from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import uuid


def find_save_sources(executable: Path, home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    game = executable.parent
    steam_roots = {home/'.local/share/Steam',home/'.steam/steam',home/'.steam/root'}
    if game.parent.name == 'common' and game.parent.parent.name == 'steamapps':
        steam_roots.add(game.parent.parent.parent)
    candidates = [game/'save',game/'saves',
                  home/'.local/share/Unepic',home/'.local/share/unepic',
                  home/'.config/Unepic',home/'.config/unepic',home/'.unepic']
    for steam in steam_roots:
        userdata = steam/'userdata'
        if userdata.is_dir():
            candidates.extend(userdata.glob('*/233980/remote'))
    result = set()
    for path in candidates:
        if path.is_dir() and any(p.is_file() for p in path.rglob('*')):
            result.add(path.resolve())
    return sorted(result)


def backup_saves(sources: list[Path], destination: Path) -> Path:
    destination = destination.resolve()
    sources = sorted({source.resolve() for source in sources if source.is_dir()})
    files = []
    for index,source in enumerate(sources):
        if destination.is_relative_to(source):
            raise ValueError('Backup destination is inside its source directory')
        for path in sorted(source.rglob('*')):
            if path.is_file() and not path.is_symlink():
                files.append((index,source,path))
    if not files:
        raise ValueError('No save files found. Select the save directory before changing the game.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = destination/(stamp+'-'+uuid.uuid4().hex[:8])
    target.mkdir(parents=True)
    manifest = {'created_utc':stamp,'sources':[str(s) for s in sources],'files':[]}
    for index,source,path in files:
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
        if (before.st_mtime_ns,before.st_size) != (after.st_mtime_ns,after.st_size):
            raise ValueError('A save changed during backup; retry after saving finishes')
        relative = Path(str(index))/path.relative_to(source)
        copied = target/relative
        copied.parent.mkdir(parents=True,exist_ok=True)
        copied.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        if hashlib.sha256(copied.read_bytes()).hexdigest() != digest:
            raise ValueError('Save backup verification failed')
        manifest['files'].append({'path':str(relative),'size':len(data),'sha256':digest})
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return target
