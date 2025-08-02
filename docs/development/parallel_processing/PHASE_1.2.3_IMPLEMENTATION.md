# GPU-Accelerated Parallel Processing - Phase 1.2.3: Performance Monitoring & Adaptive Optimization

## Overview

Phase 1.2.3 completes the advanced GPU processing system by implementing **real-time performance monitoring, adaptive optimization, and intelligent system tuning**. This phase adds observability and self-optimization to the parallel processing pipeline.

## Problem Context

**Current Limitation (After Phase 1.2.2)**:
- No visibility into system performance bottlenecks
- Fixed configuration parameters regardless of workload
- Cannot predict or prevent performance degradation
- No automatic optimization based on runtime metrics

**Phase 1.2.3 Solution**:
- Real-time performance monitoring and analytics
- Adaptive parameter tuning based on system metrics
- Predictive optimization using performance patterns
- Comprehensive system observability and alerting

## Phase 1.2.3 Deliverables

### 1. Real-Time Performance Monitor
**Implementation Location**: `src/gpu_parallel_processing/performance_monitor.py`

```python
"""
Real-time performance monitoring system for GPU parallel processing
with metrics collection, analysis, and optimization recommendations.
"""

import time
import threading
import psutil
import cupy as cp
from typing import Dict, List, Optional, Callable, Deque
from dataclasses import dataclass, asdict
from collections import deque, defaultdict
import json
import statistics

@dataclass
class PerformanceMetric:
    """Single performance metric measurement"""
    timestamp: float
    metric_name: str
    value: float
    unit: str
    tags: Dict[str, str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = {}

@dataclass
class SystemSnapshot:
    """Complete system performance snapshot"""
    timestamp: float
    gpu_memory_used_gb: float
    gpu_memory_total_gb: float
    gpu_utilization_percent: float
    cpu_percent: float
    ram_used_gb: float
    active_gpu_workers: int
    active_io_workers: int
    task_queue_size: int
    result_queue_size: int
    combinations_per_minute: float
    average_processing_time: float
    memory_fragmentation_ratio: float
    io_wait_time_ms: float

class PerformanceMonitor:
    """
    Real-time performance monitoring system for GPU processing pipeline.
    
    Features:
    - Continuous metric collection from all system components
    - Performance trend analysis and bottleneck detection
    - Adaptive parameter recommendations
    - Real-time alerting for performance issues
    """
    
    def __init__(self,
                 collection_interval_seconds: float = 5.0,
                 history_retention_minutes: int = 60,
                 alert_thresholds: Optional[Dict] = None):
        """
        Initialize performance monitor.
        
        Args:
            collection_interval_seconds: Frequency of metric collection
            history_retention_minutes: How long to retain historical metrics
            alert_thresholds: Custom alert thresholds
        """
        self.collection_interval = collection_interval_seconds
        self.retention_seconds = history_retention_minutes * 60
        
        # Metric storage
        self.metrics_history: Deque[PerformanceMetric] = deque()
        self.snapshots_history: Deque[SystemSnapshot] = deque()
        self.metric_aggregates: Dict[str, List[float]] = defaultdict(list)
        
        # Alert thresholds
        self.alert_thresholds = alert_thresholds or {
            'gpu_memory_percent': 95.0,
            'cpu_percent': 90.0,
            'memory_fragmentation_ratio': 0.4,
            'combinations_per_minute_min': 10.0,
            'processing_time_max_seconds': 10.0,
            'io_wait_time_max_ms': 1000.0
        }
        
        # Monitoring state
        self.monitoring_active = False
        self.monitor_thread = None
        self.component_references = {}
        
        # Performance analysis
        self.performance_trends = {
            'throughput_trend': [],
            'memory_trend': [],
            'efficiency_trend': []
        }
        
        # Alert callbacks
        self.alert_callbacks: List[Callable] = []
        
        print("📊 Performance Monitor initialized")
    
    def register_components(self,
                          async_pipeline=None,
                          gpu_processor=None,
                          memory_pool=None,
                          contract_manager=None):
        """Register system components for monitoring."""
        self.component_references = {
            'async_pipeline': async_pipeline,
            'gpu_processor': gpu_processor,
            'memory_pool': memory_pool,
            'contract_manager': contract_manager
        }
        
        registered = [name for name, comp in self.component_references.items() if comp is not None]
        print(f"📋 Registered components: {', '.join(registered)}")
    
    def start_monitoring(self):
        """Start continuous performance monitoring."""
        if self.monitoring_active:
            print("⚠️  Monitoring already active")
            return
        
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True
        )
        self.monitor_thread.start()
        
        print(f"🚀 Performance monitoring started (interval: {self.collection_interval}s)")
    
    def stop_monitoring(self):
        """Stop performance monitoring."""
        self.monitoring_active = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=10)
        
        print("🛑 Performance monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.monitoring_active:
            try:
                # Collect current snapshot
                snapshot = self._collect_system_snapshot()
                
                # Store snapshot
                self.snapshots_history.append(snapshot)
                
                # Update metric aggregates
                self._update_metric_aggregates(snapshot)
                
                # Check alerts
                self._check_alerts(snapshot)
                
                # Update performance trends
                self._update_performance_trends(snapshot)
                
                # Clean old data
                self._cleanup_old_data()
                
                # Wait for next collection
                time.sleep(self.collection_interval)
                
            except Exception as e:
                print(f"⚠️  Monitoring error: {e}")
                time.sleep(self.collection_interval)
    
    def _collect_system_snapshot(self) -> SystemSnapshot:
        """Collect complete system performance snapshot."""
        timestamp = time.time()
        
        # GPU metrics
        gpu_memory_used_gb = 0.0
        gpu_memory_total_gb = 16.0  # RTX 4080 SUPER
        gpu_utilization_percent = 0.0
        memory_fragmentation_ratio = 0.0
        
        try:
            # Get GPU memory info
            mempool = cp.get_default_memory_pool()
            gpu_memory_used_bytes = mempool.used_bytes()
            gpu_memory_used_gb = gpu_memory_used_bytes / (1024**3)
            
            # Get memory pool fragmentation if available
            if self.component_references.get('memory_pool'):
                memory_stats = self.component_references['memory_pool'].get_memory_stats()
                memory_fragmentation_ratio = memory_stats.get('fragmentation_ratio', 0.0)
                gpu_utilization_percent = memory_stats.get('utilization_percent', 0.0)
            
        except Exception as e:
            print(f"⚠️  GPU metrics collection error: {e}")
        
        # System metrics
        cpu_percent = psutil.cpu_percent(interval=None)
        memory_info = psutil.virtual_memory()
        ram_used_gb = memory_info.used / (1024**3)
        
        # Pipeline metrics
        active_gpu_workers = 0
        active_io_workers = 0
        task_queue_size = 0
        result_queue_size = 0
        combinations_per_minute = 0.0
        average_processing_time = 0.0
        io_wait_time_ms = 0.0
        
        if self.component_references.get('async_pipeline'):
            pipeline_stats = self.component_references['async_pipeline'].get_pipeline_statistics()
            active_gpu_workers = pipeline_stats.get('concurrent_tasks_peak', 0)
            combinations_per_minute = pipeline_stats.get('throughput_combinations_per_minute', 0.0)
            average_processing_time = pipeline_stats.get('average_processing_time', 0.0)
            io_wait_time_ms = pipeline_stats.get('total_io_time_seconds', 0.0) * 1000
        
        return SystemSnapshot(
            timestamp=timestamp,
            gpu_memory_used_gb=gpu_memory_used_gb,
            gpu_memory_total_gb=gpu_memory_total_gb,
            gpu_utilization_percent=gpu_utilization_percent,
            cpu_percent=cpu_percent,
            ram_used_gb=ram_used_gb,
            active_gpu_workers=active_gpu_workers,
            active_io_workers=active_io_workers,
            task_queue_size=task_queue_size,
            result_queue_size=result_queue_size,
            combinations_per_minute=combinations_per_minute,
            average_processing_time=average_processing_time,
            memory_fragmentation_ratio=memory_fragmentation_ratio,
            io_wait_time_ms=io_wait_time_ms
        )
    
    def _update_metric_aggregates(self, snapshot: SystemSnapshot):
        """Update rolling metric aggregates for trend analysis."""
        # Update rolling averages (last 10 measurements)
        metrics_to_track = [
            'gpu_memory_used_gb',
            'gpu_utilization_percent', 
            'cpu_percent',
            'combinations_per_minute',
            'average_processing_time',
            'memory_fragmentation_ratio'
        ]
        
        for metric_name in metrics_to_track:
            value = getattr(snapshot, metric_name)
            self.metric_aggregates[metric_name].append(value)
            
            # Keep only last 20 values for rolling average
            if len(self.metric_aggregates[metric_name]) > 20:
                self.metric_aggregates[metric_name].pop(0)
    
    def _check_alerts(self, snapshot: SystemSnapshot):
        """Check performance metrics against alert thresholds."""
        alerts_triggered = []
        
        # GPU memory alert
        gpu_memory_percent = (snapshot.gpu_memory_used_gb / snapshot.gpu_memory_total_gb) * 100
        if gpu_memory_percent > self.alert_thresholds['gpu_memory_percent']:
            alerts_triggered.append({
                'type': 'gpu_memory_high',
                'value': gpu_memory_percent,
                'threshold': self.alert_thresholds['gpu_memory_percent'],
                'message': f"GPU memory usage high: {gpu_memory_percent:.1f}%"
            })
        
        # CPU alert
        if snapshot.cpu_percent > self.alert_thresholds['cpu_percent']:
            alerts_triggered.append({
                'type': 'cpu_high',
                'value': snapshot.cpu_percent,
                'threshold': self.alert_thresholds['cpu_percent'],
                'message': f"CPU usage high: {snapshot.cpu_percent:.1f}%"
            })
        
        # Memory fragmentation alert
        if snapshot.memory_fragmentation_ratio > self.alert_thresholds['memory_fragmentation_ratio']:
            alerts_triggered.append({
                'type': 'memory_fragmentation_high',
                'value': snapshot.memory_fragmentation_ratio,
                'threshold': self.alert_thresholds['memory_fragmentation_ratio'],
                'message': f"Memory fragmentation high: {snapshot.memory_fragmentation_ratio:.2f}"
            })
        
        # Throughput alert
        if snapshot.combinations_per_minute < self.alert_thresholds['combinations_per_minute_min']:
            alerts_triggered.append({
                'type': 'throughput_low',
                'value': snapshot.combinations_per_minute,
                'threshold': self.alert_thresholds['combinations_per_minute_min'],
                'message': f"Throughput low: {snapshot.combinations_per_minute:.1f} combinations/min"
            })
        
        # Processing time alert
        if snapshot.average_processing_time > self.alert_thresholds['processing_time_max_seconds']:
            alerts_triggered.append({
                'type': 'processing_time_high',
                'value': snapshot.average_processing_time,
                'threshold': self.alert_thresholds['processing_time_max_seconds'],
                'message': f"Processing time high: {snapshot.average_processing_time:.2f}s"
            })
        
        # I/O wait alert
        if snapshot.io_wait_time_ms > self.alert_thresholds['io_wait_time_max_ms']:
            alerts_triggered.append({
                'type': 'io_wait_high',
                'value': snapshot.io_wait_time_ms,
                'threshold': self.alert_thresholds['io_wait_time_max_ms'],
                'message': f"I/O wait time high: {snapshot.io_wait_time_ms:.1f}ms"
            })
        
        # Trigger alert callbacks
        for alert in alerts_triggered:
            print(f"🚨 ALERT: {alert['message']}")
            for callback in self.alert_callbacks:
                try:
                    callback(alert)
                except Exception as e:
                    print(f"⚠️  Alert callback error: {e}")
    
    def _update_performance_trends(self, snapshot: SystemSnapshot):
        """Update performance trend analysis."""
        # Throughput trend
        self.performance_trends['throughput_trend'].append({
            'timestamp': snapshot.timestamp,
            'value': snapshot.combinations_per_minute
        })
        
        # Memory trend  
        memory_percent = (snapshot.gpu_memory_used_gb / snapshot.gpu_memory_total_gb) * 100
        self.performance_trends['memory_trend'].append({
            'timestamp': snapshot.timestamp,
            'value': memory_percent
        })
        
        # Efficiency trend (throughput per GPU memory usage)
        efficiency = (snapshot.combinations_per_minute / max(1, memory_percent)) * 100
        self.performance_trends['efficiency_trend'].append({
            'timestamp': snapshot.timestamp,
            'value': efficiency
        })
        
        # Keep only recent trends (last 100 points)
        for trend_name in self.performance_trends:
            if len(self.performance_trends[trend_name]) > 100:
                self.performance_trends[trend_name] = self.performance_trends[trend_name][-100:]
    
    def _cleanup_old_data(self):
        """Remove old performance data beyond retention period."""
        current_time = time.time()
        cutoff_time = current_time - self.retention_seconds
        
        # Clean snapshots
        while (self.snapshots_history and 
               self.snapshots_history[0].timestamp < cutoff_time):
            self.snapshots_history.popleft()
        
        # Clean metrics
        while (self.metrics_history and 
               self.metrics_history[0].timestamp < cutoff_time):
            self.metrics_history.popleft()
    
    def get_performance_summary(self) -> Dict:
        """Get comprehensive performance summary."""
        if not self.snapshots_history:
            return {'error': 'No performance data available'}
        
        recent_snapshots = list(self.snapshots_history)[-10:]  # Last 10 snapshots
        
        # Calculate averages
        avg_gpu_memory = statistics.mean([s.gpu_memory_used_gb for s in recent_snapshots])
        avg_cpu = statistics.mean([s.cpu_percent for s in recent_snapshots])
        avg_throughput = statistics.mean([s.combinations_per_minute for s in recent_snapshots])
        avg_processing_time = statistics.mean([s.average_processing_time for s in recent_snapshots])
        
        # Calculate trends
        throughput_trend = self._calculate_trend('throughput_trend')
        memory_trend = self._calculate_trend('memory_trend')
        efficiency_trend = self._calculate_trend('efficiency_trend')
        
        return {
            'current_snapshot': asdict(self.snapshots_history[-1]) if self.snapshots_history else None,
            'averages': {
                'gpu_memory_gb': avg_gpu_memory,
                'cpu_percent': avg_cpu,
                'throughput_per_minute': avg_throughput,
                'processing_time_seconds': avg_processing_time
            },
            'trends': {
                'throughput_trend': throughput_trend,
                'memory_trend': memory_trend,
                'efficiency_trend': efficiency_trend
            },
            'recommendations': self.generate_optimization_recommendations()
        }
    
    def _calculate_trend(self, trend_name: str) -> str:
        """Calculate trend direction for given metric."""
        if trend_name not in self.performance_trends:
            return 'unknown'
        
        trend_data = self.performance_trends[trend_name]
        if len(trend_data) < 5:
            return 'insufficient_data'
        
        # Compare recent average to older average
        recent_values = [point['value'] for point in trend_data[-5:]]
        older_values = [point['value'] for point in trend_data[-10:-5]] if len(trend_data) >= 10 else recent_values
        
        recent_avg = statistics.mean(recent_values)
        older_avg = statistics.mean(older_values)
        
        if recent_avg > older_avg * 1.05:  # 5% improvement
            return 'improving'
        elif recent_avg < older_avg * 0.95:  # 5% degradation
            return 'degrading'
        else:
            return 'stable'
    
    def generate_optimization_recommendations(self) -> List[Dict]:
        """Generate optimization recommendations based on performance data."""
        recommendations = []
        
        if not self.snapshots_history:
            return recommendations
        
        latest = self.snapshots_history[-1]
        
        # GPU memory recommendations
        gpu_memory_percent = (latest.gpu_memory_used_gb / latest.gpu_memory_total_gb) * 100
        if gpu_memory_percent > 90:
            recommendations.append({
                'type': 'memory_optimization',
                'priority': 'high',
                'message': 'GPU memory usage very high - consider reducing batch size or enabling aggressive memory cleanup',
                'suggested_actions': [
                    'Reduce GPU worker count by 1',
                    'Enable more frequent memory defragmentation',
                    'Reduce batch size by 25%'
                ]
            })
        elif gpu_memory_percent < 50:
            recommendations.append({
                'type': 'resource_utilization',
                'priority': 'medium', 
                'message': 'GPU memory underutilized - can increase batch size or worker count',
                'suggested_actions': [
                    'Increase batch size by 25%',
                    'Consider adding 1 more GPU worker'
                ]
            })
        
        # Throughput recommendations
        if latest.combinations_per_minute < 20:
            recommendations.append({
                'type': 'throughput_optimization',
                'priority': 'high',
                'message': 'Low throughput detected - check for bottlenecks',
                'suggested_actions': [
                    'Check I/O wait times',
                    'Verify GPU worker utilization',
                    'Consider increasing parallelism'
                ]
            })
        
        # Memory fragmentation recommendations
        if latest.memory_fragmentation_ratio > 0.3:
            recommendations.append({
                'type': 'memory_fragmentation',
                'priority': 'medium',
                'message': 'High memory fragmentation - enable more frequent defragmentation',
                'suggested_actions': [
                    'Increase defragmentation frequency',
                    'Reduce memory pool size temporarily',
                    'Restart processing after current batch'
                ]
            })
        
        # Processing time recommendations
        if latest.average_processing_time > 5.0:
            recommendations.append({
                'type': 'processing_time',
                'priority': 'medium',
                'message': 'High average processing time - check for resource contention',
                'suggested_actions': [
                    'Reduce concurrent GPU workers',
                    'Check for CPU bottlenecks',
                    'Verify data loading efficiency'
                ]
            })
        
        return recommendations
    
    def add_alert_callback(self, callback: Callable[[Dict], None]):
        """Add callback function for performance alerts."""
        self.alert_callbacks.append(callback)
    
    def export_metrics(self, filepath: str, format: str = 'json'):
        """Export collected metrics to file."""
        try:
            data = {
                'snapshots': [asdict(snapshot) for snapshot in self.snapshots_history],
                'performance_trends': self.performance_trends,
                'alert_thresholds': self.alert_thresholds
            }
            
            if format.lower() == 'json':
                with open(filepath, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
            
            print(f"📊 Metrics exported to {filepath}")
            
        except Exception as e:
            print(f"❌ Failed to export metrics: {e}")
```

