import socket
import threading
import queue
import re
import csv
from collections import defaultdict, deque
import time

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np

# ---------- CONFIG: match ESP32 settings ----------
ULTRA_PERIOD = 200    # ms
SOUND_PERIOD = 2000   # ms

period_map = {
    "Ultra": ULTRA_PERIOD,
    "Sound": SOUND_PERIOD,
}

# scale used to normalize tardiness into utility
scale_map = {
    "Ultra": ULTRA_PERIOD,
    "Sound": SOUND_PERIOD,
    "PIR":   50,      # relative deadline in firmware
    "Button": 50,
}

# M2M Traffic Classification (Industrial IoT)
delay_sensitive_tasks = ["PIR", "Button", "Ultra"]  # Emergency/safety-critical
delay_tolerant_tasks = ["Sound"]  # Monitoring/diagnostics

# ---------- Queues & storage ----------

line_queue = queue.Queue()

# Completed job records (one dict per finished job)
jobs = []

# Partial data (we see EDF first, DONE later)
job_partial = {}

# Per-task time series
waiting_times   = defaultdict(list)
waiting_times_t = defaultdict(list)

tardiness_vals   = defaultdict(list)
tardiness_vals_t = defaultdict(list)

frame_delay_vals   = defaultdict(list)   # only for periodic tasks
frame_delay_vals_t = defaultdict(list)

utility_vals   = defaultdict(list)       # per-task utility
utility_vals_t = defaultdict(list)

miss_rate_t = []
miss_rate_v = []

# Global utility average
global_util_t = []
global_util_v = []

# Response time tracking
resp_time_vals = defaultdict(list)
resp_time_vals_t = defaultdict(list)

# Task-specific statistics for summary
task_stats = defaultdict(lambda: {
    'jobs': 0,
    'misses': 0,
    'total_waiting': 0.0,
    'total_tardiness': 0.0,
    'total_resp_time': 0.0,
    'total_utility': 0.0,
    'max_waiting': 0.0,
    'max_tardiness': 0.0,
    'max_resp_time': 0.0
})

# Session start time
session_start_time = time.time()

# CSV
csv_filename = "edf_results.csv"
csv_header_written = False
csv_lock = threading.Lock()

# Regex patterns
edf_re  = re.compile(r"EDF name=(\w+) job=(\d+) rel=(\d+) start=(\d+) dl=(\d+)")
done_re = re.compile(r"DONE name=(\w+) job=(\d+) end=(\d+) val=(\d+)")

# Debug: Track received messages per task
task_message_count = defaultdict(int)

# ---------- CSV helper ----------

def write_csv_row(row):
    global csv_header_written
    with csv_lock:
        write_header = not csv_header_written
        with open(csv_filename, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=row.keys())
            if write_header:
                w.writeheader()
                csv_header_written = True
            w.writerow(row)

# ---------- TCP server ----------

def tcp_server(host="0.0.0.0", port=5000):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(1)
    print(f"[SERVER] Listening on {host}:{port}")

    conn, addr = s.accept()
    print(f"[SERVER] Connected by {addr}")

    buf = ""
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                print("[SERVER] Connection closed.")
                break
            buf += data.decode("utf-8", errors="ignore")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line_queue.put(line.strip())
    except Exception as e:
        print("[SERVER] Error:", e)
    finally:
        conn.close()
        s.close()

server_thread = threading.Thread(target=tcp_server, daemon=True)
server_thread.start()

# ---------- Metrics helpers ----------

def recompute_global_miss_rate():
    if not jobs:
        return 0.0
    misses = sum(1 for j in jobs if j["tardiness"] > 0)
    return misses / len(jobs)

def calculate_utility(tardiness, scale, utility_type='soft'):
    """Calculate utility based on different real-time models."""
    if utility_type == 'hard':
        # Hard real-time: utility drops to 0 if deadline missed
        return 1.0 if tardiness <= 0 else 0.0
    elif utility_type == 'soft':
        # Soft real-time: linear degradation after deadline
        if tardiness <= 0:
            return 1.0
        else:
            return max(0.0, 1.0 - tardiness / scale)
    elif utility_type == 'firm':
        # Firm real-time: similar to hard but occasional misses acceptable
        if tardiness <= 0:
            return 1.0
        elif tardiness < scale * 0.2:  # Within 20% tolerance
            return 0.5
        else:
            return 0.0
    else:
        return 1.0 if tardiness <= 0 else 0.0

_last_summary_job_count = 0

