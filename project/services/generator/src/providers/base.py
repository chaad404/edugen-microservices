from abc import ABC, abstractmethod
from typing import List, Tuple
from ..schemas import GenerateBatchRequest, GeneratedMCQ

class BaseLLMProvider(ABC):
    """Abstract base class for all question generation providers."""

    @abstractmethod
    def generate(self, req: GenerateBatchRequest) -> Tuple[List[GeneratedMCQ], int, float]:
        """
        Generates MCQs given a request.
        Returns: (questions: List[GeneratedMCQ], tokens_used: int, estimated_cost_usd: float)
        """
        pass
