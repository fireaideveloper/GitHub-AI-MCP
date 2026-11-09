class AppError(Exception):
    """Safe, public failure with a stable machine code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)
