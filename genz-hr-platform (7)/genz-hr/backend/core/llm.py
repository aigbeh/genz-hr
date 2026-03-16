"""
GENZ HR — Ollama LLM Client
Local AI inference wrapper. All processing stays on-device.
"""
import json
import httpx
from typing import Optional, Generator
from loguru import logger

from backend.core.config import settings


class OllamaClient:
    """
    Thin wrapper around the Ollama REST API.
    Used by GENZ Agents for document generation and analysis.
    """

    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.model = model or settings.OLLAMA_MODEL
        self._client = httpx.Client(timeout=120.0)

    def is_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            resp = self._client.get(f"{self.base_url}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str, system: str = "", temperature: float = 0.3) -> str:
        """
        Generate text from a prompt.
        Returns the full response as a string.
        """
        if not self.is_available():
            logger.warning("Ollama not available — using fallback response")
            return self._fallback_response(prompt)

        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "top_p": 0.9,
                    "num_predict": 1024,
                },
            }
            resp = self._client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=90.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")

        except Exception as e:
            logger.error(f"Ollama generate error: {e}")
            return self._fallback_response(prompt)

    def generate_json(self, prompt: str, system: str = "") -> dict:
        """Generate and parse a JSON response."""
        json_system = (system or "") + "\nRespond ONLY with valid JSON. No markdown, no preamble."
        raw = self.generate(prompt, system=json_system, temperature=0.1)

        # Strip code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e} — raw: {raw[:200]}")
            return {"error": "Failed to parse JSON response", "raw": raw[:500]}

    def analyze_cv(self, cv_text: str, position: str, required_skills: list) -> dict:
        """Use LLM to enhance CV analysis with narrative summary."""
        prompt = f"""
You are an HR specialist. Analyze this CV for the position of {position}.

Required skills: {', '.join(required_skills[:10])}

CV Text (first 2000 chars):
{cv_text[:2000]}

Return JSON with these fields:
- summary: 2-3 sentence candidate summary
- top_strengths: list of 3 strengths
- concerns: list of 1-2 concerns or gaps
- recommendation: "strongly recommend" | "recommend" | "consider" | "do not recommend"
"""
        return self.generate_json(prompt)

    def generate_performance_analysis(
        self, employee_name: str, tasks: list, completion_pct: float, period: str
    ) -> str:
        """Generate narrative performance analysis."""
        task_summary = "\n".join(
            f"- {t.get('description', 'Task')}: {t.get('status', 'unknown')} (weight: {t.get('weight', 0)}%)"
            for t in tasks[:10]
        )
        prompt = f"""
You are an HR performance analyst. Write a professional 3-paragraph performance review for:

Employee: {employee_name}
Period: {period}
Completion: {completion_pct:.0f}%
Tasks:
{task_summary}

Include: overall assessment, specific achievements, areas for improvement.
Keep it professional, specific, and constructive. Max 200 words.
"""
        return self.generate(prompt, temperature=0.5)

    def generate_hr_policy(self, company_name: str, industry: str, policy_type: str) -> str:
        """Generate an HR policy document draft."""
        prompt = f"""
You are a Nigerian HR compliance specialist. Write a {policy_type} policy for:

Company: {company_name}
Industry: {industry}

Requirements:
- Comply with Nigerian Labour Act (Cap L1 LFN 2004)
- Include practical, enforceable clauses
- Use clear, professional language
- Keep to 400-600 words

Start directly with the policy title and content.
"""
        return self.generate(prompt, temperature=0.3)

    def summarize_anomalies(self, anomalies: list[dict], company_name: str) -> str:
        """Generate a concise anomaly summary for Esther."""
        if not anomalies:
            return "No anomalies detected."

        items = "\n".join(f"- {a.get('employee', 'Unknown')}: {a.get('reason', '')}"
                          for a in anomalies[:10])
        prompt = f"""
Summarize these HR anomalies for {company_name} in 2-3 sentences.
Focus on what needs immediate attention. Be concise and direct.

Anomalies:
{items}
"""
        return self.generate(prompt, temperature=0.2)

    def _fallback_response(self, prompt: str) -> str:
        """Graceful fallback when Ollama is offline."""
        return (
            "[AI analysis unavailable — Ollama not running. "
            "Start Ollama with: ollama serve]"
        )

    def close(self):
        self._client.close()


# Singleton client
llm_client = OllamaClient()