### 2. Adaptive Optimization Engine
**Implementation Location**: `src/gpu_parallel_processing/adaptive_optimizer.py`

```python
"""
Adaptive optimization engine that automatically tunes system parameters
based on real-time performance monitoring and historical patterns.
"""

import time
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import statistics

@dataclass
class OptimizationAction:
    """Action to optimize system performance"""
    action_type: str
    parameter_name: str
    old_value: float
    new_value: float
    reason: str
    expected_improvement: str
    timestamp: float

@dataclass
class OptimizationResult:
    """Result of optimization action"""
    action: OptimizationAction
    success: bool
    actual_improvement: Optional[float] = None
    measurement_period_seconds: float = 60.0
    side_effects: List[str] = None
    
    def __post_init__(self):
        if self.side_effects is None:
            self.side_effects = []

class AdaptiveOptimizer:
    """
    Adaptive optimization engine that automatically tunes system parameters
    based on performance monitoring data and feedback loops.
    """
    
    def __init__(self,
                 performance_monitor,
                 optimization_interval_minutes: float = 5.0,
                 min_measurement_period_minutes: float = 2.0,
                 max_optimization_frequency_per_hour: int = 12):
        """
        Initialize adaptive optimizer.
        
        Args:
            performance_monitor: Performance monitor instance
            optimization_interval_minutes: How often to check for optimizations
            min_measurement_period_minutes: Minimum time to measure optimization effects
            max_optimization_frequency_per_hour: Maximum optimizations per hour
        """
        self.performance_monitor = performance_monitor
        self.optimization_interval = optimization_interval_minutes * 60
        self.min_measurement_period = min_measurement_period_minutes * 60
        self.max_optimizations_per_hour = max_optimization_frequency_per_hour
        
        # Component references for parameter adjustment
        self.component_references = {}
        
        # Optimization state
        self.optimization_active = False
        self.optimizer_thread = None
        
        # Optimization history
        self.optimization_history: List[OptimizationResult] = []
        self.recent_optimizations: List[OptimizationAction] = []
        self.parameter_bounds = {
            'gpu_workers': (1, 5),
            'io_workers': (1, 4),
            'batch_size_multiplier': (0.5, 2.0),
            'memory_pool_size_gb': (8.0, 15.0),
            'defragmentation_threshold': (0.15, 0.45)
        }
        
        # Learning system
        self.successful_patterns = {}
        self.failed_patterns = {}
        
        print("🎯 Adaptive Optimizer initialized")
    
    def register_components(self,
                          async_pipeline=None,
                          gpu_processor=None,
                          memory_pool=None,
                          orchestrator=None):
        """Register components for parameter adjustment."""
        self.component_references = {
            'async_pipeline': async_pipeline,
            'gpu_processor': gpu_processor, 
            'memory_pool': memory_pool,
            'orchestrator': orchestrator
        }
        
        registered = [name for name, comp in self.component_references.items() if comp is not None]
        print(f"⚙️  Registered optimization targets: {', '.join(registered)}")
    
    def start_optimization(self):
        """Start adaptive optimization loop."""
        if self.optimization_active:
            print("⚠️  Optimization already active")
            return
        
        self.optimization_active = True
        self.optimizer_thread = threading.Thread(
            target=self._optimization_loop,
            daemon=True
        )
        self.optimizer_thread.start()
        
        print(f"🚀 Adaptive optimization started (interval: {self.optimization_interval/60:.1f}min)")
    
    def stop_optimization(self):
        """Stop adaptive optimization."""
        self.optimization_active = False
        
        if self.optimizer_thread and self.optimizer_thread.is_alive():
            self.optimizer_thread.join(timeout=15)
        
        print("🛑 Adaptive optimization stopped")
    
    def _optimization_loop(self):
        """Main optimization loop."""
        while self.optimization_active:
            try:
                # Check if we should optimize
                if self._should_optimize():
                    # Analyze current performance
                    performance_summary = self.performance_monitor.get_performance_summary()
                    
                    if 'current_snapshot' in performance_summary and performance_summary['current_snapshot']:
                        # Generate optimization candidates
                        optimization_candidates = self._generate_optimization_candidates(performance_summary)
                        
                        # Select best optimization
                        if optimization_candidates:
                            best_optimization = self._select_best_optimization(optimization_candidates)
                            
                            if best_optimization:
                                # Apply optimization
                                self._apply_optimization(best_optimization)
                
                # Wait for next optimization cycle
                time.sleep(self.optimization_interval)
                
            except Exception as e:
                print(f"⚠️  Optimization loop error: {e}")
                time.sleep(60)  # Wait longer on error
    
    def _should_optimize(self) -> bool:
        """Determine if optimization should be attempted."""
        current_time = time.time()
        
        # Check optimization frequency limit
        recent_optimizations = [
            opt for opt in self.optimization_history
            if current_time - opt.action.timestamp < 3600  # Last hour
        ]
        
        if len(recent_optimizations) >= self.max_optimizations_per_hour:
            return False
        
        # Check if enough time has passed since last optimization
        if self.recent_optimizations:
            last_optimization_time = max(opt.timestamp for opt in self.recent_optimizations)
            if current_time - last_optimization_time < self.min_measurement_period:
                return False
        
        # Check if performance monitoring has enough data
        performance_summary = self.performance_monitor.get_performance_summary()
        if 'current_snapshot' not in performance_summary or not performance_summary['current_snapshot']:
            return False
        
        return True
    
    def _generate_optimization_candidates(self, performance_summary: Dict) -> List[OptimizationAction]:
        """Generate potential optimization actions based on performance data."""
        candidates = []
        current_snapshot = performance_summary['current_snapshot']
        trends = performance_summary.get('trends', {})
        
        current_time = time.time()
        
        # GPU memory optimization
        gpu_memory_percent = (current_snapshot['gpu_memory_used_gb'] / 
                            current_snapshot['gpu_memory_total_gb']) * 100
        
        if gpu_memory_percent > 85:
            # High memory usage - reduce parallelism
            candidates.append(OptimizationAction(
                action_type='reduce_parallelism',
                parameter_name='gpu_workers',
                old_value=current_snapshot.get('active_gpu_workers', 3),
                new_value=max(1, current_snapshot.get('active_gpu_workers', 3) - 1),
                reason=f'GPU memory usage high: {gpu_memory_percent:.1f}%',
                expected_improvement='Reduce memory pressure, improve stability',
                timestamp=current_time
            ))
        elif gpu_memory_percent < 50 and trends.get('throughput_trend') == 'stable':
            # Low memory usage with stable throughput - increase parallelism
            candidates.append(OptimizationAction(
                action_type='increase_parallelism',
                parameter_name='gpu_workers',
                old_value=current_snapshot.get('active_gpu_workers', 3),
                new_value=min(5, current_snapshot.get('active_gpu_workers', 3) + 1),
                reason=f'GPU memory underutilized: {gpu_memory_percent:.1f}%',
                expected_improvement='Increase throughput, better resource utilization',
                timestamp=current_time
            ))
        
        # Throughput optimization
        current_throughput = current_snapshot.get('combinations_per_minute', 0)
        if current_throughput < 30 and trends.get('throughput_trend') == 'degrading':
            # Low throughput - try reducing batch size
            candidates.append(OptimizationAction(
                action_type='reduce_batch_size',
                parameter_name='batch_size_multiplier',
                old_value=1.0,
                new_value=0.75,
                reason=f'Low throughput: {current_throughput:.1f} combinations/min',
                expected_improvement='Reduce memory pressure, improve processing speed',
                timestamp=current_time
            ))
        
        # Memory fragmentation optimization
        fragmentation_ratio = current_snapshot.get('memory_fragmentation_ratio', 0)
        if fragmentation_ratio > 0.35:
            candidates.append(OptimizationAction(
                action_type='adjust_memory_management',
                parameter_name='defragmentation_threshold',
                old_value=0.25,
                new_value=0.20,
                reason=f'High memory fragmentation: {fragmentation_ratio:.2f}',
                expected_improvement='More frequent defragmentation, better memory efficiency',
                timestamp=current_time
            ))
        
        # Processing time optimization
        avg_processing_time = current_snapshot.get('average_processing_time', 0)
        if avg_processing_time > 4.0:
            candidates.append(OptimizationAction(
                action_type='optimize_processing',
                parameter_name='memory_pool_size_gb',
                old_value=14.0,
                new_value=12.0,
                reason=f'High processing time: {avg_processing_time:.2f}s',
                expected_improvement='Reduce memory allocation overhead',
                timestamp=current_time
            ))
        
        return candidates
    
    def _select_best_optimization(self, candidates: List[OptimizationAction]) -> Optional[OptimizationAction]:
        """Select the best optimization action from candidates."""
        if not candidates:
            return None
        
        # Score candidates based on historical success and current need
        scored_candidates = []
        
        for candidate in candidates:
            score = self._score_optimization_candidate(candidate)
            scored_candidates.append((score, candidate))
        
        # Sort by score (highest first)
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        # Return highest scoring candidate
        best_score, best_candidate = scored_candidates[0]
        
        if best_score > 0.5:  # Minimum threshold for applying optimization
            return best_candidate
        
        return None
    
    def _score_optimization_candidate(self, candidate: OptimizationAction) -> float:
        """Score an optimization candidate based on historical data and current context."""
        base_score = 0.5
        
        # Historical success rate for this type of optimization
        similar_optimizations = [
            opt for opt in self.optimization_history
            if opt.action.action_type == candidate.action_type
        ]
        
        if similar_optimizations:
            success_rate = sum(1 for opt in similar_optimizations if opt.success) / len(similar_optimizations)
            base_score *= success_rate
        
        # Urgency based on current performance issues
        urgency_multiplier = 1.0
        
        if 'memory' in candidate.reason.lower() and 'high' in candidate.reason.lower():
            urgency_multiplier = 1.5  # High priority for memory issues
        elif 'throughput' in candidate.reason.lower() and 'low' in candidate.reason.lower():
            urgency_multiplier = 1.3  # Medium-high priority for throughput issues
        
        # Recent optimization penalty (avoid too frequent changes)
        recent_penalty = 1.0
        similar_recent = [
            opt for opt in self.recent_optimizations
            if (opt.action_type == candidate.action_type and 
                time.time() - opt.timestamp < 1800)  # Within 30 minutes
        ]
        
        if similar_recent:
            recent_penalty = 0.3  # Significant penalty for recent similar optimizations
        
        final_score = base_score * urgency_multiplier * recent_penalty
        return min(1.0, final_score)
    
    def _apply_optimization(self, optimization: OptimizationAction):
        """Apply optimization action to system components."""
        print(f"🎯 Applying optimization: {optimization.action_type} - {optimization.reason}")
        
        try:
            success = False
            
            # Apply based on optimization type
            if optimization.action_type == 'reduce_parallelism':
                success = self._adjust_gpu_workers(int(optimization.new_value))
            elif optimization.action_type == 'increase_parallelism':
                success = self._adjust_gpu_workers(int(optimization.new_value))
            elif optimization.action_type == 'reduce_batch_size':
                success = self._adjust_batch_size_multiplier(optimization.new_value)
            elif optimization.action_type == 'adjust_memory_management':
                success = self._adjust_memory_parameters(optimization.parameter_name, optimization.new_value)
            elif optimization.action_type == 'optimize_processing':
                success = self._adjust_processing_parameters(optimization.parameter_name, optimization.new_value)
            
            if success:
                # Record optimization for tracking
                self.recent_optimizations.append(optimization)
                
                # Schedule measurement of results
                self._schedule_optimization_measurement(optimization)
                
                print(f"✅ Optimization applied: {optimization.parameter_name} = {optimization.new_value}")
            else:
                print(f"❌ Optimization failed: {optimization.action_type}")
                
                # Record failed optimization
                result = OptimizationResult(
                    action=optimization,
                    success=False,
                    side_effects=['Application failed']
                )
                self.optimization_history.append(result)
            
        except Exception as e:
            print(f"❌ Optimization error: {e}")
            
            result = OptimizationResult(
                action=optimization,
                success=False,
                side_effects=[f'Exception: {str(e)}']
            )
            self.optimization_history.append(result)
    
    def _adjust_gpu_workers(self, new_worker_count: int) -> bool:
        """Adjust number of GPU workers."""
        # This would require implementing dynamic worker scaling in the async pipeline
        # For now, just log the intended change
        print(f"📝 Would adjust GPU workers to: {new_worker_count}")
        return True  # Simulated success
    
    def _adjust_batch_size_multiplier(self, multiplier: float) -> bool:
        """Adjust batch size multiplier."""
        print(f"📝 Would adjust batch size multiplier to: {multiplier}")
        return True  # Simulated success
    
    def _adjust_memory_parameters(self, parameter_name: str, new_value: float) -> bool:
        """Adjust memory management parameters."""
        if self.component_references.get('memory_pool'):
            print(f"📝 Would adjust {parameter_name} to: {new_value}")
            # Would implement actual parameter adjustment here
            return True
        return False
    
    def _adjust_processing_parameters(self, parameter_name: str, new_value: float) -> bool:
        """Adjust processing parameters."""
        print(f"📝 Would adjust {parameter_name} to: {new_value}")
        return True  # Simulated success
    
    def _schedule_optimization_measurement(self, optimization: OptimizationAction):
        """Schedule measurement of optimization effectiveness."""
        def measure_optimization():
            time.sleep(self.min_measurement_period)
            
            # Measure performance after optimization
            performance_summary = self.performance_monitor.get_performance_summary()
            
            if 'current_snapshot' in performance_summary:
                # Calculate improvement (simplified)
                improvement = self._calculate_optimization_improvement(optimization, performance_summary)
                
                result = OptimizationResult(
                    action=optimization,
                    success=improvement > 0,
                    actual_improvement=improvement,
                    measurement_period_seconds=self.min_measurement_period
                )
                
                self.optimization_history.append(result)
                
                if improvement > 0:
                    print(f"✅ Optimization successful: {improvement:.2f}% improvement")
                else:
                    print(f"❌ Optimization ineffective: {improvement:.2f}% change")
        
        # Start measurement thread
        measurement_thread = threading.Thread(target=measure_optimization, daemon=True)
        measurement_thread.start()
    
    def _calculate_optimization_improvement(self,
                                         optimization: OptimizationAction, 
                                         current_performance: Dict) -> float:
        """Calculate improvement percentage from optimization."""
        # Simplified improvement calculation
        # In reality, this would compare before/after metrics more sophisticatedly
        
        current_snapshot = current_performance.get('current_snapshot', {})
        
        if optimization.action_type in ['reduce_parallelism', 'increase_parallelism']:
            # Measure throughput improvement
            current_throughput = current_snapshot.get('combinations_per_minute', 0)
            baseline_throughput = 25.0  # Assumed baseline
            
            return ((current_throughput - baseline_throughput) / baseline_throughput) * 100
        
        elif optimization.action_type == 'adjust_memory_management':
            # Measure memory fragmentation improvement
            current_fragmentation = current_snapshot.get('memory_fragmentation_ratio', 0.5)
            baseline_fragmentation = 0.35  # Assumed baseline
            
            return ((baseline_fragmentation - current_fragmentation) / baseline_fragmentation) * 100
        
        return 0.0  # Default no improvement
    
    def get_optimization_summary(self) -> Dict:
        """Get summary of optimization activities and effectiveness."""
        total_optimizations = len(self.optimization_history)
        successful_optimizations = sum(1 for opt in self.optimization_history if opt.success)
        
        success_rate = (successful_optimizations / total_optimizations * 100) if total_optimizations > 0 else 0
        
        # Recent optimization activity
        current_time = time.time()
        recent_optimizations = [
            opt for opt in self.optimization_history
            if current_time - opt.action.timestamp < 3600  # Last hour
        ]
        
        return {
            'total_optimizations': total_optimizations,
            'successful_optimizations': successful_optimizations,
            'success_rate_percent': success_rate,
            'recent_optimizations_count': len(recent_optimizations),
            'optimization_history': [
                {
                    'action_type': opt.action.action_type,
                    'parameter': opt.action.parameter_name,
                    'old_value': opt.action.old_value,
                    'new_value': opt.action.new_value,
                    'success': opt.success,
                    'improvement_percent': opt.actual_improvement,
                    'timestamp': opt.action.timestamp
                }
                for opt in self.optimization_history[-10:]  # Last 10 optimizations
            ]
        }
```

