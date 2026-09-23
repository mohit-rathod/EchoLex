import { writeFileSync } from "node:fs";

const datasource = { type: "prometheus", uid: "prometheus" };
const modelScope = 'job=~"vllm-.*",model_service=~"$model"';
const standardScope = 'job=~"vllm-(llm|stt)",model_service=~"$model"';
const ttsScope = 'job="vllm-tts",model_service=~"$model"';
const gpuScope = 'job="dcgm-exporter",gpu=~"$gpu"';
let panelId = 1;
let y = 0;
const panels = [];

const target = (expr, legendFormat, refId = "A", extra = {}) => ({
  expr,
  legendFormat,
  refId,
  ...extra,
});

const thresholds = (...steps) => ({
  mode: "absolute",
  steps: steps.map(([value, color]) => ({ value, color })),
});

const healthyBinary = thresholds([null, "red"], [1, "green"]);
const saturationPct = thresholds([null, "green"], [70, "yellow"], [85, "red"]);
const memoryPct = thresholds([null, "green"], [80, "yellow"], [92, "red"]);
const queueThresholds = thresholds([null, "green"], [1, "yellow"], [3, "red"]);
const gpuTempThresholds = thresholds([null, "green"], [75, "yellow"], [85, "red"]);
const cpuTempThresholds = thresholds([null, "green"], [75, "yellow"], [90, "red"]);
const kvThresholds = thresholds([null, "green"], [70, "yellow"], [90, "red"]);
const nonZeroBad = thresholds([null, "green"], [0.000001, "red"]);

const base = (type, title, x, width, height, targets = [], options = {}) => ({
  id: panelId++,
  type,
  title,
  datasource,
  gridPos: { x, y, w: width, h: height },
  targets,
  options,
  fieldConfig: { defaults: {}, overrides: [] },
});

const stat = (title, x, width, targets, {
  unit = "short",
  description = "",
  threshold = null,
  colorMode = "value",
  graphMode = "area",
  min = undefined,
  max = undefined,
  decimals = undefined,
} = {}) => {
  const p = base("stat", title, x, width, 5, targets, {
    colorMode,
    graphMode,
    justifyMode: "auto",
    orientation: "auto",
    reduceOptions: { calcs: ["lastNotNull"], fields: "", values: false },
    textMode: "auto",
  });
  p.description = description;
  p.fieldConfig.defaults = { unit, noValue: "N/A" };
  if (threshold) p.fieldConfig.defaults.thresholds = threshold;
  if (min !== undefined) p.fieldConfig.defaults.min = min;
  if (max !== undefined) p.fieldConfig.defaults.max = max;
  if (decimals !== undefined) p.fieldConfig.defaults.decimals = decimals;
  return p;
};

const gauge = (title, x, width, targets, {
  unit = "percent",
  description = "",
  threshold = saturationPct,
  min = 0,
  max = 100,
} = {}) => {
  const p = base("gauge", title, x, width, 6, targets, {
    orientation: "auto",
    reduceOptions: { calcs: ["lastNotNull"], fields: "", values: false },
    showThresholdLabels: false,
    showThresholdMarkers: true,
  });
  p.description = description;
  p.fieldConfig.defaults = { unit, noValue: "N/A", min, max, thresholds: threshold };
  return p;
};

const timeseries = (title, x, width, targets, {
  unit = "short",
  description = "",
  min = undefined,
  max = undefined,
  threshold = null,
  height = 8,
} = {}) => {
  const p = base("timeseries", title, x, width, height, targets, {
    legend: { displayMode: "table", placement: "bottom", calcs: ["lastNotNull", "mean", "max"] },
    tooltip: { mode: "multi", sort: "desc" },
  });
  p.description = description;
  p.fieldConfig.defaults = {
    unit,
    noValue: "N/A",
    custom: {
      drawStyle: "line",
      lineInterpolation: "smooth",
      lineWidth: 2,
      fillOpacity: 10,
      showPoints: "never",
      spanNulls: false,
      axisCenteredZero: false,
    },
  };
  if (min !== undefined) p.fieldConfig.defaults.min = min;
  if (max !== undefined) p.fieldConfig.defaults.max = max;
  if (threshold) p.fieldConfig.defaults.thresholds = threshold;
  return p;
};

const textPanel = (title, content, height = 4) => {
  const p = base("text", title, 0, 24, height, [], {
    mode: "markdown",
    content,
  });
  return p;
};

const row = (title, collapsed = false) => {
  panels.push({ id: panelId++, type: "row", title, collapsed, gridPos: { x: 0, y, w: 24, h: 1 }, panels: [] });
  y += 1;
};

const histAvg = (metric, scope, window = "5m", by = "model_service") =>
  `sum by (${by}) (rate(${metric}_sum{${scope}}[${window}])) / sum by (${by}) (rate(${metric}_count{${scope}}[${window}]))`;

const histQ = (metric, scope, quantile = 0.95, window = "5m", by = "model_service") =>
  `histogram_quantile(${quantile}, sum by (${by}, le) (rate(${metric}_bucket{${scope}}[${window}])))`;

const compatCounter = (metric, scope) => `${metric}_total{${scope}} or ${metric}{${scope}}`;
const compatRate = (metric, scope, window = "1m") => `rate(${metric}_total{${scope}}[${window}]) or rate(${metric}{${scope}}[${window}])`;

