import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_demo_heal_toggle_and_snapshot(app):
    from unepic_trainer.ui import Window
    window = Window(demo=True)
    try:
        assert window.hp.value() == 75
        assert window.heal_button.isEnabled()
        window.heal_button.click()
        assert window.hp.value() == 100
        window.god_button.click()
        assert window.god_button.isChecked()
        assert window.god_button.text() == 'God mode: on'
        window.god_button.click()
        assert not window.god_button.isChecked()
    finally:
        window.close()


def test_progression_pending_and_campaign_cap_disable_only_progression(app):
    from dataclasses import replace
    from unepic_trainer.ui import Window
    window = Window(demo=True)
    try:
        window.show_progression_pending(True)
        assert not window.level_button.isEnabled()
        assert all(not b.isEnabled() for b in window.points_buttons.values())
        assert window.heal_button.isEnabled() and window.minion_heal_button.isEnabled()
        window.show_progression_pending(False)
        window.show_snapshot(replace(window._snapshot,level=25))
        assert not window.level_button.isEnabled()
        assert all(b.isEnabled() for b in window.points_buttons.values())
    finally:
        window.close()


def test_save_game_button_simulates_and_disables_pending_or_missing_hero(app):
    from unepic_trainer.ui import Window
    window = Window(demo=True)
    try:
        before = window._snapshot
        assert window.save_game_button.text() == 'Save game' and window.save_game_button.isEnabled()
        window.save_game_button.click()
        assert 'simulated' in window.status.text().lower() and window._snapshot == before
        window.show_save_pending(True)
        assert not window.save_game_button.isEnabled() and window.heal_button.isEnabled()
        assert not window.level_button.isEnabled()
        window.show_save_pending(False); assert window.save_game_button.isEnabled()
        window.show_snapshot(None); assert not window.save_game_button.isEnabled()
    finally:
        window.close()


def test_gold_buttons_are_in_player_and_share_one_shot_pending_state(app):
    from unepic_trainer.ui import Window
    window = Window(demo=True)
    try:
        assert set(window.gold_buttons) == {100,1000,10000}
        for amount,button in window.gold_buttons.items():
            assert button.parent() is window.player_card and button.isEnabled()
            button.click(); assert window.status.text() == f'Demo · added {amount} gold'
        window.show_progression_pending(True)
        assert all(not b.isEnabled() for b in window.gold_buttons.values())
        assert not window.save_game_button.isEnabled()
        window.show_progression_pending(False)
        window.show_snapshot(None)
        assert all(not b.isEnabled() for b in window.gold_buttons.values())
    finally:
        window.close()


def test_credits_buttons_use_full_name_and_share_pending_and_save_guards(app):
    from unepic_trainer.ui import Window
    w = Window(demo=True)
    try:
        assert w.credits_title.text() == 'Unepic Credits'
        assert set(w.credits_buttons) == {100,1000,10000}
        for amount,b in w.credits_buttons.items():
            assert b.parent() is w.player_card and b.isEnabled()
            b.click(); assert w.status.text() == f'Demo · added {amount} Unepic Credits'
        w.show_progression_pending(True); assert all(not b.isEnabled() for b in w.credits_buttons.values())
        w.show_progression_pending(False); w.show_save_pending(True)
        assert all(not b.isEnabled() for b in w.credits_buttons.values())
        w.show_save_pending(False); w.show_snapshot(None)
        assert all(not b.isEnabled() for b in w.credits_buttons.values())
    finally:
        w.close()


def test_missing_hero_disables_actions(app):
    from unepic_trainer.ui import Window
    window = Window(demo=True)
    try:
        window.show_snapshot(None)
        assert not window.heal_button.isEnabled()
        assert not window.god_button.isEnabled()
        assert window.hp.value() == 0
        window.show_error('Unsupported version')
        assert 'Unsupported version' in window.error.text()
        assert not window.heal_button.isEnabled()
    finally:
        window.close()


def test_kp_bar_buttons_cap_and_locked_pending_save_states(app):
    from dataclasses import replace
    from unepic_trainer.ui import Window
    w = Window(demo=True)
    try:
        assert set(w.kp_buttons) == {1,10,100}
        w.show_snapshot(replace(w._snapshot,kill_points=8,kill_points_unlocked=True))
        assert w.kp.value() == 8 and w.kp.maximum() == 25
        assert w.kp.format() == '1.6 / 5 KP'
        assert all(b.parent() is w.player_card and b.isEnabled() for b in w.kp_buttons.values())
        w.kp_buttons[1].click(); assert w._snapshot.kill_points == 13
        w.kp_buttons[100].click(); assert w._snapshot.kill_points == 25
        assert w.kp.format() == '5 / 5 KP'
        assert all(not b.isEnabled() for b in w.kp_buttons.values())
        w.show_snapshot(replace(w._snapshot,kill_points=0,kill_points_unlocked=False))
        assert w.kp.format() == 'Kill Points locked'
        assert all(not b.isEnabled() for b in w.kp_buttons.values())
        w.show_snapshot(replace(w._snapshot,kill_points=8,kill_points_unlocked=True))
        w.show_progression_pending(True); assert all(not b.isEnabled() for b in w.kp_buttons.values())
        w.show_progression_pending(False); w.show_save_pending(True)
        assert all(not b.isEnabled() for b in w.kp_buttons.values())
        w.show_save_pending(False); w.show_snapshot(None)
        assert w.kp.format() == 'KP unavailable'
        assert all(not b.isEnabled() for b in w.kp_buttons.values())
    finally:
        w.close()


def test_real_window_closes_worker_without_connection(app):
    from unepic_trainer.ui import Window
    import time
    window = Window()
    window.show()
    window.close()
    deadline = time.monotonic()+5
    while window.thread.isRunning() and time.monotonic()<deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not window.thread.isRunning()


def test_minion_demo_has_independent_hp_and_maximum_energy_controls(app):
    from unepic_trainer.ui import Window
    window = Window(demo=True)
    try:
        assert window.minion_hp.value() == 50
        assert window.minion_energy.value() == 25
        window.minion_heal_button.click()
        assert window.minion_hp.value() == 100
        assert window.minion_energy.value() == 25 and window.hp.value() == 75
        window.energy_button.click()
        assert window.minion_energy.value() == 100
        assert window.energy_button.isChecked()
        assert not window.minion_god_button.isChecked() and not window.god_button.isChecked()
        window.minion_god_button.click()
        assert window.minion_god_button.isChecked() and not window.god_button.isChecked()
        window.show_minions(())
        assert not window.minion_heal_button.isEnabled()
        assert window.minion_god_button.isEnabled() and window.energy_button.isEnabled()
        window.energy_button.click()
        window.minion_god_button.click()
        assert not window.energy_button.isEnabled() and not window.minion_god_button.isEnabled()
    finally:
        window.close()


def test_player_and_minion_columns_include_progression_controls(app):
    from unepic_trainer.ui import Window
    window = Window(demo=True)
    window.show(); app.processEvents()
    try:
        assert window.player_card.x()+window.player_card.width() <= window.minion_card.x()
        for increment in (1,10,100):
            before = window._snapshot.free_points
            window.points_buttons[increment].click()
            assert window._snapshot.free_points == before+increment
        before = window._snapshot.level
        window.level_button.click()
        assert window._snapshot.level == before+1 and window._snapshot.xp == 0
        assert window.minion_hp.value() == 50 and window.minion_energy.value() == 25
        window.show_snapshot(None)
        assert not window.level_button.isEnabled()
        assert all(not b.isEnabled() for b in window.points_buttons.values())
    finally:
        window.close()
