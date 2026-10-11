import argparse
from dataclasses import replace
from pathlib import Path
import signal
import sys

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot, Qt
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from .backend import Backend, BackendError, LiveReadUnavailable
from .backup import backup_saves, find_save_sources
from .character import CharacterSnapshot, heal, read_character
from .hooks import GodMode, EnergyLock
from .minions import MinionSnapshot, read_minions, heal_minions
from .processes import find_candidates, is_current
from .progression import Progression
from .saving import SaveGame
from .runtime import default_data_directory


class Worker(QObject):
    snapshot_updated = Signal(object)
    status_changed = Signal(str)
    operation_failed = Signal(str)
    candidates_updated = Signal(object)
    state_changed = Signal(bool,bool)
    minions_updated = Signal(object)
    minion_state_changed = Signal(bool,bool)
    busy_changed = Signal(bool)
    progression_pending = Signal(bool)
    save_pending = Signal(bool)
    finished = Signal()
    shutdown_rejected = Signal()

    def __init__(self, project: Path, save_dir: Path | None):
        super().__init__()
        self.project = project.resolve()
        self.save_dir = save_dir
        self.backend = Backend()
        self.mode = GodMode()
        self.energy_lock = EnergyLock()
        self.progression = Progression()
        self.saving = SaveGame()
        self.backup = None
        self.timer = None
        self._live_unavailable = False

    @Slot()
    def start(self):
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.dispatch('refresh',None)

    def _backup_before_change(self):
        if self.backup is not None:
            return
        executable = Path(self.backend.identity.executable)
        if self.project.is_relative_to(executable.parent):
            raise BackendError('Project directory must be outside the game installation')
        sources = find_save_sources(executable)
        if self.save_dir is not None:
            sources.append(self.save_dir)
        self.backup = backup_saves(sources,self.project/'backups')

    def _disconnect(self):
        identity = self.backend.identity
        if identity and is_current(identity):
            self.saving.cancel(self.backend)
            self.progression.disable_all(self.backend)
            self.energy_lock.disable_all(self.backend)
            self.mode.disable_all(self.backend)
        self.backend.detach()
        self.mode = GodMode()
        self.energy_lock = EnergyLock()
        self.progression = Progression()
        self.saving = SaveGame()
        self.save_pending.emit(False)
        self.progression_pending.emit(False)
        self.backup = None
        self._live_unavailable = False
        self.snapshot_updated.emit(None)
        self.minions_updated.emit(())
        self.minion_state_changed.emit(False,False)
        self.state_changed.emit(False,False)
        self.status_changed.emit('Disconnected')

    @Slot(str,object)
    def dispatch(self, action, payload):
        self.busy_changed.emit(True)
        try:
            if action == 'refresh':
                if self.backend.identity is None:
                    self.candidates_updated.emit(find_candidates())
                else:
                    self._refresh()
            elif action == 'attach':
                self.backend.attach(payload)
                self._live_unavailable = False
                self.state_changed.emit(True,False)
                self.status_changed.emit(f'Connected · PID {payload.pid}')
                self._refresh()
            elif action == 'detach':
                self._disconnect()
            elif action == 'save-dir':
                self.save_dir = Path(payload)
                self.backup = None
                self.status_changed.emit('Save directory selected')
            elif action in ('points','level-up','gold','credits','kill-points'):
                if self.saving.pending:
                    raise BackendError('Wait for the pending save request before changing the character')
                with self.backend.stopped():
                    self._backup_before_change()
                    self.progression.submit(self.backend,action,payload if action in ('points','gold','credits','kill-points') else 0)
                self.progression_pending.emit(True)
                self._refresh()
                if self.progression.pending:
                    self.status_changed.emit('Progression request queued · resume the game if paused')
            elif action == 'save-game':
                if self.progression.pending:
                    raise BackendError('Wait for the pending character update before saving')
                with self.backend.stopped():
                    self._backup_before_change()
                    self.saving.submit(self.backend)
                self.save_pending.emit(True)
                self._refresh()
                if self.saving.pending:
                    self.status_changed.emit('Save request queued · resume the game if paused')
            elif action in ('heal','god','minion-heal','minion-god','minion-energy'):
                if action in ('god','minion-god','minion-energy') and not payload:
                    if action == 'minion-energy':
                        self.energy_lock.disable(self.backend)
                    else:
                        self.mode.disable(self.backend,'minion' if action == 'minion-god' else 'player')
                    self.backend.resume()
                else:
                    with self.backend.stopped():
                        self._backup_before_change()
                        if action == 'heal':
                            heal(self.backend)
                        elif action == 'minion-heal':
                            heal_minions(self.backend)
                        elif action == 'minion-energy':
                            self.energy_lock.enable(self.backend)
                        else:
                            self.mode.enable(self.backend,'minion' if action == 'minion-god' else 'player')
                self.state_changed.emit(True,self.mode.active)
                self.minion_state_changed.emit(self.mode.minion_active,self.energy_lock.active)
                self.status_changed.emit('Connected to the game')
                self._refresh()
            elif action == 'shutdown':
                self._disconnect()
                if self.timer is not None:
                    self.timer.stop()
                self.finished.emit()
        except Exception as error:
            self.save_pending.emit(self.saving.pending)
            self.operation_failed.emit(str(error))
            self.state_changed.emit(self.backend.identity is not None,self.mode.active)
            self.minion_state_changed.emit(self.mode.minion_active,self.energy_lock.active)
            if action == 'shutdown':
                self.shutdown_rejected.emit()
        finally:
            self.busy_changed.emit(False)

    @Slot()
    def poll(self):
        if self.backend.identity is None:
            return
        try:
            if not is_current(self.backend.identity):
                self._disconnect()
                self.status_changed.emit('The game has exited')
                return
            if self.backend.unsafe:
                raise BackendError('Recovery required; the game remains paused')
            if self._live_unavailable:
                return
            snapshot,pets = self._live_snapshot()
            self.snapshot_updated.emit(snapshot)
            self.minions_updated.emit(pets)
        except LiveReadUnavailable:
            self._live_unavailable = True
            self.status_changed.emit('Connected · manual readings only; use Refresh')
        except Exception as error:
            self.snapshot_updated.emit(None)
            self.minions_updated.emit(())
            self.operation_failed.emit(str(error))

    def _live_snapshot(self):
        # Live displays are best-effort. Retry once if a room transition or
        # an in-progress protected-value update makes the sample inconsistent.
        for attempt in range(2):
            try:
                with self.backend.live() as reader:
                    profile = reader.profile
                    anchors = (profile.entity_slot,profile.hero+0x197c0)
                    before = tuple(reader.read(address,8) for address in anchors)
                    snapshot = read_character(reader)
                    pets = read_minions(reader)
                    if before != tuple(reader.read(address,8) for address in anchors):
                        raise BackendError('Character or room changed during live reading')
                    self._poll_progression(reader)
                    self._poll_saving(reader)
                return snapshot,pets
            except LiveReadUnavailable:
                raise
            except BackendError:
                if attempt:
                    raise

    def _refresh(self):
        """An explicit action may request a stopped read if live access fails."""
        try:
            snapshot,pets = self._live_snapshot()
            self._live_unavailable = False
            self.status_changed.emit(f'Connected · PID {self.backend.identity.pid}')
        except LiveReadUnavailable:
            self._live_unavailable = True
            with self.backend.stopped():
                snapshot,pets = read_character(self.backend),read_minions(self.backend)
                self._poll_progression(self.backend)
                self._poll_saving(self.backend)
            self.status_changed.emit('Connected · manual readings only; use Refresh')
        self.snapshot_updated.emit(snapshot)
        self.minions_updated.emit(pets)

    def _poll_progression(self,reader):
        if not self.progression.pending:
            return
        try:
            result = self.progression.poll(reader)
        except BackendError as error:
            if self.progression.pending:
                raise  # A transient read failure may be retried.
            self.operation_failed.emit(str(error))
            return
        finally:
            self.progression_pending.emit(self.progression.pending)
        if result:
            action,amount = result
            self.status_changed.emit('Kill Points updated · maximum 5 KP' if action == 'kill-points' else
                                     f'Added {amount} Unepic Credits' if action == 'credits' else
                                     f'Added {amount} {action}' if action in ('points','gold') else 'Level up completed')

    def _poll_saving(self,reader):
        if not self.saving.pending:
            return
        slot = self.saving.poll(reader)
        self.save_pending.emit(self.saving.pending)
        if slot is not None:
            self.status_changed.emit('Save request processed · check the game confirmation')


