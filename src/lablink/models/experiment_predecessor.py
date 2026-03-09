"""ExperimentPredecessor model — DAG link between experiments."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from lablink.models.base import Base


class ExperimentPredecessor(Base):
    """Association table linking an experiment to one of its predecessors.

    Forms a DAG (directed acyclic graph) of experiment lineage.
    Composite PK (experiment_id, predecessor_id) enforces uniqueness.
    """

    __tablename__ = "experiment_predecessors"
    __table_args__ = (
        UniqueConstraint(
            "experiment_id", "predecessor_id", name="uq_experiment_predecessor"
        ),
    )

    experiment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiments.id"), primary_key=True
    )
    predecessor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiments.id"), primary_key=True
    )
