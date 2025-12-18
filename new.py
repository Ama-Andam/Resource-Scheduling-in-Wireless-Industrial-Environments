# Industrial Real-Time Scheduling Simulator
# Simulates an industrial IoT environment with CONSTRAINED DEADLINES
# Implements and compares EDF, RM, and FIFO scheduling algorithms
#
# This scenario operates at ~92.2% CPU utilization with critical design:
# - Some tasks have deadlines MUCH SHORTER than their periods (D << P)
# - RM assigns priority based on PERIOD only (ignores deadline constraints)
# - EDF assigns priority based on DEADLINE (optimal for constrained deadlines)
# - This creates the classic scenario where EDF outperforms RM
#
# Industrial Sensor Configuration (Constrained Deadline Tasks):
# 1. Ultrasonic Distance Sensor (Ultra): period=100ms, wcet=32ms, deadline=100ms
#    - Purpose: High-speed collision avoidance
#    - Processing: Multi-echo processing, obstacle classification
#    - Utilization: 32.0%, D/P ratio: 100%
#    - RM Priority: 1 (HIGHEST - shortest period)
#
# 2. PIR Motion Detection (PIR): period=200ms, wcet=25ms, deadline=80ms
#    - Purpose: Rapid intrusion detection (TIGHT DEADLINE!)
#    - Processing: Fast pattern matching, immediate alert generation
#    - Utilization: 12.5%, D/P ratio: 40% (VERY CONSTRAINED!)
#    - RM Priority: 2 (Medium-High)
#    - ** Problem: RM gives it medium priority, but deadline is VERY urgent! **
#
# 3. Button/Safety Switch (Button): period=300ms, wcet=35ms, deadline=120ms
#    - Purpose: Emergency stop with fast response requirement
#    - Processing: Triple-redundant validation, immediate safety response
#    - Utilization: 11.7%, D/P ratio: 40% (VERY CONSTRAINED!)
#    - RM Priority: 4 (LOWEST - longest period)
#    - ** Problem: RM gives it LOW priority, but deadline is critical! **
#
# 4. Sound/Vibration Sensor (Sound): period=500ms, wcet=180ms, deadline=500ms
#    - Purpose: Machine health monitoring (can tolerate some delay)
#    - Processing: FFT analysis, spectral analysis, trend monitoring
#    - Utilization: 36.0%, D/P ratio: 100%
#    - RM Priority: 3 (Low)
#
# Total CPU Utilization: ~92.2% (Above RM bound of 75.7%, Below EDF limit of 100%)
# 
# THE CRITICAL DIFFERENCE:
# - RM Priority Order: Ultra > PIR > Sound > Button (based on period)
# - But PIR and Button have URGENT deadlines that arrive much sooner!
# - EDF dynamically recognizes when PIR/Button jobs have urgent deadlines
# - RM blindly follows period-based priority, causing PIR/Button to miss deadlines
#
# Expected Results:
# - EDF: 0-20 missed deadlines (handles constrained deadlines optimally)
# - RM: 80-200+ missed deadlines (wrong priorities for constrained deadlines)
# - FIFO: 150-300+ missed deadlines (no intelligence whatsoever)
#
# This is the textbook scenario where EDF's optimality shines!

import pandas as pd
from collections import deque
import heapq
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap
import numpy as np

class Task:
    def __init__(self, name, period, wcet, deadline):
        self.name = name
        self.period = period
        self.wcet = wcet
        self.deadline = deadline
        self.priority = period  # For RM scheduling
        
    def __repr__(self):
        return f"Task({self.name}, P={self.period}, C={self.wcet}, D={self.deadline})"

class Job:
    def __init__(self, task, arrival_time, job_number):
        self.task = task
        self.arrival_time = arrival_time
        self.absolute_deadline = arrival_time + task.deadline
        self.remaining_time = task.wcet
        self.job_number = job_number
        self.start_time = None
        self.finish_time = None
        self.response_time = None
        self.missed_deadline = False
        
    def __lt__(self, other):
        # For EDF: earlier deadline has higher priority
        return self.absolute_deadline < other.absolute_deadline
    
    def __repr__(self):
        return f"{self.task.name}_{self.job_number}"

class RTScheduler:
    def __init__(self, tasks, simulation_time=10000):
        self.tasks = tasks
        self.simulation_time = simulation_time
        self.current_time = 0
        self.ready_queue = []
        self.current_job = None
        self.completed_jobs = []
        self.timeline = []
        self.job_counters = {task.name: 0 for task in tasks}
        
    def generate_jobs(self):
        """Generate all jobs for the simulation period"""
        jobs = []
        for task in self.tasks:
            num_jobs = self.simulation_time // task.period
            for i in range(num_jobs + 1):
                arrival = i * task.period
                if arrival < self.simulation_time:
                    self.job_counters[task.name] += 1
                    job = Job(task, arrival, self.job_counters[task.name])
                    jobs.append(job)
        return sorted(jobs, key=lambda x: x.arrival_time)
    
    def schedule_edf(self):
        """EDF Scheduling Algorithm"""
        jobs = self.generate_jobs()
        job_queue = deque(jobs)
        self.ready_queue = []
        self.current_time = 0
        self.current_job = None
        self.completed_jobs = []
        self.timeline = []
        
        while self.current_time < self.simulation_time or self.ready_queue or self.current_job:
            # Add newly arrived jobs to ready queue
            while job_queue and job_queue[0].arrival_time <= self.current_time:
                job = job_queue.popleft()
                heapq.heappush(self.ready_queue, job)
            
            # Check for deadline misses
            for job in self.ready_queue:
                if job.absolute_deadline < self.current_time:
                    job.missed_deadline = True
            
            # If current job is done, move to completed
            if self.current_job and self.current_job.remaining_time == 0:
                self.current_job.finish_time = self.current_time
                self.current_job.response_time = self.current_job.finish_time - self.current_job.arrival_time
                if self.current_job.finish_time > self.current_job.absolute_deadline:
                    self.current_job.missed_deadline = True
                self.completed_jobs.append(self.current_job)
                self.current_job = None
            
            # Preempt if a higher priority job is available
            if self.ready_queue:
                highest_priority_job = self.ready_queue[0]
                if self.current_job is None or highest_priority_job.absolute_deadline < self.current_job.absolute_deadline:
                    if self.current_job:
                        heapq.heappush(self.ready_queue, self.current_job)
                    self.current_job = heapq.heappop(self.ready_queue)
                    if self.current_job.start_time is None:
                        self.current_job.start_time = self.current_time
            
            # Execute current job
            if self.current_job:
                self.timeline.append({
                    'time': self.current_time,
                    'job': str(self.current_job),
                    'task': self.current_job.task.name
                })
                self.current_job.remaining_time -= 1
                self.current_time += 1
            else:
                # Idle time
                self.timeline.append({
                    'time': self.current_time,
                    'job': 'IDLE',
                    'task': 'IDLE'
                })
                self.current_time += 1
                
            # Break if we've exceeded simulation time and queues are empty
            if self.current_time >= self.simulation_time and not self.ready_queue and not self.current_job:
                break
        
        return self.analyze_results()
    
    def schedule_rm(self):
        """Rate Monotonic Scheduling Algorithm"""
        jobs = self.generate_jobs()
        job_queue = deque(jobs)
        self.ready_queue = []
        self.current_time = 0
        self.current_job = None
        self.completed_jobs = []
        self.timeline = []
        
        while self.current_time < self.simulation_time or self.ready_queue or self.current_job:
            # Add newly arrived jobs to ready queue
            while job_queue and job_queue[0].arrival_time <= self.current_time:
                job = job_queue.popleft()
                self.ready_queue.append(job)
            
            # Sort ready queue by period (RM priority)
            self.ready_queue.sort(key=lambda x: x.task.priority)
            
            # Check for deadline misses
            for job in self.ready_queue:
                if job.absolute_deadline < self.current_time:
                    job.missed_deadline = True
            
            # If current job is done, move to completed
            if self.current_job and self.current_job.remaining_time == 0:
                self.current_job.finish_time = self.current_time
                self.current_job.response_time = self.current_job.finish_time - self.current_job.arrival_time
                if self.current_job.finish_time > self.current_job.absolute_deadline:
                    self.current_job.missed_deadline = True
                self.completed_jobs.append(self.current_job)
                self.current_job = None
            
            # Preempt if a higher priority job is available
            if self.ready_queue:
                highest_priority_job = self.ready_queue[0]
                if self.current_job is None or highest_priority_job.task.priority < self.current_job.task.priority:
                    if self.current_job:
                        self.ready_queue.append(self.current_job)
                    self.current_job = self.ready_queue.pop(0)
                    if self.current_job.start_time is None:
                        self.current_job.start_time = self.current_time
            
            # Execute current job
            if self.current_job:
                self.timeline.append({
                    'time': self.current_time,
                    'job': str(self.current_job),
                    'task': self.current_job.task.name
                })
                self.current_job.remaining_time -= 1
                self.current_time += 1
            else:
                # Idle time
                self.timeline.append({
                    'time': self.current_time,
                    'job': 'IDLE',
                    'task': 'IDLE'
                })
                self.current_time += 1
                
            # Break if we've exceeded simulation time and queues are empty
            if self.current_time >= self.simulation_time and not self.ready_queue and not self.current_job:
                break
        
        return self.analyze_results()
    
    def schedule_fifo(self):
        """First In First Out Scheduling Algorithm (Non-preemptive)"""
        jobs = self.generate_jobs()
        job_queue = deque(jobs)
        self.ready_queue = []
        self.current_time = 0
        self.current_job = None
        self.completed_jobs = []
        self.timeline = []
        
        while self.current_time < self.simulation_time or self.ready_queue or self.current_job:
            # Add newly arrived jobs to ready queue
            while job_queue and job_queue[0].arrival_time <= self.current_time:
                job = job_queue.popleft()
                self.ready_queue.append(job)
            
            # Check for deadline misses
            for job in self.ready_queue:
                if job.absolute_deadline < self.current_time:
                    job.missed_deadline = True
            
            # If current job is done, move to completed
            if self.current_job and self.current_job.remaining_time == 0:
                self.current_job.finish_time = self.current_time
                self.current_job.response_time = self.current_job.finish_time - self.current_job.arrival_time
                if self.current_job.finish_time > self.current_job.absolute_deadline:
                    self.current_job.missed_deadline = True
                self.completed_jobs.append(self.current_job)
                self.current_job = None
            
            # FIFO: No preemption - select next job only when current is done
            if self.current_job is None and self.ready_queue:
                self.current_job = self.ready_queue.pop(0)  # First come, first served
                if self.current_job.start_time is None:
                    self.current_job.start_time = self.current_time
            
            # Execute current job
            if self.current_job:
                self.timeline.append({
                    'time': self.current_time,
                    'job': str(self.current_job),
                    'task': self.current_job.task.name
                })
                self.current_job.remaining_time -= 1
                self.current_time += 1
            else:
                # Idle time
                self.timeline.append({
                    'time': self.current_time,
                    'job': 'IDLE',
                    'task': 'IDLE'
                })
                self.current_time += 1
                
            # Break if we've exceeded simulation time and queues are empty
            if self.current_time >= self.simulation_time and not self.ready_queue and not self.current_job:
                break
        
        return self.analyze_results()
    
    def analyze_results(self):
        """Analyze scheduling results"""
        total_jobs = len(self.completed_jobs)
        missed_deadlines = sum(1 for job in self.completed_jobs if job.missed_deadline)
        
        if total_jobs > 0:
            avg_response_time = sum(job.response_time for job in self.completed_jobs if job.response_time) / total_jobs
            max_response_time = max((job.response_time for job in self.completed_jobs if job.response_time), default=0)
            min_response_time = min((job.response_time for job in self.completed_jobs if job.response_time), default=0)
        else:
            avg_response_time = 0
            max_response_time = 0
            min_response_time = 0
        
        # Calculate CPU utilization
        idle_time = sum(1 for entry in self.timeline if entry['job'] == 'IDLE')
        cpu_utilization = ((len(self.timeline) - idle_time) / len(self.timeline)) * 100 if self.timeline else 0
        
        # Per-task statistics
        task_stats = {}
        for task in self.tasks:
            task_jobs = [job for job in self.completed_jobs if job.task.name == task.name]
            if task_jobs:
                task_stats[task.name] = {
                    'total_jobs': len(task_jobs),
                    'missed_deadlines': sum(1 for job in task_jobs if job.missed_deadline),
                    'avg_response_time': sum(job.response_time for job in task_jobs if job.response_time) / len(task_jobs),
                    'max_response_time': max((job.response_time for job in task_jobs if job.response_time), default=0)
                }
        
        return {
            'total_jobs': total_jobs,
            'missed_deadlines': missed_deadlines,
            'avg_response_time': avg_response_time,
            'max_response_time': max_response_time,
            'min_response_time': min_response_time,
            'cpu_utilization': cpu_utilization,
            'task_stats': task_stats,
            'timeline': self.timeline,
            'completed_jobs': self.completed_jobs
        }

