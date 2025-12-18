# ESP32 EDF Real-Time Scheduler
## Presentation Slides (10-15 Minutes)

---

## Slide 1: Title Slide
**ESP32 EDF Real-Time Scheduler**
**Industrial IoT Sensor Scheduling System**

- Student: [Your Name]
- Date: December 7, 2025
- Course: [Course Name/Number]

---

## Slide 2: Problem Statement

### Industrial IoT Challenge
**Goal:** Design and implement a real-time scheduler for wireless industrial environment to **reduce latency** and ensure all sensors report data at appropriate times with minimal delays

**Physical Sensors Deployed:**
- ✅ **Ultrasonic (HC-SR04):** Collision avoidance (200ms period) - SAFETY CRITICAL
- ✅ **Sound/Vibration:** Machine health monitoring (2s period)
- ✅ **PIR Motion:** Intrusion detection (event-driven)
- ✅ **Emergency Button:** Safety override (event-driven)

**Challenge:** How to schedule real hardware tasks with different deadlines and priorities on a resource-constrained embedded system?

---

## Slide 3: Two-Part Approach

### Part 1: Python Simulation (Algorithm Comparison)
**Compare three scheduling algorithms:**
- **EDF** (Earliest Deadline First) - Dynamic priority
- **RM** (Rate Monotonic) - Static priority by period
- **FIFO** (First In First Out) - No priority

**Simulation Results:** EDF achieves 0 misses, RM 0 misses, FIFO 300 misses

### Part 2: ESP32 Hardware Implementation
**Real embedded system** with:
- Custom EDF scheduler on ESP32
- Live WiFi data transmission
- Real-time monitoring dashboard

**Why Both?** Simulation validates theory → Hardware proves practical implementation

---

## Slide 4: EDF Algorithm Explained

### Earliest Deadline First (EDF)
**Core Principle:** Always execute the task with the **nearest absolute deadline**

**Why EDF?**
- ✅ **Optimal** for single-core systems (proven mathematically)
- ✅ Dynamic priority based on urgency
- ✅ Handles constrained deadlines (deadline < period)
- ✅ CPU utilization up to 100%

**Algorithm:**
1. Calculate absolute deadline when task releases
2. Select job with earliest deadline from ready queue
3. Execute (with preemption if urgent task arrives)
4. Repeat

---

## Slide 5: Simulation Results (Python)

### Algorithm Comparison - 30 Second Simulation

**Industrial IoT Task Set (92.2% CPU Utilization):**
- Ultra: 100ms period, 32ms WCET, 100ms deadline
- PIR: 200ms period, 25ms WCET, **80ms deadline** (constrained!)
- Sound: 500ms period, 180ms WCET, 500ms deadline
- Button: 300ms period, 35ms WCET, **120ms deadline** (constrained!)

**Results:**
| Algorithm | Missed Deadlines | Avg Latency | Status |
|-----------|------------------|-------------|--------|
| **EDF** | **0** ✅ | 82.26ms | Optimal |
| **RM** | **0** ✅ | 84.05ms | Good |
| **FIFO** | **300** ❌ | 119.72ms | Failed |

**Key Insight:** EDF provides lowest latency for constrained deadline tasks

---

## Slide 6: ESP32 Hardware System

### Real Embedded Implementation
**ESP32-WROOM-32D** (240MHz, WiFi enabled)

| Sensor | GPIO Pin | Period | Deadline | Type |
|--------|----------|--------|----------|------|
| Ultrasonic | 18, 5 | 200ms | 180ms | Periodic |
| Sound | 34 | 2000ms | 1950ms | Periodic |
| PIR Motion | 19 | Event | 50ms | Event |
| Button | 23 | Event | 50ms | Event |

### EDF Scheduler Core (C++)
```cpp
Task* pickEDF() {
  for (Task* t : all) {
    if (t->ready && t->dl < bestDL) {
      bestDL = t->dl;
      best = t;
    }
  }
  return best;  // Earliest deadline
}
```

**CPU Utilization:** ~15% (well below 100% limit)

*[Screenshot: esp32_edf_live_dashboard.png]*

---

## Slide 7: Live Monitoring Dashboard

### Python Real-Time Visualization System

**Two Dashboards:**

**1. Simulation Dashboard** (`new.py`)
- Compares EDF vs RM vs FIFO side-by-side
- 13+ comprehensive analysis plots
- Gantt charts, latency analysis, utility curves

