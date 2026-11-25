class Rejected(ValueError):
    def __init__(self, message, status=400, code=None, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details
