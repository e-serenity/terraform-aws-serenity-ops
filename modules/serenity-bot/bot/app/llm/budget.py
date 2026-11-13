"""Token Budget & ReAct Circuit Breaker for Serenity-Ops investigations."""

from typing import Any
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.utils.logging import get_logger

logger = get_logger("llm.budget")


class TokenBudgetExceededError(RuntimeError):
    """Raised when an investigation exceeds its configured token or iteration budget."""

    def __init__(self, message: str, total_tokens: int, llm_calls: int, tools_invoked: list[str]):
        super().__init__(message)
        self.total_tokens = total_tokens
        self.llm_calls = llm_calls
        self.tools_invoked = tools_invoked


class TokenBudgetTracker(BaseCallbackHandler):
    """Tracks token consumption and tool invocations across a ReAct investigation session.

    Triggers a graceful circuit breaker if token usage or LLM step count exceeds configured limits.
    """

    def __init__(self, max_token_budget: int = 32_000, max_llm_calls: int = 12) -> None:
        super().__init__()
        self.max_token_budget = max(1_000, max_token_budget)
        self.max_llm_calls = max(2, max_llm_calls)
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.total_tokens: int = 0
        self.llm_calls: int = 0
        self.tools_invoked: list[str] = []
        self.last_assistant_text: str = ""

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        name = serialized.get("name") or kwargs.get("name") or "unknown_tool"
        self.tools_invoked.append(str(name))

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        self.llm_calls += 1
        step_input = 0
        step_output = 0

        # 1. Check standard LLMResult.llm_output token usage if provided
        llm_output = response.llm_output or {}
        usage = llm_output.get("usage") or llm_output.get("token_usage") or {}
        if isinstance(usage, dict):
            step_input += int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            step_output += int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)

        # 2. Check generation message usage_metadata (LangChain >= 0.3 standard for Bedrock & Gemini)
        for gen_list in response.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                if msg is not None:
                    content = getattr(msg, "content", "")
                    if isinstance(content, str) and content.strip():
                        self.last_assistant_text = content.strip()
                    usage_meta = getattr(msg, "usage_metadata", None) or {}
                    if isinstance(usage_meta, dict) and (step_input == 0 and step_output == 0):
                        step_input += int(usage_meta.get("input_tokens") or 0)
                        step_output += int(usage_meta.get("output_tokens") or 0)
                elif getattr(gen, "text", ""):
                    self.last_assistant_text = gen.text.strip()

        # 3. Fallback character-based estimation (~4 chars/token) if provider omitted metadata
        if step_input == 0 and step_output == 0 and self.last_assistant_text:
            step_output = max(1, len(self.last_assistant_text) // 4)

        self.input_tokens += step_input
        self.output_tokens += step_output
        self.total_tokens = self.input_tokens + self.output_tokens

        if self.total_tokens > self.max_token_budget:
            logger.warning(
                "Token budget circuit breaker triggered: %d / %d tokens (calls=%d)",
                self.total_tokens,
                self.max_token_budget,
                self.llm_calls,
            )
            raise TokenBudgetExceededError(
                f"Token budget exceeded ({self.total_tokens} > {self.max_token_budget} tokens)",
                total_tokens=self.total_tokens,
                llm_calls=self.llm_calls,
                tools_invoked=list(self.tools_invoked),
            )

        if self.llm_calls > self.max_llm_calls:
            logger.warning(
                "Iteration circuit breaker triggered: %d / %d LLM calls (tokens=%d)",
                self.llm_calls,
                self.max_llm_calls,
                self.total_tokens,
            )
            raise TokenBudgetExceededError(
                f"Maximum reasoning steps exceeded ({self.llm_calls} > {self.max_llm_calls} steps)",
                total_tokens=self.total_tokens,
                llm_calls=self.llm_calls,
                tools_invoked=list(self.tools_invoked),
            )