const standardRequestRate = `sum by (model_service) (${compatRate("vllm:request_success", standardScope, "1m")})`;
const ttsRequestRate = `sum by (model_service) (${compatRate("vllm_omni:requests_success", ttsScope, "1m")})`;
const requestRate = `${standardRequestRate} or ${ttsRequestRate}`;
const runningByModel = `sum by (model_service) (vllm:num_requests_running{${standardScope}}) or sum by (model_service) (vllm_omni:num_requests_running{${ttsScope}})`;
const waitingByModel = `sum by (model_service) (vllm:num_requests_waiting{${standardScope}}) or sum by (model_service) (vllm_omni:num_requests_waiting{${ttsScope}})`;
const totalRunning = `(sum(vllm:num_requests_running{job=~"vllm-(llm|stt)"}) or vector(0)) + (sum(vllm_omni:num_requests_running{job="vllm-tts"}) or vector(0))`;
const totalWaiting = `(sum(vllm:num_requests_waiting{job=~"vllm-(llm|stt)"}) or vector(0)) + (sum(vllm_omni:num_requests_waiting{job="vllm-tts"}) or vector(0))`;
const totalRequestRate = `(sum(${compatRate("vllm:request_success", 'job=~"vllm-(llm|stt)"', "1m")}) or vector(0)) + (sum(${compatRate("vllm_omni:requests_success", 'job="vllm-tts"', "1m")}) or vector(0))`;
const generationCounter = compatCounter("vllm:generation_tokens", standardScope);
const promptCounter = compatCounter("vllm:prompt_tokens", standardScope);
const preemptionCounter = compatCounter("vllm:num_preemptions", standardScope);
const totalPreemptionCounter = compatCounter("vllm:num_preemptions", 'job=~"vllm-(llm|stt)"');
const generationRate1m = compatRate("vllm:generation_tokens", standardScope, "1m");
const promptRate1m = compatRate("vllm:prompt_tokens", standardScope, "1m");
const preemptionRate5m = compatRate("vllm:num_preemptions", standardScope, "5m");
const totalPreemptionRate5m = compatRate("vllm:num_preemptions", 'job=~"vllm-(llm|stt)"', "5m");

const hostRamTotal = `sum(node_memory_MemTotal_bytes{job="node-exporter"})`;
const hostRamAvailable = `sum(node_memory_MemAvailable_bytes{job="node-exporter"})`;
const hostRamUsed = `(${hostRamTotal}) - (${hostRamAvailable})`;
const hostRamUsedPct = `100 * (1 - (${hostRamAvailable}) / (${hostRamTotal}))`;
const hostRamAvailablePct = `100 * (${hostRamAvailable}) / (${hostRamTotal})`;
const cpuTotalCores = `count(node_cpu_seconds_total{job="node-exporter",mode="idle"})`;
const cpuBusyCores = `sum(1 - rate(node_cpu_seconds_total{job="node-exporter",mode="idle"}[1m]))`;
const cpuUtilPct = `100 * (${cpuBusyCores}) / (${cpuTotalCores})`;
const cpuTemp = `max(node_hwmon_temp_celsius{job="node-exporter",chip=~".*(coretemp|k10temp|zenpower|cpu).*"}) or max(node_thermal_zone_temp{job="node-exporter",type=~".*(cpu|x86).*"})`;

const vramUsed = `sum(DCGM_FI_DEV_FB_USED{${gpuScope}}) * 1024 * 1024`;
const vramFree = `sum(DCGM_FI_DEV_FB_FREE{${gpuScope}}) * 1024 * 1024`;
const vramReserved = `(sum(DCGM_FI_DEV_FB_RESERVED{${gpuScope}}) or vector(0)) * 1024 * 1024`;
const vramTotal = `(${vramUsed}) + (${vramFree}) + (${vramReserved})`;
const vramUsedPct = `100 * (${vramUsed}) / (${vramTotal})`;
const vramFreePct = `100 * (${vramFree}) / (${vramTotal})`;
const gpuUtilMax = `max(DCGM_FI_DEV_GPU_UTIL{${gpuScope}})`;
const gpuTempMax = `max(DCGM_FI_DEV_GPU_TEMP{${gpuScope}})`;
const fleetKvMax = `100 * max(vllm:kv_cache_usage_perc{${standardScope}})`;

row("00 · Reliability summary");
panels.push(
  stat("Model scrape health", 0, 4, [target(`min(up{job=~"vllm-.*"})`, "all models")], {
    description: "1 means every vLLM/vLLM-Omni target is being scraped successfully.", threshold: healthyBinary, colorMode: "background", graphMode: "none", min: 0, max: 1,
  }),
  stat("Infrastructure scrape health", 4, 4, [target(`min(up{job=~"(node-exporter|dcgm-exporter|qdrant)"})`, "infra")], {
    description: "Host, GPU exporter and Qdrant scrape health.", threshold: healthyBinary, colorMode: "background", graphMode: "none", min: 0, max: 1,
  }),
  stat("Running requests · all models", 8, 4, [target(totalRunning, "running")], { description: "Current requests executing across all inference services." }),
  stat("Waiting requests · all models", 12, 4, [target(totalWaiting, "waiting")], { description: "Current queue depth across all inference services.", threshold: queueThresholds, colorMode: "background", graphMode: "none" }),
  stat("Request throughput · all models", 16, 4, [target(totalRequestRate, "completed")], { unit: "reqps", description: "Completed request throughput across LLM, STT and TTS." }),
  stat("Preemptions / min", 20, 4, [target(`sum(${totalPreemptionRate5m}) * 60`, "preemptions")], { description: "Scheduler preemptions across standard vLLM engines. Sustained non-zero values indicate resource pressure.", threshold: nonZeroBad, colorMode: "background", graphMode: "none" }),
);
y += 5;
panels.push(
  gauge("CPU utilization", 0, 4, [target(cpuUtilPct, "CPU")], { description: "Busy CPU time across all logical cores." }),
  gauge("Host RAM used", 4, 4, [target(hostRamUsedPct, "RAM")], { description: "System RAM used percentage based on MemAvailable.", threshold: memoryPct }),
  gauge("GPU compute utilization", 8, 4, [target(gpuUtilMax, "GPU")], { description: "Maximum GPU utilization among selected GPUs." }),
  gauge("VRAM used", 12, 4, [target(vramUsedPct, "VRAM")], { description: "Total selected-GPU framebuffer memory used percentage.", threshold: memoryPct }),
  gauge("Fleet KV cache · max", 16, 4, [target(fleetKvMax, "KV")], { description: "Maximum KV-cache utilization across selected standard vLLM models. Max is used instead of average so a saturated model is not hidden.", threshold: kvThresholds }),
  gauge("GPU temperature · max", 20, 4, [target(gpuTempMax, "GPU")], { unit: "celsius", description: "Maximum GPU temperature among selected GPUs.", threshold: gpuTempThresholds, min: 0, max: 100 }),
);
y += 6;

