Markdown

# m-internals 

**Zero-dependency, VFS-native kernel state observability suite.**

When a production microservice freezes, logs are useless. Standard engineers run `top` and guess. `m-internals` parses the Virtual File System (`/proc`) to mathematically prove *why* a process is blocked, mapping the exact kernel wait channel (`wchan`) to its structural root cause.

No agents. No daemons. No compilation. 100% Bash/Python native execution. Built for bare-metal, Alpine, and distroless environments.

## The Arsenal

`m-internals` operates on a Master/Subsystem architecture. You execute the master router (`mi-hunt`), and it dynamically hands execution (`exec`) to the correct diagnostic engine based on the target's kernel state.

| Subsystem | Trigger State (`wchan`) | Failure Domain |
|---|---|---|
| `pipe_hunter` | `pipe_wait`, `anon_pipe_read` | IPC deadlocks, Ghost Readers, buffer exhaustion. |
| `toxic_hunter` | `hrtimer_nanosleep`, `do_nanosleep` | Micro-sleep thrashing, CPU cache pollution. |
| `do_wait_hunter` | `do_wait`, `wait_consider_task` | Parent/child lifecycles, unreaped zombies, async stalls. |
| `futex_hunter` | `futex_wait_queue_me`, `futex_do_wait` | Multi-thread memory locks, contention hotspots. |
| `sk_hunter` | `sk_data_wait`, `poll_schedule_timeout*` | TCP buffer starvation, event-loop blocking. |

## Installation

`m-internals` is 100% transparent text. No compiled blobs. Audit the code yourself in 60 seconds. Choose your preferred installation path below:

### Option A: User-Level (Zero Sudo Required - Recommended)
Installs safely into your user's local path without requiring root privileges.

```bash
git clone [https://github.com/TshepoMoholoholo/m-internals.git](https://github.com/TshepoMoholoholo/m-internals.git)
cd m-internals
chmod +x *hunter mi-hunt

# Ensure ~/.local/bin exists and is in your PATH
mkdir -p ~/.local/bin
ln -s "$(pwd)/mi-hunt" ~/.local/bin/mi-hunt
ln -s "$(pwd)/pipe_hunter" ~/.local/bin/pipe_hunter
ln -s "$(pwd)/toxic_hunter" ~/.local/bin/toxic_hunter
ln -s "$(pwd)/do_wait_hunter.py" ~/.local/bin/do_wait_hunter
ln -s "$(pwd)/futex_hunter" ~/.local/bin/futex_hunter
ln -s "$(pwd)/sk_hunter" ~/.local/bin/sk_hunter
hash -r

Option B: System-Wide (Requires Root)

For global deployment across all user accounts on the server.
Bash

git clone [https://github.com/TshepoMoholoholo/m-internals.git](https://github.com/TshepoMoholoholo/m-internals.git)
cd m-internals
chmod +x *hunter mi-hunt

sudo ln -s "$(pwd)/mi-hunt" /usr/local/bin/mi-hunt
sudo ln -s "$(pwd)/pipe_hunter" /usr/local/bin/pipe_hunter
sudo ln -s "$(pwd)/toxic_hunter" /usr/local/bin/toxic_hunter
sudo ln -s "$(pwd)/do_wait_hunter.py" /usr/local/bin/do_wait_hunter
sudo ln -s "$(pwd)/futex_hunter" /usr/local/bin/futex_hunter
sudo ln -s "$(pwd)/sk_hunter" /usr/local/bin/sk_hunter
hash -r

Usage: Target the Victim

Operational Rule: Always point the router at the Victim (the process that is actively frozen/complaining), not the Suspect.
Bash

mi-hunt <PID>

Example: Identifying a Futex Deadlock
Plaintext

$ mi-hunt 179544
m-internals :: futex_hunter
Target : 179544 (contention)    | Parent: 147208
State  : S                      | Total Threads : 1002

▼ FUTEX CONTENTION TOPOLOGY [Primary: 0x403080]
  │
  ├─ Contention Map
  │  ├─ [0x7fdc88e8fce8] : 1 thread(s) blocked
  │  └─ [0x403080] : 1000 thread(s) blocked [HOTSPOT]
  │
  └─ Lock Holder Isolation (Task Elimination)
     ├─ Holder TID   : 179545
     ├─ Holder Name  : contention
     ├─ Wait Channel : wait_woken
     └─ Target State : Interactive I/O (stdin / terminal read)

[!] DIAGNOSIS: DEADLOCK / CRITICAL SECTION STALL
    Software Bug: Blocking read executed inside locked critical section.
    1000 thread(s) starved waiting on uaddr 0x403080.

Architectural Limitations (The Edge of User-Space)

This tool maps structural state by polling /proc. It is bound by the physical limits of user-space polling:

    Uninterruptible Sleep (D State): Processes trapped in hardware/disk locks (blk_update_request, xfs_log_force) cannot be safely profiled via /proc loops without risking terminal hangs.

    Microsecond I/O: Block I/O operations happen too fast for 1-second polling loops to catch reliably.

To trace D state locks and microsecond latency, event-driven kernel tracing (eBPF) is required. m-internals handles the other 90% of user-space execution and concurrency failures.
Core Philosophy

    The Rule of Silence: The master router (mi-hunt) is completely invisible. It reads the state and uses exec to instantly replace itself with the target subsystem, ensuring zero memory bloat.

    Structural Proof over Heuristics: We do not guess based on CPU utilization. We map file descriptors (fd), wait channels (wchan), and process topology (stat) to prove the execution path mathematically.

    Immutability: Designed to run in read-only environments. m-internals modifies nothing.