def print_task_summary():
    """Print per-task summary stats to the console."""
    global _last_summary_job_count
    if len(jobs) == _last_summary_job_count:
        return  # nothing new
    _last_summary_job_count = len(jobs)

    print("\n" + "="*60)
    print(f"  EDF REAL-TIME PERFORMANCE SUMMARY ({len(jobs)} jobs)")
    print("="*60)
    
    # Show task activity status
    print("\n🔄 TASK ACTIVITY STATUS:")
    for task in ["Ultra", "PIR", "Sound", "Button"]:
        count = task_message_count.get(task, 0)
        status = "✅ ACTIVE" if count > 0 else "⚠️  WAITING"
        task_type = "(Periodic)" if task in ["Ultra", "Sound"] else "(Event-Driven)"
        print(f"   {task:8s} {task_type:15s}: {status:12s} - {count} messages received")
    
    if task_message_count.get("Button", 0) == 0:
        print("\n💡 TIP: Button is event-driven. Press the physical button on ESP32 to see data!")
    
    task_names = sorted({j["name"] for j in jobs})
    
    for name in task_names:
        js = [j for j in jobs if j["name"] == name]
        n  = len(js)
        if n == 0:
            continue

        stats = task_stats[name]
        
        waits   = [j["waiting"] for j in js]
        tards   = [j["tardiness"] for j in js]
        resps   = [j["resp_time"] for j in js]
        util    = [j["utility"] for j in js]
        misses  = sum(1 for j in js if j["tardiness"] > 0)

        avg_wait = sum(waits) / n
        max_wait = max(waits)

        avg_tard = sum(tards) / n
        max_tard = max(tards)

        avg_resp = sum(resps) / n
        max_resp = max(resps)

        avg_util = sum(util) / n
        miss_rate = misses / n
        
        # Classify task type
        task_type = "Delay-Sensitive" if name in delay_sensitive_tasks else "Delay-Tolerant"

        print(f"\n📊 Task: {name} ({task_type})")
        print(f"   Jobs Completed : {n}")
        print(f"   Deadline Misses: {misses}  (miss rate = {miss_rate*100:.1f}%)")
        print(f"   Waiting Time   : avg {avg_wait:.2f} ms, max {max_wait:.2f} ms")
        print(f"   Tardiness      : avg {avg_tard:.2f} ms, max {max_tard:.2f} ms")
        print(f"   Response Time  : avg {avg_resp:.2f} ms, max {max_resp:.2f} ms")
        print(f"   Utility        : avg {avg_util:.3f}")
    
    # Global statistics
    if jobs:
        global_miss_rate = recompute_global_miss_rate()
        global_avg_util = sum(j["utility"] for j in jobs) / len(jobs)
        global_avg_resp = sum(j["resp_time"] for j in jobs) / len(jobs)
        
        print("\n" + "-"*60)
        print(f"🌐 GLOBAL METRICS")
        print(f"   Total Jobs        : {len(jobs)}")
        print(f"   Global Miss Rate  : {global_miss_rate*100:.1f}%")
        print(f"   Global Avg Utility: {global_avg_util:.3f}")
        print(f"   Global Avg Resp   : {global_avg_resp:.2f} ms")
        
        # Session duration
        elapsed = time.time() - session_start_time
        print(f"   Session Duration  : {elapsed:.1f} seconds")
    
    print("="*60 + "\n")

# ---------- Matplotlib live plots ----------

plt.style.use("seaborn-v0_8-darkgrid")

# Create comprehensive dashboard with multiple subplots
fig = plt.figure(figsize=(20, 13))
gs = fig.add_gridspec(4, 3, hspace=0.4, wspace=0.35, top=0.96, bottom=0.05, left=0.06, right=0.98)

# Row 1: Main metrics
ax_resp = fig.add_subplot(gs[0, 0])      # Response time
ax_wait = fig.add_subplot(gs[0, 1])      # Waiting time
ax_tard = fig.add_subplot(gs[0, 2])      # Tardiness

# Row 2: Advanced metrics
ax_util = fig.add_subplot(gs[1, 0])      # Utility curves
ax_frame = fig.add_subplot(gs[1, 1])     # Frame delay (periodic)
ax_miss = fig.add_subplot(gs[1, 2])      # Miss rate

# Row 3: Distribution analysis
ax_resp_dist = fig.add_subplot(gs[2, 0]) # Response time distribution
ax_util_box = fig.add_subplot(gs[2, 1])  # Utility box plots
ax_latency = fig.add_subplot(gs[2, 2])   # M2M latency classification

# Row 4: Timeline and statistics
ax_timeline = fig.add_subplot(gs[3, :])  # Gantt-style execution timeline

# Enhanced color mapping for tasks (more vibrant and distinct)
task_colors = {
    'Ultra': '#E63946',   # Bright red - high priority ultrasonic
    'PIR': '#06FFA5',     # Bright cyan - motion detection
    'Sound': '#FFB703',   # Golden yellow - monitoring
    'Button': '#FF006E'   # Hot pink - emergency
}

# Symbols for tasks (for scatter plots)
task_symbols = {
    'Ultra': 's',   # square
    'PIR': '^',     # triangle
    'Sound': 'o',   # circle
    'Button': 'D'   # diamond
}

# Symbol sizes
MARKER_SIZE_LINE = 6
MARKER_SIZE_TIMELINE = 200
LINE_WIDTH = 2.0

