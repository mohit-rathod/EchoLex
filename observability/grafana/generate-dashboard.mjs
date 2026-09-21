import { writeFileSync } from "node:fs";

const datasource = { type: "prometheus", uid: "prometheus" };
const scope = 'job=~"vllm-.*",model_service=~"$model"';
const standardScope = `${scope},inference_role!="tts"`;
const ttsScope = `${scope},inference_role="tts"`;
let panelId = 1;
let y = 0;
const panels = [];

const target = (expr, legendFormat, refId = "A", extra = {}) => ({
  expr,
  legendFormat,
  refId,
  ...extra,
});

const base = (type, title, x, width, height, targets, options = {}) => ({
  id: panelId++,
  type,
  title,
  datasource,
  gridPos: { x, y, w: width, h: height },
  targets,
  options,
  fieldConfig: { defaults: {}, overrides: [] },
});

const stat = (title, x, width, targets, unit = "short", description = "") => {
  const p = base("stat", title, x, width, 5, targets, {
    colorMode: "value",
    graphMode: "area",
    justifyMode: "auto",
    orientation: "auto",
    reduceOptions: { calcs: ["lastNotNull"], fields: "", values: false },
    textMode: "auto",
  });
  p.description = description;
  p.fieldConfig.defaults = { unit, noValue: "N/A" };
  return p;
};

const timeseries = (title, x, width, targets, unit = "short", description = "") => {
  const p = base("timeseries", title, x, width, 8, targets, {
    legend: { displayMode: "table", placement: "bottom", calcs: ["lastNotNull", "mean", "max"] },
    tooltip: { mode: "multi", sort: "desc" },
  });
  p.description = description;
  p.fieldConfig.defaults = {
    unit,
    custom: { drawStyle: "line", lineInterpolation: "linear", lineWidth: 2, fillOpacity: 8, showPoints: "never", spanNulls: true },
  };
  return p;
};

const row = (title) => {
  panels.push({ id: panelId++, type: "row", title, collapsed: false, gridPos: { x: 0, y, w: 24, h: 1 }, panels: [] });
  y += 1;
};

const requestRate =
  `sum by (model_service) (rate(vllm:request_success_total{${standardScope}}[1m])) ` +
  `or sum by (model_service) (rate(vllm_omni:requests_success_total{${ttsScope}}[1m]))`;
const running =
  `sum by (model_service) (vllm:num_requests_running{${standardScope}}) ` +
  `or sum by (model_service) (vllm_omni:num_requests_running{${ttsScope}})`;
const waiting =
  `sum by (model_service) (vllm:num_requests_waiting{${standardScope}}) ` +
  `or sum by (model_service) (vllm_omni:num_requests_waiting{${ttsScope}})`;
const e2e = (quantile) =>
  `histogram_quantile(${quantile}, sum by (model_service, le) (rate(vllm:e2e_request_latency_seconds_bucket{${standardScope}}[5m]))) ` +
  `or histogram_quantile(${quantile}, sum by (model_service, le) (rate(vllm_omni:e2e_request_latency_s_bucket{${ttsScope}}[5m])))`;

row("Model inventory and live summary");
panels.push(
  stat("Scrape health", 0, 4, [target(`min by (model_service) (up{${scope}})`, "{{model_service}}")], "short", "1 means Prometheus can scrape the model server; 0 means the target is unavailable."),
  stat("Completed requests / sec", 4, 4, [target(requestRate, "{{model_service}}")], "reqps"),
  stat("Running requests", 8, 4, [target(running, "{{model_service}}")]),
  stat("Waiting requests", 12, 4, [target(waiting, "{{model_service}}")]),
  stat("p95 end-to-end latency", 16, 4, [target(e2e(0.95), "{{model_service}}")], "s"),
  stat("Output tokens / sec", 20, 4, [target(`sum by (model_service) (rate(vllm:generation_tokens_total{${scope}}[1m]))`, "{{model_service}}")], "tps")
);
y += 5;

const inventory = base("table", "Configured model and serving parameters", 0, 24, 7, [
  target(`max by (model_service, inference_role, model_repository, model_dtype, model_quantization, max_model_len, max_num_seqs, gpu_memory_utilization, execution_mode) (up{${scope}})`, "", "A", { format: "table", instant: true }),
], { showHeader: true, cellHeight: "sm" });
inventory.description = "Static labels are defined beside each Prometheus target, so the dashboard exposes the model configuration even when there is no inference traffic.";
inventory.transformations = [{ id: "labelsToFields", options: {} }];
panels.push(inventory);
y += 7;

