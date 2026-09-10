from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from src.analytics.composure_scorer import FILLER_WORDS
from src.config import config

logger = logging.getLogger(__name__)


SYCOPHANTIC_PREFIX_PATTERNS = [
    re.compile(r"^good point[,\.\!]?\s*(but\s*|however\s*)?", re.IGNORECASE),
    re.compile(r"^i understand[,\.\!]?\s*(that\s*|what you'?re saying[,\.]?\s*)?(but\s*|however\s*)?", re.IGNORECASE),
    re.compile(r"^that'?s (a\s*)?(fair|valid|good) point[,\.\!]?\s*(but\s*|however\s*)?", re.IGNORECASE),
    re.compile(r"^fair enough[,\.\!]?\s*(but\s*|however\s*)?", re.IGNORECASE),
    re.compile(r"^great question[,\.\!]?\s*", re.IGNORECASE),
    re.compile(r"^i hear you[,\.\!]?\s*(but\s*|however\s*)?", re.IGNORECASE),
    re.compile(r"^you'?re right[,\.\!]?\s*(that\s*)?(but\s*|however\s*)?", re.IGNORECASE),
    re.compile(r"^i see what you mean[,\.\!]?\s*(but\s*|however\s*)?", re.IGNORECASE),
    re.compile(r"^while that may be true[,\.\!]?\s*", re.IGNORECASE),
]


def clean_spoken_text(text: str) -> str:
    """Sanitize LLM output for spoken TTS:
    - Strip markdown, asterisks, citations, extra whitespace.
    - Aggressively purge polite sycophantic prefixes ("Good point", "I understand", etc.).
    - Enforce adversarial brevity (<25 words per turn) while preserving concluding trap questions.
    """
    cleaned = re.sub(r"[\*\_#`~\[\]]", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Remove leading/trailing quotation marks often emitted by LLMs
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()

    # Strip sycophantic polite agreement prefixes
    for pat in SYCOPHANTIC_PREFIX_PATTERNS:
        cleaned = pat.sub("", cleaned).strip()

    # Capitalize first character if stripped
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]

    # Enforce spoken brevity (<25 words)
    words = cleaned.split(" ")
    if len(words) > 25:
        # Split sentences and prioritize keeping the final challenge/question
        sentences = re.split(r"(?<=[.?!])\s+", cleaned)
        if len(sentences) > 1 and len(sentences[-1].split(" ")) <= 18:
            # Keep first sentence snippet + final trap question
            final_q = sentences[-1]
            remaining_budget = 24 - len(final_q.split(" "))
            first_words = sentences[0].split(" ")[:max(4, remaining_budget)]
            first_part = " ".join(first_words).rstrip(".,!?")
            cleaned = f"{first_part}. {final_q}"
        else:
            # Hard truncate words while ensuring ending punctuation
            cleaned = " ".join(words[:24]).rstrip(".,;:") + "?"

    return cleaned


def extract_and_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Robustly extract and parse JSON object from LLM response text, stripping markdown code blocks."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Regex search for the outermost {...} block
    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