**2. ESP32 Live Dashboard** (`script.py`)  
- 12-panel real-time visualization
- Response Time, Waiting, Tardiness, Utility
- M2M Traffic Classification
- Execution Timeline from actual hardware

**Data Flow:** ESP32 → WiFi → Python (500ms refresh)

*[Screenshots: Both dashboards]*

---

## Slide 8: ESP32 Problem Discovered!

### Initial Hardware Performance: 100% Deadline Misses ❌

**Symptoms:**
- All Ultrasonic tasks shown in RED on timeline
- Ultra miss rate: **100%**
- System utility: **~0** (complete failure)

**Root Cause Analysis:**
```cpp
// Sound task was BLOCKING for 100ms!
for (int i = 0; i < 50; i++) {
  sum += analogRead(SOUND_PIN);
  delay(2);  // 2ms × 50 = 100ms blocking!
}
```

**Impact:** Ultra (200ms period) couldn't execute in time

**Note:** Simulation worked fine—this was a **real hardware timing issue**

---

## Slide 9: Hardware Optimization Solution

### 41x Faster Execution! ⚡

**Before Optimization:**
```cpp
const int N = 50;              // 50 samples
delay(2);                      // 2ms per sample
// Total: 100ms blocking
```

**After Optimization:**
```cpp
const int N = 12;              // 12 samples (sufficient)
delayMicroseconds(200);        // 200µs per sample
// Total: 2.4ms blocking (41x faster!)
```

**Also adjusted deadlines:**
- Ultra: 200ms → 180ms (tight, safety-critical)
- Sound: 2000ms → 1950ms (relaxed, monitoring)

**Result:** Hardware now matches simulation performance!

---

## Slide 10: Results Comparison

### Simulation vs Hardware Performance

**Python Simulation Results:**
| Algorithm | Miss Rate | Avg Latency | Performance |
|-----------|-----------|-------------|-------------|
| EDF | 0% | 82.26ms | ⭐ Optimal |
| RM | 0% | 84.05ms | Good |
| FIFO | 49.2% | 119.72ms | Failed |

**ESP32 Hardware Results (After Optimization):**
| Metric | Before | After | Status |
|--------|--------|-------|--------|
| Ultra Miss Rate | 100% ❌ | **0%** ✅ | Perfect |
| Avg Response | ~120ms | **40.3ms** | Excellent |
| System Utility | ~0 | **1.000** | Perfect |

**Conclusion:** Both simulation and hardware validate EDF superiority

*[Screenshots: simulation + hardware dashboards]*

---

## Slide 11: M2M Traffic & Why EDF Wins

### Industrial IoT Traffic Classification

**Delay-Sensitive (Low Latency Required):**
- Ultrasonic, PIR, Button → **Avg latency: ~50ms** ✅

**Delay-Tolerant (Can Wait):**
- Sound monitoring → **Avg latency: ~250ms** (acceptable)

### Why EDF Outperforms RM & FIFO

| Algorithm | Priority | Optimality | Our Result |
|-----------|----------|------------|------------|
| **EDF** ⭐ | Dynamic (deadline) | Optimal | **0% misses** |
| **RM** | Static (period) | Sub-optimal | 0% misses* |
| **FIFO** | None | Poor | **49% misses** |

*RM also achieved 0% in simulation but **2ms higher latency** than EDF

**Key:** EDF automatically prioritizes urgent deadlines

---

## Slide 12: Real-World Applications

### Where This Technology is Used Today

**Industrial Automation:**
- Factory sensor networks, robot coordination

**Automotive:**
- ADAS systems, collision avoidance, brake-by-wire

**Medical Devices:**
- Patient monitors, infusion pumps, ventilators

**Aerospace:**
- Flight control, avionics, satellite operations

**Common Thread:** Safety-critical systems requiring deterministic, deadline-driven scheduling

---

## Slide 13: Lessons Learned

### Key Technical Insights

**1. Blocking Destroys Real-Time Performance**
- 100ms blocking → 100% failures
- Solution: Minimize delays, use microseconds

**2. Measurement is Critical**
- Live visualization revealed the problem
- Data-driven optimization = success

**3. Deadline Design Matters**
- Tight deadlines for safety-critical tasks
- Relaxed deadlines for monitoring tasks

**4. EDF is Optimal but Requires Care**
- Works perfectly when designed correctly
- Blocking time must be minimized

---

## Slide 14: Conclusions & Achievements

### Project Success Summary

