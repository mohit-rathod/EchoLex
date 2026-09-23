#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def escape(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def metric(name: str, value, labels=None) -> str:
    if value is None:
        return ""

    if labels:
        labels_text = ",".join(
            f'{key}="{escape(value)}"'
            for key, value in labels.items()
        )

        return f"{name}{{{labels_text}}} {value}\n"

    return f"{name} {value}\n"


def parse_number(value: str):
    value = value.strip()

    invalid = {
        "",
        "n/a",
        "[not supported]",
        "not supported",
        "[not available]",
    }

    if value.lower() in invalid:
        return None

    match = re.search(
        r"[-+]?\d+(?:\.\d+)?",
        value.replace(",", ""),
    )

    if not match:
        return None

    return float(match.group(0))


# ---------------------------------------------------------------------------
# HOST / CPU / RAM
# ---------------------------------------------------------------------------

def node_metrics() -> str:
    proc = Path(os.getenv("HOST_PROC", "/host/proc"))
    sysfs = Path(os.getenv("HOST_SYS", "/host/sys"))

    output = []

    # -----------------------------------------------------------------------
    # Memory
    # -----------------------------------------------------------------------

    memory = {}

    try:
        for line in (proc / "meminfo").read_text().splitlines():
            key, raw = line.split(":", 1)

            parts = raw.split()

            if not parts:
                continue

            value = float(parts[0])

            if len(parts) > 1 and parts[1].lower() == "kb":
                value *= 1024

            memory[key] = value

    except OSError:
        pass

    for key in (
        "MemTotal",
        "MemAvailable",
        "MemFree",
        "Buffers",
        "Cached",
    ):
        if key in memory:
            output.append(
                metric(
                    f"node_memory_{key}_bytes",
                    memory[key],
                )
            )

    # -----------------------------------------------------------------------
    # CPU
    # -----------------------------------------------------------------------

    cpu_modes = [
        "user",
        "nice",
        "system",
        "idle",
        "iowait",
        "irq",
        "softirq",
        "steal",
        "guest",
        "guest_nice",
    ]

    try:
        clock_ticks = float(
            os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        )
    except Exception:
        clock_ticks = 100.0

    try:
        for line in (proc / "stat").read_text().splitlines():

            parts = line.split()

            if not parts:
                continue

            if not re.fullmatch(r"cpu\d+", parts[0]):
                continue

            cpu = parts[0][3:]

            for index, raw in enumerate(parts[1:]):

                if index >= len(cpu_modes):
                    break

                try:
                    seconds = float(raw) / clock_ticks
                except ValueError:
                    continue

                output.append(
                    metric(
                        "node_cpu_seconds_total",
                        seconds,
                        {
                            "cpu": cpu,
                            "mode": cpu_modes[index],
                        },
                    )
                )

    except OSError:
        pass

    # -----------------------------------------------------------------------
    # Load average
    # -----------------------------------------------------------------------

    try:
        loads = (proc / "loadavg").read_text().split()

        if len(loads) >= 3:
            output.append(metric("node_load1", float(loads[0])))
            output.append(metric("node_load5", float(loads[1])))
            output.append(metric("node_load15", float(loads[2])))

    except Exception:
        pass

    # -----------------------------------------------------------------------
    # CPU / board temperature via hwmon
    # -----------------------------------------------------------------------

    hwmon_root = sysfs / "class" / "hwmon"

    if hwmon_root.exists():

        for hwmon in sorted(hwmon_root.glob("hwmon*")):

            try:
                chip = (hwmon / "name").read_text().strip()
            except OSError:
                chip = hwmon.name

            for temp_file in sorted(
                hwmon.glob("temp*_input")
            ):

                try:
                    temperature = (
                        float(temp_file.read_text().strip())
                        / 1000.0
                    )
                except Exception:
                    continue

                stem = temp_file.name.removesuffix(
                    "_input"
                )

                try:
                    sensor = (
                        hwmon /
                        f"{stem}_label"
                    ).read_text().strip()

                except OSError:
                    sensor = stem

                output.append(
                    metric(
                        "node_hwmon_temp_celsius",
                        temperature,
                        {
                            "chip": chip,
                            "sensor": sensor,
                        },
                    )
                )

    # -----------------------------------------------------------------------
    # Thermal zones
    # -----------------------------------------------------------------------

    thermal_root = sysfs / "class" / "thermal"

    if thermal_root.exists():

        for zone in sorted(
            thermal_root.glob("thermal_zone*")
        ):

            try:
                temperature = (
                    float(
                        (zone / "temp")
                        .read_text()
                        .strip()
                    )
                    / 1000.0
                )

                zone_type = (
                    (zone / "type")
                    .read_text()
                    .strip()
                )

            except Exception:
                continue

            output.append(
                metric(
                    "node_thermal_zone_temp",
                    temperature,
                    {
                        "zone": zone.name,
                        "type": zone_type,
                    },
                )
            )

    return "".join(output)


