"""Step log: every stage records what it did, so the dashboard can show the processing report."""
from dataclasses import dataclass, field


@dataclass
class StepLog:
    steps: list = field(default_factory=list)

    def add(self, stage, step, title, detail, rows=None, removed=None):
        self.steps.append(dict(stage=stage, step=step, title=title, detail=detail, rows=rows, removed=removed))

    def table(self):
        import pandas as pd
        return pd.DataFrame(self.steps)