panels.push(textPanel(
  "Metric semantics · exact last-request values",
  "**Exact values for the last completed request are not retained by stock Prometheus histograms.** TTFT, E2E, TPOT, queue, prefill, decode and per-request token counts are therefore shown as **recent mean (1 minute)**, **rolling mean (5 minutes)** and/or percentiles. Current gauges such as running requests, waiting requests and KV-cache usage are exact at scrape time. To display the literal last request, emit request-level metrics/logs/traces from the caller or a request-aware proxy with a request ID and completion timestamp; do not infer it from histogram buckets.",
  4,
));
y += 4;

row("01 · Host system · CPU and memory");
panels.push(
  stat("System RAM · total", 0, 4, [target(hostRamTotal, "total")], { unit: "bytes" }),
  stat("System RAM · used", 4, 4, [target(hostRamUsed, "used")], { unit: "bytes" }),
  stat("System RAM · used %", 8, 4, [target(hostRamUsedPct, "used")], { unit: "percent", threshold: memoryPct, colorMode: "background", graphMode: "none", min: 0, max: 100 }),
  stat("System RAM · available", 12, 4, [target(hostRamAvailable, "available")], { unit: "bytes" }),
  stat("System RAM · available %", 16, 4, [target(hostRamAvailablePct, "available")], { unit: "percent", min: 0, max: 100 }),
  stat("CPU temperature · max", 20, 4, [target(cpuTemp, "CPU")], { unit: "celsius", description: "Maximum CPU-related hwmon/thermal-zone sensor when exposed by the Linux host.", threshold: cpuTempThresholds, colorMode: "background", graphMode: "none" }),
);
y += 5;
panels.push(
  stat("CPU logical cores", 0, 6, [target(cpuTotalCores, "cores")], { description: "Logical processors visible to the host exporter." }),
  stat("CPU busy cores", 6, 6, [target(cpuBusyCores, "busy cores")], { decimals: 2, description: "Equivalent number of logical CPU cores currently busy over the last minute." }),
  stat("CPU utilization %", 12, 6, [target(cpuUtilPct, "CPU")], { unit: "percent", threshold: saturationPct, colorMode: "background", graphMode: "none", min: 0, max: 100 }),
  stat("Load average · 1m", 18, 6, [target(`sum(node_load1{job="node-exporter"})`, "load")], { decimals: 2, description: "Linux 1-minute load average. Compare it with logical core count." }),
);
y += 5;
panels.push(
  timeseries("CPU utilization and busy-core pressure", 0, 12, [
    target(cpuUtilPct, "CPU utilization %", "A"),
  ], { unit: "percent", min: 0, max: 100, description: "CPU utilization trend. Use the busy-core stat above to convert percentage into effective cores." }),
  timeseries("System memory used / available", 12, 12, [
    target(`(${hostRamUsed})`, "used", "A"),
    target(`(${hostRamAvailable})`, "available", "B"),
  ], { unit: "bytes", min: 0 }),
);
y += 8;
panels.push(
  timeseries("CPU temperature sensors", 0, 12, [
    target(`node_hwmon_temp_celsius{job="node-exporter",chip=~".*(coretemp|k10temp|zenpower|cpu).*"}`, "{{chip}} / {{sensor}}", "A"),
    target(`node_thermal_zone_temp{job="node-exporter",type=~".*(cpu|x86).*"}`, "{{type}} / zone {{zone}}", "B"),
  ], { unit: "celsius", min: 0, description: "No data is expected if the host/WSL2 VM does not expose thermal sensors into /sys." }),
  timeseries("CPU load average", 12, 12, [
    target(`node_load1{job="node-exporter"}`, "1m", "A"),
    target(`node_load5{job="node-exporter"}`, "5m", "B"),
    target(`node_load15{job="node-exporter"}`, "15m", "C"),
  ], { description: "Linux scheduler load, useful for detecting CPU-side backpressure around tokenization, audio processing and data movement." }),
);
y += 8;