# ---------------------------------------------------------------------------
# NVIDIA
# ---------------------------------------------------------------------------

def nvidia_query(fields):
    if not shutil.which("nvidia-smi"):
        return []

    command = [
        "nvidia-smi",
        f"--query-gpu={','.join(fields)}",
        "--format=csv,noheader,nounits",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

    except Exception:
        return []

    if result.returncode != 0:
        return []

    return list(
        csv.reader(
            result.stdout.splitlines(),
            skipinitialspace=True,
        )
    )


def gpu_metrics() -> str:

    fields = [
        "index",
        "name",
        "memory.used",
        "memory.free",
        "memory.total",
        "utilization.gpu",
        "utilization.memory",
        "temperature.gpu",
        "power.draw",
        "clocks.sm",
        "clocks.mem",
    ]

    rows = nvidia_query(fields)

    if not rows:
        return ""

    output = []
    labels_by_gpu = {}

    for row in rows:

        if len(row) < len(fields):
            continue

        values = dict(zip(fields, row))

        gpu = values["index"].strip()

        labels = {
            "gpu": gpu,
            "modelName": values["name"].strip(),
        }

        labels_by_gpu[gpu] = labels

        memory_used = parse_number(
            values["memory.used"]
        )

        memory_free = parse_number(
            values["memory.free"]
        )

        memory_total = parse_number(
            values["memory.total"]
        )

        gpu_util = parse_number(
            values["utilization.gpu"]
        )

        memory_util = parse_number(
            values["utilization.memory"]
        )

        gpu_temp = parse_number(
            values["temperature.gpu"]
        )

        power = parse_number(
            values["power.draw"]
        )

        sm_clock = parse_number(
            values["clocks.sm"]
        )

        memory_clock = parse_number(
            values["clocks.mem"]
        )

        # VRAM
        output.append(
            metric(
                "DCGM_FI_DEV_FB_USED",
                memory_used,
                labels,
            )
        )

        output.append(
            metric(
                "DCGM_FI_DEV_FB_FREE",
                memory_free,
                labels,
            )
        )

        output.append(
            metric(
                "DCGM_FI_DEV_FB_RESERVED",
                0,
                labels,
            )
        )

        output.append(
            metric(
                "DCGM_FI_DEV_FB_TOTAL",
                memory_total,
                labels,
            )
        )

        # GPU utilization
        output.append(
            metric(
                "DCGM_FI_DEV_GPU_UTIL",
                gpu_util,
                labels,
            )
        )

        # Compatibility with Grafana DCGM queries.
        if gpu_util is not None:
            output.append(
                metric(
                    "DCGM_FI_PROF_GR_ENGINE_ACTIVE",
                    gpu_util / 100.0,
                    labels,
                )
            )

        if memory_util is not None:
            output.append(
                metric(
                    "DCGM_FI_PROF_DRAM_ACTIVE",
                    memory_util / 100.0,
                    labels,
                )
            )

        # Temperature
        output.append(
            metric(
                "DCGM_FI_DEV_GPU_TEMP",
                gpu_temp,
                labels,
            )
        )

        # Power
        output.append(
            metric(
                "DCGM_FI_DEV_POWER_USAGE",
                power,
                labels,
            )
        )

        # Clocks
        output.append(
            metric(
                "DCGM_FI_DEV_SM_CLOCK",
                sm_clock,
                labels,
            )
        )

        output.append(
            metric(
                "DCGM_FI_DEV_MEM_CLOCK",
                memory_clock,
                labels,
            )
        )

    # -----------------------------------------------------------------------
    # PCIe throughput
    # NVIDIA reports these in KiB/s.
    # -----------------------------------------------------------------------

    pcie_rows = nvidia_query(
        [
            "index",
            "pcie.rx_util",
            "pcie.tx_util",
        ]
    )

    for row in pcie_rows:

        if len(row) < 3:
            continue

        gpu = row[0].strip()

        labels = labels_by_gpu.get(
            gpu,
            {
                "gpu": gpu,
                "modelName": "unknown",
            },
        )

        rx = parse_number(row[1])
        tx = parse_number(row[2])

        if rx is not None:
            output.append(
                metric(
                    "DCGM_FI_PROF_PCIE_RX_BYTES",
                    rx * 1024,
                    labels,
                )
            )

        if tx is not None:
            output.append(
                metric(
                    "DCGM_FI_PROF_PCIE_TX_BYTES",
                    tx * 1024,
                    labels,
                )
            )

    # -----------------------------------------------------------------------
    # Memory temperature, where supported.
    # -----------------------------------------------------------------------

    memory_temp_rows = nvidia_query(
        [
            "index",
            "temperature.memory",
        ]
    )

    for row in memory_temp_rows:

        if len(row) < 2:
            continue

        gpu = row[0].strip()

        labels = labels_by_gpu.get(
            gpu,
            {
                "gpu": gpu,
                "modelName": "unknown",
            },
        )

        output.append(
            metric(
                "DCGM_FI_DEV_MEMORY_TEMP",
                parse_number(row[1]),
                labels,
            )
        )

    # -----------------------------------------------------------------------
    # ECC counters, when supported.
    # -----------------------------------------------------------------------

    ecc_rows = nvidia_query(
        [
            "index",
            "ecc.errors.corrected.volatile.total",
            "ecc.errors.uncorrected.volatile.total",
        ]
    )

    for row in ecc_rows:

        if len(row) < 3:
            continue

        gpu = row[0].strip()

        labels = labels_by_gpu.get(
            gpu,
            {
                "gpu": gpu,
                "modelName": "unknown",
            },
        )

        output.append(
            metric(
                "DCGM_FI_DEV_ECC_SBE_VOL_TOTAL",
                parse_number(row[1]),
                labels,
            )
        )

        output.append(
            metric(
                "DCGM_FI_DEV_ECC_DBE_VOL_TOTAL",
                parse_number(row[2]),
                labels,
            )
        )

    return "".join(
        value
        for value in output
        if value
    )


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):

    mode = "node"

    def do_GET(self):

        if self.path == "/healthz":
            payload = b"ok\n"

            self.send_response(200)

        elif self.path in ("/", "/metrics"):

            if self.mode == "node":
                body = node_metrics()
            else:
                body = gpu_metrics()

            if not body:
                payload = (
                    'echolex_hardware_exporter_up '
                    f'{{mode="{self.mode}"}} 0\n'
                ).encode()

                self.send_response(503)

            else:
                body += (
                    'echolex_hardware_exporter_up'
                    f'{{mode="{self.mode}"}} 1\n'
                )

                payload = body.encode()

                self.send_response(200)

        else:
            self.send_response(404)
            self.end_headers()
            return

        self.send_header(
            "Content-Type",
            "text/plain; version=0.0.4",
        )

        self.send_header(
            "Content-Length",
            str(len(payload)),
        )

        self.end_headers()

        self.wfile.write(payload)

    def log_message(self, *_):
        return


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mode",
        choices=("node", "gpu"),
        required=True,
    )

    parser.add_argument(
        "--port",
        type=int,
        required=True,
    )

    args = parser.parse_args()

    Handler.mode = args.mode

    server = ThreadingHTTPServer(
        ("0.0.0.0", args.port),
        Handler,
    )

    print(
        f"hardware exporter mode={args.mode} "
        f"listening on :{args.port}",
        flush=True,
    )

    server.serve_forever()


if __name__ == "__main__":
    main()
