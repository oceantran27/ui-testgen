import os
from pathlib import Path
from functools import lru_cache
from app.core.logging import logger

class PromptManager:
    """
    Manages loading and caching of agent prompts from text files.
    """
    
    def __init__(self, prompts_dir: str | Path | None = None):
        if prompts_dir is None:
            # Default to be/app/prompts/
            self.prompts_dir = Path(__file__).resolve().parents[1] / "prompts"
        else:
            self.prompts_dir = Path(prompts_dir)
            
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory not found at {self.prompts_dir}")

    @lru_cache(maxsize=32)
    def get_prompt(self, name: str) -> str:
        """
        Loads a prompt by name from the prompts directory.
        Looks for {name}.txt.
        """
        file_path = self.prompts_dir / f"{name}.txt"
        
        if not file_path.exists():
            logger.error(f"Prompt file not found: {file_path}")
            # Fallback or raise error? For now, return empty or a placeholder
            return f"Error: Prompt '{name}' not found."
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return content
        except Exception as e:
            logger.exception(f"Failed to read prompt file {file_path}: {e}")
            return f"Error: Failed to load prompt '{name}'."

# Singleton instance
prompt_manager = PromptManager()