row("02 · NVIDIA GPU · VRAM, compute, thermal and PCIe");
panels.push(
  stat("VRAM · total", 0, 4, [target(vramTotal, "selected GPU(s)")], { unit: "bytes", description: "Used + free + reserved framebuffer memory." }),
  stat("VRAM · used", 4, 4, [target(vramUsed, "used")], { unit: "bytes" }),
  stat("VRAM · used %", 8, 4, [target(vramUsedPct, "used")], { unit: "percent", threshold: memoryPct, colorMode: "background", graphMode: "none", min: 0, max: 100 }),
  stat("VRAM · free", 12, 4, [target(vramFree, "free")], { unit: "bytes" }),
  stat("VRAM · free %", 16, 4, [target(vramFreePct, "free")], { unit: "percent", min: 0, max: 100 }),
  stat("GPU temperature · max", 20, 4, [target(gpuTempMax, "GPU")], { unit: "celsius", threshold: gpuTempThresholds, colorMode: "background", graphMode: "none" }),
);
y += 5;
panels.push(
  gauge("GPU utilization", 0, 6, [target(`max(DCGM_FI_DEV_GPU_UTIL{${gpuScope}})`, "GPU")], { description: "DCGM device utilization (%)." }),
  gauge("Compute-engine active", 6, 6, [target(`100 * max(DCGM_FI_PROF_GR_ENGINE_ACTIVE{${gpuScope}})`, "GR engine")], { description: "Profiling ratio for graphics/compute engine active time. Hardware/driver support is required." }),
  gauge("Tensor-pipe active", 12, 6, [target(`100 * max(DCGM_FI_PROF_PIPE_TENSOR_ACTIVE{${gpuScope}})`, "tensor")], { description: "Tensor-pipe active ratio when supported by the GPU." }),
  gauge("DRAM active", 18, 6, [target(`100 * max(DCGM_FI_PROF_DRAM_ACTIVE{${gpuScope}})`, "DRAM")], { description: "Fraction of cycles with device-memory traffic, when profiling metrics are supported." }),
);
y += 6;
panels.push(
  timeseries("GPU utilization · per GPU", 0, 12, [
    target(`DCGM_FI_DEV_GPU_UTIL{${gpuScope}}`, "GPU {{gpu}} · {{modelName}}", "A"),
    target(`100 * DCGM_FI_PROF_GR_ENGINE_ACTIVE{${gpuScope}}`, "GPU {{gpu}} · compute-engine active", "B"),
  ], { unit: "percent", min: 0, max: 100 }),
  timeseries("VRAM used / free · per GPU", 12, 12, [
    target(`DCGM_FI_DEV_FB_USED{${gpuScope}} * 1024 * 1024`, "GPU {{gpu}} used", "A"),
    target(`DCGM_FI_DEV_FB_FREE{${gpuScope}} * 1024 * 1024`, "GPU {{gpu}} free", "B"),
    target(`DCGM_FI_DEV_FB_RESERVED{${gpuScope}} * 1024 * 1024`, "GPU {{gpu}} reserved", "C"),
  ], { unit: "bytes", min: 0 }),
);
y += 8;
panels.push(
  timeseries("GPU and memory temperature", 0, 12, [
    target(`DCGM_FI_DEV_GPU_TEMP{${gpuScope}}`, "GPU {{gpu}} core", "A"),
    target(`DCGM_FI_DEV_MEMORY_TEMP{${gpuScope}}`, "GPU {{gpu}} memory", "B"),
  ], { unit: "celsius", min: 0, description: "Use this with throttling panels below to distinguish high temperature from actual thermal limiting." }),
  timeseries("PCIe bandwidth", 12, 12, [
    target(`DCGM_FI_PROF_PCIE_RX_BYTES{${gpuScope}}`, "GPU {{gpu}} RX · host → device", "A"),
    target(`DCGM_FI_PROF_PCIE_TX_BYTES{${gpuScope}}`, "GPU {{gpu}} TX · device → host", "B"),
  ], { unit: "Bps", min: 0, description: "DCGM profiling PCIe bandwidth. These fields are hardware/driver dependent; N/A is valid when unsupported." }),
);
y += 8;
panels.push(
  timeseries("GPU power and clocks", 0, 12, [
    target(`DCGM_FI_DEV_POWER_USAGE{${gpuScope}}`, "GPU {{gpu}} power (W)", "A"),
  ], { unit: "watt", min: 0 }),
  timeseries("GPU clocks", 12, 12, [
    target(`DCGM_FI_DEV_SM_CLOCK{${gpuScope}} * 1000000`, "GPU {{gpu}} SM", "A"),
    target(`DCGM_FI_DEV_MEM_CLOCK{${gpuScope}} * 1000000`, "GPU {{gpu}} memory", "B"),
  ], { unit: "hertz", min: 0, description: "Clock drops during load can indicate thermal or power throttling." }),
);
y += 8;
panels.push(
  stat("Last GPU XID code", 0, 6, [target(`max(DCGM_FI_DEV_XID_ERRORS{${gpuScope}})`, "XID")], { description: "0 / N/A is normal. A non-zero XID code should be correlated with driver logs and NVIDIA XID documentation.", threshold: nonZeroBad, colorMode: "background", graphMode: "none" }),
  stat("Pending retired pages", 6, 6, [target(`max(DCGM_FI_DEV_RETIRED_PENDING{${gpuScope}})`, "pending")], { description: "1 means a GPU page is pending retirement.", threshold: nonZeroBad, colorMode: "background", graphMode: "none" }),
  stat("PCIe replays · last 5m", 12, 6, [target(`sum(increase(DCGM_FI_DEV_PCIE_REPLAY_COUNTER{${gpuScope}}[5m]))`, "replays")], { description: "Growth can indicate PCIe link integrity or transport issues." }),
  stat("ECC double-bit errors · last 5m", 18, 6, [target(`sum(increase(DCGM_FI_DEV_ECC_DBE_VOL_TOTAL{${gpuScope}}[5m]))`, "DBE")], { description: "Uncorrectable/double-bit ECC errors are a high-priority hardware reliability signal.", threshold: nonZeroBad, colorMode: "background", graphMode: "none" }),
);
y += 5;

