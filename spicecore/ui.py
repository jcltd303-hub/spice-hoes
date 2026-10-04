"""Terminal UI helpers for spicecore."""
from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
    from rich.table import Table
    _HAS_RICH = True
except ImportError:  # pragma: no cover - plain-text fallback
    _HAS_RICH = False
    Console = Panel = Progress = Table = None


class SpiceUI:
    def __init__(self, force_json=False, no_color=False):
        self.force_json = force_json
        self.pretty = _HAS_RICH and (not force_json) and sys.stdout.isatty()
        self.console = None
        if self.pretty:
            self.console = Console(color_system=None if no_color else "auto", force_terminal=self.pretty)
        self._progress = None
        self._task = None

    def header(self, command):
        if self.pretty:
            self.console.print(Panel.fit("[bold magenta]SPICECORE[/]\n[dim]" + command + "[/]", border_style="magenta"))

    def start_progress(self, label="Starting"):
        if not self.pretty:
            return
        self._progress = Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
        )
        self._progress.start()
        self._task = self._progress.add_task(label, total=100, completed=0)

    def update_progress(self, percent, label):
        if self._progress is not None and self._task is not None:
            self._progress.update(self._task, completed=max(0, min(100, percent)), description=label)

    def stop_progress(self, success=True):
        if self._progress is not None:
            if self._task is not None and success:
                self._progress.update(self._task, completed=100, description="Complete")
            self._progress.stop()
        self._progress = None
        self._task = None

    def metrics(self, output):
        rows = output if isinstance(output, list) else [output]
        if not self.pretty or not rows or not all(isinstance(row, dict) for row in rows):
            return False
        preferred = ["persona_id","name","published","impressions","clicks","click_rate","revenue_cents","refund_cents","cost_cents","net_cents","pending_review","spent_today_cents","rl_experiences","rl_minimum_experiences","rl_ready","experiences","minimum_experiences","ready"]
        keys = [k for k in preferred if any(k in row for row in rows)]
        if not keys:
            return False
        table = Table(title="Metrics", header_style="bold magenta", border_style="cyan")
        for key in keys:
            table.add_column(key.replace("_", " ").title())
        for row in rows:
            rendered = []
            for key in keys:
                value = row.get(key, "")
                if key.endswith("_cents") and isinstance(value, (int, float)):
                    money = "${:,.2f}".format(value / 100)
                    if key == "net_cents":
                        money = ("[green]" + money + "[/green]") if value >= 0 else ("[red]" + money + "[/red]")
                    rendered.append(money)
                elif key == "click_rate" and isinstance(value, (int, float)):
                    rendered.append("{:.2f}%".format(value * 100))
                elif key in ("ready", "rl_ready"):
                    rendered.append("[green]READY[/green]" if value else "[yellow]LEARNING[/yellow]")
                else:
                    rendered.append(str(value))
            table.add_row(*rendered)
        self.console.print(table)
        return True

    def result(self, output, command):
        if self.force_json or not self.pretty:
            print(json.dumps(output, indent=2, ensure_ascii=False))
            return
        if command in {"stats", "autopilot-status", "rl-status"} and self.metrics(output):
            return
        if isinstance(output, dict):
            status = output.get("status")
            if status is not None:
                self.console.print("[bold green]status[/]: " + str(status))
            for key in ("run_id","plan_id","candidate_id","persona_id","provider","architecture"):
                if output.get(key) is not None:
                    self.console.print("[cyan]" + key + "[/]: " + str(output[key]))
            if command == "moa":
                ok = output.get("successful_experts", 0)
                total = len(output.get("experts", []))
                self.console.print("[magenta]experts[/]: {}/{} successful".format(ok, total))
                if output.get("synthesis") is not None:
                    self.console.print(Panel(json.dumps(output["synthesis"], indent=2, ensure_ascii=False), title="MoA synthesis", border_style="cyan"))
                return
        self.console.print_json(json.dumps(output, ensure_ascii=False))