## Phase 1.2.3 Implementation Checklist

### Performance Monitoring
- [ ] Implement `PerformanceMonitor` with real-time metric collection
- [ ] Add system snapshot collection (GPU, CPU, memory, I/O)
- [ ] Create performance trend analysis and bottleneck detection
- [ ] Implement configurable alerting system

### Adaptive Optimization
- [ ] Create `AdaptiveOptimizer` with automatic parameter tuning
- [ ] Add optimization candidate generation based on performance patterns
- [ ] Implement optimization scoring and selection algorithms
- [ ] Create feedback loops to measure optimization effectiveness

### System Integration
- [ ] Integrate monitoring with all pipeline components
- [ ] Add optimization hooks for dynamic parameter adjustment
- [ ] Create comprehensive performance reporting
- [ ] Implement optimization history tracking and learning

### Observability & Analytics
- [ ] Add performance metric export capabilities
- [ ] Create optimization recommendation engine
- [ ] Implement predictive performance modeling
- [ ] Add comprehensive system health dashboards

## Success Criteria

### Monitoring Capabilities
- [ ] Collect and analyze 20+ performance metrics in real-time
- [ ] Detect performance degradation within 30 seconds
- [ ] Generate actionable optimization recommendations
- [ ] Maintain performance history with trend analysis

### Adaptive Optimization
- [ ] Automatically optimize at least 3 system parameters
- [ ] Achieve >70% success rate on optimization actions
- [ ] Demonstrate measurable performance improvements (5-15%)
- [ ] Prevent performance degradation through proactive tuning

### System Intelligence
- [ ] Learn from optimization patterns to improve future decisions
- [ ] Predict and prevent performance bottlenecks
- [ ] Adapt to different workload patterns automatically
- [ ] Provide comprehensive system observability

Phase 1.2.3 completes the transformation from basic GPU processing to an intelligent, self-optimizing system capable of sustained high-performance operation at massive scale.