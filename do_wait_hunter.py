#!/usr/bin/env python3
"""
================================================================================
SRE NATIVE DIAGNOSTIC TOOLKIT: do_wait_hunter.py (v2.2)
================================================================================
Philosophy : Zero external dependencies, zero sub-processes, 100% /proc parsing.
Purpose    : Production root-cause analysis for process hangs, parent-child
             lifecycles (do_wait), IPC pipe deadlocks, and futex thread locks.
Targets    : Distroless containers, Alpine, minimal Linux hosts.
Branding   : m-internals UI standard.
================================================================================
"""

import os
import sys
import glob
import time
from datetime import datetime

def check_proc_exists(pid):
    """Verifies if the target PID exists in the local namespace."""
    return os.path.exists(f"/proc/{pid}")

def get_ppid(pid):
    """Extracts the Parent PID (PPID) from /proc/$PID/stat."""
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            content = f.read()
            rpar_idx = content.rfind(')')
            if rpar_idx != -1:
                fields = content[rpar_idx + 2:].split()
                return int(fields[1])
    except Exception:
        return 0
    return 0

def get_process_name(pid):
    """Retrieves the executable comm name for a PID."""
    try:
        with open(f"/proc/{pid}/comm", "r") as f:
            return f.read().strip()
    except Exception:
        return "unknown"

def get_process_start_time(pid):
    """
    Extracts process creation timestamp from /proc/$PID mtime.
    Avoids clock-tick (USER_HZ) calculations by inspecting the inode mtime.
    """
    try:
        stat_info = os.stat(f"/proc/{pid}")
        return datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return "Unknown"

def parse_stat(pid):
    """Extracts State and WCHAN from /proc/$PID/stat and /proc/$PID/wchan."""
    state = "UNKNOWN"
    wchan = "unknown"
    
    # 1. Read State from /proc/$PID/stat
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            content = f.read()
            rpar_idx = content.rfind(')')
            if rpar_idx != -1:
                fields = content[rpar_idx + 2:].split()
                state = fields[0]
    except Exception:
        pass

    # 2. Read WCHAN kernel function symbol
    try:
        with open(f"/proc/{pid}/wchan", "r") as f:
            wchan = f.read().strip()
    except Exception:
        pass

    return state, wchan

def parse_pending_signals(pid):
    """Checks SigPnd from /proc/$PID/status for queued, unhandled signals."""
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("SigPnd:"):
                    sig_hex = line.split()[1].strip()
                    sig_int = int(sig_hex, 16)
                    if sig_int != 0:
                        return f"0x{sig_hex} (Active)"
                    return "None"
    except Exception:
        pass
    return "Unknown"

def count_worker_threads(pid):
    """Scans /proc/$PID/task/ to count additional threads in the process group."""
    try:
        tasks = os.listdir(f"/proc/{pid}/task")
        count = len(tasks) - 1
        return count if count >= 0 else 0
    except Exception:
        return 0

def find_open_pipes(pid):
    """Scans /proc/$PID/fd/ to identify open IPC pipe descriptors."""
    pipes = []
    fd_dir = f"/proc/{pid}/fd"
    try:
        for fd in os.listdir(fd_dir):
            fd_path = os.path.join(fd_dir, fd)
            try:
                target = os.readlink(fd_path)
                if "pipe:" in target or "fifo:" in target:
                    pipes.append((fd, target))
            except Exception:
                continue
    except Exception:
        pass
    return pipes

def find_child_processes(parent_pid):
    """Identifies direct child processes by checking PPID in /proc/[0-9]*/stat."""
    children = []
    for proc_path in glob.glob("/proc/[0-9]*"):
        try:
            pid = os.path.basename(proc_path)
            with open(f"{proc_path}/stat", "r") as f:
                content = f.read()
                rpar_idx = content.rfind(')')
                if rpar_idx != -1:
                    fields = content[rpar_idx + 2:].split()
                    ppid = int(fields[1])
                    if ppid == parent_pid:
                        children.append(int(pid))
        except Exception:
            continue
    return sorted(children)

def interpret_wchan(state, wchan):
    """Decoupled state/wchan matrix supporting truncated kernel symbols."""
    state = state.upper()
    wchan = wchan.lower() if wchan else ""

    if state == 'R': return "SPINNING"
    if state == 'Z': return "ZOMBIE"
    if state == 'T': return "STOPPED"
    if state == 'D': return "UNINTERRUPTIBLE"

    if "do_wait" in wchan: return "WAITING"
    elif "pipe" in wchan or "fifo" in wchan: return "PIPE_BLOCKED"
    elif "futex" in wchan: return "LOCKED"
    elif "nanosleep" in wchan or "poll" in wchan or "epoll" in wchan: return "SLEEPING"
    elif state == 'S': return "SLEEPING"

    return "UNKNOWN"