def main():
    # Define tasks (sensors) - Industrial IoT Environment designed to favor EDF
    # Key insight: Tasks with long periods but tight deadlines favor EDF over RM
    # RM assigns priority by period (shorter period = higher priority)
    # EDF assigns priority by absolute deadline (earlier deadline = higher priority)
    tasks = [
        Task("Ultra", period=100, wcet=32, deadline=100),      # Ultrasonic: Shortest period, highest RM priority (32% util)
        Task("PIR", period=200, wcet=25, deadline=80),         # PIR: Medium period but VERY tight deadline (12.5% util, 40% deadline!)
        Task("Sound", period=500, wcet=180, deadline=500),     # Sound/Vibration: Heavy processing (36% util)
        Task("Button", period=300, wcet=35, deadline=120)      # Button: Medium period, tight deadline (11.7% util, 40% deadline!)
    ]
    
    # Calculate theoretical CPU utilization
    cpu_util = sum(task.wcet / task.period for task in tasks)
    rm_bound = 4*(2**(1/4)-1)  # RM schedulability bound for 4 tasks (~0.757)
    
    print("="*80)
    print("INDUSTRIAL REAL-TIME SCHEDULING SIMULATION - EDF-FAVORABLE SCENARIO")
    print("="*80)
    print(f"\nSensor Configuration (Mixed Deadline Constraints):")
    for task in tasks:
        utilization = (task.wcet/task.period)*100
        deadline_ratio = (task.deadline/task.period)*100
        print(f"  {task.name:12} - Period: {task.period:4}ms, WCET: {task.wcet:3}ms, Deadline: {task.deadline:4}ms")
        print(f"                 Utilization: {utilization:5.2f}%, Deadline/Period: {deadline_ratio:5.1f}%")
    
    print(f"\n{'='*80}")
    print(f"Total CPU Utilization: {cpu_util:.4f} ({cpu_util*100:.2f}%)")
    print(f"{'='*80}")
    print(f"EDF Schedulability Bound:    100.00% → {'SCHEDULABLE ✓' if cpu_util <= 1.0 else 'OVERLOADED ✗'}")
    print(f"RM Schedulability Bound:     {rm_bound*100:5.2f}% → {'SCHEDULABLE ✓' if cpu_util <= rm_bound else 'NOT GUARANTEED ✗'}")
    print(f"FIFO Schedulability:         N/A (no theoretical guarantees)")
    
    print(f"\n** KEY INSIGHT: PIR and Button have TIGHT deadlines relative to periods **")
    print(f"   - PIR deadline is only 40% of its period (very urgent!)")
    print(f"   - Button deadline is only 40% of its period (critical!)")
    print(f"   - RM assigns priority by PERIOD (ignores tight deadlines)")
    print(f"   - EDF assigns priority by DEADLINE (handles this optimally)")
    print(f"\n   At {cpu_util*100:.1f}% utilization, EDF should significantly outperform RM!\n")
    
    simulation_time = 30000  # 30 seconds
    
    # Run EDF scheduling
    print("=" * 60)
    print("EDF (Earliest Deadline First) Scheduling")
    print("=" * 60)
    scheduler_edf = RTScheduler(tasks, simulation_time)
    results_edf = scheduler_edf.schedule_edf()
    
    print(f"Total Jobs Completed: {results_edf['total_jobs']}")
    print(f"Missed Deadlines: {results_edf['missed_deadlines']}")
    print(f"Average Response Time: {results_edf['avg_response_time']:.2f} ms")
    print(f"Max Response Time: {results_edf['max_response_time']:.2f} ms")
    print(f"Min Response Time: {results_edf['min_response_time']:.2f} ms")
    print(f"CPU Utilization: {results_edf['cpu_utilization']:.2f}%\n")
    
    print("Per-Task Statistics (EDF):")
    for task_name, stats in results_edf['task_stats'].items():
        print(f"  {task_name}: {stats['total_jobs']} jobs, "
              f"{stats['missed_deadlines']} missed, "
              f"Avg RT: {stats['avg_response_time']:.2f} ms, "
              f"Max RT: {stats['max_response_time']:.2f} ms")
    print()
    
    # Run RM scheduling
    print("=" * 60)
    print("RM (Rate Monotonic) Scheduling")
    print("=" * 60)
    scheduler_rm = RTScheduler(tasks, simulation_time)
    results_rm = scheduler_rm.schedule_rm()
    
    print(f"Total Jobs Completed: {results_rm['total_jobs']}")
    print(f"Missed Deadlines: {results_rm['missed_deadlines']}")
    print(f"Average Response Time: {results_rm['avg_response_time']:.2f} ms")
    print(f"Max Response Time: {results_rm['max_response_time']:.2f} ms")
    print(f"Min Response Time: {results_rm['min_response_time']:.2f} ms")
    print(f"CPU Utilization: {results_rm['cpu_utilization']:.2f}%\n")
    
    print("Per-Task Statistics (RM):")
    for task_name, stats in results_rm['task_stats'].items():
        print(f"  {task_name}: {stats['total_jobs']} jobs, "
              f"{stats['missed_deadlines']} missed, "
              f"Avg RT: {stats['avg_response_time']:.2f} ms, "
              f"Max RT: {stats['max_response_time']:.2f} ms")
    print()
    
    # Run FIFO scheduling
    print("=" * 60)
    print("FIFO (First In First Out) Scheduling")
    print("=" * 60)
    scheduler_fifo = RTScheduler(tasks, simulation_time)
    results_fifo = scheduler_fifo.schedule_fifo()
    
    print(f"Total Jobs Completed: {results_fifo['total_jobs']}")
    print(f"Missed Deadlines: {results_fifo['missed_deadlines']}")
    print(f"Average Response Time: {results_fifo['avg_response_time']:.2f} ms")
    print(f"Max Response Time: {results_fifo['max_response_time']:.2f} ms")
    print(f"Min Response Time: {results_fifo['min_response_time']:.2f} ms")
    print(f"CPU Utilization: {results_fifo['cpu_utilization']:.2f}%\n")
    
    print("Per-Task Statistics (FIFO):")
    for task_name, stats in results_fifo['task_stats'].items():
        print(f"  {task_name}: {stats['total_jobs']} jobs, "
              f"{stats['missed_deadlines']} missed, "
              f"Avg RT: {stats['avg_response_time']:.2f} ms, "
              f"Max RT: {stats['max_response_time']:.2f} ms")
    print()
    
    # Comparison Summary
    print("=" * 60)
    print("COMPARISON SUMMARY")
    print("=" * 60)
    print(f"{'Metric':<30} {'EDF':<15} {'RM':<15} {'FIFO':<15}")
    print("-" * 75)
    print(f"{'Missed Deadlines':<30} {results_edf['missed_deadlines']:<15} {results_rm['missed_deadlines']:<15} {results_fifo['missed_deadlines']:<15}")
    print(f"{'Avg Response Time (ms)':<30} {results_edf['avg_response_time']:<15.2f} {results_rm['avg_response_time']:<15.2f} {results_fifo['avg_response_time']:<15.2f}")
    print(f"{'Max Response Time (ms)':<30} {results_edf['max_response_time']:<15.2f} {results_rm['max_response_time']:<15.2f} {results_fifo['max_response_time']:<15.2f}")
    print(f"{'CPU Utilization (%)':<30} {results_edf['cpu_utilization']:<15.2f} {results_rm['cpu_utilization']:<15.2f} {results_fifo['cpu_utilization']:<15.2f}")
    print()
    
    # Determine best algorithm
    algorithms = [
        ('EDF', results_edf),
        ('RM', results_rm),
        ('FIFO', results_fifo)
    ]
    
    best_deadlines = min(algorithms, key=lambda x: x[1]['missed_deadlines'])
    best_response = min(algorithms, key=lambda x: x[1]['avg_response_time'])
    best_cpu = max(algorithms, key=lambda x: x[1]['cpu_utilization'])
    
    print("Best Performance:")
    print(f"  Fewest Missed Deadlines: {best_deadlines[0]}")
    print(f"  Lowest Avg Response Time: {best_response[0]}")
    print(f"  Highest CPU Utilization: {best_cpu[0]}")
    print()
    
    # Export results to CSV
    export_results_to_csv(results_edf, results_rm, results_fifo)
    
    print("Results exported to CSV files successfully!")
    
    # Generate visualizations
    create_all_visualizations(results_edf, results_rm, results_fifo)

