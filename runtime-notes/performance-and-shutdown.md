# Periodic polling and application shutdown

## Report and reproduction

The user reported short game freezes once or twice per second, followed by a disappearing trainer window whose process remained alive. Ctrl-C did not stop that process; Ctrl-\ was needed. Both reports concern the actual game. The host's precise hidden-window shutdown condition has not been independently observed.

The old one-second timer entered an all-stop context. It read every room object through a separate GDB command and rescanned the full room during ENERGY refill and its return snapshot. A controlled room with 100 objects made 332 reads. Modeling the controller's 5 ms additional-response window per read produced 1.764 seconds spent in the stopped polling path. Nested stopped contexts share the same outer stop; their count does not represent independent physical interrupts. This controlled measurement is not an actual Unepic timing trace.

CLI subprocess tests reproduced Ctrl-C failing to terminate or throwing KeyboardInterrupt into a Qt callback without quitting. SIGTERM previously killed the process directly. Default no-game window closing already exited successfully; disabling implicit last-window quitting reproduced a hidden window with a surviving event loop. This demonstrates the prior dependence on implicit Qt policy, not the host's exact policy setting.

## Correction

Automatic polling opens `/proc/PID/mem` read-only and uses positioned reads without debugger commands or target interrupts. The descriptor is closed on success and errors; PID/executable identity is checked around the view. Character and room pointer changes invalidate the sample; a read/validation failure is retried once. Samples are for display only. All memory changes still use fresh all-stop validation through the original backend.

When the host denies live access, the application reports manual readings only. Connect, explicit Refresh and user actions may obtain one stopped snapshot, while the periodic timer never falls back to stop/resume. Access permissions and ptrace policy are unchanged. Linux documents the access check in [proc_pid_mem(5)](https://man7.org/linux/man-pages/man5/proc_pid_mem.5.html).

The polling path no longer calls ENERGY refill. Activation fills the resource, and existing dynamic ENERGY trampolines enforce the current cap on spending, regeneration and cap stores. Replacement pets are protected on their next ENERGY update.

Window close and SIGINT/SIGTERM request normal worker shutdown. A main-thread Python timer services pending signals. The worker restores hooks and detaches before the window emits shutdown completion; the main loop quits explicitly and waits for the completed thread. Failed recovery leaves the window/worker alive and a later close or signal retries. No forced application exit bypasses restoration. Qt's thread lifecycle is documented in [QThread](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html).

## Checks and limits

Full suite: **376 passed, 5 skipped**, all skips existing real-GDB ptrace refusals. Live reading of an owned native fixture passes in this sandbox: the fixture executes damage and energy commands while its live view is open, readings change accordingly, and no GDB commands are sent.

Regressions cover periodic reads with ENERGY on/off and zero stops/writes, denied access followed by manual refresh, transition retry, read-only views, identity expiry, invalid/incomplete ranges and descriptor cleanup. Actual Qt main-loop subprocess tests cover normal/demo closing, SIGINT/SIGTERM, closing when implicit Qt quitting is disabled, reaping a real GDB child, terminal process-group SIGINT and cleanup rejection followed by successful retry.

The new 100-object controlled local-view poll took about 6 ms with 118 reads, zero target stops and zero writes. Its in-memory adapter measurement illustrates the removed round trips; it is not a host performance guarantee.

2026-10-09 host follow-up: the user reports "everything works now" (translated from Bulgarian), following the correction of both reported problems. Record periodic stalls and lingering-process behavior as resolved in the reported session. No timings, process listing, terminal output or separate toggle/close/Ctrl-C results were supplied.

Detailed coverage remains open: recall/resummon and room transitions, each shutdown path with all hooks active, ordinary damage/spending after detaching, and save/load. The general confirmation does not individually establish these cases. Previously force-killed trainer processes contain old code and are not upgraded in place.