def analyze_process(pid):
    """Main diagnostic routine formatted for m-internals."""
    if not check_proc_exists(pid):
        print(f"[-] Error: PID {pid} does not exist.")
        sys.exit(1)

    comm = get_process_name(pid)
    ppid = get_ppid(pid)
    start_time = get_process_start_time(pid)
    parent_state, parent_wchan = parse_stat(pid)
    pending_signals = parse_pending_signals(pid)
    worker_threads = count_worker_threads(pid)
    pipes = find_open_pipes(pid)
    children = find_child_processes(pid)

    # m-internals Header
    print(f"m-internals :: do_wait_hunter")
    print(f"Target : {pid} ({comm}) | Parent: {ppid}")
    print(f"State  : {parent_state} | Wchan : {parent_wchan}")
    print("")

    # Topology Tree
    print(f"▼ PROCESS TOPOLOGY [Target: {pid}]")
    print(f"  │")
    print(f"  ├─ Start Time : {start_time}")
    print(f"  ├─ Signals    : {pending_signals}")
    print(f"  ├─ Threads    : {worker_threads}")
    print(f"  └─ Open Pipes : {len(pipes)}")
    if pipes:
        for i, (fd, target) in enumerate(pipes):
            prefix = "     └─" if i == len(pipes) - 1 else "     ├─"
            print(f"{prefix} FD {fd} -> {target}")

    print("")
    
    # Child Tree
    print(f"▼ CHILD WORKER DYNAMICS ({len(children)} found)")
    if not children:
        print(f"  └─ No direct child processes found.")
    else:
        print(f"  │")
        for i, child_pid in enumerate(children):
            c_comm = get_process_name(child_pid)
            c_state, c_wchan = parse_stat(child_pid)
            c_interp = interpret_wchan(c_state, c_wchan)
            prefix = "  └─" if i == len(children) - 1 else "  ├─"
            print(f"{prefix} [{child_pid}] {c_comm} | State: {c_state} | Wchan: {c_wchan} [{c_interp}]")

    print("")

    # Diagnostic Rule Engine Engine (Promoted Zombie Check)
    zombies = []
    spinning = []
    sleeping = []
    locked = []

    for child_pid in children:
        c_state, c_wchan = parse_stat(child_pid)
        if c_state == 'Z':
            zombies.append(child_pid)
        elif c_state == 'R':
            spinning.append(child_pid)
        elif "futex" in c_wchan.lower():
            locked.append(child_pid)
        else:
            sleeping.append(child_pid)

    if zombies:
        print(f"[!] DIAGNOSIS: UNREAPED ZOMBIE CHILDREN")
        print(f"    Reason: Target is in state [{parent_state}] ({parent_wchan}) and is NOT reaping its children.")
        print(f"    Child {zombies} terminated but remains in the process table. Target's signal handler (SIGCHLD) is missing or blocked.")
    elif "do_wait" in parent_wchan:
        if not children:
            print(f"[!] DIAGNOSIS: ORPHANED WAIT STATE")
            print(f"    Reason: Target is blocked in do_wait, but no children exist. Child exited rapidly or reparented.")
        elif spinning:
            print(f"[!] DIAGNOSIS: CPU SPIN DEADLOCK")
            print(f"    Reason: Target waiting cleanly, but Child {spinning} is burning CPU in an infinite loop (State 'R').")
        elif locked:
            print(f"[!] DIAGNOSIS: MULTI-THREAD FUTEX DEADLOCK")
            print(f"    Reason: Target waiting cleanly, but Child {locked} is trapped on a mutex lock.")
        elif sleeping:
            print(f"[!] DIAGNOSIS: CASCADING SLEEP HANG")
            print(f"    Reason: Target waiting cleanly. Child {sleeping} is blocked on {parse_stat(sleeping[0])[1]}. Investigate child.")
    elif "futex" in parent_wchan.lower():
        print(f"[!] DIAGNOSIS: PARENT FUTEX DEADLOCK")
        print(f"    Reason: Target PID {pid} is deadlocked internally on a multi-threaded mutex.")
    elif parent_state == 'R':
        print(f"[!] DIAGNOSIS: CPU SPIN (USER-SPACE)")
        print(f"    Reason: Target PID {pid} is burning CPU in user-space (State 'R'). Profile execution loop.")
    else:
        print(f"[!] DIAGNOSIS: ASYNCHRONOUS STALL")
        print(f"    Reason: Target process is in state [{parent_state}] | Wchan: [{parent_wchan}]. Evaluate downstream dependencies.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 do_wait_hunter.py <PID>")
        sys.exit(1)

    target_pid = int(sys.argv[1])
    analyze_process(target_pid)
