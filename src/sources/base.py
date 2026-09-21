"""Source adapter interface. Each implementation is responsible only for
acquisition — normalization happens downstream in jobs/normalize.py."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.jobs.schemas import RawJob


class JobSource(ABC):
    def __init__(self, company_name: str, identifier: str):
        self.company_name = company_name
        self.identifier = identifier

    @abstractmethod
    def fetch_jobs(self) -> list[RawJob]:
        """Fetch raw postings for this company. Must not raise on a single
        malformed posting — skip it and continue. May raise on total failure
        (network/HTTP error); the caller (workflows/process_job.py) is
        responsible for isolating one source's failure from the others."""
        raise NotImplementedError
