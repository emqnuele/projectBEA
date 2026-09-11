"""`bea --update` on a terminal: a live list of steps and a verdict.

The report is the same object the dashboard renders; this only decides how it
looks on a terminal. The one rule it follows is the one `--doctor` follows: a
failure that does not say what to type next is a failure that becomes an issue.
"""

from pathlib import Path
from typing import Optional

from src.core.update import runner
from src.core.update.reconcile import CONFLICT, KEPT, MERGED, REMOVED, UNTOUCHED
from src.core.update.runner import DONE, FAILED, SKIPPED, Report

MARKS = {
    runner.RUNNING: "[dim]·[/dim]",
    DONE: "[green]✓[/green]",
    SKIPPED: "[dim]–[/dim]",
    FAILED: "[red]✗[/red]",
}

PROMPT_MARKS = {
    UNTOUCHED: "[dim]·[/dim]",
    KEPT: "[green]✓[/green]",
    MERGED: "[green]✓[/green]",
    REMOVED: "[yellow]![/yellow]",
    CONFLICT: "[yellow]![/yellow]",
}


def run_update(root: Optional[Path] = None, console=None, rebuild: bool = True) -> int:
    """The command. Returns a shell exit code: 0 when she is on the new version."""
    from rich.console import Console

    from src.utils.logger import quieten

    quieten()
    console = console or Console()
    root = root or runner.ROOT

    console.print()
    console.rule("[bold]Updating[/bold]", align="left", style="dim")
    console.print()

    drawn = set()

    def show(step: runner.Step) -> None:
        # a step is drawn once it has settled, so the list does not scroll past
        # itself on a terminal that cannot repaint
        if step.status == runner.RUNNING or step.id in drawn:
            return
        drawn.add(step.id)
        console.print(f"  {MARKS.get(step.status, ' ')} [bold]{step.label}[/bold]"
                      + (f"  [dim]{step.detail}[/dim]" if step.detail else ""))

    report = runner.apply(root=root, source="cli", progress=show, rebuild=rebuild)
    return _verdict(console, report)


def _verdict(console, report: Report) -> int:
    console.print()

    if report.status == runner.CURRENT:
        console.print("  [green]Nothing to do — she is already up to date.[/green]")
        console.print()
        return 0

    if report.status == runner.BLOCKED:
        console.print(f"  [yellow]{report.headline}.[/yellow] {report.detail}")
        for path in report.blocked_paths:
            console.print(f"      [cyan]{path}[/cyan]")
        console.print()
        return 1

    if report.status == runner.FAILED_RUN:
        console.print(f"  [red]{report.headline}.[/red] {report.detail}")
        if report.backup:
            console.print(f"  [dim]Your files are in data/.backups/{report.backup}[/dim]")
        console.print()
        return 1

    if report.commits:
        console.print(f"  [bold]What is new[/bold] [dim]({len(report.commits)} commits)[/dim]")
        for commit in report.commits[:10]:
            console.print(f"      [dim]{commit['sha']}[/dim]  {commit['subject']}")
        if len(report.commits) > 10:
            console.print(f"      [dim]… and {len(report.commits) - 10} more[/dim]")
        console.print()

    if report.prompts:
        console.print("  [bold]Your prompts[/bold]")
        for outcome in report.prompts:
            mark = PROMPT_MARKS.get(outcome.state, " ")
            console.print(f"      {mark} [bold]{Path(outcome.path).name}[/bold]  [dim]{outcome.detail}[/dim]")
        console.print()

    reviews = report.reviews
    if reviews:
        console.print(f"  [yellow]{len(reviews)} prompt(s) kept your version and could not take the new one.[/yellow]")
        console.print("  [dim]Yours is still in place and she runs exactly as before. The new version "
                      "is beside it:[/dim]")
        for outcome in reviews:
            console.print(f"      [cyan]{outcome.path}.new[/cyan]")
        console.print("  [dim]Compare them in Settings → Personality, or with:[/dim]")
        console.print(f"      [cyan]diff {reviews[0].path} {reviews[0].path}.new[/cyan]")
        console.print()

    failed = [s for s in report.steps if s.status == FAILED]
    if failed:
        console.print("  [yellow]She is on the new version, but part of the rebuild did not run:[/yellow]")
        for step in failed:
            console.print(f"      [cyan]{step.detail}[/cyan]")
        console.print()
        return 1

    console.print("  [green]Updated.[/green] Restart her to load it:")
    console.print("      [cyan]uv run bea --web[/cyan]")
    console.print()
    return 0