row("Traffic, throughput and request outcomes");
panels.push(
  timeseries("Completed request rate", 0, 12, [target(requestRate, "{{model_service}}")], "reqps"),
  timeseries("Request outcomes", 12, 12, [
    target(`sum by (model_service, finished_reason) (rate(vllm:request_success_total{${standardScope}}[1m]))`, "{{model_service}} / {{finished_reason}}", "A"),
    target(`sum by (model_service, finished_reason) (rate(vllm_omni:requests_success_total{${ttsScope}}[1m]))`, "{{model_service}} / {{finished_reason}}", "B"),
  ], "reqps")
);
y += 8;
panels.push(
  timeseries("Token throughput", 0, 12, [
    target(`sum by (model_service) (rate(vllm:prompt_tokens_total{${scope}}[1m]))`, "{{model_service}} input", "A"),
    target(`sum by (model_service) (rate(vllm:generation_tokens_total{${scope}}[1m]))`, "{{model_service}} output", "B"),
  ], "tps", "For ASR/TTS, token semantics are engine/model dependent. Audio-native performance is shown in the TTS section."),
  timeseries("HTTP request and server-error rate", 12, 12, [
    target(`sum by (model_service) (rate(http_requests_total{${scope}}[1m]))`, "{{model_service}} all", "A"),
    target(`sum by (model_service) (rate(http_requests_total{${scope},status=~"5.*"}[1m]))`, "{{model_service}} 5xx", "B"),
  ], "reqps")
);
y += 8;