def export_results_to_csv(results_edf, results_rm, results_fifo):
    """Export scheduling results to CSV files"""
    
    # Summary comparison
    summary_data = {
        'Algorithm': ['EDF', 'RM', 'FIFO'],
        'Total_Jobs': [results_edf['total_jobs'], results_rm['total_jobs'], results_fifo['total_jobs']],
        'Missed_Deadlines': [results_edf['missed_deadlines'], results_rm['missed_deadlines'], results_fifo['missed_deadlines']],
        'Avg_Response_Time': [results_edf['avg_response_time'], results_rm['avg_response_time'], results_fifo['avg_response_time']],
        'Max_Response_Time': [results_edf['max_response_time'], results_rm['max_response_time'], results_fifo['max_response_time']],
        'Min_Response_Time': [results_edf['min_response_time'], results_rm['min_response_time'], results_fifo['min_response_time']],
        'CPU_Utilization': [results_edf['cpu_utilization'], results_rm['cpu_utilization'], results_fifo['cpu_utilization']]
    }
    df_summary = pd.DataFrame(summary_data)
    df_summary.to_csv('scheduling_comparison_summary.csv', index=False)
    
    # Per-task statistics for each algorithm
    for algo_name, results in [('EDF', results_edf), ('RM', results_rm), ('FIFO', results_fifo)]:
        task_data = []
        for task_name, stats in results['task_stats'].items():
            task_data.append({
                'Task': task_name,
                'Total_Jobs': stats['total_jobs'],
                'Missed_Deadlines': stats['missed_deadlines'],
                'Avg_Response_Time': stats['avg_response_time'],
                'Max_Response_Time': stats['max_response_time']
            })
        df_task = pd.DataFrame(task_data)
        df_task.to_csv(f'{algo_name.lower()}_task_statistics.csv', index=False)
    
    # Job details for each algorithm
    for algo_name, results in [('EDF', results_edf), ('RM', results_rm), ('FIFO', results_fifo)]:
        job_data = []
        for job in results['completed_jobs']:
            job_data.append({
                'Job': str(job),
                'Task': job.task.name,
                'Arrival_Time': job.arrival_time,
                'Start_Time': job.start_time,
                'Finish_Time': job.finish_time,
                'Deadline': job.absolute_deadline,
                'Response_Time': job.response_time,
                'Missed_Deadline': job.missed_deadline
            })
        df_jobs = pd.DataFrame(job_data)
        df_jobs.to_csv(f'{algo_name.lower()}_job_details.csv', index=False)

def visualize_gantt_chart(results, algorithm_name, max_time=2000):
    """Create a Gantt chart showing task execution timeline"""
    fig, ax = plt.subplots(figsize=(18, 6))
    
    # Color map for different tasks
    colors = {'Ultra': '#FF6B6B', 'Sound': '#4ECDC4', 'PIR': '#45B7D1', 'Button': '#FFA07A', 'IDLE': '#E8E8E8'}
    # Marker styles for different tasks
    markers = {'Ultra': 's', 'Sound': 'o', 'PIR': '^', 'Button': 'D'}  # square, circle, triangle, diamond
    
    # Get timeline up to max_time
    timeline = [entry for entry in results['timeline'] if entry['time'] < max_time]
    
    # Create a mapping of tasks to y-positions
    task_names = ['Ultra', 'Sound', 'PIR', 'Button']
    task_to_y = {task: idx for idx, task in enumerate(task_names)}
    
    # Track job executions for scatter plot
    task_executions = {task: [] for task in task_names}
    
    # Group consecutive same tasks for background shading
    if timeline:
        current_task = timeline[0]['task']
        start_time = timeline[0]['time']
        
        for entry in timeline:
            if entry['task'] != 'IDLE' and entry['task'] in task_names:
                task_executions[entry['task']].append(entry['time'])
        
        # Plot background regions for continuous task execution periods
        i = 0
        while i < len(timeline):
            if timeline[i]['task'] != 'IDLE':
                task = timeline[i]['task']
                if task in task_names:
                    start = timeline[i]['time']
                    # Find end of this execution burst
                    j = i
                    while j < len(timeline) and timeline[j]['task'] == task:
                        j += 1
                    end = timeline[j-1]['time'] + 1
                    
                    # Draw subtle background bar
                    y_pos = task_to_y[task]
                    ax.barh(y_pos, end - start, left=start, height=0.6, 
                           color=colors[task], alpha=0.15, edgecolor='none')
                    i = j
                else:
                    i += 1
            else:
                i += 1
    
    # Plot execution points as scatter
    for task in task_names:
        if task_executions[task]:
            # Sample points to avoid overcrowding (take every Nth point based on density)
            times = task_executions[task]
            if len(times) > 500:
                # If too many points, sample them
                step = len(times) // 500
                times = times[::step]
            
            y_positions = [task_to_y[task]] * len(times)
            ax.scatter(times, y_positions, c=colors[task], marker=markers[task], 
                      s=30, edgecolors='black', linewidths=0.5, alpha=0.8, zorder=3)
    
    # Formatting
    ax.set_xlabel('Time (ms)', fontsize=13, fontweight='bold')
    ax.set_ylabel('Task', fontsize=13, fontweight='bold')
    ax.set_title(f'{algorithm_name} Scheduling - Execution Timeline (0-{max_time}ms)', 
                fontsize=15, fontweight='bold', pad=15)
    ax.set_ylim(-0.5, len(task_names) - 0.5)
    ax.set_xlim(0, max_time)
    ax.set_yticks(range(len(task_names)))
    ax.set_yticklabels(task_names, fontsize=11)
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.invert_yaxis()  # Put first task at top
    
    # Add vertical lines at regular intervals
    for x in range(0, max_time, 1000):
        ax.axvline(x=x, color='gray', alpha=0.2, linestyle='-', linewidth=0.5)
    
    # Legend with markers and colors
    legend_elements = [plt.Line2D([0], [0], marker=markers[task], color='w', 
                                 markerfacecolor=colors[task], markersize=10, 
                                 markeredgecolor='black', markeredgewidth=0.5,
                                 label=task, linestyle='None') 
                      for task in task_names]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10, 
             framealpha=0.9, title='Tasks', title_fontsize=11)
    
    # Add statistics box
    stats_text = f"CPU Utilization: {results['cpu_utilization']:.1f}%\n"
    stats_text += f"Missed Deadlines: {results['missed_deadlines']}\n"
    stats_text += f"Avg Response Time: {results['avg_response_time']:.1f}ms"
    
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
           fontsize=9, verticalalignment='top',
           bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.tight_layout()
    plt.savefig(f'{algorithm_name.lower()}_gantt_chart.png', dpi=300, bbox_inches='tight')
    print(f"Saved {algorithm_name.lower()}_gantt_chart.png")