panels.push(
  timeseries("GPU throttling pressure", 0, 12, [
    target(`100 * rate(DCGM_FI_DEV_THERMAL_VIOLATION{${gpuScope}}[5m]) / 1e9`, "GPU {{gpu}} thermal-limited time", "A"),
    target(`100 * rate(DCGM_FI_DEV_POWER_VIOLATION{${gpuScope}}[5m]) / 1e9`, "GPU {{gpu}} power-limited time", "B"),
    target(`100 * rate(DCGM_FI_DEV_RELIABILITY_VIOLATION{${gpuScope}}[5m]) / 1e9`, "GPU {{gpu}} reliability-limited time", "C"),
  ], { unit: "percent", min: 0, description: "Percent of wall time spent under a DCGM limiter over the last 5 minutes." }),
  timeseries("GPU reliability events", 12, 12, [
    target(`increase(DCGM_FI_DEV_PCIE_REPLAY_COUNTER{${gpuScope}}[5m])`, "GPU {{gpu}} PCIe replays / 5m", "A"),
    target(`increase(DCGM_FI_DEV_ECC_SBE_VOL_TOTAL{${gpuScope}}[5m])`, "GPU {{gpu}} ECC single-bit / 5m", "B"),
    target(`increase(DCGM_FI_DEV_ECC_DBE_VOL_TOTAL{${gpuScope}}[5m])`, "GPU {{gpu}} ECC double-bit / 5m", "C"),
  ], { min: 0, description: "Non-zero double-bit ECC or sustained PCIe replay growth deserves investigation." }),
);
y += 8;

row("03 · All models combined · scheduler and throughput");
panels.push(
  stat("Running requests", 0, 4, [target(totalRunning, "running")]),
  stat("Waiting requests", 4, 4, [target(totalWaiting, "waiting")], { threshold: queueThresholds, colorMode: "background", graphMode: "none" }),
  stat("Fleet KV cache · max", 8, 4, [target(`100 * max(vllm:kv_cache_usage_perc{job=~"vllm-(llm|stt)"})`, "max")], { unit: "percent", threshold: kvThresholds, colorMode: "background", graphMode: "none", min: 0, max: 100 }),
  stat("Preemptions · total", 12, 4, [target(`sum(${totalPreemptionCounter})`, "preemptions")], { description: "Cumulative scheduler preemptions since process start." }),
  stat("Request throughput", 16, 4, [target(totalRequestRate, "requests")], { unit: "reqps" }),
  stat("Output-token throughput", 20, 4, [target(`sum(${generationRate1m})`, "tokens")], { unit: "tps", description: "Standard vLLM generation-token throughput; TTS audio is tracked separately." }),
);
y += 5;
panels.push(
  timeseries("Running and waiting requests · all models", 0, 12, [
    target(totalRunning, "running", "A"),
    target(totalWaiting, "waiting", "B"),
  ], { min: 0 }),
  timeseries("Request throughput · all models", 12, 12, [
    target(totalRequestRate, "completed requests / sec", "A"),
  ], { unit: "reqps", min: 0 }),
);
y += 8;
panels.push(
  timeseries("KV-cache utilization · per model", 0, 12, [
    target(`100 * max by (model_service) (vllm:kv_cache_usage_perc{${standardScope}})`, "{{model_service}}", "A"),
  ], { unit: "percent", min: 0, max: 100, description: "KV cache is a token-model metric; TTS audio serving may use a different cache model." }),
  timeseries("Scheduler preemptions", 12, 12, [
    target(`sum by (model_service) (${preemptionRate5m}) * 60`, "{{model_service}} / min", "A"),
  ], { unit: "ops", min: 0, description: "Sustained preemptions usually indicate KV/cache or scheduling pressure." }),
);
y += 8;
panels.push(
  timeseries("Token throughput · standard vLLM models", 0, 12, [
    target(`sum by (model_service) (${promptRate1m})`, "{{model_service}} input", "A"),
    target(`sum by (model_service) (${generationRate1m})`, "{{model_service}} output", "B"),
  ], { unit: "tps", min: 0 }),
  timeseries("Waiting requests · reason", 12, 12, [
    target(`sum by (model_service, reason) (vllm:num_requests_waiting_by_reason{${standardScope}})`, "{{model_service}} / {{reason}}", "A"),
  ], { min: 0, description: "If supported by the installed vLLM version, distinguishes capacity waits from requests deferred by transient constraints." }),
);
y += 8;

