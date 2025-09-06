from __future__ import annotations
import google.generativeai as genai
from .config import GOOGLE_API_KEY, GEMINI_MODEL

class LLMClient:
    """Chat con Gemini (google-generativeai) con historial en memoria."""
    def __init__(self):
        if not GOOGLE_API_KEY:
            raise RuntimeError("Falta GOOGLE_API_KEY en el entorno (.env).")
        genai.configure(api_key=GOOGLE_API_KEY)
        self.model = genai.GenerativeModel(GEMINI_MODEL)
        self.chat = self.model.start_chat(history=[])

    def ask(self, user_text: str) -> str:
        resp = self.chat.send_message(user_text)
        text = getattr(resp, "text", None)
        if text is None:
            parts = []
            try:
                for cand in getattr(resp, "candidates", []) or []:
                    content = getattr(cand, "content", None)
                    if content and hasattr(content, "parts"):
                        for part in content.parts:
                            t = getattr(part, "text", None) or str(part)
                            parts.append(t)
            except Exception:
                pass
            text = "\n".join(p for p in parts if p)
        return text or ""


    def start(self, system_instruction: str | None = None):
        """(Re)inicia el chat opcionalmente con un system_instruction."""
        import google.generativeai as genai
        if system_instruction:
            self.model = genai.GenerativeModel(self.model.model_name if hasattr(self.model, "model_name") else "gemini-1.5-flash",
                                               system_instruction=system_instruction)
        self.chat = self.model.start_chat(history=[])
        return self