✅ **Implemented custom EDF scheduler on ESP32**
- Dynamic deadline-based priority
- Handles periodic + event-driven tasks

✅ **Achieved perfect real-time performance**
- 0% miss rate, 1.0 utility, 40ms avg response

✅ **Created comprehensive monitoring system**
- 12-panel live dashboard with real-time visualization

✅ **Demonstrated engineering methodology**
- Problem identification → Root cause → Optimization → Validation

**Deliverables:** ESP32 firmware, Python dashboard, performance data, documentation

---

## Slide 15: Q&A

### Thank You!

**Contact Information:**
- Email: [your.email@university.edu]
- GitHub: [github.com/yourusername/esp32-edf-scheduler]

**Project Components:**
- ✅ ESP32 firmware (230 lines C++)
- ✅ Python monitoring dashboard (900 lines)
- ✅ Live 12-panel visualization
- ✅ CSV data export & analysis
- ✅ Complete documentation

**Questions?**

---

## Backup Slide: Task State Diagram

```
[IDLE] --release--> [READY] --schedule--> [RUNNING] --complete--> [IDLE]
   ↑                   ↑                      |
   |                   |                   preempt
   |                   +-----------------------+
   |
   +-- (periodic: wait for next period)
   +-- (event: wait for trigger)
```

---

## Backup Slide: Schedulability Analysis

### EDF Schedulability Test

**Theorem:** A set of n periodic tasks is schedulable by EDF if and only if:

```
U = Σ(Ci/Ti) ≤ 1
```

Where:
- Ci = Worst-case execution time of task i
- Ti = Period of task i
- U = Total CPU utilization

**Our System:**
- U_ultra = 30/200 = 0.15 (15%)
- U_sound = 2.4/2000 = 0.0012 (0.12%)
- **U_total = 0.1512 (15.12%) << 1** ✅

**Conclusion:** System is schedulable with large safety margin

---

## Backup Slide: Timing Constraints

### Real-Time Terminology

**Release Time (r):** When task becomes available
**Start Time (s):** When task begins execution
**Finish Time (f):** When task completes
**Deadline (d):** Latest acceptable completion time

**Key Metrics:**
- **Waiting Time:** s - r
- **Response Time:** f - r
- **Tardiness:** max(0, f - d)
- **Lateness:** f - d (can be negative)

---

## Backup Slide: ESP32 Pin Configuration

### Complete Hardware Setup

| Component | ESP32 Pin | Configuration | Notes |
|-----------|-----------|---------------|-------|
| Ultrasonic TRIG | GPIO 18 | OUTPUT | Trigger pulse |
| Ultrasonic ECHO | GPIO 5 | INPUT | Echo receive |
| Sound Sensor | GPIO 34 | INPUT (ADC) | Analog read |
| PIR Motion | GPIO 19 | INPUT | Digital HIGH detect |
| Emergency Button | GPIO 23 | INPUT_PULLUP | Active LOW |
| WiFi | Built-in | - | TCP client |

**Power:** 3.3V/5V via USB or external
**Ground:** Common ground for all sensors

---

## Notes for Presenter

### Slide Timing Guide (25 min presentation)

- Slides 1-4: Introduction & Problem (5 min)
- Slides 5-8: Algorithm & Implementation (7 min)
- Slides 9-13: Results & Performance (6 min)
- Slides 14-19: Analysis & Applications (5 min)
- Slides 20-25: Conclusions & Q&A (2 min)

### Key Points to Emphasize

1. **Problem-Solution Structure:** Started with deadline misses → identified root cause → optimized → validated
2. **Real-Time Criticality:** Emphasize safety-critical nature of collision avoidance
3. **EDF Optimality:** Explain why EDF is theoretically optimal for single-core systems
4. **Practical Results:** Show actual data from your system (use screenshots)
5. **Lessons Learned:** Share insights about blocking time being critical

### Demo Tips

- Have ESP32 pre-connected and running
- Keep Python dashboard open on second screen
- Prepare button/PIR triggers for live demo
- Have backup screenshots in case of technical issues
- Show CSV output to demonstrate data logging

### Potential Questions to Prepare For

1. "Why not use FreeRTOS?" → Explain educational value of custom implementation
2. "What about multi-core scheduling?" → Mention future work
3. "How does this compare to Linux RT?" → Discuss embedded vs general-purpose OS
4. "What about priority inversion?" → Explain how EDF avoids this with dynamic priorities
5. "Real-world deployment considerations?" → Discuss watchdogs, fault tolerance, testing