STYLE = '''
QWidget { background: #151b26; color: #e7edf5; font-family: sans-serif; font-size: 14px; }
QLabel#title { font-size: 29px; font-weight: 700; }
QLabel#muted { color: #95a3b8; }
QLabel#tag { color: #82dab9; background: #243d37; border-radius: 5px; padding: 6px 10px; }
QFrame#card { background: #202939; border-radius: 12px; }
QFrame#card QLabel { background: transparent; }
QPushButton { background: #2c394e; border: 1px solid #3b4c66; border-radius: 7px; padding: 9px; }
QPushButton:hover { background: #354760; }
QPushButton:disabled { color: #69788d; background: #202939; border-color: #2d3644; }
QPushButton#god { font-size: 17px; padding: 14px; }
QPushButton#god:checked, QPushButton#toggle:checked { background: #236b53; border-color: #75d9b4; color: white; }
QComboBox { background: #202939; border: 1px solid #3b4c66; padding: 9px; border-radius: 7px; }
QProgressBar { background: #121824; border: none; border-radius: 7px; text-align: center; height: 27px; }
QProgressBar::chunk { background: #48bb91; border-radius: 7px; }
QProgressBar#energy::chunk { background: #589cd6; }
QLabel#error { color: #ffbb99; font-size: 12px; }
'''


