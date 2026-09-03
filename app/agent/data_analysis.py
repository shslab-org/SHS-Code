from __future__ import annotations

"""
DataAnalysisAgent — SHSCode specialised for data exploration, statistics, and charting.

Inherits from SHSCode via the correct MRO:
  DataAnalysisAgent → SHSCode → ToolCallAgent → ReActAgent → BaseAgent

The only change from SHSCode is:
  • Custom system_prompt (data-analysis focus)
  • DataVisualization tool added to the standard toolkit
"""

from app.agent.shscode import SHSCode
from app.tool.data_viz import DataVisualization


DATA_ANALYSIS_PROMPT = """\
You are a data analysis AI agent specialised in exploring datasets, computing
statistics, and producing charts. Use Python for computation and the data_viz
tool to generate charts. Save all outputs to workspace/.

Your process:
  1. Load and inspect the data (shape, types, nulls, sample rows).
  2. Compute descriptive statistics (mean, median, std, correlations, etc.).
  3. Identify patterns, anomalies, or insights.
  4. Produce at least one chart that visualises the most important finding.
  5. Write a plain-language summary (workspace/analysis_summary.md).
  6. Call terminate when all deliverables are saved.
"""


class DataAnalysisAgent(SHSCode):
    """
    SHSCode-derived agent with data-analysis focus.

    Uses super().__init__() to traverse the full MRO:
      DataAnalysisAgent.__init__
        → SHSCode.__init__           (sets mode, session_id)
          → ToolCallAgent.__init__ (creates LLM, selector, retry_policy)
            → ReActAgent.__init__  (nothing extra)
              → BaseAgent.__init__ (sets state, memory, gate, db, …)

    After the full chain runs, we extend the toolkit with DataVisualization.
    """

    name          = "data_analysis"
    system_prompt = DATA_ANALYSIS_PROMPT

    def __init__(self) -> None:
        # Correctly calls the full MRO — no manual attribute assignment
        super().__init__()

        # Add DataVisualization on top of SHSCode's standard toolkit
        self.tools.add(DataVisualization())

        # FIX: Rebuild the tool selector so it knows about the new tool,
        # but carry over the old selector's stats so that performance history
        # (success/failure counts) is not lost across the rebuild.
        from app.tool.selector import ToolSelector
        old_stats = self._selector.get_stats() if hasattr(self, "_selector") else {}
        self._selector = ToolSelector(tool_names=list(self.tools._tools.keys()))
        # Restore any accumulated stats for tools that still exist
        if old_stats:
            self._selector.set_stats(old_stats)
