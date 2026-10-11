def test_real_owned_minion_hp_and_maximum_energy_are_independent(target):
    from conftest import attach_or_skip
    from unepic_trainer.backend import Backend
    from unepic_trainer.hooks import GodMode, EnergyLock
    from unepic_trainer.minions import read_minions, heal_minions
    proc,data,identity,profile = target
    backend = Backend(profile); attach_or_skip(backend,identity)
    mode,energy = GodMode(),EnergyLock()
    try:
        pet, = read_minions(backend)
        assert (pet.current_hp,pet.energy) == (40,25)
        heal_minions(backend)
        mode.enable(backend,'minion'); energy.enable(backend)
        proc.stdin.write('pets\n'); proc.stdin.flush()
        assert proc.stdout.readline().strip() == '80 100 25 15'
        energy.disable(backend)
        proc.stdin.write('pets\n'); proc.stdin.flush()
        assert proc.stdout.readline().strip() == '80 90 10 5'
        mode.disable(backend,'minion')
        proc.stdin.write('pets\n'); proc.stdin.flush()
        assert proc.stdout.readline().strip().split()[:2] == ['65','80']
    finally:
        energy.disable_all(backend); mode.disable_all(backend); backend.detach()
