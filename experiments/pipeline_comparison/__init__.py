"""
Full Pipeline Comparison Experiment Framework
==============================================
Plan methods, retrieval methods, pipeline runner, metrics, and report generation
for end-to-end EDA framework comparison experiments.
"""

from .pipeline_runner import PipelineRunner
from .plan_methods import (
    OursPlanMethod,
    CoTPlanMethod,
    SelfReflectionPlanMethod,
    ToTPlanMethod,
    AutoGenPlanMethod,
    create_plan_method,
)
from .retrieval_methods import (
    OursRetrieval,
    NaiveRAGRetrieval,
    CritiqueRAGRetrieval,
    CRAGRetrieval,
    create_retrieval_method,
)
from .metrics import (
    calculate_target_deviation,
    aggregate_metrics,
    compute_per_case_metrics,
    compute_final_report,
)
from .report_generator import generate_markdown_report
