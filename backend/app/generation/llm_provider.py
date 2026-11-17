from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generator
import time
import logging

logger = logging.getLogger(__name__)

class BaseLLMProvider(ABC):
    """Abstract base class for LLM generation providers."""

    @abstractmethod
    def generate_answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate an answer given a user query and a list of retrieved context chunks.
        Returns a dict: {"answer": str, "model": str}
        """
        pass

    @abstractmethod
    def generate_answer_stream(self, query: str, context_chunks: List[Dict[str, Any]]) -> Generator[Dict[str, Any], None, None]:
        """Stream answer tokens given a user query and a list of retrieved context chunks."""
        pass

    @abstractmethod
    def extract_text_from_image(self, image_bytes: bytes, mime_type: str = "image/png") -> str:
        """Extract and transcribe all text, bills, notes, and tables from an image."""
        pass

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """Check if provider credentials and connectivity are valid."""
        pass


class GeminiLLMProvider(BaseLLMProvider):
    """Google Gemini API implementation supporting google-genai and google-generativeai."""

    def __init__(self, api_key: str, model_name: str = "gemini-3.6-flash"):
        self.api_key = api_key
        self.model_name = model_name or "gemini-3.6-flash"
        self._client = None
        self._sdk_type = None
        self._initialize_client()

    def _initialize_client(self):
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            logger.warning("GEMINI_API_KEY is not set or using placeholder.")
            return

        # Attempt modern google-genai SDK first
        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
            self._sdk_type = "google-genai"
            logger.info("Initialized Gemini client via google-genai SDK.")
            return
        except (ImportError, Exception) as e:
            logger.debug(f"google-genai SDK initialization note: {e}")

        # Fallback to google-generativeai
        try:
            import google.generativeai as genai_legacy
            genai_legacy.configure(api_key=self.api_key)
            self._client = genai_legacy.GenerativeModel(self.model_name)
            self._sdk_type = "google-generativeai"
            logger.info("Initialized Gemini client via google-generativeai SDK.")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")

    def _refresh_credentials_if_needed(self):
        from app.core.config import Settings
        try:
            current_settings = Settings()
            fresh_key = current_settings.GEMINI_API_KEY.strip()
            fresh_model = current_settings.GEMINI_MODEL or "gemini-3.5-flash-lite"
            if fresh_key and fresh_key != "your_gemini_api_key_here":
                if self._client is None or self.api_key != fresh_key or self.model_name != fresh_model:
                    self.api_key = fresh_key
                    self.model_name = fresh_model
                    self._initialize_client()
        except Exception as e:
            logger.debug(f"Could not refresh settings: {e}")

    def check_health(self) -> Dict[str, Any]:
        self._refresh_credentials_if_needed()
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return {
                "status": "warning",
                "configured": False,
                "message": "GEMINI_API_KEY is not configured in .env"
            }

        try:
            if self._sdk_type == "google-genai":
                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents="Respond with the single word: OK"
                )
                text = response.text if hasattr(response, "text") else str(response)
                return {"status": "ok", "configured": True, "model": self.model_name, "sample_response": text.strip()}
            elif self._sdk_type == "google-generativeai":
                response = self._client.generate_content("Respond with the single word: OK")
                return {"status": "ok", "configured": True, "model": self.model_name, "sample_response": response.text.strip()}
            else:
                return {
                    "status": "error",
                    "configured": True,
                    "message": "Neither google-genai nor google-generativeai SDK could be loaded."
                }
        except Exception as e:
            logger.error(f"Gemini health check error: {e}")
            return {
                "status": "error",
                "configured": True,
                "message": str(e)
            }

    def extract_text_from_image(self, image_bytes: bytes, mime_type: str = "image/png") -> str:
        """
        Uses Gemini Vision to perform high-accuracy OCR on bills, handwritten/printed notes, receipts, and scans.
        """
        self._refresh_credentials_if_needed()
        if not self._client:
            raise RuntimeError("Gemini API key is not configured. Cannot process image OCR.")

        ocr_prompt = (
            "You are a specialized OCR and document analysis engine.\n"
            "Extract and transcribe all text, numbers, bill line items, totals, dates, headers, "
            "handwritten notes, and tables from this document image with highest accuracy.\n"
            "Preserve original wording, numbers, line breaks, and structure."
        )

        try:
            models_to_try = [self.model_name]
            for m in ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash"]:
                if m not in models_to_try:
                    models_to_try.append(m)


            for attempt, target_model in enumerate(models_to_try):
                try:
                    if self._sdk_type == "google-genai":
                        from google.genai import types
                        response = self._client.models.generate_content(
                            model=target_model,
                            contents=[
                                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                                ocr_prompt
                            ]
                        )
                        text = response.text if hasattr(response, "text") else str(response)
                        return text.strip()
                    elif self._sdk_type == "google-generativeai":
                        import io
                        import PIL.Image
                        image = PIL.Image.open(io.BytesIO(image_bytes))
                        response = self._client.generate_content([ocr_prompt, image])
                        return response.text.strip()
                except Exception as e:
                    err_msg = str(e)
                    if ("503" in err_msg or "UNAVAILABLE" in err_msg) and attempt < len(models_to_try) - 1:
                        logger.info(f"Vision OCR model {target_model} busy, trying {models_to_try[attempt+1]}...")
                        continue
                    raise e
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Image text extraction failed: {err_msg}")
            if "401" in err_msg or "UNAUTHENTICATED" in err_msg or "ACCESS_TOKEN_TYPE_UNSUPPORTED" in err_msg:
                raise RuntimeError(
                    "Gemini API key authentication failed (401 Unauthorized). "
                    "The key in .env appears to be an internal session token ('AQ...'). "
                    "Gemini Vision requires a free API key from https://aistudio.google.com/apikey (starts with 'AIzaSy...'). "
                    "Please update GEMINI_API_KEY in .env."
                )
            raise RuntimeError(f"OCR / Vision extraction error: {err_msg}")

    def _build_grounded_prompt(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        context_blocks = []
        for i, chunk in enumerate(context_chunks, 1):
            doc_name = chunk.get("document_name", "Unknown Document")
            page_num = chunk.get("page_number", "Unknown Page")
            content = chunk.get("content", "").strip()
            context_blocks.append(f"[Source {i}: {doc_name}, Page {page_num}]\n{content}")

        context_str = "\n\n".join(context_blocks)

        return f"""You are a helpful, knowledgeable, and grounded AI assistant answering questions based on the provided document excerpts.

