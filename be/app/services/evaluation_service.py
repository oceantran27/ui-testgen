import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class EvaluationService:
    """Service for evaluating AI model outputs against Ground Truth."""

    def calculate_score(
        self, 
        om_intents: List[Dict[str, Any]], 
        total_gt_count: int, 
        threshold: float = 0.7,
        penalty_factor: float = 2.0
    ) -> Dict[str, Any]:
        """
        DEPRECATED: This scoring mechanism is no longer in use.
        The evaluation logic has been moved to the standalone `evaluation` module.
        This method is kept for backward compatibility and will be removed in a future version.
        """
        logger.warning("The 'calculate_score' method is deprecated and will be removed in a future version.")
        return {}