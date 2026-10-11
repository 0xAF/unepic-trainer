"""GDB/MI mutations and live read-only monitoring, used by one worker."""
from contextlib import contextmanager
import json
import os
import time
from pathlib import Path

from pygdbmi.gdbcontroller import GdbController

from .processes import ProcessIdentity, is_current, validate_target
from .profiles import Profile, UNEPIC
from .runtime import gdb_launch_command


class BackendError(RuntimeError):
    pass


class LiveReadUnavailable(BackendError):
    """The host does not permit reading /proc/PID/mem."""


class _LiveMemory:
    """A read-only view for display snapshots, never for write decisions."""
    def __init__(self, profile, fd):
        self.profile = profile
        self._fd = fd

    @contextmanager
    def stopped(self):
        # Existing snapshot parsers also work with this read-only interface.
        # This context deliberately does not interrupt the target.
        yield self

    def read(self, address, size):
        if self._fd is None:
            raise BackendError('Live memory view is closed')
        if address <= 0 or address > 0x7fffffffffff or size <= 0 or size > 1024*1024:
            raise BackendError('Invalid memory range')
        try:
            data = os.pread(self._fd,size,address)
        except OSError as error:
            raise BackendError(f'Cannot read live memory; the scene may have changed: {error}') from error
        if len(data) != size:
            raise BackendError('Incomplete live memory response')
        return data

    def write(self, address, data):
        raise BackendError('Live memory view is read-only; changes require a stopped target')

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


def find_near_gap(site: int, ranges: list[tuple[int, int]], size: int) -> int:
    if size <= 0 or size % 4096:
        raise BackendError('Allocation size must be a positive page multiple')
    cursor = max(0x10000, (site + 5 - (1 << 31) + 4095) & ~4095)
    limit = min(0x7fffffffffff, site + (1 << 31) - 4096)
    for start,end in sorted(ranges):
        if end <= cursor:
            continue
        if start >= cursor + size and cursor + size <= limit:
            return cursor
        cursor = max(cursor,(end+4095)&~4095)
        if cursor+size > limit:
            break
    if cursor+size <= limit:
        return cursor
    raise BackendError('No free page in signed jump range')