row("04 · Per-model latency · TTFT, E2E, TPOT and ITL");
panels.push(
  stat("TTFT · recent mean 1m", 0, 4, [target(histAvg("vllm:time_to_first_token_seconds", standardScope, "1m"), "{{model_service}}")], { unit: "s", description: "Reliable recent mean; not the literal last request." }),
  stat("TTFT · rolling mean 5m", 4, 4, [target(histAvg("vllm:time_to_first_token_seconds", standardScope, "5m"), "{{model_service}}")], { unit: "s" }),
  stat("E2E · recent mean 1m", 8, 4, [target(`${histAvg("vllm:e2e_request_latency_seconds", standardScope, "1m")} or ${histAvg("vllm_omni:e2e_request_latency_s", ttsScope, "1m")}`, "{{model_service}}")], { unit: "s", description: "Recent mean across standard vLLM or vLLM-Omni E2E histograms." }),
  stat("E2E · rolling mean 5m", 12, 4, [target(`${histAvg("vllm:e2e_request_latency_seconds", standardScope, "5m")} or ${histAvg("vllm_omni:e2e_request_latency_s", ttsScope, "5m")}`, "{{model_service}}")], { unit: "s" }),
  stat("TPOT · recent mean 1m", 16, 4, [target(histAvg("vllm:request_time_per_output_token_seconds", standardScope, "1m"), "{{model_service}}")], { unit: "s", description: "Per-request time per output token. Applies to engines exposing token metrics." }),
  stat("TPOT · rolling mean 5m", 20, 4, [target(histAvg("vllm:request_time_per_output_token_seconds", standardScope, "5m"), "{{model_service}}")], { unit: "s" }),
);
y += 5;
panels.push(
  timeseries("TTFT · mean and tail", 0, 12, [
    target(histAvg("vllm:time_to_first_token_seconds", standardScope, "5m"), "{{model_service}} mean", "A"),
    target(histQ("vllm:time_to_first_token_seconds", standardScope, 0.95), "{{model_service}} p95", "B"),
    target(histQ("vllm:time_to_first_token_seconds", standardScope, 0.99), "{{model_service}} p99", "C"),
  ], { unit: "s", min: 0 }),
  timeseries("End-to-end latency · mean and tail", 12, 12, [
    target(`${histAvg("vllm:e2e_request_latency_seconds", standardScope)} or ${histAvg("vllm_omni:e2e_request_latency_s", ttsScope)}`, "{{model_service}} mean", "A"),
    target(`${histQ("vllm:e2e_request_latency_seconds", standardScope, 0.95)} or ${histQ("vllm_omni:e2e_request_latency_s", ttsScope, 0.95)}`, "{{model_service}} p95", "B"),
    target(`${histQ("vllm:e2e_request_latency_seconds", standardScope, 0.99)} or ${histQ("vllm_omni:e2e_request_latency_s", ttsScope, 0.99)}`, "{{model_service}} p99", "C"),
  ], { unit: "s", min: 0 }),
);
y += 8;
panels.push(
  timeseries("TPOT · mean and tail", 0, 12, [
    target(histAvg("vllm:request_time_per_output_token_seconds", standardScope), "{{model_service}} mean", "A"),
    target(histQ("vllm:request_time_per_output_token_seconds", standardScope, 0.95), "{{model_service}} p95", "B"),
    target(histQ("vllm:request_time_per_output_token_seconds", standardScope, 0.99), "{{model_service}} p99", "C"),
  ], { unit: "s", min: 0 }),
  timeseries("Inter-token latency · mean and tail", 12, 12, [
    target(histAvg("vllm:inter_token_latency_seconds", standardScope), "{{model_service}} mean", "A"),
    target(histQ("vllm:inter_token_latency_seconds", standardScope, 0.95), "{{model_service}} p95", "B"),
    target(histQ("vllm:inter_token_latency_seconds", standardScope, 0.99), "{{model_service}} p99", "C"),
  ], { unit: "s", min: 0, description: "ITL is the gap between successive streamed output events." }),
);
y += 8;

row("05 · Per-model queue, prefill and decode");
panels.push(
  stat("Waiting now", 0, 4, [target(waitingByModel, "{{model_service}}")], { threshold: queueThresholds, colorMode: "background", graphMode: "none" }),
  stat("Queue · mean 5m", 4, 4, [target(histAvg("vllm:request_queue_time_seconds", standardScope), "{{model_service}}")], { unit: "s" }),
  stat("Prefill · recent mean 1m", 8, 4, [target(histAvg("vllm:request_prefill_time_seconds", standardScope, "1m"), "{{model_service}}")], { unit: "s", description: "Recent mean; not exact last request." }),
  stat("Prefill · mean 5m", 12, 4, [target(histAvg("vllm:request_prefill_time_seconds", standardScope), "{{model_service}}")], { unit: "s" }),
  stat("Decode · recent mean 1m", 16, 4, [target(histAvg("vllm:request_decode_time_seconds", standardScope, "1m"), "{{model_service}}")], { unit: "s", description: "Recent mean; not exact last request." }),
  stat("Decode · mean 5m", 20, 4, [target(histAvg("vllm:request_decode_time_seconds", standardScope), "{{model_service}}")], { unit: "s" }),
);
y += 5;
panels.push(
  timeseries("Queue time · mean and p95", 0, 8, [
    target(histAvg("vllm:request_queue_time_seconds", standardScope), "{{model_service}} mean", "A"),
    target(histQ("vllm:request_queue_time_seconds", standardScope, 0.95), "{{model_service}} p95", "B"),
  ], { unit: "s", min: 0 }),
  timeseries("Prefill time · mean and p95", 8, 8, [
    target(histAvg("vllm:request_prefill_time_seconds", standardScope), "{{model_service}} mean", "A"),
    target(histQ("vllm:request_prefill_time_seconds", standardScope, 0.95), "{{model_service}} p95", "B"),
  ], { unit: "s", min: 0 }),
  timeseries("Decode time · mean and p95", 16, 8, [
    target(histAvg("vllm:request_decode_time_seconds", standardScope), "{{model_service}} mean", "A"),
    target(histQ("vllm:request_decode_time_seconds", standardScope, 0.95), "{{model_service}} p95", "B"),
  ], { unit: "s", min: 0 }),
);
y += 8;
panels.push(
  timeseries("Running / waiting · per model", 0, 12, [
    target(runningByModel, "{{model_service}} running", "A"),
    target(waitingByModel, "{{model_service}} waiting", "B"),
  ], { min: 0 }),
  timeseries("Inference running-phase time", 12, 12, [
    target(histAvg("vllm:request_inference_time_seconds", standardScope), "{{model_service}} mean", "A"),
    target(histQ("vllm:request_inference_time_seconds", standardScope, 0.95), "{{model_service}} p95", "B"),
  ], { unit: "s", min: 0, description: "Time in the model RUNNING phase, useful alongside queue/prefill/decode to isolate scheduler vs execution delay." }),
);
y += 8;

