import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "llama3.1:8b")

VALID_STANCES = {"supportive", "opposed", "neutral"}


class DebaterAgent:
    def __init__(self, country: str, policy_context: str) -> None:
        self.country = country
        self.policy_context = policy_context

    def _build_prompt(self, topic: str, history: list[dict]) -> str:
        if history:
            lines = [
                f"{entry['agent']}: {entry['message']}"
                for entry in history[-6:]
            ]
            history_text = "\n".join(lines)
        else:
            history_text = "No prior statements have been made. You are the first to speak."

        return (
            f"You are the official debate representative for {self.country}.\n"
            f"You are participating in a structured international policy debate.\n"
            f"The debate topic is: \"{topic}\"\n\n"
            f"Debate history so far:\n{history_text}\n\n"
            f"Your country's official policy positions relevant to this topic:\n"
            f"{self.policy_context}\n\n"
            f"Instructions:\n"
            f"1. Respond strictly as the {self.country} representative. Do not speak for any other country.\n"
            f"2. Ground every claim you make in the policy positions listed above. Do not introduce positions that are not in your policy context.\n"
            f"3. Your response must be a single coherent paragraph of three to five sentences.\n"
            f"4. Briefly acknowledge the most recent speaker's point before presenting {self.country}'s position.\n"
            f"5. The very last line of your response must state your stance using this exact format:\n"
            f"   Stance: supportive\n"
            f"   or\n"
            f"   Stance: opposed\n"
            f"   or\n"
            f"   Stance: neutral\n"
            f"   Choose the stance that accurately reflects {self.country}'s position on the topic.\n"
        )

    async def generate(self, topic: str, history: list[dict]) -> dict:
        prompt = self._build_prompt(topic=topic, history=history)
        payload = {
            "model": LLM_MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 512,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                raw_text: str = result.get("response", "").strip()
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {OLLAMA_BASE_URL}. "
                f"Ensure the Ollama service is running. Detail: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Network error communicating with Ollama: {exc}"
            ) from exc

        stance = self._extract_stance(raw_text)
        clean_message = self._clean_message(raw_text)

        logger.info("Agent %s generated response with stance: %s", self.country, stance)
        return {"message": clean_message, "stance": stance}

    @staticmethod
    def _extract_stance(text: str) -> str:
        match = re.search(
            r"Stance:\s*(supportive|opposed|neutral)",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).lower()
        tail = text[-120:].lower()
        for stance in VALID_STANCES:
            if stance in tail:
                return stance
        return "neutral"

    @staticmethod
    def _clean_message(text: str) -> str:
        cleaned = re.sub(
            r"\n?Stance:\s*(supportive|opposed|neutral)[.\s]*$",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        return cleaned