def update(frame):
    # ---- Drain queue & parse new lines ----
    while True:
        try:
            line = line_queue.get_nowait()
        except queue.Empty:
            break

        if not line:
            continue

        m = edf_re.match(line)
        if m:
            name, job, rel, start, dl = m.groups()
            key = (name, int(job))
            job_partial.setdefault(key, {})
            job_partial[key].update({
                "name":  name,
                "job":   int(job),
                "rel":   int(rel),
                "start": int(start),
                "dl":    int(dl),
            })
            task_message_count[name] += 1
            continue

        m = done_re.match(line)
        if m:
            name, job, end, val = m.groups()
            key = (name, int(job))
            p = job_partial.get(key)
            if not p:
                continue  # missed EDF line, skip
            p["end"] = int(end)
            p["val"] = int(val)

            # Metrics
            rel   = p["rel"]
            start = p["start"]
            dl    = p["dl"]
            end_t = p["end"]

            waiting   = start - rel
            resp_time = end_t - rel
            tard      = max(0, end_t - dl)

            p["waiting"]    = waiting
            p["resp_time"]  = resp_time
            p["tardiness"]  = tard

            # Frame delay (for periodic tasks)
            period = period_map.get(name)
            if period is not None and period > 0:
                frame_delay = waiting / period
            else:
                frame_delay = None
            p["frame_delay"] = frame_delay

            # Utility (soft real-time model)
            scale = scale_map.get(name, None)
            if scale is None or scale <= 0:
                util = 1.0 if tard == 0 else 0.0
            else:
                util = calculate_utility(tard, scale, 'soft')
            p["utility"] = util

            jobs.append(p)

            t_ms = end_t

            # Update task statistics
            stats = task_stats[name]
            stats['jobs'] += 1
            if tard > 0:
                stats['misses'] += 1
            stats['total_waiting'] += waiting
            stats['total_tardiness'] += tard
            stats['total_resp_time'] += resp_time
            stats['total_utility'] += util
            stats['max_waiting'] = max(stats['max_waiting'], waiting)
            stats['max_tardiness'] = max(stats['max_tardiness'], tard)
            stats['max_resp_time'] = max(stats['max_resp_time'], resp_time)

            # time series
            waiting_times[name].append(waiting)
            waiting_times_t[name].append(t_ms)

            tardiness_vals[name].append(tard)
            tardiness_vals_t[name].append(t_ms)
            
            resp_time_vals[name].append(resp_time)
            resp_time_vals_t[name].append(t_ms)

            if frame_delay is not None:
                frame_delay_vals[name].append(frame_delay)
                frame_delay_vals_t[name].append(t_ms)

            utility_vals[name].append(util)
            utility_vals_t[name].append(t_ms)

            # global miss rate
            mr = recompute_global_miss_rate()
            miss_rate_t.append(t_ms)
            miss_rate_v.append(mr)

            # global avg utility
            avg_u = sum(j["utility"] for j in jobs) / len(jobs)
            global_util_t.append(t_ms)
            global_util_v.append(avg_u)

            # CSV
            write_csv_row(p)

            # cleanup
            del job_partial[key]

    # print per-task summary when new jobs arrive
    print_task_summary()

    # ---- Update plots ----
    
    # Clear all axes
    for ax in [ax_resp, ax_wait, ax_tard, ax_util, ax_frame, ax_miss, 
               ax_resp_dist, ax_util_box, ax_latency, ax_timeline]:
        ax.clear()

    # ========== Row 1: Main Timing Metrics ==========
    
    # 1) Response Time over time
    for name, xs in resp_time_vals_t.items():
        ys = resp_time_vals[name]
        if xs:
            ax_resp.plot(xs, ys, marker=task_symbols.get(name, 'o'), 
                        color=task_colors.get(name, 'gray'), 
                        label=name, alpha=0.8, markersize=MARKER_SIZE_LINE, 
                        linewidth=LINE_WIDTH, markeredgecolor='white', markeredgewidth=0.5)
    ax_resp.set_ylabel("Response Time (ms)", fontsize=11, fontweight='bold')
    ax_resp.set_title("Response Time: Release → Completion", fontsize=12, fontweight='bold', pad=10)
    ax_resp.legend(loc="upper left", fontsize=9, framealpha=0.95, edgecolor='black')
    ax_resp.grid(True, alpha=0.4, linestyle='--', linewidth=0.7)
    ax_resp.set_xlabel("Time (ms)", fontsize=10)

    # 2) Waiting time
    for name, xs in waiting_times_t.items():
        ys = waiting_times[name]
        if xs:
            ax_wait.plot(xs, ys, marker=task_symbols.get(name, 'o'), 
                        color=task_colors.get(name, 'gray'),
                        label=name, alpha=0.8, markersize=MARKER_SIZE_LINE, 
                        linewidth=LINE_WIDTH, markeredgecolor='white', markeredgewidth=0.5)
    ax_wait.set_ylabel("Waiting Time (ms)", fontsize=11, fontweight='bold')
    ax_wait.set_title("Waiting Time: Release → Start", fontsize=12, fontweight='bold', pad=10)
    ax_wait.legend(loc="upper left", fontsize=9, framealpha=0.95, edgecolor='black')
    ax_wait.grid(True, alpha=0.4, linestyle='--', linewidth=0.7)
    ax_wait.set_xlabel("Time (ms)", fontsize=10)

    # 3) Tardiness
    for name, xs in tardiness_vals_t.items():
        ys = tardiness_vals[name]
        if xs:
            ax_tard.plot(xs, ys, marker=task_symbols.get(name, 'o'),
                        color=task_colors.get(name, 'gray'),
                        label=name, alpha=0.8, markersize=MARKER_SIZE_LINE, 
                        linewidth=LINE_WIDTH, markeredgecolor='white', markeredgewidth=0.5)
    ax_tard.set_ylabel("Tardiness (ms)", fontsize=11, fontweight='bold')
    ax_tard.set_title("Tardiness: Deadline Miss Amount", fontsize=12, fontweight='bold', pad=10)
    ax_tard.legend(loc="upper left", fontsize=9, framealpha=0.95, edgecolor='black')
    ax_tard.grid(True, alpha=0.4, linestyle='--', linewidth=0.7)
    ax_tard.axhline(y=0, color='#2ECC71', linestyle='-', linewidth=2, alpha=0.6, label='On-time threshold')
    ax_tard.set_xlabel("Time (ms)", fontsize=10)

    # ========== Row 2: Advanced Metrics ==========

    # 4) Utility curves (per-task + global)
    for name, xs in utility_vals_t.items():
        ys = utility_vals[name]
        if xs:
            ax_util.plot(xs, ys, marker='.', 
                        color=task_colors.get(name, 'gray'),
                        label=f"{name}", alpha=0.7, markersize=4, linewidth=LINE_WIDTH)
    # Global average utility - thicker line
    if global_util_t:
        ax_util.plot(global_util_t, global_util_v, 'k-', linewidth=3.5,
                     label="Global Average", alpha=0.9, zorder=10)
    ax_util.set_ylabel("Utility", fontsize=11, fontweight='bold')
    ax_util.set_ylim(-0.05, 1.05)
    ax_util.set_title("Utility Function (1=Perfect, 0=Failed)", fontsize=12, fontweight='bold', pad=10)
    ax_util.legend(loc="lower left", fontsize=9, framealpha=0.95, edgecolor='black')
    ax_util.grid(True, alpha=0.4, linestyle='--', linewidth=0.7)
    ax_util.axhline(y=0.5, color='#F39C12', linestyle='--', linewidth=2, alpha=0.7, label='50% threshold')
    ax_util.axhline(y=0.8, color='#2ECC71', linestyle='--', linewidth=1.5, alpha=0.5)
    ax_util.set_xlabel("Time (ms)", fontsize=10)

    # 5) Frame delay (periodic tasks only)
    for name, xs in frame_delay_vals_t.items():
        ys = frame_delay_vals[name]
        if xs:
            ax_frame.plot(xs, ys, marker=task_symbols.get(name, 'o'),
                         color=task_colors.get(name, 'gray'),
                         label=name, alpha=0.8, markersize=MARKER_SIZE_LINE, 
                         linewidth=LINE_WIDTH, markeredgecolor='white', markeredgewidth=0.5)
    ax_frame.set_ylabel("Frame Delay (frames)", fontsize=11, fontweight='bold')
    ax_frame.set_title("Frame Delay = Waiting ÷ Period", fontsize=12, fontweight='bold', pad=10)
    ax_frame.legend(loc="upper left", fontsize=9, framealpha=0.95, edgecolor='black')
    ax_frame.grid(True, alpha=0.4, linestyle='--', linewidth=0.7)
    ax_frame.axhline(y=1.0, color='#E74C3C', linestyle='--', linewidth=2, alpha=0.6, label='1 frame late')
    ax_frame.set_xlabel("Time (ms)", fontsize=10)

    # 6) Cumulative miss rate
    if miss_rate_t:
        ax_miss.plot(miss_rate_t, miss_rate_v, 'r-', linewidth=3)
        ax_miss.fill_between(miss_rate_t, 0, miss_rate_v, alpha=0.25, color='#E74C3C')
    ax_miss.set_ylabel("Miss Rate", fontsize=11, fontweight='bold')
    ax_miss.set_ylim(-0.05, 1.05)
    ax_miss.set_title("Cumulative Deadline Miss Rate", fontsize=12, fontweight='bold', pad=10)
    ax_miss.grid(True, alpha=0.4, linestyle='--', linewidth=0.7)
    ax_miss.axhline(y=0.05, color='#F39C12', linestyle='--', linewidth=2, alpha=0.7, label='5% acceptable')
    ax_miss.axhline(y=0.1, color='#E74C3C', linestyle='--', linewidth=2, alpha=0.7, label='10% critical')
    ax_miss.legend(loc='upper left', fontsize=9, framealpha=0.95, edgecolor='black')
    ax_miss.set_xlabel("Time (ms)", fontsize=10)

    # ========== Row 3: Distribution Analysis ==========

    # 7) Response time distribution (box plot)
    if jobs:
        task_names_sorted = sorted({j["name"] for j in jobs})
        resp_data = []
        labels = []
        for name in task_names_sorted:
            resp_vals = [j["resp_time"] for j in jobs if j["name"] == name]
            if resp_vals:
                resp_data.append(resp_vals)
                labels.append(name)
        
        if resp_data:
            bp = ax_resp_dist.boxplot(resp_data, labels=labels, patch_artist=True, 
                                      showmeans=True, meanline=True,
                                      boxprops=dict(linewidth=2),
                                      whiskerprops=dict(linewidth=2),
                                      capprops=dict(linewidth=2),
                                      medianprops=dict(linewidth=2.5, color='#C0392B'),
                                      meanprops=dict(linewidth=2.5, color='#2980B9', linestyle='--'))
            # Color boxes by task
            for patch, label in zip(bp['boxes'], labels):
                patch.set_facecolor(task_colors.get(label, 'lightblue'))
                patch.set_alpha(0.7)
            
            ax_resp_dist.set_ylabel("Response Time (ms)", fontsize=11, fontweight='bold')
            ax_resp_dist.set_title("Response Time Distribution per Task", fontsize=12, fontweight='bold', pad=10)
            ax_resp_dist.grid(True, alpha=0.4, axis='y', linestyle='--', linewidth=0.7)
            ax_resp_dist.set_xlabel("Task", fontsize=10, fontweight='bold')

    # 8) Utility box plots
    if jobs:
        task_names_sorted = sorted({j["name"] for j in jobs})
        util_data = []
        labels = []
        for name in task_names_sorted:
            util_vals = [j["utility"] for j in jobs if j["name"] == name]
            if util_vals:
                util_data.append(util_vals)
                labels.append(name)
        
        if util_data:
            bp = ax_util_box.boxplot(util_data, labels=labels, patch_artist=True,
                                     showmeans=True, meanline=True,
                                     boxprops=dict(linewidth=2),
                                     whiskerprops=dict(linewidth=2),
                                     capprops=dict(linewidth=2),
                                     medianprops=dict(linewidth=2.5, color='#C0392B'),
                                     meanprops=dict(linewidth=2.5, color='#2980B9', linestyle='--'))
            for patch, label in zip(bp['boxes'], labels):
                patch.set_facecolor(task_colors.get(label, 'lightgreen'))
                patch.set_alpha(0.7)
            
            ax_util_box.set_ylabel("Utility", fontsize=11, fontweight='bold')
            ax_util_box.set_ylim(-0.05, 1.05)
            ax_util_box.set_title("Utility Distribution per Task", fontsize=12, fontweight='bold', pad=10)
            ax_util_box.grid(True, alpha=0.4, axis='y', linestyle='--', linewidth=0.7)
            ax_util_box.axhline(y=0.8, color='#2ECC71', linestyle='--', linewidth=1.5, alpha=0.5)
            ax_util_box.set_xlabel("Task", fontsize=10, fontweight='bold')

    # 9) M2M Latency Classification
    if jobs:
        # Classify by delay sensitivity
        delay_sens_resp = [j["resp_time"] for j in jobs if j["name"] in delay_sensitive_tasks]
        delay_tol_resp = [j["resp_time"] for j in jobs if j["name"] in delay_tolerant_tasks]
        
        data_to_plot = []
        labels_to_plot = []
        colors_to_plot = []
        
        if delay_sens_resp:
            data_to_plot.append(delay_sens_resp)
            labels_to_plot.append("Delay-\nSensitive")
            colors_to_plot.append('#E63946')
        
        if delay_tol_resp:
            data_to_plot.append(delay_tol_resp)
            labels_to_plot.append("Delay-\nTolerant")
            colors_to_plot.append('#FFB703')
        
        if data_to_plot:
            bp = ax_latency.boxplot(data_to_plot, labels=labels_to_plot, 
                                   patch_artist=True, showmeans=True, meanline=True,
                                   boxprops=dict(linewidth=2.5),
                                   whiskerprops=dict(linewidth=2.5),
                                   capprops=dict(linewidth=2.5),
                                   medianprops=dict(linewidth=3, color='#1A1A1A'),
                                   meanprops=dict(linewidth=3, color='white', linestyle='--'))
            for patch, color in zip(bp['boxes'], colors_to_plot):
                patch.set_facecolor(color)
                patch.set_alpha(0.8)
                patch.set_edgecolor('black')
                patch.set_linewidth(2)
            
            # Add statistics with better formatting
            if delay_sens_resp:
                avg_sens = np.mean(delay_sens_resp)
                max_sens = np.max(delay_sens_resp)
                stats_text = f'Avg: {avg_sens:.1f}ms\nMax: {max_sens:.1f}ms'
                ax_latency.text(1, 0.98, stats_text, 
                               transform=ax_latency.transAxes, 
                               fontsize=9, verticalalignment='top',
                               bbox=dict(boxstyle='round,pad=0.5', facecolor='#E63946', 
                                       alpha=0.7, edgecolor='black', linewidth=1.5),
                               color='white', fontweight='bold', ha='right')
            if delay_tol_resp:
                avg_tol = np.mean(delay_tol_resp)
                max_tol = np.max(delay_tol_resp)
                stats_text = f'Avg: {avg_tol:.1f}ms\nMax: {max_tol:.1f}ms'
                ax_latency.text(0.99, 0.02, stats_text,
                               transform=ax_latency.transAxes,
                               fontsize=9, verticalalignment='bottom', 
                               horizontalalignment='right',
                               bbox=dict(boxstyle='round,pad=0.5', facecolor='#FFB703',
                                       alpha=0.7, edgecolor='black', linewidth=1.5),
                               color='black', fontweight='bold')
            
            ax_latency.set_ylabel("Latency (ms)", fontsize=11, fontweight='bold')
            ax_latency.set_title("M2M Traffic Classification (Industrial IoT)", fontsize=12, fontweight='bold', pad=10)
            ax_latency.grid(True, alpha=0.4, axis='y', linestyle='--', linewidth=0.7)
            ax_latency.set_xlabel("Traffic Class", fontsize=10, fontweight='bold')

    # ========== Row 4: Execution Timeline (Gantt-style) ==========
    
    if jobs:
        # Show last N jobs for clarity
        max_jobs_display = 80
        recent_jobs = jobs[-max_jobs_display:] if len(jobs) > max_jobs_display else jobs
        
        task_names_sorted = ["Ultra", "PIR", "Sound", "Button"]
        task_y_pos = {name: i for i, name in enumerate(task_names_sorted)}
        
        for job in recent_jobs:
            name = job["name"]
            if name not in task_y_pos:
                continue
            
            y_pos = task_y_pos[name]
            start = job["start"]
            end = job["end"]
            duration = end - start
            
            # Color based on deadline miss
            is_late = job["tardiness"] > 0
            color = '#E74C3C' if is_late else task_colors.get(name, 'blue')
            alpha_marker = 0.9
            
            # Draw execution block with enhanced visibility
            ax_timeline.scatter(start, y_pos, 
                              marker=task_symbols.get(name, 'o'),
                              s=MARKER_SIZE_TIMELINE, color=color, alpha=alpha_marker, 
                              edgecolors='black', linewidths=1.5, zorder=5)
            
            # Background shading for duration
            ax_timeline.barh(y_pos, duration, left=start, height=0.4,
                           color=color, alpha=0.3, edgecolor='none', zorder=2)
            
            # Add vertical separator every 1000ms
            if len(recent_jobs) > 0:
                min_time = min(j["start"] for j in recent_jobs)
                max_time = max(j["end"] for j in recent_jobs)
                time_range = max_time - min_time
                if time_range > 2000:  # Only add separators if range is large
                    sep_start = int(min_time / 1000) * 1000
                    for sep_time in range(sep_start, int(max_time) + 1000, 1000):
                        if sep_time > min_time:
                            ax_timeline.axvline(x=sep_time, color='gray', linestyle=':', 
                                              linewidth=1, alpha=0.4, zorder=1)
        
        # Build y-tick labels with activity indicators
        ytick_labels = []
        for name in task_names_sorted:
            job_count = len([j for j in jobs if j["name"] == name])
            if job_count > 0:
                ytick_labels.append(f"{name} ✓")  # Active task
            else:
                ytick_labels.append(f"{name} ⚠")  # No data yet
        
        ax_timeline.set_yticks(range(len(task_names_sorted)))
        ax_timeline.set_yticklabels(ytick_labels, fontsize=11, fontweight='bold')
        ax_timeline.set_xlabel("Time (ms)", fontsize=11, fontweight='bold')
        ax_timeline.set_title(f"Execution Timeline - Last {len(recent_jobs)} Jobs (Scatter=Start, Shaded=Duration)", 
                             fontsize=12, fontweight='bold', pad=10)
        ax_timeline.grid(True, alpha=0.3, axis='x', linestyle='--', linewidth=0.7)
        
        # Enhanced legend
        from matplotlib.patches import Patch
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], marker='o', color='w', markerfacecolor='#2ECC71', 
                   markersize=10, label='On Time', markeredgecolor='black', markeredgewidth=1.5),
            Line2D([0], [0], marker='o', color='w', markerfacecolor='#E74C3C', 
                   markersize=10, label='Missed Deadline', markeredgecolor='black', markeredgewidth=1.5)
        ]
        ax_timeline.legend(handles=legend_elements, loc='upper right', fontsize=10, 
                          framealpha=0.95, edgecolor='black', fancybox=True, shadow=True)
        
        # Enhanced statistics box
        if jobs:
            total_jobs = len(jobs)
            total_misses = sum(1 for j in jobs if j["tardiness"] > 0)
            miss_rate = (total_misses / total_jobs * 100) if total_jobs > 0 else 0
            avg_resp = np.mean([j["resp_time"] for j in jobs])
            avg_util = np.mean([j["utility"] for j in jobs])
            
            # Add task activity status
            active_tasks = []
            inactive_tasks = []
            for task in ["Ultra", "PIR", "Sound", "Button"]:
                if any(j["name"] == task for j in jobs):
                    active_tasks.append(task)
                else:
                    inactive_tasks.append(task)
            
            stats_text = (f'📊 Total Jobs: {total_jobs}  |  '
                         f'❌ Misses: {total_misses} ({miss_rate:.1f}%)  |  '
                         f'⏱️  Avg Response: {avg_resp:.1f}ms  |  '
                         f'📈 Avg Utility: {avg_util:.3f}')
            
            if inactive_tasks:
                stats_text += f'\n⚠️  Inactive Tasks: {", ".join(inactive_tasks)} (waiting for events/button press)'
            
            ax_timeline.text(0.5, -0.15, stats_text, transform=ax_timeline.transAxes,
                           fontsize=10, verticalalignment='top', ha='center',
                           bbox=dict(boxstyle='round,pad=0.8', facecolor='#F8F9FA', 
                                   alpha=0.95, edgecolor='black', linewidth=2),
                           fontweight='bold')

    # Main title with better styling
    fig.suptitle('🔴 ESP32 EDF Real-Time Scheduler - Live Performance Dashboard', 
                 fontsize=16, fontweight='bold', y=0.995, 
                 bbox=dict(boxstyle='round,pad=0.8', facecolor='#2C3E50', 
                          alpha=0.9, edgecolor='white', linewidth=2),
                 color='white')

    plt.tight_layout()