row("06 · Per-model tokens, KV cache and request shape");
panels.push(
  stat("Generated tokens · total", 0, 4, [target(`sum by (model_service) (${generationCounter})`, "{{model_service}}")], { description: "Cumulative generated tokens since model-server process start." }),
  stat("Generated tokens / request · mean 5m", 4, 4, [target(histAvg("vllm:request_generation_tokens", standardScope), "{{model_service}}")], { description: "Reliable rolling per-request mean; exact last request requires request-level instrumentation." }),
  stat("Prompt tokens · total", 8, 4, [target(`sum by (model_service) (${promptCounter})`, "{{model_service}}")]),
  stat("Prompt tokens / request · mean 5m", 12, 4, [target(histAvg("vllm:request_prompt_tokens", standardScope), "{{model_service}}")]),
  stat("KV cache utilization", 16, 4, [target(`100 * max by (model_service) (vllm:kv_cache_usage_perc{${standardScope}})`, "{{model_service}}")], { unit: "percent", threshold: kvThresholds, colorMode: "background", graphMode: "none", min: 0, max: 100 }),
  stat("Prefix-cache hit ratio", 20, 4, [target(`100 * sum by (model_service) (rate(vllm:prefix_cache_hits{${standardScope}}[5m])) / sum by (model_service) (rate(vllm:prefix_cache_queries{${standardScope}}[5m]))`, "{{model_service}}")], { unit: "percent", min: 0, max: 100 }),
);
y += 5;
panels.push(
  timeseries("Prompt and output token throughput", 0, 12, [
    target(`sum by (model_service) (${promptRate1m})`, "{{model_service}} prompt", "A"),
    target(`sum by (model_service) (${generationRate1m})`, "{{model_service}} generated", "B"),
  ], { unit: "tps", min: 0 }),
  timeseries("Request throughput · per model", 12, 12, [
    target(requestRate, "{{model_service}}", "A"),
  ], { unit: "reqps", min: 0 }),
);
y += 8;
panels.push(
  timeseries("Prompt tokens / request · distribution", 0, 12, [
    target(histQ("vllm:request_prompt_tokens", standardScope, 0.50), "{{model_service}} p50", "A"),
    target(histQ("vllm:request_prompt_tokens", standardScope, 0.95), "{{model_service}} p95", "B"),
    target(histQ("vllm:request_prompt_tokens", standardScope, 0.99), "{{model_service}} p99", "C"),
  ], { min: 0, description: "Prompt length is a major driver of TTFT and prefill cost." }),
  timeseries("Generated tokens / request · distribution", 12, 12, [
    target(histQ("vllm:request_generation_tokens", standardScope, 0.50), "{{model_service}} p50", "A"),
    target(histQ("vllm:request_generation_tokens", standardScope, 0.95), "{{model_service}} p95", "B"),
    target(histQ("vllm:request_generation_tokens", standardScope, 0.99), "{{model_service}} p99", "C"),
  ], { min: 0, description: "Output length is a major driver of E2E latency and decode occupancy." }),
);
y += 8;
panels.push(
  timeseries("KV-cache utilization", 0, 12, [
    target(`100 * max by (model_service) (vllm:kv_cache_usage_perc{${standardScope}})`, "{{model_service}}", "A"),
  ], { unit: "percent", min: 0, max: 100 }),
  timeseries("Prefix-cache efficiency", 12, 12, [
    target(`100 * sum by (model_service) (rate(vllm:prefix_cache_hits{${standardScope}}[5m])) / sum by (model_service) (rate(vllm:prefix_cache_queries{${standardScope}}[5m]))`, "{{model_service}} hit ratio", "A"),
  ], { unit: "percent", min: 0, max: 100 }),
);
y += 8;

row("07 · Model reliability and outcomes");
panels.push(
  timeseries("Model scrape health", 0, 8, [target(`up{${modelScope}}`, "{{model_service}}", "A")], { min: 0, max: 1 }),
  timeseries("Completed requests by finish reason", 8, 8, [
    target(`sum by (model_service, finished_reason) (rate(vllm:request_success_total{${standardScope}}[1m]))`, "{{model_service}} / {{finished_reason}}", "A"),
    target(`sum by (model_service, finished_reason) (rate(vllm_omni:requests_success_total{${ttsScope}}[1m]))`, "{{model_service}} / {{finished_reason}}", "B"),
  ], { unit: "reqps", min: 0 }),
  timeseries("Corrupted / NaN requests", 16, 8, [
    target(`sum by (model_service) (rate(vllm:corrupted_requests_total{${standardScope}}[5m]) or rate(vllm:corrupted_requests{${standardScope}}[5m])) * 60`, "{{model_service}} / min", "A"),
  ], { unit: "ops", min: 0, description: "Available when vLLM is configured to compute/report NaNs in logits. Any sustained non-zero value is a reliability signal." }),
);
y += 8;

const inventory = base("table", "Configured model and serving parameters", 0, 24, 7, [
  target(`max by (model_service, inference_role, model_repository, model_dtype, model_quantization, max_model_len, max_num_seqs, gpu_memory_utilization, enforce_eager) (up{${modelScope}})`, "", "A", { format: "table", instant: true }),
], { showHeader: true, cellHeight: "sm" });
inventory.description = "Static labels are sourced from the Compose Prometheus scrape configuration so the dashboard shows runtime model configuration without hardcoding model names in the dashboard.";
inventory.transformations = [{ id: "labelsToFields", options: {} }];
panels.push(inventory);
y += 7;