class Backend:
    def __init__(self, profile: Profile = UNEPIC, timeout: float = 4.0):
        self.profile = profile
        self.timeout = timeout
        self.identity: ProcessIdentity | None = None
        self._gdb = None
        self._token = 0
        self._running = False
        self._stop_count = 0
        self._last_stop = {}
        self.unsafe = False
        self.active_patches: dict[int, bytes] = {}

    def _check(self):
        if self.identity is None or not is_current(self.identity):
            raise BackendError('Target process exited or its identity changed')
        if self._gdb is None:
            raise BackendError('GDB is disconnected')

    def _observe(self, responses):
        for response in responses:
            if response['type'] == 'notify':
                if response['message'] == 'running':
                    self._running = True
                elif response['message'] == 'stopped':
                    self._running = False
                    self._stop_count += 1
                    self._last_stop = response.get('payload') or {}
                elif response['message'] == 'thread-group-exited':
                    self._running = False

    def _command(self, command: str):
        if self._gdb is None:
            raise BackendError('GDB is disconnected')
        self._token += 1
        token = self._token
        try:
            self._gdb.write(f'{token}{command}', read_response=False)
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                responses = self._gdb.get_gdb_response(timeout_sec=0.05,
                                                      raise_error_on_timeout=False)
                self._observe(responses)
                for response in responses:
                    if response['type'] == 'result' and response.get('token') == token:
                        if response['message'] == 'error':
                            raise BackendError((response.get('payload') or {}).get('msg','GDB error'))
                        return response.get('payload') or {}
            raise BackendError(f'GDB timeout: {command.split()[0]}')
        except BackendError:
            raise
        except Exception as error:
            raise BackendError(f'GDB transport: {error}') from error

    def _wait_stopped(self, after: int | None = None):
        deadline = time.monotonic() + self.timeout
        while self._running or (after is not None and self._stop_count <= after):
            if time.monotonic() >= deadline:
                raise BackendError('GDB timeout waiting for stopped process')
            responses = self._gdb.get_gdb_response(timeout_sec=0.05,
                                                  raise_error_on_timeout=False)
            self._observe(responses)
            self._check()

    def attach(self, identity: ProcessIdentity):
        if self._gdb is not None:
            raise BackendError('Already connected')
        if not validate_target(identity, self.profile):
            raise BackendError('Unsupported build or changed process')
        try:
            self._gdb = GdbController(
                command=gdb_launch_command(),
                time_to_check_for_additional_output_sec=0.005)
            self.identity = identity
            for setting in ('pagination off', 'confirm off', 'mi-async on',
                            'non-stop off', 'debuginfod enabled off'):
                self._command('-gdb-set ' + setting)
            self._running = True
            self._command(f'-target-attach {identity.pid}')
            self._wait_stopped()
            self._check()
            self.resume()
        except Exception as error:
            if self._gdb is not None:
                self._gdb.exit()
            self._gdb = None
            self.identity = None
            if isinstance(error, BackendError):
                raise
            raise BackendError(str(error)) from error

    def pause(self):
        self._check()
        if self._running:
            before = self._stop_count
            self._command('-exec-interrupt --all')
            self._wait_stopped(before)

    def resume(self):
        self._check()
        if self.unsafe:
            raise BackendError('Recovery required; target left stopped')
        if not self._running:
            self._running = True
            self._command('-exec-continue --all')

    @contextmanager
    def stopped(self):
        self._check()
        was_running = self._running
        self.pause()
        try:
            yield self
        finally:
            if was_running and not self.unsafe and self.identity and is_current(self.identity):
                self.resume()

    def _require_stopped(self):
        self._check()
        if self._running:
            raise BackendError('Memory operation requires stopped process')

    @contextmanager
    def live(self):
        """Read a running target without GDB round trips or stop/resume."""
        self._check()
        if self.unsafe:
            raise BackendError('Recovery required; target left stopped')
        try:
            fd = os.open(f'/proc/{self.identity.pid}/mem',os.O_RDONLY | os.O_CLOEXEC)
        except OSError as error:
            raise LiveReadUnavailable('Live memory access unavailable; use Refresh for manual readings. '
                                      + str(error)) from error
        memory = _LiveMemory(self.profile,fd)
        try:
            self._check()
            yield memory
            self._check()
        finally:
            memory.close()

    def read(self, address: int, size: int) -> bytes:
        self._require_stopped()
        if address <= 0 or size <= 0 or size > 1024 * 1024:
            raise BackendError('Invalid memory range')
        payload = self._command(f'-data-read-memory-bytes {address:#x} {size}')
        chunks = payload.get('memory', [])
        try:
            # GDB may return several blocks; require exact contiguous coverage.
            cursor = address
            result = bytearray()
            for chunk in chunks:
                if int(chunk['begin'],16) != cursor:
                    raise BackendError('Noncontiguous memory response')
                data = bytes.fromhex(chunk['contents'])
                result.extend(data)
                cursor += len(data)
            if len(result) != size:
                raise BackendError('Incomplete memory response')
            return bytes(result)
        except (KeyError, ValueError) as error:
            raise BackendError('Invalid memory response') from error

    def write(self, address: int, data: bytes):
        self._require_stopped()
        if address <= 0 or not data or len(data) > 1024 * 1024:
            raise BackendError('Invalid memory write')
        self._command(f'-data-write-memory-bytes {address:#x} {data.hex()}')
        if self.read(address,len(data)) != data:
            raise BackendError('Memory write verification failed')

    def evaluate(self, expression: str) -> int:
        self._require_stopped()
        if expression == '$eflags':
            # GDB exposes x86 flags as a flags type, which rejects integer
            # casts. MI's hexadecimal register read avoids expression casts.
            names = self._command('-data-list-register-names').get('register-names',[])
            try:
                number = names.index('eflags')
            except ValueError as error:
                raise BackendError('GDB target has no eflags register') from error
            payload = self._command(f'-data-list-register-values x {number}')
            try:
                registers = payload['register-values']
                value = next(r['value'] for r in registers if int(r['number']) == number)
                return int(value,16)
            except (KeyError, ValueError, TypeError, StopIteration) as error:
                raise BackendError('Invalid flags register response') from error
        payload = self._command('-data-evaluate-expression ' +
                                json.dumps(f'(unsigned long long)({expression})'))
        try:
            return int(payload['value'].split()[0],0)
        except (KeyError, ValueError) as error:
            raise BackendError('Invalid expression response') from error

    def set_register(self, name: str, value: int):
        self._require_stopped()
        if name not in ('rax','rdi','rsi','rdx','r10','r8','r9','rcx','r11',
                        'rip','eflags','orig_rax'):
            raise BackendError('Unsupported register')
        self._command('-data-evaluate-expression ' + json.dumps(f'${name} = {value:#x}'))

    def instruction_pointers(self) -> list[int]:
        self._require_stopped()
        threads = self._command('-thread-info').get('threads',[])
        addresses = []
        for thread in threads:
            if thread.get('state') != 'stopped' or 'frame' not in thread:
                raise BackendError('Cannot verify all thread instruction pointers')
            addresses.append(int(thread['frame']['addr'],16))
        if not addresses:
            raise BackendError('No stopped threads')
        return addresses

    def remote_syscall(self, number: int, arguments: tuple[int, ...]) -> int:
        """Linux x86-64 mmap syscall on one thread; restore code and registers.

        Other threads remain stopped via scheduler-locking. No inferior libc
        call is made, avoiding allocation while a libc lock could be held.
        """
        self._require_stopped()
        if number != 9 or len(arguments) != 6:
            raise BackendError('Only the six-argument mmap syscall is supported')
        names = ('rax','rdi','rsi','rdx','r10','r8','r9','rcx','r11','rip','eflags','orig_rax')
        saved = {name:self.evaluate('$'+name) for name in names}
        site = saved['rip']
        ips = self.instruction_pointers()
        if site not in ips:
            raise BackendError('Cannot verify the selected thread instruction pointer')

        def overlaps_patch(address, size):
            return any(address < start+len(data) and start < address+size
                       for start,data in self.active_patches.items())

        if sum(site <= ip < site+3 for ip in ips) != 1 or overlaps_patch(site,3):
            # Waiting threads can share the same libc PC. Redirect only the
            # selected thread to a verified, unoccupied game instruction while
            # scheduler-locking keeps every other thread stopped. Restore this
            # instruction and the saved RIP before normal execution resumes.
            candidates = ((self.profile.damage_store,self.profile.original),
                (self.profile.energy_store,bytes.fromhex('f30f118308060000')),
                (self.profile.energy_regen_store,bytes.fromhex('f30f118708060000')),
                (self.profile.energy_cap_store,bytes.fromhex('f30f118f08060000')),
                (self.profile.progression_store,self.profile.progression_original))
            for candidate, expected in candidates:
                size = len(expected)
                if any(candidate <= ip < candidate+size for ip in ips) or overlaps_patch(candidate,size):
                    continue
                try:
                    observed = self.read(candidate,size)
                except BackendError:
                    continue
                if observed == expected:
                    site = candidate
                    break
            else:
                raise BackendError('Another thread or patch occupies syscall stub range, '
                                   'or instruction bytes mismatch; no safe fallback available')
        original = self.read(site,3)
        locking = self._command('-gdb-show scheduler-locking').get('value')
        if locking not in ('off','on','step','replay'):
            raise BackendError('Unknown scheduler-locking state')
        self.active_patches[site] = original
        self.unsafe = True
        unexpected_stop = False
        try:
            self.write(site,bytes.fromhex('0f05cc'))  # syscall; int3
            self._command('-gdb-set scheduler-locking on')
            self.set_register('orig_rax',0xffffffffffffffff)
            self.set_register('rax',number)
            for name,value in zip(('rdi','rsi','rdx','r10','r8','r9'),arguments):
                self.set_register(name,value & 0xffffffffffffffff)
            self.set_register('rip',site)
            before = self._stop_count
            self._running = True
            self._command('-exec-continue')
            self._wait_stopped(before)
            if self._last_stop.get('signal-name') != 'SIGTRAP' or self.evaluate('$rip') != site+3:
                unexpected_stop = True
                raise BackendError('Unexpected syscall stop; target remains stopped for recovery')
            result = self.evaluate('$rax')
        finally:
            try:
                if self._running:
                    self.pause()
                self.write(site,original)
                for name,value in saved.items():
                    self.set_register(name,value)
                self._command('-gdb-set scheduler-locking ' + locking)
                self.active_patches.pop(site,None)
                self.unsafe = unexpected_stop
            except Exception as recovery:
                self.unsafe = True
                raise BackendError(f'Syscall recovery failed; target remains stopped: {recovery}') from recovery
        if result >= 0xfffffffffffff001:
            errno = (1 << 64) - result
            raise BackendError(f'Target mmap failed (errno {errno})')
        return result

    def allocate_near(self, site: int, size: int) -> int:
        self._require_stopped()
        ranges = []
        for line in (Path('/proc')/str(self.identity.pid)/'maps').read_text().splitlines():
            start,end = line.split()[0].split('-')
            ranges.append((int(start,16),int(end,16)))
        candidate = find_near_gap(site,ranges,size)
        # MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE; never replace a map.
        result = self.remote_syscall(9,(candidate,size,7,0x100022,-1,0))
        if result != candidate:
            raise BackendError('mmap returned an unexpected address; hook not installed')
        return result

    def detach(self):
        if self._gdb is None:
            return
        current = self.identity and is_current(self.identity)
        if current:
            if self.active_patches or self.unsafe:
                raise BackendError('Restore active patches before detaching')
            self.pause()
            self._command('-target-detach')
        self._gdb.exit()
        self._gdb = None
        self.identity = None
        self._running = False