def visualize_comparison_metrics(results_edf, results_rm, results_fifo):
    """Create bar charts comparing different metrics across algorithms"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    algorithms = ['EDF', 'RM', 'FIFO']
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']
    
    # 1. Missed Deadlines
    missed = [results_edf['missed_deadlines'], results_rm['missed_deadlines'], results_fifo['missed_deadlines']]
    axes[0, 0].bar(algorithms, missed, color=colors, edgecolor='black', linewidth=1.5)
    axes[0, 0].set_title('Missed Deadlines Comparison', fontsize=12, fontweight='bold')
    axes[0, 0].set_ylabel('Number of Missed Deadlines', fontsize=10)
    axes[0, 0].grid(axis='y', alpha=0.3)
    for i, v in enumerate(missed):
        axes[0, 0].text(i, v + max(missed)*0.02, str(v), ha='center', va='bottom', fontweight='bold')
    
    # 2. Average Response Time
    avg_rt = [results_edf['avg_response_time'], results_rm['avg_response_time'], results_fifo['avg_response_time']]
    axes[0, 1].bar(algorithms, avg_rt, color=colors, edgecolor='black', linewidth=1.5)
    axes[0, 1].set_title('Average Response Time Comparison', fontsize=12, fontweight='bold')
    axes[0, 1].set_ylabel('Avg Response Time (ms)', fontsize=10)
    axes[0, 1].grid(axis='y', alpha=0.3)
    for i, v in enumerate(avg_rt):
        axes[0, 1].text(i, v + max(avg_rt)*0.02, f'{v:.1f}', ha='center', va='bottom', fontweight='bold')
    
    # 3. CPU Utilization
    cpu_util = [results_edf['cpu_utilization'], results_rm['cpu_utilization'], results_fifo['cpu_utilization']]
    axes[1, 0].bar(algorithms, cpu_util, color=colors, edgecolor='black', linewidth=1.5)
    axes[1, 0].set_title('CPU Utilization Comparison', fontsize=12, fontweight='bold')
    axes[1, 0].set_ylabel('CPU Utilization (%)', fontsize=10)
    axes[1, 0].set_ylim(0, 100)
    axes[1, 0].grid(axis='y', alpha=0.3)
    for i, v in enumerate(cpu_util):
        axes[1, 0].text(i, v + 2, f'{v:.1f}%', ha='center', va='bottom', fontweight='bold')
    
    # 4. Max Response Time
    max_rt = [results_edf['max_response_time'], results_rm['max_response_time'], results_fifo['max_response_time']]
    axes[1, 1].bar(algorithms, max_rt, color=colors, edgecolor='black', linewidth=1.5)
    axes[1, 1].set_title('Maximum Response Time Comparison', fontsize=12, fontweight='bold')
    axes[1, 1].set_ylabel('Max Response Time (ms)', fontsize=10)
    axes[1, 1].grid(axis='y', alpha=0.3)
    for i, v in enumerate(max_rt):
        axes[1, 1].text(i, v + max(max_rt)*0.02, f'{v:.1f}', ha='center', va='bottom', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig('scheduling_comparison_metrics.png', dpi=300, bbox_inches='tight')
    print(f"Saved scheduling_comparison_metrics.png")

def visualize_task_statistics(results_edf, results_rm, results_fifo):
    """Create per-task comparison charts"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    tasks = ['Ultra', 'Sound', 'PIR', 'Button']
    algorithms = ['EDF', 'RM', 'FIFO']
    
    x = np.arange(len(tasks))
    width = 0.25
    
    # 1. Missed Deadlines per Task
    edf_missed = [results_edf['task_stats'][t]['missed_deadlines'] for t in tasks]
    rm_missed = [results_rm['task_stats'][t]['missed_deadlines'] for t in tasks]
    fifo_missed = [results_fifo['task_stats'][t]['missed_deadlines'] for t in tasks]
    
    axes[0, 0].bar(x - width, edf_missed, width, label='EDF', color='#FF6B6B', edgecolor='black')
    axes[0, 0].bar(x, rm_missed, width, label='RM', color='#4ECDC4', edgecolor='black')
    axes[0, 0].bar(x + width, fifo_missed, width, label='FIFO', color='#45B7D1', edgecolor='black')
    axes[0, 0].set_title('Missed Deadlines by Task', fontsize=12, fontweight='bold')
    axes[0, 0].set_ylabel('Missed Deadlines', fontsize=10)
    axes[0, 0].set_xticks(x)
    axes[0, 0].set_xticklabels(tasks)
    axes[0, 0].legend()
    axes[0, 0].grid(axis='y', alpha=0.3)
    
    # 2. Average Response Time per Task
    edf_rt = [results_edf['task_stats'][t]['avg_response_time'] for t in tasks]
    rm_rt = [results_rm['task_stats'][t]['avg_response_time'] for t in tasks]
    fifo_rt = [results_fifo['task_stats'][t]['avg_response_time'] for t in tasks]
    
    axes[0, 1].bar(x - width, edf_rt, width, label='EDF', color='#FF6B6B', edgecolor='black')
    axes[0, 1].bar(x, rm_rt, width, label='RM', color='#4ECDC4', edgecolor='black')
    axes[0, 1].bar(x + width, fifo_rt, width, label='FIFO', color='#45B7D1', edgecolor='black')
    axes[0, 1].set_title('Average Response Time by Task', fontsize=12, fontweight='bold')
    axes[0, 1].set_ylabel('Avg Response Time (ms)', fontsize=10)
    axes[0, 1].set_xticks(x)
    axes[0, 1].set_xticklabels(tasks)
    axes[0, 1].legend()
    axes[0, 1].grid(axis='y', alpha=0.3)
    
    # 3. Max Response Time per Task
    edf_max = [results_edf['task_stats'][t]['max_response_time'] for t in tasks]
    rm_max = [results_rm['task_stats'][t]['max_response_time'] for t in tasks]
    fifo_max = [results_fifo['task_stats'][t]['max_response_time'] for t in tasks]
    
    axes[1, 0].bar(x - width, edf_max, width, label='EDF', color='#FF6B6B', edgecolor='black')
    axes[1, 0].bar(x, rm_max, width, label='RM', color='#4ECDC4', edgecolor='black')
    axes[1, 0].bar(x + width, fifo_max, width, label='FIFO', color='#45B7D1', edgecolor='black')
    axes[1, 0].set_title('Maximum Response Time by Task', fontsize=12, fontweight='bold')
    axes[1, 0].set_ylabel('Max Response Time (ms)', fontsize=10)
    axes[1, 0].set_xticks(x)
    axes[1, 0].set_xticklabels(tasks)
    axes[1, 0].legend()
    axes[1, 0].grid(axis='y', alpha=0.3)
    
    # 4. Total Jobs per Task
    edf_jobs = [results_edf['task_stats'][t]['total_jobs'] for t in tasks]
    rm_jobs = [results_rm['task_stats'][t]['total_jobs'] for t in tasks]
    fifo_jobs = [results_fifo['task_stats'][t]['total_jobs'] for t in tasks]
    
    axes[1, 1].bar(x - width, edf_jobs, width, label='EDF', color='#FF6B6B', edgecolor='black')
    axes[1, 1].bar(x, rm_jobs, width, label='RM', color='#4ECDC4', edgecolor='black')
    axes[1, 1].bar(x + width, fifo_jobs, width, label='FIFO', color='#45B7D1', edgecolor='black')
    axes[1, 1].set_title('Total Jobs Completed by Task', fontsize=12, fontweight='bold')
    axes[1, 1].set_ylabel('Number of Jobs', fontsize=10)
    axes[1, 1].set_xticks(x)
    axes[1, 1].set_xticklabels(tasks)
    axes[1, 1].legend()
    axes[1, 1].grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('task_statistics_comparison.png', dpi=300, bbox_inches='tight')
    print(f"Saved task_statistics_comparison.png")

def visualize_response_time_distribution(results_edf, results_rm, results_fifo):
    """Create response time distribution histograms"""
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    
    algorithms = [('EDF', results_edf), ('RM', results_rm), ('FIFO', results_fifo)]
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']
    
    for idx, (name, results) in enumerate(algorithms):
        response_times = [job.response_time for job in results['completed_jobs'] if job.response_time]
        
        axes[idx].hist(response_times, bins=30, color=colors[idx], edgecolor='black', alpha=0.7)
        axes[idx].set_title(f'{name} Response Time Distribution', fontsize=12, fontweight='bold')
        axes[idx].set_xlabel('Response Time (ms)', fontsize=10)
        axes[idx].set_ylabel('Frequency', fontsize=10)
        axes[idx].axvline(results['avg_response_time'], color='red', linestyle='--', 
                         linewidth=2, label=f'Mean: {results["avg_response_time"]:.1f}ms')
        axes[idx].legend()
        axes[idx].grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('response_time_distribution.png', dpi=300, bbox_inches='tight')
    print(f"Saved response_time_distribution.png")

