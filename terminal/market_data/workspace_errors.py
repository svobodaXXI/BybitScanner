"""Typed semantic failures shared by Workspace control and transport boundaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkspaceErrorDetails:
    code: str
    stage: str
    requested_symbol: str | None
    active_symbol: str | None
    retryable: bool
    message: str
    request_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "stage": self.stage,
            "requested_symbol": self.requested_symbol,
            "active_symbol": self.active_symbol,
            "retryable": self.retryable,
            "request_id": self.request_id,
            "message": self.message,
        }


class WorkspaceSemanticError(Exception):
    code = "workspace_failure"
    stage = "workspace"
    retryable = False

    def __init__(
        self, message: str, *, requested_symbol: str | None = None,
        active_symbol: str | None = None,
    ) -> None:
        super().__init__(message)
        self.requested_symbol = requested_symbol
        self.active_symbol = active_symbol

    def details(self, *, request_id: str | None = None) -> WorkspaceErrorDetails:
        return WorkspaceErrorDetails(
            code=self.code,
            stage=self.stage,
            requested_symbol=self.requested_symbol,
            active_symbol=self.active_symbol,
            retryable=self.retryable,
            request_id=request_id,
            message=str(self),
        )

    def envelope(self, *, request_id: str | None = None) -> dict[str, object]:
        return self.details(request_id=request_id).as_dict()


class UnsupportedWorkspaceInstrument(WorkspaceSemanticError, LookupError):
    code = "unsupported_instrument"
    stage = "instrument_lookup"


class WorkspaceCandidateNotReady(WorkspaceSemanticError, TimeoutError):
    code = "candidate_not_ready"
    stage = "candidate_readiness"
    retryable = True


class WorkspaceInstrumentBootstrapFailure(WorkspaceSemanticError):
    code = "instrument_bootstrap_failure"
    stage = "instrument_bootstrap"
    retryable = True


class InactiveWorkspace(WorkspaceSemanticError, LookupError):
    code = "inactive_workspace"
    stage = "active_workspace"
    retryable = True


class UnknownWorkspaceStream(WorkspaceSemanticError, LookupError):
    code = "unknown_stream"
    stage = "stream_resume"


class UpstreamWorkspaceMarketDataFailure(WorkspaceSemanticError):
    code = "upstream_market_data_failure"
    stage = "upstream_market_data"
    retryable = True