class Window(QWidget):
    request = Signal(str,object)
    shutdown_complete = Signal()

    def __init__(self, demo: bool = False, project: Path | None = None, save_dir: Path | None = None):
        super().__init__()
        self.demo = demo
        self._connected = demo
        self._has_hero = False
        self._god_active = False
        self._minion_god_active = False
        self._energy_active = False
        self._minions = ()
        self._busy = False
        self._closing = False
        self._closed_worker = demo
        self._snapshot = None
        self._progression_pending = False
        self._save_pending = False
        self.setWindowTitle('Unepic Trainer')
        self.setMinimumWidth(800)
        self.resize(860,720)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20,20,20,20)
        layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel('Unepic Trainer'); title.setObjectName('title')
        tag = QLabel('DEMO' if demo else 'LINUX'); tag.setObjectName('tag')
        header.addWidget(title); header.addStretch(); header.addWidget(tag)
        layout.addLayout(header)
        subtitle = QLabel('Your hero. Your rules.'); subtitle.setObjectName('muted')
        layout.addWidget(subtitle)
        self.status = QLabel('Demo · not connected to the game' if demo else 'Start Unepic and select its process')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.processes = QComboBox()
        self.processes.addItem('No game process found',None)
        self.refresh_button = QPushButton('Refresh')
        row.addWidget(self.processes,1); row.addWidget(self.refresh_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.attach_button = QPushButton('Connect')
        self.detach_button = QPushButton('Disconnect')
        row.addWidget(self.attach_button); row.addWidget(self.detach_button)
        layout.addLayout(row)
        columns = QHBoxLayout(); columns.setSpacing(14)
        self.player_card = card = QFrame(); card.setObjectName('card')
        content = QVBoxLayout(card); content.setContentsMargins(18,18,18,18)
        player_title = QLabel('Player'); player_title.setStyleSheet('font-size: 21px; font-weight: 600;')
        content.addWidget(player_title)
        hp_title = QLabel('HEALTH'); hp_title.setObjectName('muted')
        content.addWidget(hp_title)
        self.hp = QProgressBar(); self.hp.setRange(0,100); self.hp.setValue(0)
        self.hp.setFormat('No character loaded')
        content.addWidget(self.hp)
        self.stats = QLabel('Level —    XP —    Points —'); self.stats.setWordWrap(True)
        content.addWidget(self.stats)
        self.god_button = QPushButton('God mode: off')
        self.god_button.setObjectName('god'); self.god_button.setCheckable(True)
        content.addWidget(self.god_button)
        self.heal_button = QPushButton('Full heal')
        self.save_game_button = QPushButton('Save game')
        self.save_game_button.setToolTip('Request a save in the current slot, including Hard/Hard++. Resume if paused; check the game confirmation.')
        row = QHBoxLayout(); row.addWidget(self.heal_button); row.addWidget(self.save_game_button)
        content.addLayout(row)
        self.points_label = QLabel('Points to distribute: —'); content.addWidget(self.points_label)
        row = QHBoxLayout(); self.points_buttons = {}
        for amount in (1,10,100):
            button = QPushButton(f'+{amount}'); self.points_buttons[amount] = button
            button.clicked.connect(lambda checked=False,amount=amount:self._send('points',amount))
            row.addWidget(button)
        content.addLayout(row)
        self.xp = QProgressBar(); self.xp.setRange(0,100); self.xp.setValue(0)
        self.xp.setObjectName('energy'); self.xp.setFormat('XP unavailable'); content.addWidget(self.xp)
        self.level_button = QPushButton('Level up'); content.addWidget(self.level_button)
        self.level_button.setToolTip('Fill XP and trigger the next level immediately. Campaign maximum: level 25.')
        row = QHBoxLayout(); self.kp_buttons = {}
        self.kp = QProgressBar(); self.kp.setRange(0,25); self.kp.setValue(0)
        self.kp.setObjectName('energy'); self.kp.setFormat('KP unavailable')
        self.kp.setToolTip('Kill Points (KP) · maximum 5 KP')
        row.addWidget(self.kp,1)
        for amount in (1,10,100):
            button = QPushButton(f'+{amount}'); self.kp_buttons[amount] = button
            button.setToolTip(f'Add {amount} Kill Points, capped at 5 KP. Requires Kill Points unlocked in the game.')
            button.clicked.connect(lambda checked=False,amount=amount:self._send('kill-points',amount))
            row.addWidget(button)
        content.addLayout(row)
        gold_title = QLabel('Gold'); gold_title.setObjectName('muted')
        row = QHBoxLayout(); row.addWidget(gold_title); self.gold_buttons = {}
        for amount in (100,1000,10000):
            button = QPushButton(f'+{amount}'); self.gold_buttons[amount] = button
            button.clicked.connect(lambda checked=False,amount=amount:self._send('gold',amount))
            row.addWidget(button)
        content.addLayout(row)
        self.credits_title = QLabel('Unepic Credits'); self.credits_title.setObjectName('muted')
        row = QHBoxLayout(); row.addWidget(self.credits_title); self.credits_buttons = {}
        for amount in (100,1000,10000):
            button = QPushButton(f'+{amount}'); self.credits_buttons[amount] = button
            button.clicked.connect(lambda checked=False,amount=amount:self._send('credits',amount))
            row.addWidget(button)
        content.addLayout(row)
        content.addStretch()
        columns.addWidget(card,1)
        self.minion_card = card = QFrame(); card.setObjectName('card')
        content = QVBoxLayout(card); content.setContentsMargins(18,14,18,14)
        section_title = QLabel('Minion'); section_title.setStyleSheet('font-size: 21px; font-weight: 600;')
        content.addWidget(section_title)
        self.minion_title = QLabel('MINION'); self.minion_title.setObjectName('muted')
        self.minion_title.setWordWrap(True)
        content.addWidget(self.minion_title)
        self.minion_hp = QProgressBar(); self.minion_hp.setRange(0,100)
        self.minion_hp.setValue(0); self.minion_hp.setFormat('No minion loaded')
        content.addWidget(self.minion_hp)
        self.minion_energy = QProgressBar(); self.minion_energy.setObjectName('energy')
        self.minion_energy.setRange(0,100); self.minion_energy.setValue(0)
        self.minion_energy.setFormat('Energy unavailable'); content.addWidget(self.minion_energy)
        self.minion_heal_button = QPushButton('Heal minion')
        self.minion_god_button = QPushButton('Minion god mode: off')
        self.minion_god_button.setCheckable(True); self.minion_god_button.setObjectName('toggle')
        content.addWidget(self.minion_god_button); content.addWidget(self.minion_heal_button)
        self.energy_button = QPushButton('Lock energy at maximum: off')
        self.energy_button.setCheckable(True); self.energy_button.setObjectName('toggle')
        content.addWidget(self.energy_button); content.addStretch()
        columns.addWidget(card,1); layout.addLayout(columns,1)
        self.save_button = QPushButton('Save directory…')
        layout.addWidget(self.save_button)
        self.error = QLabel(''); self.error.setObjectName('error'); self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.PlainText)
        layout.addWidget(self.error)
        layout.addStretch()
        note = QLabel('Single-player · initial release' if not demo else 'Sample data · actions are simulated')
        note.setObjectName('muted'); layout.addWidget(note)
        self.refresh_button.clicked.connect(lambda:self._send('refresh'))
        self.attach_button.clicked.connect(lambda:self._send('attach',self.processes.currentData()))
        self.detach_button.clicked.connect(lambda:self._send('detach'))
        self.heal_button.clicked.connect(lambda:self._send('heal'))
        self.save_game_button.clicked.connect(lambda:self._send('save-game'))
        self.level_button.clicked.connect(lambda:self._send('level-up'))
        self.god_button.clicked.connect(lambda checked:self._send('god',checked))
        self.minion_heal_button.clicked.connect(lambda:self._send('minion-heal'))
        self.minion_god_button.clicked.connect(lambda checked:self._send('minion-god',checked))
        self.energy_button.clicked.connect(lambda checked:self._send('minion-energy',checked))
        self.save_button.clicked.connect(self.choose_saves)
        self.processes.currentIndexChanged.connect(self.update_controls)
        if demo:
            self.show_snapshot(CharacterSnapshot(0,75,100,3,250,5,1000,8,True))
            self.show_minions((MinionSnapshot(1,40,80,25,100),))
        else:
            self.thread = QThread(self)
            self.worker = Worker(project or Path.cwd(),save_dir)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.start)
            self.request.connect(self.worker.dispatch)
            self.worker.snapshot_updated.connect(self.show_snapshot)
            self.worker.status_changed.connect(self.status.setText)
            self.worker.operation_failed.connect(self.show_error)
            self.worker.candidates_updated.connect(self.show_candidates)
            self.worker.state_changed.connect(self.show_state)
            self.worker.minions_updated.connect(self.show_minions)
            self.worker.minion_state_changed.connect(self.show_minion_state)
            self.worker.busy_changed.connect(self.show_busy)
            self.worker.progression_pending.connect(self.show_progression_pending)
            self.worker.save_pending.connect(self.show_save_pending)
            self.worker.finished.connect(self.thread.quit)
            self.worker.shutdown_rejected.connect(self.cancel_close)
            self.thread.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.worker_closed)
            self.thread.start()
        self.update_controls()

    def _send(self, action, payload=None):
        self.error.clear()
        if self.demo:
            if action == 'kill-points' and self._snapshot:
                self.show_snapshot(replace(self._snapshot,kill_points=min(25,self._snapshot.kill_points+5*payload)))
                self.status.setText('Demo · Kill Points updated · maximum 5 KP')
            elif action == 'credits':
                self.status.setText(f'Demo · added {payload} Unepic Credits')
            elif action == 'gold':
                self.status.setText(f'Demo · added {payload} gold')
            elif action == 'save-game':
                self.status.setText('Demo · save request simulated')
            elif action == 'points' and self._snapshot:
                self.show_snapshot(replace(self._snapshot,free_points=self._snapshot.free_points+payload))
            elif action == 'level-up' and self._snapshot and self._snapshot.level < 25:
                self.show_snapshot(replace(self._snapshot,level=self._snapshot.level+1,xp=0,
                                           free_points=self._snapshot.free_points+5))
            elif action == 'heal' and self._snapshot:
                self.show_snapshot(replace(self._snapshot,current_hp=self._snapshot.max_hp))
            elif action == 'god':
                self.show_state(True,bool(payload))
            elif action == 'minion-heal':
                self.show_minions(tuple(replace(p,current_hp=p.max_hp) for p in self._minions))
            elif action == 'minion-god':
                self.show_minion_state(bool(payload),self._energy_active)
            elif action == 'minion-energy':
                if payload:
                    self.show_minions(tuple(replace(p,energy=p.max_energy) for p in self._minions))
                self.show_minion_state(self._minion_god_active,bool(payload))
            return
        if action == 'attach' and payload is None:
            return
        self.show_busy(True)
        self.request.emit(action,payload)

    @Slot(object)
    def show_snapshot(self,snapshot):
        self._snapshot = snapshot
        self._has_hero = snapshot is not None and snapshot.current_hp > 0
        if snapshot is None:
            self.hp.setValue(0); self.hp.setFormat('No character loaded')
            self.stats.setText('Level —    XP —    Points —')
            self.points_label.setText('Points to distribute: —')
            self.xp.setValue(0); self.xp.setFormat('XP unavailable')
            self.kp.setValue(0); self.kp.setFormat('KP unavailable')
        else:
            self.hp.setValue(round(100*snapshot.current_hp/snapshot.max_hp))
            self.hp.setFormat(f'{snapshot.current_hp:g} / {snapshot.max_hp} HP')
            self.stats.setText(f'Level {snapshot.level}')
            self.points_label.setText(f'Points to distribute: {snapshot.free_points}')
            self.xp.setValue(min(100,round(100*snapshot.xp/snapshot.xp_threshold)))
            self.xp.setFormat(f'{snapshot.xp} / {snapshot.xp_threshold} XP')
            self.kp.setValue(snapshot.kill_points if snapshot.kill_points_unlocked else 0)
            self.kp.setFormat(f'{snapshot.kill_points/5:g} / 5 KP' if snapshot.kill_points_unlocked else 'Kill Points locked')
        self.update_controls()

    @Slot(bool,bool)
    def show_state(self,connected,active):
        self._connected, self._god_active = connected, active
        self.god_button.setChecked(active)
        self.god_button.setText('God mode: on' if active else 'God mode: off')
        self.update_controls()

    @Slot(object)
    def show_minions(self,pets):
        self._minions = tuple(pets)
        self.minion_title.setText('MINION' if len(pets) <= 1 else f'MINIONS · {len(pets)} owned · controls apply to all')
        hp, cap = sum(p.current_hp for p in pets),sum(p.max_hp for p in pets)
        energy, energy_cap = sum(p.energy for p in pets if p.max_energy),sum(p.max_energy for p in pets)
        self.minion_hp.setValue(round(100*hp/cap) if cap else 0)
        self.minion_hp.setFormat(f'{hp:g} / {cap} HP' if cap else 'No minion loaded')
        self.minion_energy.setValue(round(100*energy/energy_cap) if energy_cap else 0)
        self.minion_energy.setFormat(f'{energy:g} / {energy_cap} ENERGY' if energy_cap else 'Energy unavailable')
        self.update_controls()

    @Slot(bool,bool)
    def show_minion_state(self,active,energy):
        self._minion_god_active, self._energy_active = active, energy
        self.minion_god_button.setChecked(active)
        self.minion_god_button.setText('Minion god mode: on' if active else 'Minion god mode: off')
        self.energy_button.setChecked(energy)
        self.energy_button.setText('Lock energy at maximum: on' if energy else 'Lock energy at maximum: off')
        self.update_controls()

    @Slot(bool)
    def show_busy(self,busy):
        self._busy = busy
        self.update_controls()

    @Slot(bool)
    def show_progression_pending(self,pending):
        self._progression_pending = pending
        self.update_controls()

    @Slot(bool)
    def show_save_pending(self,pending):
        self._save_pending = pending
        self.save_game_button.setText('Save queued…' if pending else 'Save game')
        self.update_controls()

    @Slot(str)
    def show_error(self,message):
        self.error.setText(message)
        self._has_hero = False
        self._minions = ()
        self.god_button.setChecked(self._god_active)
        self.minion_god_button.setChecked(self._minion_god_active)
        self.energy_button.setChecked(self._energy_active)
        self.update_controls()

    @Slot(object)
    def show_candidates(self,candidates):
        self.processes.clear()
        for identity in candidates:
            self.processes.addItem(f'Unepic · PID {identity.pid}',identity)
        if not candidates:
            self.processes.addItem('No game process found',None)
        self.update_controls()

    @Slot()
    def update_controls(self):
        ready = not self._busy and not self._closing
        self.save_game_button.setEnabled(ready and self._connected and self._has_hero and
                                        not self._save_pending and not self._progression_pending)
        progression_ready = ready and self._connected and self._has_hero and not self._progression_pending and not self._save_pending
        for amount,button in self.points_buttons.items():
            button.setEnabled(progression_ready and self._snapshot.free_points <= 0x7fffffff-amount)
        for button in self.gold_buttons.values():
            button.setEnabled(progression_ready)
        for button in self.credits_buttons.values():
            button.setEnabled(progression_ready)
        for button in self.kp_buttons.values():
            button.setEnabled(progression_ready and self._snapshot.kill_points_unlocked and self._snapshot.kill_points < 25)
        self.level_button.setEnabled(progression_ready and self._snapshot.level < 25)
        self.heal_button.setEnabled(ready and self._connected and self._has_hero)
        self.god_button.setEnabled(ready and self._connected and (self._has_hero or self._god_active))
        pets_ready = self._has_hero and bool(self._minions)
        self.minion_heal_button.setEnabled(ready and self._connected and pets_ready)
        self.minion_god_button.setEnabled(ready and self._connected and (pets_ready or self._minion_god_active))
        self.energy_button.setEnabled(ready and self._connected and
            ((pets_ready and any(p.max_energy for p in self._minions)) or self._energy_active))
        self.attach_button.setEnabled(ready and not self._connected and self.processes.currentData() is not None)
        self.detach_button.setEnabled(ready and self._connected and not self.demo)
        self.refresh_button.setEnabled(ready and not self.demo)
        self.processes.setEnabled(ready and not self._connected and not self.demo)
        self.save_button.setEnabled(ready and not self.demo)

    def choose_saves(self):
        directory = QFileDialog.getExistingDirectory(self,'Unepic save directory')
        if directory:
            self._send('save-dir',directory)

    @Slot()
    def cancel_close(self):
        self._closing = False
        self.update_controls()

    @Slot()
    def worker_closed(self):
        self._closed_worker = True
        self.close()

    def closeEvent(self,event):
        if self._closed_worker:
            event.accept()
            self.shutdown_complete.emit()
        else:
            event.ignore()
            if not self._closing:
                self._closing = True
                self.update_controls()
                self.request.emit('shutdown',None)