def calculate_utility(job, utility_type='hard'):
    """
    Calculate utility for a job based on different utility models
    
    utility_type options:
    - 'hard': Full utility (1.0) if deadline met, 0 if missed (Hard Real-Time)
    - 'soft': Gradual degradation after deadline (Soft Real-Time)
    - 'firm': Linear decrease before deadline, 0 after (Firm Real-Time)
    - 'delay_sensitive': Step function for delay-sensitive M2M traffic
    - 'delay_tolerant': Exponential decay for delay-tolerant M2M traffic
    """
    if job.response_time is None:
        return 0
    
    lateness = job.finish_time - job.absolute_deadline
    deadline = job.task.deadline
    latency = job.response_time  # Time from arrival to completion
    
    if utility_type == 'hard':
        # Hard real-time: binary utility
        return 1.0 if lateness <= 0 else 0.0
    
    elif utility_type == 'soft':
        # Soft real-time: exponential decay after deadline
        if lateness <= 0:
            return 1.0
        else:
            # Exponential decay: u(t) = e^(-lateness/deadline)
            return np.exp(-lateness / deadline)
    
    elif utility_type == 'firm':
        # Firm real-time: linear decrease before deadline, 0 after
        if lateness <= 0:
            # Linear increase as we approach deadline from early completion
            # Max utility at completion, decreases as we get closer to deadline
            slack = job.absolute_deadline - job.finish_time
            return 1.0 - (0.3 * (deadline - slack) / deadline)  # 70-100% utility
        else:
            return 0.0
    
    elif utility_type == 'delay_sensitive':
        # M2M Delay-sensitive traffic: Step function (like emergency button, PIR)
        # High utility if latency < threshold, drops sharply after
        threshold = deadline * 0.7  # 70% of deadline is the critical threshold
        if latency < threshold:
            return 1.0
        elif latency <= deadline:
            return 0.3  # Reduced utility but still some value
        else:
            return 0.0  # No value after deadline
    
    elif utility_type == 'delay_tolerant':
        # M2M Delay-tolerant traffic: Gradual exponential decay (like Sound sensor)
        # Can tolerate delays with graceful degradation
        a = 0.3  # Decay rate (slower = more tolerant)
        b = deadline * 0.5  # Latency where utility drops to ~50%
        utility = np.exp(-a * (latency / b))
        return max(0, utility)
    
    return 1.0

def get_task_traffic_class(task_name):
    """Classify tasks as delay-sensitive or delay-tolerant"""
    delay_sensitive_tasks = ['PIR', 'Button', 'Ultra']  # Critical, emergency, collision avoidance
    delay_tolerant_tasks = ['Sound']  # Monitoring, analysis - can tolerate delays
    
    if task_name in delay_sensitive_tasks:
        return 'delay_sensitive'
    elif task_name in delay_tolerant_tasks:
        return 'delay_tolerant'
    else:
        return 'delay_sensitive'  # Default to sensitive for safety