class LLMClient:
    """Universal low-latency streaming LLM client for adversarial debate.
    
    Supports OpenAI (gpt-4o-mini), Google Gemini (gemini-2.0-flash), Anthropic (claude-3-5-sonnet),
    and a zero-downtime heuristic mock engine for offline testing and grading.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.provider = provider or config.active_llm_provider
        self.model = model
        self._openai_client = None
        self._gemini_client = None

        if self.provider == "openai" and config.openai_api_key:
            try:
                from openai import AsyncOpenAI
                base_url = config.openai_base_url or ("https://openrouter.ai/api/v1" if config.openai_api_key.startswith("sk-or-") else None)
                client_kwargs: Dict[str, Any] = {"api_key": config.openai_api_key}
                if base_url:
                    client_kwargs["base_url"] = base_url
                    client_kwargs["default_headers"] = {
                        "HTTP-Referer": "https://github.com/miles-ai",
                        "X-Title": "Miles Voice AI",
                    }
                self._openai_client = AsyncOpenAI(**client_kwargs)
                self.model = self.model or config.openai_model
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {e}")
                self.provider = "mock"

        elif self.provider == "gemini" and config.gemini_api_key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=config.gemini_api_key)
                self.model = self.model or config.gemini_model
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
                self.provider = "mock"

        elif self.provider == "anthropic" and config.anthropic_api_key:
            self.model = self.model or "claude-3-5-sonnet-latest"

    async def stream_turn(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 60,
    ) -> AsyncIterator[str]:
        """Stream adversarial counter-arguments token-by-token."""
        if self.provider == "openai" and self._openai_client:
            async for token in self._stream_openai(messages, system_prompt, temperature, max_tokens):
                yield token
        elif self.provider == "gemini" and self._gemini_client:
            async for token in self._stream_gemini(messages, system_prompt, temperature, max_tokens):
                yield token
        elif self.provider == "anthropic" and config.anthropic_api_key:
            async for token in self._stream_anthropic(messages, system_prompt, temperature, max_tokens):
                yield token
        else:
            async for token in self._stream_heuristic_mock(messages, system_prompt):
                yield token

    async def stream_sentence_chunks(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 60,
    ) -> AsyncIterator[str]:
        """Stream LLM output grouped into spoken sentence/clause chunks for concurrent TTS pipelining.
        
        Yields clauses as soon as punctuation (., !, ?, --) or natural breath breaks occur.
        """
        buffer = ""
        is_first_chunk = True

        async for token in self.stream_turn(messages, system_prompt, temperature, max_tokens):
            buffer += token

            # Strip sycophancy on the fly from the leading tokens
            if is_first_chunk:
                for pat in SYCOPHANTIC_PREFIX_PATTERNS:
                    buffer = pat.sub("", buffer)

            # Check for punctuation boundary (. ! ? -- or comma after >= 5 words)
            words = buffer.strip().split()

            # Sentence boundary (. ! ? --)
            match = re.search(r"([.!?]+|\-\-)\s*", buffer)
            if match:
                split_idx = match.end()
                clause = buffer[:split_idx].strip()
                buffer = buffer[split_idx:]
                if clause:
                    cleaned_clause = clean_spoken_text(clause)
                    if cleaned_clause:
                        yield cleaned_clause
                        is_first_chunk = False
            elif len(words) >= 6 and re.search(r"[,;:]\s+", buffer):
                comma_match = re.search(r"[,;:]\s+", buffer)
                if comma_match:
                    split_idx = comma_match.end()
                    clause = buffer[:split_idx].strip()
                    buffer = buffer[split_idx:]
                    if clause:
                        cleaned_clause = clean_spoken_text(clause)
                        if cleaned_clause:
                            yield cleaned_clause
                            is_first_chunk = False
            elif len(words) >= 12:
                # Force split long clause to prevent TTS latency accumulation
                clause = " ".join(words[:8])
                buffer = " ".join(words[8:])
                cleaned_clause = clean_spoken_text(clause)
                if cleaned_clause:
                    yield cleaned_clause
                    is_first_chunk = False

        if buffer.strip():
            remaining = clean_spoken_text(buffer.strip())
            if remaining:
                yield remaining

    async def generate_turn(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 60,
    ) -> str:
        """Accumulate and return the complete sanitized spoken response."""
        chunks = []
        async for chunk in self.stream_turn(messages, system_prompt, temperature, max_tokens):
            chunks.append(chunk)
        raw_text = "".join(chunks)
        return clean_spoken_text(raw_text)

    async def _stream_openai(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        payload_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = "user" if m.get("role") == "user" else "assistant"
            payload_messages.append({"role": role, "content": m.get("content", "")})

        try:
            stream = await self._openai_client.chat.completions.create(
                model=self.model or config.openai_model or "gpt-4o-mini",
                messages=payload_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"OpenAI stream error: {e}. Falling back to heuristic mock.")
            async for token in self._stream_heuristic_mock(messages, system_prompt):
                yield token

    async def _stream_gemini(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        try:
            from google.genai import types
            prompt_content = f"{system_prompt}\n\n"
            for m in messages:
                prompt_content += f"{m.get('role').upper()}: {m.get('content')}\n"
            prompt_content += "ADVERSARY:"

            response = await self._gemini_client.aio.models.generate_content_stream(
                model=self.model or "gemini-2.0-flash",
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
            async for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Gemini stream error: {e}. Falling back to heuristic mock.")
            async for token in self._stream_heuristic_mock(messages, system_prompt):
                yield token

    async def _stream_anthropic(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream adversarial counter-arguments from Anthropic Messages API."""
        import json
        import httpx

        # Prepare messages adhering to Anthropic alternate role requirements
        payload_messages = []
        for m in messages:
            role = "user" if m.get("role") == "user" else "assistant"
            payload_messages.append({"role": role, "content": m.get("content", "")})

        if not payload_messages or payload_messages[0]["role"] != "user":
            payload_messages.insert(0, {"role": "user", "content": "I am ready to debate."})

        headers = {
            "x-api-key": config.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model or "claude-3-5-sonnet-latest",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": payload_messages,
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                async with client.stream("POST", "https://api.anthropic.com/v1/messages", headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        err_body = await resp.aread()
                        logger.error(f"Anthropic API error {resp.status_code}: {err_body.decode(errors='ignore')}")
                        async for token in self._stream_heuristic_mock(messages, system_prompt):
                            yield token
                        return

                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                event_data = json.loads(data_str)
                                if event_data.get("type") == "content_block_delta":
                                    delta = event_data.get("delta", {})
                                    if delta.get("type") == "text_delta" and delta.get("text"):
                                        yield delta["text"]
                            except Exception:
                                continue
        except Exception as e:
            logger.error(f"Anthropic stream error: {e}. Falling back to heuristic mock.")
            async for token in self._stream_heuristic_mock(messages, system_prompt):
                yield token

    async def _stream_heuristic_mock(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        """Offline sparring heuristic generator providing high-stakes punchy responses."""
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "").lower()
                break

        # Context-sensitive adversarial counters (<25 words)
        vc_responses = [
            "Your CAC is unsustainable and your churn will spike. Why should I fund a leaky bucket?",
            "That valuation is pure fantasy without locked enterprise contracts. What is your actual net retention?",
            "Network effects take years. What stops a well-capitalized competitor from undercutting you tomorrow?",
            "You are burning cash on marketing instead of product defensibility. What is your true payback period?",
            "That addressable market figure is wildly inflated. What percentage of that is actually serviceable?",
        ]
        salary_responses = [
            "Market data does not justify this increase without verifiable revenue attribution. What pipeline did you close?",
            "Our compensation bands are calibrated strictly against industry percentiles. Why do you deserve an out-of-band exception?",
            "Equity grants require milestone commitments. Are you willing to tie this compensation to quarterly delivery targets?",
            "Other team members deliver identical output within standard bandings. Why should finance treat you differently?",
        ]
        court_responses = [
            "Your sworn testimony directly contradicts the electronic access timestamps. Were you in the room or not?",
            "You claim complete ignorance, yet your signature authorized the financial transfer. Which statement is false?",
            "You hesitated before answering that question. Why did you wait three days before filing the incident report?",
            "That explanation defies basic common sense. Who gave you the explicit order to delete the log?",
        ]
        general_responses = [
            "That argument rests on an unproven assumption. What empirical data proves your premise?",
            "You are ignoring the catastrophic secondary consequences. How do you resolve that fatal contradiction?",
            "That is sentimental rhetoric, not hard logic. Answer the question directly.",
            "You have dodged the core counter-evidence. Where is your verifiable proof?",
        ]

        # Select matching pool
        if "marcus vance" in system_prompt.lower() or "vc_pitch" in system_prompt.lower():
            candidates = vc_responses
        elif "elena rostova" in system_prompt.lower() or "salary" in system_prompt.lower():
            candidates = salary_responses
        elif "prosecutor" in system_prompt.lower() or "cross-exam" in system_prompt.lower():
            candidates = court_responses
        else:
            candidates = general_responses

        chosen = random.choice(candidates)

        # Stream words with small async delay to emulate natural token generation
        words = chosen.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.02)

    async def generate_json_debrief(
        self,
        transcript_history: List[Dict[str, Any]],
        context: Dict[str, Any],
        model: str = "openai/gpt-4o",
    ) -> Dict[str, Any]:
        """Generate a deep post-debate evaluation using GPT-4o.

        Analyzes the full transcript, evaluates argument strength, consistency,
        filler words, hesitation, composure, and provides concrete coaching points.
        """
        import json

        # Build chronological transcript text
        transcript_lines = []
        user_word_count = 0
        user_turn_count = 0
        for entry in transcript_history:
            role = str(entry.get("role", "unknown")).upper()
            content = str(entry.get("content", "")).strip()
            interrupted = " [INTERRUPTED BY USER]" if entry.get("interrupted") else ""
            round_idx = entry.get("round", "")
            transcript_lines.append(f"[{role} Round {round_idx}]: {content}{interrupted}")
            if role == "USER":
                user_turn_count += 1
                user_word_count += len(content.split())

        transcript_text = "\n".join(transcript_lines) if transcript_lines else "No user speech recorded."

        scenario = context.get("scenario", "Debate")
        topic = context.get("topic", "General")
        persona_name = context.get("persona_name", "Adversary")
        difficulty = context.get("difficulty", "hard")

        system_prompt = (
            "You are an elite, world-class executive communication and debate evaluator for high-stakes sparring.\n"
            "Your job is to thoroughly evaluate the USER's performance against the adversary based on the complete debate transcript.\n"
            "Be rigorous, direct, and completely honest. Do NOT flatter the user.\n\n"
            "You must carefully evaluate:\n"
            "1. Actual Filler Words & Disfluencies: Detect the exact filler words ('um', 'uh', 'like', 'basically', 'actually', 'literally', 'you know', etc.) the user genuinely used. Distinguish legitimate verbs (e.g. 'I would like') from conversational crutches ('It was, like, ten percent').\n"
            "2. Cadence & Delivery: Realistic WPM based on their word count and response flow (typical human cadence is 120-180 WPM).\n"
            "3. Composure Under Pressure: Did they maintain calm authority or become defensive, evasive, or repetitive?\n"
            "4. Argument Strength & Substance: Did they answer direct questions with concrete facts/numbers, or hide behind buzzwords?\n"
            "5. Specific Weaknesses: Provide 3-4 bullet points citing EXACT quotes or moments from their answers where their argument faltered or was exposed.\n"
            "6. Actionable Coaching: Provide 3-4 concrete tactical directives on how to reframe their specific answers for maximum impact.\n\n"
            "You must return ONLY a valid JSON object with the following schema:\n"
            "{\n"
            '  "overall_score": <int 10-100>,\n'
            '  "composure_score": <int 10-100>,\n'
            '  "verdict": "<PUNCHY ALL-CAPS VERDICT TITLE, e.g. SURVIVED WITH SCARS, DISMANTLED ON UNIT ECONOMICS, COMPOSED DEFENSE>",\n'
            '  "verdict_description": "<1-2 sentence executive summary of performance>",\n'
            '  "cadence_wpm": <int 110-190>,\n'
            '  "filler_count": <int count of actual fillers used>,\n'
            '  "detected_fillers": ["<list of filler words actually used>"],\n'
            '  "key_weaknesses": [\n'
            '    "<Weakness 1 citing specific quote or argument from user>",\n'
            '    "<Weakness 2 citing specific quote or argument from user>",\n'
            '    "<Weakness 3 citing specific quote or argument from user>"\n'
            '  ],\n'
            '  "coaching_tips": [\n'
            '    "<Actionable coaching tip 1 tailored to the transcript>",\n'
            '    "<Actionable coaching tip 2 tailored to the transcript>",\n'
            '    "<Actionable coaching tip 3 tailored to the transcript>"\n'
            '  ],\n'
            '  "chapters": [\n'
            '    {"round": 1, "title": "Round 1: Initial Grilling", "summary": "<summary>", "score": <int 10-100>}\n'
            '  ],\n'
            '  "weakest_answer": {\n'
            '    "quote": "<exact user quote>",\n'
            '    "why_faltered": "<why the argument faltered>",\n'
            '    "vulnerability": "<tactical vulnerability exposed>"\n'
            '  },\n'
            '  "strongest_answer": {\n'
            '    "quote": "<exact user quote>",\n'
            '    "why_commanding": "<why it was commanding>",\n'
            '    "evidence_cited": "<evidence or metrics cited>"\n'
            '  },\n'
            '  "executive_reframes": [\n'
            '    {\n'
            '      "original_quote": "<original user quote>",\n'
            '      "executive_reframe": "<crisp, authoritative rewrite>",\n'
            '      "rationale": "<why this reframe commands the room>"\n'
            '    }\n'
            '  ]\n'
            "}"
        )

        user_prompt = (
            f"DEBATE SESSION METADATA:\n"
            f"- Scenario: {scenario}\n"
            f"- Topic: {topic}\n"
            f"- Opponent: {persona_name}\n"
            f"- Difficulty: {difficulty}\n"
            f"- User Turns Spoken: {user_turn_count}\n"
            f"- User Total Words: {user_word_count}\n\n"
            f"COMPLETE DEBATE TRANSCRIPT:\n"
            f"{transcript_text}\n\n"
            f"Evaluate the debate transcript thoroughly and return ONLY the JSON report."
        )

        # 1. Call OpenAI / OpenRouter GPT-4o
        if self._openai_client:
            try:
                response = await self._openai_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                    max_tokens=1200,
                )
                raw_json = response.choices[0].message.content
                if raw_json:
                    parsed = extract_and_parse_json(raw_json)
                    if parsed:
                        logger.info(f"[LLMClient] {model} generated debrief successfully: verdict={parsed.get('verdict')}")
                        return parsed
            except Exception as e:
                logger.error(f"[LLMClient] Error calling {model} for debrief: {e}")

        # 2. Fallback to Gemini if configured
        if self._gemini_client:
            try:
                from google.genai import types
                prompt_content = f"{system_prompt}\n\n{user_prompt}\n\nReturn JSON:"
                response = await self._gemini_client.aio.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt_content,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        response_mime_type="application/json",
                    ),
                )
                if response.text:
                    parsed = extract_and_parse_json(response.text)
                    if parsed:
                        return parsed
            except Exception as e:
                logger.error(f"[LLMClient] Gemini debrief fallback error: {e}")

        # 3. Fallback to heuristic debrief
        return self._heuristic_debrief_fallback(transcript_history, context)

    def _heuristic_debrief_fallback(
        self,
        transcript_history: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Offline fallback debrief generator grounded in actual transcript text."""
        import re

        user_texts = [
            str(entry.get("content", ""))
            for entry in transcript_history
            if str(entry.get("role", "")).lower() == "user"
        ]
        all_user_text = " ".join(user_texts)
        words = re.findall(r"\b\w+\b", all_user_text)
        word_count = len(words)

        # Detect actual fillers in user text using canonical lexicon
        detected_fillers = []
        for word in FILLER_WORDS:
            matches = re.findall(rf"\b{re.escape(word)}\b", all_user_text.lower())
            detected_fillers.extend(matches)

        score = max(55, min(92, 85 - len(detected_fillers) * 3))
        wpm = 145 if word_count > 10 else 130

        if user_texts:
            sorted_by_len = sorted(user_texts, key=lambda t: len(t.split()))
            weakest_str = sorted_by_len[0][:120]
            strongest_str = sorted_by_len[-1][:120]
            weakest = {
                "quote": weakest_str,
                "why_faltered": "Relied on conversational hedging rather than commanding empirical evidence.",
                "vulnerability": "Conceded the core premises without asserting hard counter-metrics.",
            }
            strongest = {
                "quote": strongest_str,
                "why_commanding": "Directly challenged the adversary's framing with decisive pacing.",
                "evidence_cited": "Asserted operational metrics and held ground under pressure.",
            }
        else:
            weakest = {
                "quote": "Our metrics are improving month over month.",
                "why_faltered": "Relied on qualitative optimism instead of auditable facts.",
                "vulnerability": "Left CAC payback and burn multiple undefended.",
            }
            strongest = {
                "quote": "We hold eighty percent gross margins with seven-month payback.",
                "why_commanding": "Front-loaded non-negotiable quantitative proof.",
                "evidence_cited": "Gross margin and payback window.",
            }

        reframes = [
            {
                "original_quote": weakest["quote"],
                "executive_reframe": "Our unit economics are profitable on first purchase, with a 7-month CAC payback across 1,200 paying seats.",
                "rationale": "Directly terminates the inquiry with auditable numbers, eliminating room for adversarial follow-up.",
            },
            {
                "original_quote": "We believe our moat will hold as we scale up.",
                "executive_reframe": "Our moat is proprietary workflow integration with 99.4% retention; replacement switching costs exceed $200K per customer.",
                "rationale": "Replaces belief with quantifiable switching costs and retention data.",
            },
        ]

        chapters = []
        rounds_seen = max(1, len([h for h in transcript_history if h.get("role") == "user"]))
        for r in range(1, rounds_seen + 1):
            chapters.append({
                "round": r,
                "title": f"Round {r}: Tactical Exchange",
                "summary": f"Exchanged arguments under Level {min(5, r + 1)} adversarial pressure.",
                "score": max(50, min(95, score + (r * 2) - 3)),
            })

        return {
            "overall_score": score,
            "composure_score": max(50, score - 5),
            "verdict": "CHALLENGE COMPLETED" if score >= 70 else "PRESSURE POINT EXPOSED",
            "verdict_description": "Defended core positions through adversarial questioning.",
            "cadence_wpm": wpm,
            "filler_count": len(detected_fillers),
            "detected_fillers": list(set(detected_fillers)),
            "key_weaknesses": [
                f"Used conversational filler words ({len(detected_fillers)} detected) during responses." if detected_fillers else "Relying on broad claims without citing granular metrics.",
                "Adversary successfully found leverage points in early answers.",
                "Hesitation between adversarial challenges and opening statements.",
            ],
            "coaching_tips": [
                "Lead immediately with your core metric or conclusion rather than building up.",
                "Embrace 1-2 seconds of quiet composure rather than filling space with placeholder words.",
                "Counter-attack with a clarifying question to reverse the burden of proof.",
            ],
            "chapters": chapters,
            "weakest_answer": weakest,
            "strongest_answer": strongest,
            "executive_reframes": reframes,
        }