CRITICAL INSTRUCTIONS:
1. Base your answer strictly on the provided Context excerpts below. Do not fabricate facts, external links, or hallucinate citations.
2. For every factual statement and recommendation mentioned, cite the source document name and page number (e.g. [Document: report.pdf, Page 3]).
3. When answering synthesis, roadmap, or advisory questions (such as 'what should I learn first?', 'what topics are covered?', 'how should I prepare?', or 'summarize this document'):
   - Synthesize a helpful, well-structured answer from the subjects, chapters, and study materials present in the excerpts.
   - Highlight foundational topics first (e.g., C-Programming, Data Structures, Discrete Mathematics / Set Theory, or Computer Organization) as listed in the resources, and cite the specific books, playlists, or tests provided.
4. Only if the provided context is completely unrelated to the user question, state:
"I cannot find relevant information in the provided document excerpts to answer this question."
5. Format your response cleanly using markdown (bullet points, bold headers, and clickable links if URLs are present in the excerpts).

---
CONTEXT EXCERPTS:
{context_str}
---

USER QUESTION:
{query}

GROUNDED ANSWER (with citations):"""

    def generate_answer_stream(self, query: str, context_chunks: List[Dict[str, Any]]) -> Generator[Dict[str, Any], None, None]:
        self._refresh_credentials_if_needed()
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            yield {"type": "delta", "text": "Error: GEMINI_API_KEY is not configured. Please set a valid Gemini API key in your .env file."}
            yield {"type": "done", "model": self.model_name, "full_text": "Error: GEMINI_API_KEY is not configured."}
            return

        prompt = self._build_grounded_prompt(query, context_chunks)
        models_to_try = [self.model_name]
        for fallback_m in ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash"]:
            if fallback_m not in models_to_try:
                models_to_try.append(fallback_m)


        for attempt, target_model in enumerate(models_to_try):
            accumulated = []
            try:
                if self._sdk_type == "google-genai":
                    response_stream = self._client.models.generate_content_stream(
                        model=target_model,
                        contents=prompt
                    )
                    for chunk in response_stream:
                        chunk_text = chunk.text if hasattr(chunk, "text") and chunk.text else ""
                        if chunk_text:
                            accumulated.append(chunk_text)
                            yield {"type": "delta", "text": chunk_text}
                    
                    full_answer = "".join(accumulated).strip()
                    yield {"type": "done", "model": target_model, "full_text": full_answer}
                    return
                elif self._sdk_type == "google-generativeai":
                    response_stream = self._client.generate_content(prompt, stream=True)
                    for chunk in response_stream:
                        chunk_text = chunk.text if hasattr(chunk, "text") and chunk.text else ""
                        if chunk_text:
                            accumulated.append(chunk_text)
                            yield {"type": "delta", "text": chunk_text}
                    
                    full_answer = "".join(accumulated).strip()
                    yield {"type": "done", "model": target_model, "full_text": full_answer}
                    return
                else:
                    yield {"type": "delta", "text": "Error: Gemini SDK is not available."}
                    yield {"type": "done", "model": target_model, "full_text": "Error: Gemini SDK is not available."}
                    return
            except Exception as e:
                err_msg = str(e)
                logger.warning(f"Streaming attempt {attempt + 1} with {target_model} failed: {err_msg}")
                # Retry on busy server OR transient network / DNS glitch if no tokens have been sent yet
                is_transient = (
                    "503" in err_msg or "UNAVAILABLE" in err_msg or "high demand" in err_msg.lower() or
                    "getaddrinfo" in err_msg or "Name or service not known" in err_msg or "RemoteDisconnected" in err_msg
                )
                if len(accumulated) == 0 and is_transient:
                    if attempt < len(models_to_try) - 1:
                        logger.info(f"Retrying generation with next model {models_to_try[attempt + 1]} after transient error...")
                        time.sleep(1.0)
                        continue

                if "getaddrinfo" in err_msg or "Name or service not known" in err_msg or "Failed to establish" in err_msg:
                    err_clean = (
                        "\n\n⚠️ **Network Connection Interrupted**\n\n"
                        "Could not connect to Google Gemini servers (`getaddrinfo failed`). "
                        "This indicates a temporary internet or DNS interruption. "
                        "Please verify your connection and resubmit your question."
                    )
                else:
                    err_clean = f"\n\n[Error during generation: {err_msg}]"

                yield {"type": "delta", "text": err_clean}
                yield {"type": "done", "model": target_model, "full_text": "".join(accumulated) + err_clean}
                return

    def generate_answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        self._refresh_credentials_if_needed()
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return {
                "answer": "Error: GEMINI_API_KEY is not configured. Please set a valid Gemini API key in your .env file.",
                "model": self.model_name
            }

        prompt = self._build_grounded_prompt(query, context_chunks)

        # Model candidates for automatic fallback if a model experiences high-demand 503 spikes
        models_to_try = [self.model_name]
        for fallback_m in ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash"]:
            if fallback_m not in models_to_try:
                models_to_try.append(fallback_m)


        max_retries = len(models_to_try)
        for attempt, target_model in enumerate(models_to_try):
            try:
                if self._sdk_type == "google-genai":
                    response = self._client.models.generate_content(
                        model=target_model,
                        contents=prompt
                    )
                    return {
                        "answer": response.text.strip(),
                        "model": target_model
                    }
                elif self._sdk_type == "google-generativeai":
                    response = self._client.generate_content(prompt)
                    return {
                        "answer": response.text.strip(),
                        "model": target_model
                    }
                else:
                    return {
                        "answer": "Error: Gemini SDK is not available.",
                        "model": target_model
                    }
            except Exception as e:
                err_msg = str(e)
                logger.warning(f"Generation attempt {attempt + 1} with {target_model} failed: {err_msg}")
                if "503" in err_msg or "UNAVAILABLE" in err_msg or "high demand" in err_msg.lower():
                    # High-demand spike, try next fallback model immediately
                    if attempt < max_retries - 1:
                        logger.info(f"Model {target_model} busy, falling back to {models_to_try[attempt + 1]}...")
                        continue
                    return {
                        "answer": "Gemini servers are currently experiencing high demand. Please try again in a few moments.",
                        "model": target_model
                    }
                elif "429" in err_msg or "ResourceExhausted" in err_msg or "quota" in err_msg.lower():
                    if attempt < max_retries - 1:
                        time.sleep(1.5)
                        continue
                    return {
                        "answer": "Rate limit / quota exceeded on the Gemini API free tier. Please wait a moment and try again.",
                        "model": target_model
                    }
                elif "401" in err_msg or "UNAUTHENTICATED" in err_msg or "ACCESS_TOKEN_TYPE_UNSUPPORTED" in err_msg or "invalid authentication" in err_msg.lower():
                    return {
                        "answer": (
                            "⚠️ **Gemini API Key Authentication Failed (401 Unauthorized)**\n\n"
                            "The key currently set in `.env` starts with `AQ.`, which is an internal session token rather than a valid Google Gemini API key.\n\n"
                            "**How to fix:**\n"
                            "1. Generate a free API key at [Google AI Studio](https://aistudio.google.com/apikey)\n"
                            "2. The key will start with `AIzaSy...`\n"
                            "3. Paste it into your `.env` file:\n"
                            "```ini\n"
                            "GEMINI_API_KEY=AIzaSyYourNewKeyHere\n"
                            "```\n"
                            "4. Once saved, submit your question again!"
                        ),
                        "model": self.model_name
                    }
                return {
                    "answer": f"Error generating answer: {err_msg}",
                    "model": self.model_name
                }