def save_final_plots():
    """Save comprehensive summary plots when closing."""
    if not jobs:
        print("No data to save.")
        return
    
    print("\n📊 Saving final analysis plots...")
    
    # Save the main dashboard
    fig.savefig('esp32_edf_live_dashboard.png', dpi=200, bbox_inches='tight', facecolor='white')
    print("✅ Saved: esp32_edf_live_dashboard.png (200 DPI)")
    
    # Create additional summary plots
    if len(jobs) > 10:
        # Per-task summary statistics with enhanced styling
        fig2 = plt.figure(figsize=(16, 11))
        fig2.patch.set_facecolor('white')
        gs2 = fig2.add_gridspec(2, 2, hspace=0.35, wspace=0.3, top=0.92, bottom=0.08)
        
        axes2 = [
            fig2.add_subplot(gs2[0, 0]),
            fig2.add_subplot(gs2[0, 1]),
            fig2.add_subplot(gs2[1, 0]),
            fig2.add_subplot(gs2[1, 1])
        ]
        
        task_names = sorted({j["name"] for j in jobs})
        
        # 1) Average metrics bar chart (grouped)
        ax1 = axes2[0]
        metrics = ['Waiting', 'Tardiness', 'Response']
        x = np.arange(len(task_names))
        width = 0.25
        
        for i, metric in enumerate(metrics):
            if metric == 'Waiting':
                values = [np.mean([j["waiting"] for j in jobs if j["name"] == name]) for name in task_names]
                color = '#3498DB'
            elif metric == 'Tardiness':
                values = [np.mean([j["tardiness"] for j in jobs if j["name"] == name]) for name in task_names]
                color = '#E74C3C'
            else:  # Response
                values = [np.mean([j["resp_time"] for j in jobs if j["name"] == name]) for name in task_names]
                color = '#2ECC71'
            
            bars = ax1.bar(x + i*width, values, width, label=metric, color=color, alpha=0.8, 
                          edgecolor='black', linewidth=1.5)
            
            # Add value labels on bars
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax1.text(bar.get_x() + bar.get_width()/2., height,
                            f'{height:.1f}', ha='center', va='bottom', fontsize=8, fontweight='bold')
        
        ax1.set_xlabel('Task', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Time (ms)', fontsize=12, fontweight='bold')
        ax1.set_title('Average Timing Metrics per Task', fontsize=13, fontweight='bold', pad=15)
        ax1.set_xticks(x + width)
        ax1.set_xticklabels(task_names, fontsize=11, fontweight='bold')
        ax1.legend(fontsize=10, framealpha=0.95, edgecolor='black', loc='upper left')
        ax1.grid(True, alpha=0.3, axis='y', linestyle='--')
        
        # 2) Miss rate per task
        ax2 = axes2[1]
        miss_rates = []
        for name in task_names:
            task_jobs = [j for j in jobs if j["name"] == name]
            misses = sum(1 for j in task_jobs if j["tardiness"] > 0)
            miss_rate = misses / len(task_jobs) if task_jobs else 0
            miss_rates.append(miss_rate * 100)
        
        bars = ax2.bar(task_names, miss_rates, 
                      color=[task_colors.get(name, 'gray') for name in task_names], 
                      alpha=0.85, edgecolor='black', linewidth=2)
        ax2.set_ylabel('Miss Rate (%)', fontsize=12, fontweight='bold')
        ax2.set_title('Deadline Miss Rate per Task', fontsize=13, fontweight='bold', pad=15)
        ax2.set_ylim(0, max(miss_rates) * 1.2 if miss_rates else 100)
        ax2.grid(True, alpha=0.3, axis='y', linestyle='--')
        ax2.set_xticklabels(task_names, fontsize=11, fontweight='bold')
        
        # Add value labels on bars
        for bar, rate in zip(bars, miss_rates):
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{rate:.1f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        # Add reference lines
        ax2.axhline(y=5, color='#F39C12', linestyle='--', linewidth=2, alpha=0.7, label='5% acceptable')
        ax2.axhline(y=10, color='#E74C3C', linestyle='--', linewidth=2, alpha=0.7, label='10% critical')
        ax2.legend(fontsize=9, framealpha=0.95, edgecolor='black')
        
        # 3) Utility comparison
        ax3 = axes2[2]
        util_avgs = [np.mean([j["utility"] for j in jobs if j["name"] == name]) for name in task_names]
        bars = ax3.bar(task_names, util_avgs, 
                      color=[task_colors.get(name, 'gray') for name in task_names], 
                      alpha=0.85, edgecolor='black', linewidth=2)
        ax3.set_ylabel('Average Utility', fontsize=12, fontweight='bold')
        ax3.set_title('Average Utility per Task', fontsize=13, fontweight='bold', pad=15)
        ax3.set_ylim(0, 1.1)
        ax3.axhline(y=0.8, color='#2ECC71', linestyle='--', linewidth=2, alpha=0.7, label='80% good')
        ax3.axhline(y=0.5, color='#F39C12', linestyle='--', linewidth=2, alpha=0.7, label='50% threshold')
        ax3.grid(True, alpha=0.3, axis='y', linestyle='--')
        ax3.legend(fontsize=9, framealpha=0.95, edgecolor='black')
        ax3.set_xticklabels(task_names, fontsize=11, fontweight='bold')
        
        # Add value labels
        for bar, util in zip(bars, util_avgs):
            height = bar.get_height()
            ax3.text(bar.get_x() + bar.get_width()/2., height,
                    f'{util:.3f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        # 4) Job count distribution
        ax4 = axes2[3]
        job_counts = [len([j for j in jobs if j["name"] == name]) for name in task_names]
        bars = ax4.bar(task_names, job_counts, 
                      color=[task_colors.get(name, 'gray') for name in task_names], 
                      alpha=0.85, edgecolor='black', linewidth=2)
        ax4.set_ylabel('Number of Jobs', fontsize=12, fontweight='bold')
        ax4.set_title('Job Distribution per Task', fontsize=13, fontweight='bold', pad=15)
        ax4.grid(True, alpha=0.3, axis='y', linestyle='--')
        ax4.set_xticklabels(task_names, fontsize=11, fontweight='bold')
        
        # Add value labels
        for bar, count in zip(bars, job_counts):
            height = bar.get_height()
            ax4.text(bar.get_x() + bar.get_width()/2., height,
                    f'{count}', ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        # Global title
        fig2.suptitle('🔴 ESP32 EDF Scheduler - Task Performance Summary', 
                     fontsize=16, fontweight='bold',
                     bbox=dict(boxstyle='round,pad=0.8', facecolor='#2C3E50', 
                              alpha=0.9, edgecolor='white', linewidth=2),
                     color='white')
        
        fig2.savefig('esp32_edf_task_summary.png', dpi=200, bbox_inches='tight', facecolor='white')
        print("✅ Saved: esp32_edf_task_summary.png (200 DPI)")
        plt.close(fig2)
    
    print(f"\n✅ Final CSV exported to: {csv_filename}")
    print(f"📈 Total jobs recorded: {len(jobs)}")
    print("🎉 All visualizations saved successfully!\n")

# Set up animation
ani = FuncAnimation(fig, update, interval=500)

# Handle window close to save plots
def on_close(event):
    save_final_plots()

fig.canvas.mpl_connect('close_event', on_close)

print("\n" + "="*60)
print("  ESP32 EDF REAL-TIME SCHEDULER - LIVE MONITORING")
print("="*60)
print("📡 Waiting for ESP32 connection...")
print("📊 Live dashboard will update automatically")
print("💾 CSV data exported to:", csv_filename)
print("🔴 Close the plot window to save final visualizations")
print("="*60 + "\n")

plt.show()