from pathlib import Path
import json
import pytest


def test_backup_preserves_source_and_records_files(tmp_path):
    from unepic_trainer.backup import backup_saves
    saves = tmp_path/'saves'
    saves.mkdir()
    (saves/'hero.sav').write_bytes(b'progress')
    result = backup_saves([saves],tmp_path/'project'/'backups')
    assert (saves/'hero.sav').read_bytes() == b'progress'
    copied = list(result.rglob('hero.sav'))
    assert len(copied) == 1 and copied[0].read_bytes() == b'progress'
    manifest = json.loads((result/'manifest.json').read_text())
    assert manifest['files'][0]['size'] == 8


def test_missing_saves_and_recursive_destination_refused(tmp_path):
    from unepic_trainer.backup import backup_saves
    with pytest.raises(ValueError,match='save'):
        backup_saves([],tmp_path/'backups')
    saves = tmp_path/'saves'
    saves.mkdir()
    (saves/'hero.sav').write_bytes(b'progress')
    with pytest.raises(ValueError,match='inside'):
        backup_saves([saves],saves/'backups')


def test_discovery_reads_steam_game_app_directory(tmp_path):
    from unepic_trainer.backup import find_save_sources
    game = tmp_path/'Steam'/'steamapps'/'common'/'Unepic'
    game.mkdir(parents=True)
    remote = tmp_path/'Steam'/'userdata'/'123'/'233980'/'remote'
    remote.mkdir(parents=True)
    (remote/'hero.sav').write_bytes(b'save')
    assert remote in find_save_sources(game/'unepic64s',home=tmp_path/'home')