row("08 · TTS / vLLM-Omni audio quality");
panels.push(
  stat("Audio TTFP · mean 5m", 0, 6, [target(histAvg("vllm_omni:audio_ttfp_s", ttsScope), "{{model_service}}")], { unit: "s", description: "Audio time-to-first-packet, the TTS analogue of TTFT." }),
  stat("Audio RTF · mean 5m", 6, 6, [target(histAvg("vllm_omni:audio_rtf", ttsScope), "{{model_service}}")], { description: "Real-time factor. Below 1 means synthesis is faster than playback." }),
  stat("Audio underrun · p95", 12, 6, [target(histQ("vllm_omni:audio_underrun_s", ttsScope, 0.95), "{{model_service}}")], { unit: "s", description: "Streaming gaps audible to a listener." }),
  stat("TTS request throughput", 18, 6, [target(ttsRequestRate, "{{model_service}}")], { unit: "reqps" }),
);
y += 5;
panels.push(
  timeseries("Audio time to first packet", 0, 12, [
    target(histAvg("vllm_omni:audio_ttfp_s", ttsScope), "{{model_service}} mean", "A"),
    target(histQ("vllm_omni:audio_ttfp_s", ttsScope, 0.95), "{{model_service}} p95", "B"),
    target(histQ("vllm_omni:audio_ttfp_s", ttsScope, 0.99), "{{model_service}} p99", "C"),
  ], { unit: "s", min: 0 }),
  timeseries("Audio real-time factor", 12, 12, [
    target(histAvg("vllm_omni:audio_rtf", ttsScope), "{{model_service}} mean", "A"),
    target(histQ("vllm_omni:audio_rtf", ttsScope, 0.95), "{{model_service}} p95", "B"),
  ], { min: 0, description: "RTF < 1 is faster than real time; RTF > 1 cannot keep up with playback without buffering." }),
);
y += 8;
panels.push(
  timeseries("Generated audio duration", 0, 12, [
    target(histQ("vllm_omni:audio_duration_s", ttsScope, 0.50), "{{model_service}} p50", "A"),
    target(histQ("vllm_omni:audio_duration_s", ttsScope, 0.95), "{{model_service}} p95", "B"),
  ], { unit: "s", min: 0 }),
  timeseries("Audio underrun", 12, 12, [
    target(histQ("vllm_omni:audio_underrun_s", ttsScope, 0.95), "{{model_service}} p95", "A"),
  ], { unit: "s", min: 0 }),
);
y += 8;
panels.push(
  timeseries("Audio frames generated / sec", 0, 12, [target(`sum by (model_service) (rate(vllm_omni:audio_frames_total{${ttsScope}}[1m]))`, "{{model_service}}", "A")], { unit: "ops", min: 0 }),
  timeseries("TTS failures and skipped audio", 12, 12, [
    target(`sum by (model_service, reason) (rate(vllm_omni:requests_failed_total{${ttsScope}}[1m]))`, "{{model_service}} failed / {{reason}}", "A"),
    target(`sum by (model_service, reason) (rate(vllm_omni:audio_skipped_requests_total{${ttsScope}}[1m]))`, "{{model_service}} skipped / {{reason}}", "B"),
  ], { unit: "reqps", min: 0 }),
);
y += 8;

const dashboard = {
  annotations: {
    list: [{
      builtIn: 1,
      datasource: { type: "grafana", uid: "-- Grafana --" },
      enable: true,
      hide: true,
      iconColor: "rgba(0, 211, 255, 1)",
      name: "Annotations & Alerts",
      type: "dashboard",
    }],
  },
  description: "Reliability-first observability for Echolex: Linux host, NVIDIA GPU/VRAM, vLLM LLM/STT, vLLM-Omni TTS and combined inference fleet health. Exact last-request latency is intentionally not inferred from Prometheus histograms.",
  editable: true,
  fiscalYearStartMonth: 0,
  graphTooltip: 1,
  id: null,
  links: [],
  liveNow: false,
  panels,
  refresh: "5s",
  schemaVersion: 39,
  tags: ["echolex", "vllm", "inference", "gpu", "dcgm", "node-exporter", "reliability"],
  templating: {
    list: [
      {
        name: "model",
        label: "Model",
        type: "query",
        datasource,
        definition: 'label_values(up{job=~"vllm-.*"}, model_service)',
        query: { query: 'label_values(up{job=~"vllm-.*"}, model_service)', refId: "PrometheusVariableQueryEditor-VariableQuery" },
        includeAll: true,
        allValue: ".*",
        multi: true,
        refresh: 1,
        sort: 1,
        current: { selected: true, text: "All", value: "$__all" },
      },
      {
        name: "gpu",
        label: "GPU",
        type: "query",
        datasource,
        definition: 'label_values(DCGM_FI_DEV_GPU_UTIL{job="dcgm-exporter"}, gpu)',
        query: { query: 'label_values(DCGM_FI_DEV_GPU_UTIL{job="dcgm-exporter"}, gpu)', refId: "PrometheusVariableQueryEditor-GPU" },
        includeAll: true,
        allValue: ".*",
        multi: true,
        refresh: 1,
        sort: 1,
        current: { selected: true, text: "All", value: "$__all" },
      },
    ],
  },
  time: { from: "now-30m", to: "now" },
  timepicker: {
    refresh_intervals: ["5s", "10s", "30s", "1m", "5m"],
    time_options: ["5m", "15m", "30m", "1h", "3h", "6h", "12h", "24h", "2d", "7d"],
  },
  timezone: "browser",
  title: "Echolex · Inference & GPU Reliability",
  uid: "echolex-inference-gpu-reliability",
  version: 1,
  weekStart: "",
};

writeFileSync(new URL("./model-observability.json", import.meta.url), `${JSON.stringify(dashboard, null, 2)}\n`);