row("Latency and phase breakdown");
panels.push(
  timeseries("End-to-end latency percentiles", 0, 12, [
    target(e2e(0.50), "{{model_service}} p50", "A"),
    target(e2e(0.95), "{{model_service}} p95", "B"),
    target(e2e(0.99), "{{model_service}} p99", "C"),
  ], "s"),
  timeseries("Time to first token (TTFT)", 12, 12, [
    target(`histogram_quantile(0.50, sum by (model_service, le) (rate(vllm:time_to_first_token_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p50", "A"),
    target(`histogram_quantile(0.95, sum by (model_service, le) (rate(vllm:time_to_first_token_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p95", "B"),
    target(`histogram_quantile(0.99, sum by (model_service, le) (rate(vllm:time_to_first_token_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p99", "C"),
  ], "s")
);
y += 8;
panels.push(
  timeseries("Inter-token latency / TPOT", 0, 12, [
    target(`histogram_quantile(0.50, sum by (model_service, le) (rate(vllm:inter_token_latency_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p50", "A"),
    target(`histogram_quantile(0.95, sum by (model_service, le) (rate(vllm:inter_token_latency_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p95", "B"),
    target(`histogram_quantile(0.99, sum by (model_service, le) (rate(vllm:inter_token_latency_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p99", "C"),
  ], "s"),
  timeseries("Queue latency", 12, 12, [
    target(`histogram_quantile(0.50, sum by (model_service, le) (rate(vllm:request_queue_time_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p50", "A"),
    target(`histogram_quantile(0.95, sum by (model_service, le) (rate(vllm:request_queue_time_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p95", "B"),
    target(`histogram_quantile(0.99, sum by (model_service, le) (rate(vllm:request_queue_time_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p99", "C"),
  ], "s")
);
y += 8;
panels.push(
  timeseries("Prefill latency", 0, 12, [
    target(`histogram_quantile(0.50, sum by (model_service, le) (rate(vllm:request_prefill_time_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p50", "A"),
    target(`histogram_quantile(0.95, sum by (model_service, le) (rate(vllm:request_prefill_time_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p95", "B"),
  ], "s"),
  timeseries("Decode latency", 12, 12, [
    target(`histogram_quantile(0.50, sum by (model_service, le) (rate(vllm:request_decode_time_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p50", "A"),
    target(`histogram_quantile(0.95, sum by (model_service, le) (rate(vllm:request_decode_time_seconds_bucket{${scope}}[5m])))`, "{{model_service}} p95", "B"),
  ], "s")
);
y += 8;

row("Scheduler, cache and request shape");
panels.push(
  timeseries("Running and waiting requests", 0, 12, [target(running, "{{model_service}} running", "A"), target(waiting, "{{model_service}} waiting", "B")]),
  timeseries("KV-cache utilization", 12, 12, [target(`max by (model_service) (vllm:kv_cache_usage_perc{${scope}})`, "{{model_service}}")], "percentunit")
);
y += 8;
panels.push(
  timeseries("Scheduler preemptions", 0, 12, [target(`sum by (model_service) (rate(vllm:num_preemptions_total{${scope}}[1m]))`, "{{model_service}}")], "ops"),
  timeseries("Prefix-cache hit ratio", 12, 12, [
    target(`sum by (model_service) (rate(vllm:prefix_cache_hits{${scope}}[5m])) / clamp_min(sum by (model_service) (rate(vllm:prefix_cache_queries{${scope}}[5m])), 0.000001)`, "{{model_service}}"),
  ], "percentunit")
);
y += 8;
panels.push(
  timeseries("Prompt-token distribution", 0, 12, [
    target(`histogram_quantile(0.50, sum by (model_service, le) (rate(vllm:request_prompt_tokens_bucket{${scope}}[5m])))`, "{{model_service}} p50", "A"),
    target(`histogram_quantile(0.95, sum by (model_service, le) (rate(vllm:request_prompt_tokens_bucket{${scope}}[5m])))`, "{{model_service}} p95", "B"),
  ], "short"),
  timeseries("Generated-token distribution", 12, 12, [
    target(`histogram_quantile(0.50, sum by (model_service, le) (rate(vllm:request_generation_tokens_bucket{${scope}}[5m])))`, "{{model_service}} p50", "A"),
    target(`histogram_quantile(0.95, sum by (model_service, le) (rate(vllm:request_generation_tokens_bucket{${scope}}[5m])))`, "{{model_service}} p95", "B"),
  ], "short")
);
y += 8;

row("TTS / vLLM-Omni audio metrics");
panels.push(
  timeseries("Audio time to first packet", 0, 12, [
    target(`histogram_quantile(0.50, sum by (model_service, le) (rate(vllm_omni:audio_ttfp_s_bucket{${ttsScope}}[5m])))`, "{{model_service}} p50", "A"),
    target(`histogram_quantile(0.95, sum by (model_service, le) (rate(vllm_omni:audio_ttfp_s_bucket{${ttsScope}}[5m])))`, "{{model_service}} p95", "B"),
  ], "s"),
  timeseries("Audio real-time factor", 12, 12, [
    target(`histogram_quantile(0.50, sum by (model_service, le) (rate(vllm_omni:audio_rtf_bucket{${ttsScope}}[5m])))`, "{{model_service}} p50", "A"),
    target(`histogram_quantile(0.95, sum by (model_service, le) (rate(vllm_omni:audio_rtf_bucket{${ttsScope}}[5m])))`, "{{model_service}} p95", "B"),
  ], "short", "RTF below 1 means audio is generated faster than real time.")
);
y += 8;
panels.push(
  timeseries("Generated audio duration", 0, 12, [
    target(`histogram_quantile(0.50, sum by (model_service, le) (rate(vllm_omni:audio_duration_s_bucket{${ttsScope}}[5m])))`, "{{model_service}} p50", "A"),
    target(`histogram_quantile(0.95, sum by (model_service, le) (rate(vllm_omni:audio_duration_s_bucket{${ttsScope}}[5m])))`, "{{model_service}} p95", "B"),
  ], "s"),
  timeseries("Audio underrun", 12, 12, [
    target(`histogram_quantile(0.95, sum by (model_service, le) (rate(vllm_omni:audio_underrun_s_bucket{${ttsScope}}[5m])))`, "{{model_service}} p95", "A"),
  ], "s", "Values above 0 indicate that a streaming listener would hear a gap.")
);
y += 8;
panels.push(
  timeseries("Audio frames generated / sec", 0, 12, [target(`sum by (model_service) (rate(vllm_omni:audio_frames_total{${ttsScope}}[1m]))`, "{{model_service}}")], "ops"),
  timeseries("TTS failures and skipped audio", 12, 12, [
    target(`sum by (model_service, reason) (rate(vllm_omni:requests_failed_total{${ttsScope}}[1m]))`, "{{model_service}} failed / {{reason}}", "A"),
    target(`sum by (model_service, reason) (rate(vllm_omni:audio_skipped_requests_total{${ttsScope}}[1m]))`, "{{model_service}} skipped / {{reason}}", "B"),
  ], "reqps")
);

const dashboard = {
  annotations: { list: [{ builtIn: 1, datasource: { type: "grafana", uid: "-- Grafana --" }, enable: true, hide: true, iconColor: "rgba(0, 211, 255, 1)", name: "Annotations & Alerts", type: "dashboard" }] },
  description: "Inference-only observability for the EchoLex LLM, speech-to-text and text-to-speech model servers. Select All for a combined comparison or choose an individual model.",
  editable: true,
  fiscalYearStartMonth: 0,
  graphTooltip: 1,
  id: null,
  links: [],
  liveNow: false,
  panels,
  refresh: "5s",
  schemaVersion: 39,
  tags: ["vllm", "inference", "llm", "stt", "tts"],
  templating: {
    list: [{
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
    }],
  },
  time: { from: "now-30m", to: "now" },
  timepicker: {},
  timezone: "browser",
  title: "Model Inference Observability",
  uid: "model-inference-observability",
  version: 1,
  weekStart: "",
};

writeFileSync(new URL("./model-observability.json", import.meta.url), `${JSON.stringify(dashboard, null, 2)}\n`);