def main():
    parser = argparse.ArgumentParser(description='Unepic Linux single-player trainer')
    parser.add_argument('--demo',action='store_true',help='Preview using simulated data')
    parser.add_argument('--project-dir',type=Path,default=default_data_directory(),help='Data and backup directory')
    parser.add_argument('--save-dir',type=Path,help='Additional save directory to back up')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName('Unepic Trainer')
    # Exit explicitly after verified worker cleanup, independent of the
    # desktop's implicit last-window policy.
    app.setQuitOnLastWindowClosed(False)
    window = Window(args.demo,args.project_dir,args.save_dir)
    window.shutdown_complete.connect(app.quit)
    close_requested = False

    def request_close(signum,frame):
        nonlocal close_requested
        close_requested = True

    def service_signals():
        nonlocal close_requested
        if close_requested:
            close_requested = False
            window.close()

    # A Python callback in the main Qt loop services pending OS signals.
    # The signal handler itself does not touch widgets or bypass restoration.
    signal_timer = QTimer(app)
    signal_timer.setInterval(100)
    signal_timer.timeout.connect(service_signals)
    previous = {kind:signal.getsignal(kind) for kind in (signal.SIGINT,signal.SIGTERM)}
    for kind in previous:
        signal.signal(kind,request_close)
    signal_timer.start()
    window.show()
    try:
        result = app.exec()
        if not args.demo:
            window.thread.wait()
        return result
    finally:
        signal_timer.stop()
        for kind,handler in previous.items():
            signal.signal(kind,handler)