def visualize_utility_curves(results_edf, results_rm, results_fifo):
    """Visualize utility curves for different real-time models"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    algorithms = [('EDF', results_edf, '#FF6B6B'), 
                  ('RM', results_rm, '#4ECDC4'), 
                  ('FIFO', results_fifo, '#45B7D1')]
    
    utility_types = ['hard', 'soft', 'firm']
    
    # 1. Hard Real-Time Utility
    ax = axes[0, 0]
    for name, results, color in algorithms:
        utilities = [calculate_utility(job, 'hard') for job in results['completed_jobs']]
        avg_utility = np.mean(utilities) * 100
        total_utility = sum(utilities)
        
        ax.bar(name, avg_utility, color=color, edgecolor='black', linewidth=1.5, alpha=0.8)
        ax.text(name, avg_utility + 2, f'{avg_utility:.1f}%\n({int(total_utility)} jobs)', 
               ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax.set_title('Hard Real-Time Utility (Binary)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Average Utility (%)', fontsize=10)
    ax.set_ylim(0, 105)
    ax.grid(axis='y', alpha=0.3)
    ax.axhline(y=100, color='green', linestyle='--', alpha=0.5, label='Max Utility')
    
    # 2. Soft Real-Time Utility
    ax = axes[0, 1]
    for name, results, color in algorithms:
        utilities = [calculate_utility(job, 'soft') for job in results['completed_jobs']]
        avg_utility = np.mean(utilities) * 100
        
        ax.bar(name, avg_utility, color=color, edgecolor='black', linewidth=1.5, alpha=0.8)
        ax.text(name, avg_utility + 2, f'{avg_utility:.1f}%', 
               ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax.set_title('Soft Real-Time Utility (Exponential Decay)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Average Utility (%)', fontsize=10)
    ax.set_ylim(0, 105)
    ax.grid(axis='y', alpha=0.3)
    ax.axhline(y=100, color='green', linestyle='--', alpha=0.5, label='Max Utility')
    
    # 3. Firm Real-Time Utility
    ax = axes[1, 0]
    for name, results, color in algorithms:
        utilities = [calculate_utility(job, 'firm') for job in results['completed_jobs']]
        avg_utility = np.mean(utilities) * 100
        
        ax.bar(name, avg_utility, color=color, edgecolor='black', linewidth=1.5, alpha=0.8)
        ax.text(name, avg_utility + 2, f'{avg_utility:.1f}%', 
               ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax.set_title('Firm Real-Time Utility (Linear Degradation)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Average Utility (%)', fontsize=10)
    ax.set_ylim(0, 105)
    ax.grid(axis='y', alpha=0.3)
    ax.axhline(y=100, color='green', linestyle='--', alpha=0.5, label='Max Utility')
    
    # 4. Utility Function Models (Theoretical curves)
    ax = axes[1, 1]
    time_range = np.linspace(-50, 150, 300)  # Time relative to deadline
    deadline_point = 0
    
    # Hard real-time
    hard_utility = np.where(time_range <= deadline_point, 1.0, 0.0)
    ax.plot(time_range, hard_utility, 'r-', linewidth=2.5, label='Hard RT', alpha=0.8)
    
    # Soft real-time
    soft_utility = np.where(time_range <= deadline_point, 
                           1.0, 
                           np.exp(-time_range / 50))
    ax.plot(time_range, soft_utility, 'b-', linewidth=2.5, label='Soft RT', alpha=0.8)
    
    # Firm real-time
    firm_utility = np.where(time_range <= deadline_point, 
                           0.7 + 0.3 * (1 - time_range / (-50)),
                           0.0)
    firm_utility = np.clip(firm_utility, 0, 1)
    ax.plot(time_range, firm_utility, 'g-', linewidth=2.5, label='Firm RT', alpha=0.8)
    
    ax.axvline(x=0, color='black', linestyle='--', linewidth=2, label='Deadline')
    ax.set_title('Utility Function Models', fontsize=12, fontweight='bold')
    ax.set_xlabel('Time Relative to Deadline (ms)', fontsize=10)
    ax.set_ylabel('Utility', fontsize=10)
    ax.set_xlim(-50, 150)
    ax.set_ylim(-0.05, 1.1)
    ax.legend(loc='upper right', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.fill_between(time_range, 0, 1.1, where=(time_range <= 0), 
                    color='green', alpha=0.1, label='Before Deadline')
    ax.fill_between(time_range, 0, 1.1, where=(time_range > 0), 
                    color='red', alpha=0.1, label='After Deadline')
    
    plt.tight_layout()
    plt.savefig('utility_curves.png', dpi=300, bbox_inches='tight')
    print(f"Saved utility_curves.png")

def visualize_cumulative_utility(results_edf, results_rm, results_fifo):
    """Visualize cumulative utility over time"""
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    
    algorithms = [('EDF', results_edf, '#FF6B6B'), 
                  ('RM', results_rm, '#4ECDC4'), 
                  ('FIFO', results_fifo, '#45B7D1')]
    
    utility_types = [('Hard RT', 'hard'), ('Soft RT', 'soft'), ('Firm RT', 'firm')]
    
    for idx, (util_name, util_type) in enumerate(utility_types):
        ax = axes[idx]
        
        for name, results, color in algorithms:
            # Sort jobs by finish time
            sorted_jobs = sorted([j for j in results['completed_jobs'] if j.finish_time], 
                                key=lambda x: x.finish_time)
            
            times = []
            cumulative_utility = []
            total_util = 0
            
            for job in sorted_jobs:
                utility = calculate_utility(job, util_type)
                total_util += utility
                times.append(job.finish_time)
                cumulative_utility.append(total_util)
            
            if times:
                ax.plot(times, cumulative_utility, linewidth=2.5, label=name, color=color, alpha=0.8)
        
        ax.set_title(f'Cumulative Utility Over Time ({util_name})', fontsize=12, fontweight='bold')
        ax.set_xlabel('Time (ms)', fontsize=10)
        ax.set_ylabel('Cumulative Utility', fontsize=10)
        ax.legend(loc='lower right', fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, 10000)  # First 10 seconds
    
    plt.tight_layout()
    plt.savefig('cumulative_utility.png', dpi=300, bbox_inches='tight')
    print(f"Saved cumulative_utility.png")

def visualize_per_task_utility(results_edf, results_rm, results_fifo):
    """Visualize utility per task for each algorithm"""
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    
    tasks = ['Ultra', 'Sound', 'PIR', 'Button']
    algorithms = [('EDF', results_edf), ('RM', results_rm), ('FIFO', results_fifo)]
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A']
    
    utility_type = 'soft'  # Using soft real-time model
    
    for idx, (name, results) in enumerate(algorithms):
        ax = axes[idx]
        
        task_utilities = []
        for task in tasks:
            task_jobs = [job for job in results['completed_jobs'] if job.task.name == task]
            utilities = [calculate_utility(job, utility_type) for job in task_jobs]
            avg_utility = np.mean(utilities) * 100 if utilities else 0
            task_utilities.append(avg_utility)
        
        bars = ax.bar(tasks, task_utilities, color=colors, edgecolor='black', linewidth=1.5, alpha=0.8)
        
        # Add value labels on bars
        for bar, value in zip(bars, task_utilities):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                   f'{value:.1f}%', ha='center', va='bottom', fontsize=9, fontweight='bold')
        
        ax.set_title(f'{name} - Utility by Task (Soft RT)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Average Utility (%)', fontsize=10)
        ax.set_ylim(0, 105)
        ax.grid(axis='y', alpha=0.3)
        ax.axhline(y=100, color='green', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig('per_task_utility.png', dpi=300, bbox_inches='tight')
    print(f"Saved per_task_utility.png")

def visualize_latency_analysis(results_edf, results_rm, results_fifo):
    """Visualize latency (response time) distribution and impact - M2M style"""
    fig = plt.figure(figsize=(18, 11))
    gs = fig.add_gridspec(3, 3, hspace=0.35, wspace=0.35)
    
    algorithms = [('EDF', results_edf, '#FF6B6B'), 
                  ('RM', results_rm, '#4ECDC4'), 
                  ('FIFO', results_fifo, '#45B7D1')]
    
    # 1. Latency Distribution Histograms (Top row) - IMPROVED
    for idx, (name, results, color) in enumerate(algorithms):
        ax = fig.add_subplot(gs[0, idx])
        latencies = [job.response_time for job in results['completed_jobs'] if job.response_time]
        
        # Create histogram with better bins
        n, bins, patches = ax.hist(latencies, bins=25, color=color, edgecolor='black', 
                                   alpha=0.7, linewidth=1)
        
        # Add mean line
        mean_lat = results['avg_response_time']
        ax.axvline(mean_lat, color='red', linestyle='--', linewidth=2.5, 
                  label=f'Mean: {mean_lat:.1f}ms', zorder=5)
        
        ax.set_title(f'{name} Latency Distribution', fontsize=12, fontweight='bold')
        ax.set_xlabel('Latency (ms)', fontsize=10)
        ax.set_ylabel('Frequency', fontsize=10)
        ax.legend(fontsize=9, loc='upper right')
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.set_xlim(0, max(latencies) * 1.1 if latencies else 100)
    
    # 2. Traffic Class Box Plot (Row 2, spanning all columns) - CLEANED UP
    ax1 = fig.add_subplot(gs[1, :])
    
    delay_sensitive_tasks = ['PIR', 'Button', 'Ultra']
    delay_tolerant_tasks = ['Sound']
    
    data_to_plot = []
    positions = []
    labels = []
    colors_box = []
    
    pos = 1
    for name, results, color in algorithms:
        # Delay-sensitive latencies
        sens_latencies = [job.response_time for job in results['completed_jobs'] 
                         if job.task.name in delay_sensitive_tasks and job.response_time]
        # Delay-tolerant latencies  
        tol_latencies = [job.response_time for job in results['completed_jobs'] 
                        if job.task.name in delay_tolerant_tasks and job.response_time]
        
        data_to_plot.extend([sens_latencies, tol_latencies])
        positions.extend([pos, pos + 0.8])
        labels.extend([f'{name}\nDelay-Sensitive', f'{name}\nDelay-Tolerant'])
        colors_box.extend([color, color])
        pos += 2.5
    
    bp = ax1.boxplot(data_to_plot, positions=positions, widths=0.6, patch_artist=True,
                     showmeans=True, meanprops=dict(marker='^', markerfacecolor='green', 
                                                     markersize=8, markeredgecolor='black'),
                     medianprops=dict(color='black', linewidth=2),
                     boxprops=dict(linewidth=1.5),
                     whiskerprops=dict(linewidth=1.5),
                     capprops=dict(linewidth=1.5))
    
    for patch, color in zip(bp['boxes'], colors_box):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    
    ax1.set_title('Latency by Traffic Class (M2M Classification)', fontsize=13, fontweight='bold', pad=10)
    ax1.set_ylabel('Latency (ms)', fontsize=11, fontweight='bold')
    ax1.set_xticks(positions)
    ax1.set_xticklabels(labels, fontsize=9, rotation=0)
    ax1.grid(axis='y', alpha=0.3, linestyle='--')
    ax1.set_ylim(0, None)
    
    # Add separators between algorithms
    for x in [4.25, 9]:
        ax1.axvline(x=x, color='gray', alpha=0.3, linestyle='-', linewidth=1.5)
    
    # 3. Utility Curves (Bottom left two) - ENHANCED
    ax2 = fig.add_subplot(gs[2, 0])
    latency_range = np.linspace(0, 150, 500)
    
    # Delay-sensitive curve (step function)
    threshold = 70
    utility_sens = np.where(latency_range < threshold, 1.0,
                           np.where(latency_range < 100, 0.3, 0.0))
    ax2.plot(latency_range, utility_sens, 'r-', linewidth=3.5, label='Delay-Sensitive', zorder=3)
    ax2.axvline(threshold, color='orange', linestyle='--', alpha=0.6, linewidth=2,
               label=f'Threshold: {threshold}ms')
    ax2.fill_between(latency_range, 0, 1, where=(latency_range < threshold), 
                    color='green', alpha=0.15, label='High Utility')
    ax2.fill_between(latency_range, 0, 1, where=(latency_range >= threshold), 
                    color='red', alpha=0.15, label='Low/No Utility')
    
    ax2.set_title('Delay-Sensitive Traffic\n(PIR, Button, Ultra)', fontsize=11, fontweight='bold')
    ax2.set_xlabel('Latency (ms)', fontsize=10)
    ax2.set_ylabel('Utility', fontsize=10)
    ax2.legend(fontsize=8, loc='upper right')
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.set_xlim(0, 150)
    ax2.set_ylim(-0.05, 1.1)
    
    # Delay-tolerant curve (exponential decay)
    ax3 = fig.add_subplot(gs[2, 1])
    a = 0.3
    b = 100
    utility_tol = np.exp(-a * (latency_range / b))
    ax3.plot(latency_range, utility_tol, 'b-', linewidth=3.5, label='Delay-Tolerant', zorder=3)
    ax3.axhline(0.5, color='orange', linestyle='--', alpha=0.6, linewidth=2,
               label='50% Utility')
    ax3.fill_between(latency_range, 0, utility_tol, color='blue', alpha=0.15,
                    label='Remaining Utility')
    
    ax3.set_title('Delay-Tolerant Traffic\n(Sound/Vibration)', fontsize=11, fontweight='bold')
    ax3.set_xlabel('Latency (ms)', fontsize=10)
    ax3.set_ylabel('Utility', fontsize=10)
    ax3.legend(fontsize=8, loc='upper right')
    ax3.grid(True, alpha=0.3, linestyle='--')
    ax3.set_xlim(0, 150)
    ax3.set_ylim(-0.05, 1.1)
    
    # 4. Average Latency Comparison (Bottom right) - IMPROVED
    ax4 = fig.add_subplot(gs[2, 2])
    
    x_pos = np.arange(len(algorithms))
    width = 0.35
    
    sens_avgs = []
    tol_avgs = []
    
    for name, results, color in algorithms:
        sens_latencies = [job.response_time for job in results['completed_jobs'] 
                         if job.task.name in delay_sensitive_tasks and job.response_time]
        tol_latencies = [job.response_time for job in results['completed_jobs'] 
                        if job.task.name in delay_tolerant_tasks and job.response_time]
        
        sens_avgs.append(np.mean(sens_latencies) if sens_latencies else 0)
        tol_avgs.append(np.mean(tol_latencies) if tol_latencies else 0)
    
    bars1 = ax4.bar(x_pos - width/2, sens_avgs, width, label='Delay-Sensitive', 
            color='#FF6B6B', edgecolor='black', alpha=0.8, linewidth=1.5)
    bars2 = ax4.bar(x_pos + width/2, tol_avgs, width, label='Delay-Tolerant', 
            color='#4ECDC4', edgecolor='black', alpha=0.8, linewidth=1.5)
    
    # Add value labels on bars
    for bar in bars1:
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height + max(sens_avgs)*0.02,
                f'{height:.1f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    for bar in bars2:
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height + max(tol_avgs)*0.02,
                f'{height:.1f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax4.set_title('Avg Latency by Traffic Class', fontsize=11, fontweight='bold')
    ax4.set_ylabel('Average Latency (ms)', fontsize=10, fontweight='bold')
    ax4.set_xlabel('Scheduler', fontsize=10, fontweight='bold')
    ax4.set_xticks(x_pos)
    ax4.set_xticklabels([name for name, _, _ in algorithms], fontsize=10)
    ax4.legend(fontsize=9, loc='upper left')
    ax4.grid(axis='y', alpha=0.3, linestyle='--')
    
    plt.suptitle('Latency Analysis - M2M Traffic Classification', fontsize=15, fontweight='bold', y=0.995)
    plt.savefig('latency_analysis_m2m.png', dpi=300, bbox_inches='tight')
    print(f"Saved latency_analysis_m2m.png")

def print_latency_summary(results_edf, results_rm, results_fifo):
    """Print detailed latency analysis summary"""
    print("\n" + "="*80)
    print("LATENCY ANALYSIS - M2M TRAFFIC CLASSIFICATION")
    print("="*80)
    
    delay_sensitive_tasks = ['PIR', 'Button', 'Ultra']
    delay_tolerant_tasks = ['Sound']
    
    algorithms = [('EDF', results_edf), ('RM', results_rm), ('FIFO', results_fifo)]
    
    for name, results in algorithms:
        print(f"\n{name} Scheduler:")
        print("-" * 40)
        
        # Delay-sensitive analysis
        sens_jobs = [job for job in results['completed_jobs'] 
                    if job.task.name in delay_sensitive_tasks]
        sens_latencies = [job.response_time for job in sens_jobs if job.response_time]
        sens_missed = sum(1 for job in sens_jobs if job.missed_deadline)
        
        if sens_latencies:
            print(f"  Delay-Sensitive Tasks (PIR, Button, Ultra):")
            print(f"    Average Latency: {np.mean(sens_latencies):.2f} ms")
            print(f"    Max Latency: {np.max(sens_latencies):.2f} ms")
            print(f"    Min Latency: {np.min(sens_latencies):.2f} ms")
            print(f"    Missed Deadlines: {sens_missed}/{len(sens_jobs)}")
            print(f"    Success Rate: {((len(sens_jobs)-sens_missed)/len(sens_jobs)*100):.1f}%")
        
        # Delay-tolerant analysis
        tol_jobs = [job for job in results['completed_jobs'] 
                   if job.task.name in delay_tolerant_tasks]
        tol_latencies = [job.response_time for job in tol_jobs if job.response_time]
        tol_missed = sum(1 for job in tol_jobs if job.missed_deadline)
        
        if tol_latencies:
            print(f"  Delay-Tolerant Tasks (Sound):")
            print(f"    Average Latency: {np.mean(tol_latencies):.2f} ms")
            print(f"    Max Latency: {np.max(tol_latencies):.2f} ms")
            print(f"    Min Latency: {np.min(tol_latencies):.2f} ms")
            print(f"    Missed Deadlines: {tol_missed}/{len(tol_jobs)}")
            print(f"    Success Rate: {((len(tol_jobs)-tol_missed)/len(tol_jobs)*100):.1f}%")
    
    print("\n" + "="*80)

def visualize_deadline_miss_timeline(results_edf, results_rm, results_fifo):
    """Show when deadline misses occur over time"""
    fig, axes = plt.subplots(3, 1, figsize=(16, 10), sharex=True)
    
    algorithms = [('EDF', results_edf, '#FF6B6B'), 
                  ('RM', results_rm, '#4ECDC4'), 
                  ('FIFO', results_fifo, '#45B7D1')]
    
    task_names = ['Ultra', 'PIR', 'Button', 'Sound']
    task_colors = {'Ultra': '#FF6B6B', 'PIR': '#45B7D1', 'Button': '#FFA07A', 'Sound': '#4ECDC4'}
    
    for idx, (name, results, color) in enumerate(algorithms):
        ax = axes[idx]
        
        # Get missed deadline events
        missed_jobs = [job for job in results['completed_jobs'] if job.missed_deadline]
        
        if missed_jobs:
            times = [job.finish_time for job in missed_jobs]
            tasks = [job.task.name for job in missed_jobs]
            
            # Plot missed deadlines as scatter
            for task in task_names:
                task_times = [t for t, tn in zip(times, tasks) if tn == task]
                task_y = [task_names.index(task)] * len(task_times)
                if task_times:
                    ax.scatter(task_times, task_y, c=task_colors[task], s=100, 
                             marker='X', edgecolors='black', linewidth=1.5, 
                             label=f'{task} ({len(task_times)} misses)', alpha=0.8)
        
        ax.set_ylabel(f'{name}', fontsize=11, fontweight='bold')
        ax.set_yticks(range(len(task_names)))
        ax.set_yticklabels(task_names)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, 10000)  # First 10 seconds
        
        if missed_jobs:
            ax.legend(loc='upper right', fontsize=9)
            ax.set_title(f'{name}: {len(missed_jobs)} Total Deadline Misses', 
                        fontsize=11, fontweight='bold')
        else:
            ax.set_title(f'{name}: No Deadline Misses ✓', 
                        fontsize=11, fontweight='bold', color='green')
    
    axes[2].set_xlabel('Time (ms)', fontsize=11, fontweight='bold')
    fig.suptitle('Deadline Miss Timeline (First 10 seconds)', fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig('deadline_miss_timeline.png', dpi=300, bbox_inches='tight')
    print(f"Saved deadline_miss_timeline.png")

def visualize_latency_heatmap(results_edf, results_rm, results_fifo):
    """Create a heatmap showing latency patterns over time"""
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    
    algorithms = [('EDF', results_edf), ('RM', results_rm), ('FIFO', results_fifo)]
    tasks = ['Ultra', 'PIR', 'Button', 'Sound']
    
    time_window = 10000  # First 10 seconds
    bin_size = 500  # 500ms bins
    num_bins = time_window // bin_size
    
    for idx, (name, results) in enumerate(algorithms):
        ax = axes[idx]
        
        # Create matrix: tasks x time_bins
        latency_matrix = np.zeros((len(tasks), num_bins))
        count_matrix = np.zeros((len(tasks), num_bins))
        
        for job in results['completed_jobs']:
            if job.finish_time < time_window and job.response_time:
                task_idx = tasks.index(job.task.name)
                time_bin = int(job.finish_time // bin_size)
                if time_bin < num_bins:
                    latency_matrix[task_idx, time_bin] += job.response_time
                    count_matrix[task_idx, time_bin] += 1
        
        # Calculate average latency per bin
        with np.errstate(divide='ignore', invalid='ignore'):
            avg_latency = np.where(count_matrix > 0, latency_matrix / count_matrix, 0)
        
        # Plot heatmap
        im = ax.imshow(avg_latency, aspect='auto', cmap='RdYlGn_r', interpolation='nearest')
        ax.set_yticks(range(len(tasks)))
        ax.set_yticklabels(tasks)
        ax.set_xlabel('Time Window (500ms bins)', fontsize=10)
        ax.set_title(f'{name} Latency Heatmap', fontsize=12, fontweight='bold')
        
        # Add colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label('Avg Latency (ms)', fontsize=9)
        
        # Add grid
        ax.set_xticks(np.arange(num_bins))
        ax.set_xticklabels([f'{i*bin_size}' for i in range(num_bins)], rotation=45, fontsize=8)
        ax.grid(False)
    
    plt.tight_layout()
    plt.savefig('latency_heatmap.png', dpi=300, bbox_inches='tight')
    print(f"Saved latency_heatmap.png")

def visualize_schedulability_analysis(results_edf, results_rm, results_fifo):
    """Show schedulability metrics and CPU load analysis"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    algorithms = [('EDF', results_edf, '#FF6B6B'), 
                  ('RM', results_rm, '#4ECDC4'), 
                  ('FIFO', results_fifo, '#45B7D1')]
    
    # 1. Success Rate by Task
    ax = axes[0, 0]
    tasks = ['Ultra', 'PIR', 'Button', 'Sound']
    x = np.arange(len(tasks))
    width = 0.25
    
    for i, (name, results, color) in enumerate(algorithms):
        success_rates = []
        for task in tasks:
            task_jobs = [job for job in results['completed_jobs'] if job.task.name == task]
            missed = sum(1 for job in task_jobs if job.missed_deadline)
            success_rate = ((len(task_jobs) - missed) / len(task_jobs) * 100) if task_jobs else 0
            success_rates.append(success_rate)
        
        ax.bar(x + i*width, success_rates, width, label=name, color=color, 
               edgecolor='black', alpha=0.8)
    
    ax.set_ylabel('Success Rate (%)', fontsize=10, fontweight='bold')
    ax.set_title('Deadline Success Rate by Task', fontsize=12, fontweight='bold')
    ax.set_xticks(x + width)
    ax.set_xticklabels(tasks)
    ax.set_ylim(0, 105)
    ax.axhline(y=100, color='green', linestyle='--', alpha=0.5)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    # 2. Latency Reduction (compared to FIFO baseline)
    ax = axes[0, 1]
    fifo_avg = results_fifo['avg_response_time']
    
    latency_reduction = []
    algo_names = []
    colors_bar = []
    
    for name, results, color in algorithms:
        if name != 'FIFO':
            reduction = ((fifo_avg - results['avg_response_time']) / fifo_avg) * 100
            latency_reduction.append(reduction)
            algo_names.append(name)
            colors_bar.append(color)
    
    bars = ax.bar(algo_names, latency_reduction, color=colors_bar, 
                  edgecolor='black', linewidth=1.5, alpha=0.8)
    
    for bar, value in zip(bars, latency_reduction):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 1,
               f'{value:.1f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    ax.set_ylabel('Latency Reduction (%)', fontsize=10, fontweight='bold')
    ax.set_title('Latency Reduction vs FIFO Baseline', fontsize=12, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    ax.axhline(y=0, color='black', linestyle='-', linewidth=1)
    
    # 3. Jitter Analysis (variation in response time)
    ax = axes[1, 0]
    jitters = []
    algo_names_all = []
    colors_all = []
    
    for name, results, color in algorithms:
        response_times = [job.response_time for job in results['completed_jobs'] if job.response_time]
        jitter = np.std(response_times) if response_times else 0
        jitters.append(jitter)
        algo_names_all.append(name)
        colors_all.append(color)
    
    bars = ax.bar(algo_names_all, jitters, color=colors_all, 
                  edgecolor='black', linewidth=1.5, alpha=0.8)
    
    for bar, value in zip(bars, jitters):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 1,
               f'{value:.1f}ms', ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    ax.set_ylabel('Jitter (Std Dev of Latency, ms)', fontsize=10, fontweight='bold')
    ax.set_title('Latency Jitter (Lower is Better)', fontsize=12, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    
    # 4. Overall Performance Score
    ax = axes[1, 1]
    
    # Calculate composite score (lower is better)
    scores = []
    for name, results, color in algorithms:
        # Normalize metrics (0-100 scale, lower is better)
        miss_score = (results['missed_deadlines'] / results['total_jobs']) * 100 if results['total_jobs'] > 0 else 0
        latency_score = (results['avg_response_time'] / 300) * 100  # Normalize by 300ms
        jitter_score = (np.std([job.response_time for job in results['completed_jobs'] if job.response_time]) / 100) * 100
        
        # Weighted composite (lower is better)
        composite = (miss_score * 0.5) + (latency_score * 0.3) + (jitter_score * 0.2)
        scores.append(composite)
    
    # Invert for display (higher bars = better performance)
    performance_scores = [100 - s for s in scores]
    
    bars = ax.bar(algo_names_all, performance_scores, color=colors_all, 
                  edgecolor='black', linewidth=1.5, alpha=0.8)
    
    for bar, value in zip(bars, performance_scores):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 1,
               f'{value:.1f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    ax.set_ylabel('Performance Score (Higher is Better)', fontsize=10, fontweight='bold')
    ax.set_title('Overall Performance Score', fontsize=12, fontweight='bold')
    ax.set_ylim(0, 105)
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('schedulability_analysis.png', dpi=300, bbox_inches='tight')
    print(f"Saved schedulability_analysis.png")

def visualize_qos_metrics(results_edf, results_rm, results_fifo):
    """Quality of Service metrics visualization"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    algorithms = [('EDF', results_edf, '#FF6B6B'), 
                  ('RM', results_rm, '#4ECDC4'), 
                  ('FIFO', results_fifo, '#45B7D1')]
    
    # 1. Throughput (jobs completed per second)
    ax = axes[0, 0]
    throughputs = []
    for name, results, color in algorithms:
        throughput = (results['total_jobs'] / 30)  # jobs per second (30 second simulation)
        throughputs.append(throughput)
    
    bars = ax.bar([n for n, _, _ in algorithms], throughputs, 
                  color=[c for _, _, c in algorithms], edgecolor='black', alpha=0.8)
    
    for bar, value in zip(bars, throughputs):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
               f'{value:.1f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    ax.set_ylabel('Throughput (jobs/sec)', fontsize=10, fontweight='bold')
    ax.set_title('System Throughput', fontsize=12, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    
    # 2. Reliability (percentage of jobs meeting deadlines)
    ax = axes[0, 1]
    reliability = []
    for name, results, color in algorithms:
        rel = ((results['total_jobs'] - results['missed_deadlines']) / results['total_jobs'] * 100) if results['total_jobs'] > 0 else 0
        reliability.append(rel)
    
    bars = ax.bar([n for n, _, _ in algorithms], reliability, 
                  color=[c for _, _, c in algorithms], edgecolor='black', alpha=0.8)
    
    for bar, value in zip(bars, reliability):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 1,
               f'{value:.1f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    ax.set_ylabel('Reliability (%)', fontsize=10, fontweight='bold')
    ax.set_title('System Reliability (Deadline Met %)', fontsize=12, fontweight='bold')
    ax.set_ylim(0, 105)
    ax.axhline(y=100, color='green', linestyle='--', alpha=0.5)
    ax.grid(axis='y', alpha=0.3)
    
    # 3. Predictability (coefficient of variation)
    ax = axes[1, 0]
    predictability = []
    for name, results, color in algorithms:
        response_times = [job.response_time for job in results['completed_jobs'] if job.response_time]
        if response_times:
            cv = (np.std(response_times) / np.mean(response_times)) * 100  # Coefficient of variation
            predictability.append(cv)
        else:
            predictability.append(0)
    
    bars = ax.bar([n for n, _, _ in algorithms], predictability, 
                  color=[c for _, _, c in algorithms], edgecolor='black', alpha=0.8)
    
    for bar, value in zip(bars, predictability):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 1,
               f'{value:.1f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    ax.set_ylabel('Coefficient of Variation (%)', fontsize=10, fontweight='bold')
    ax.set_title('Response Time Predictability (Lower is Better)', fontsize=12, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    
    # 4. QoS Summary Radar Chart
    ax = axes[1, 1]
    
    categories = ['Reliability', 'Low Latency', 'Predictability', 'CPU Efficiency', 'Throughput']
    num_vars = len(categories)
    
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    angles += angles[:1]
    
    ax = plt.subplot(2, 2, 4, projection='polar')
    
    for name, results, color in algorithms:
        # Normalize all metrics to 0-100 scale
        rel = ((results['total_jobs'] - results['missed_deadlines']) / results['total_jobs'] * 100) if results['total_jobs'] > 0 else 0
        lat = 100 - min(100, (results['avg_response_time'] / 300) * 100)  # Lower is better, invert
        response_times = [job.response_time for job in results['completed_jobs'] if job.response_time]
        pred = 100 - min(100, (np.std(response_times) / np.mean(response_times)) * 100) if response_times else 0
        cpu_eff = results['cpu_utilization']
        thr = min(100, (results['total_jobs'] / 30) * 5)  # Scale throughput
        
        values = [rel, lat, pred, cpu_eff, thr]
        values += values[:1]
        
        ax.plot(angles, values, 'o-', linewidth=2, label=name, color=color)
        ax.fill(angles, values, alpha=0.15, color=color)
    
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_title('QoS Summary (Normalized 0-100)', fontsize=12, fontweight='bold', pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=9)
    ax.grid(True)
    
    plt.tight_layout()
    plt.savefig('qos_metrics.png', dpi=300, bbox_inches='tight')
    print(f"Saved qos_metrics.png")

def create_all_visualizations(results_edf, results_rm, results_fifo):
    """Generate all visualization plots"""
    print("\n" + "="*60)
    print("GENERATING VISUALIZATIONS")
    print("="*60)
    
    # Gantt charts for each algorithm (first 5000ms for better visibility)
    visualize_gantt_chart(results_edf, 'EDF', max_time=5000)
    visualize_gantt_chart(results_rm, 'RM', max_time=5000)
    visualize_gantt_chart(results_fifo, 'FIFO', max_time=5000)
    
    # Comparison metrics
    visualize_comparison_metrics(results_edf, results_rm, results_fifo)
    
    # Task statistics
    visualize_task_statistics(results_edf, results_rm, results_fifo)
    
    # Response time distribution
    visualize_response_time_distribution(results_edf, results_rm, results_fifo)
    
    # Utility curves and analysis
    visualize_utility_curves(results_edf, results_rm, results_fifo)
    visualize_cumulative_utility(results_edf, results_rm, results_fifo)
    visualize_per_task_utility(results_edf, results_rm, results_fifo)
    
    # M2M Latency Analysis (CRITICAL for your project)
    visualize_latency_analysis(results_edf, results_rm, results_fifo)
    
    # NEW: Advanced visualizations
    visualize_deadline_miss_timeline(results_edf, results_rm, results_fifo)
    visualize_latency_heatmap(results_edf, results_rm, results_fifo)
    visualize_schedulability_analysis(results_edf, results_rm, results_fifo)
    visualize_qos_metrics(results_edf, results_rm, results_fifo)
    
    print("="*60)
    print("All visualizations saved successfully!")
    print("="*60)
    
    # Print latency summary
    print_latency_summary(results_edf, results_rm, results_fifo)

if __name__ == "__main__":
    main()    








