def normalize_analysis_model_name(model_name: str | None) -> str:
    selected_model = (model_name or "gemini-2.5-flash").strip().lower()

    if selected_model == "openai":
        return "openai"
    if selected_model in {"gemini", "gemini-2.5-flash", "gemini-1.5-flash"}:
        return selected_model
    return "gemini-2.5-flash"


def resolve_gemini_model_name(model_name: str | None) -> str:
    normalized_model = normalize_analysis_model_name(model_name)
    return "gemini-2.5-flash" if normalized_model == "gemini" else normalized_model
