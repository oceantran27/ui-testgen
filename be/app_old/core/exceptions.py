class AIProcessingError(Exception):
    """Raised when there is an issue processing data with the AI service."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class DatabaseConnectionError(Exception):
    """Raised when there is an issue connecting to the database."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
