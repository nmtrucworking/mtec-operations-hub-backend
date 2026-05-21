class EvaluationNotificationService:
    def notify(self, event_type: str, payload: dict) -> None:
        _ = event_type, payload
