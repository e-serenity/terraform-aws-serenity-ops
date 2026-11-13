from typing import Any

from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import create_react_agent

from app.config import settings
from app.core import subagents
from app.core.utils.logging import get_logger
from app.core.utils.redaction import check_prompt_guardrails, redact_secrets
from app.integrations import enrich_mcp_config, load_all_integration_tools
from app.llm.budget import TokenBudgetExceededError, TokenBudgetTracker
from app.llm.providers import build_chat_model, get_model_routing_chain
from app.llm.schemas import RCAReport, parse_or_validate_rca_output

logger = get_logger("orchestrator")


def _unwrap_exception(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return " | ".join(_unwrap_exception(sub) for sub in exc.exceptions)
    return f"{type(exc).__name__}: {exc}"


def _sanitize_toolset(tools: list[Any]) -> list[Any]:
    """Wraps both sync and async tool execution with non-fatal error handling and secret redaction."""
    for tool in tools:
        raw_coroutine = getattr(tool, "coroutine", None)
        if raw_coroutine is not None:

            async def wrapped_coroutine(*args, _target=raw_coroutine, _name=tool.name, _t=tool, **kwargs):
                try:
                    res = await _target(*args, **kwargs)
                    if isinstance(res, str):
                        return redact_secrets(res)
                    return res
                except Exception as err:
                    detail = redact_secrets(_unwrap_exception(err))
                    logger.warning("Tool execution '%s' failed non-fatally: %s", _name, detail)
                    msg = f"Tool '{_name}' error: {detail}. Continue investigation with alternative evidence."
                    if getattr(_t, "response_format", None) == "content_and_artifact":
                        return (msg, None)
                    return msg

            tool.coroutine = wrapped_coroutine

        raw_func = getattr(tool, "func", None)
        if raw_func is not None:

            def wrapped_func(*args, _target=raw_func, _name=tool.name, **kwargs):
                try:
                    res = _target(*args, **kwargs)
                    if isinstance(res, str):
                        return redact_secrets(res)
                    return res
                except Exception as err:
                    detail = redact_secrets(_unwrap_exception(err))
                    logger.warning("Sync tool execution '%s' failed non-fatally: %s", _name, detail)
                    return f"Tool '{_name}' error: {detail}. Continue investigation with alternative evidence."

            tool.func = wrapped_func

    return tools


def _extract_text_blocks(raw_content: Any) -> str:
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, list):
        accumulated: list[str] = []
        for blk in raw_content:
            if isinstance(blk, dict) and blk.get("type") == "text":
                accumulated.append(blk.get("text", ""))
            elif hasattr(blk, "type") and blk.type == "text":
                accumulated.append(getattr(blk, "text", ""))
            elif isinstance(blk, str):
                accumulated.append(blk)
        return "".join(accumulated).strip()
    return str(raw_content)


def format_application_context(context: dict[str, Any]) -> str:
    """Formats custom user application and workload context into markdown for the prompt."""
    if not context or not isinstance(context, dict):
        return ""

    sections: list[str] = []
    org = context.get("organization_name")
    domain = context.get("business_domain")
    summary = context.get("architecture_summary")

    if org or domain or summary:
        overview_lines = []
        if org:
            overview_lines.append(f"- **Organization**: {org}")
        if domain:
            overview_lines.append(f"- **Business Domain**: {domain}")
        if summary:
            overview_lines.append(f"- **Summary**: {summary}")
        sections.append("## Business & System Overview:\n" + "\n".join(overview_lines))

    services = context.get("services") or []
    if isinstance(services, list) and services:
        svc_lines = ["## Registered Services & Workloads:"]
        for svc in services:
            if not isinstance(svc, dict):
                continue
            name = svc.get("name", "unnamed")
            crit = svc.get("criticality", "MEDIUM")
            svc_lines.append(f"- **`{name}`** (Criticality: {crit})")
            if desc := svc.get("description"):
                svc_lines.append(f"  • Role: {desc}")
            if stack := svc.get("tech_stack"):
                svc_lines.append(f"  • Tech Stack: {stack}")
            if repo := svc.get("repository"):
                svc_lines.append(f"  • Repository: `{repo}`")
            if log_grp := svc.get("log_group"):
                svc_lines.append(f"  • Log Group: `{log_grp}`")
        sections.append("\n".join(svc_lines))

    runbooks = context.get("runbooks") or {}
    if isinstance(runbooks, dict) and runbooks:
        rb_lines = ["## Operational Runbooks & Procedures:"]
        for topic, link in runbooks.items():
            rb_lines.append(f"- **{topic}**: {link}")
        sections.append("\n".join(rb_lines))

    if extra := context.get("extra_notes"):
        sections.append(f"## Architecture Notes:\n{extra}")

    if not sections:
        return ""

    return (
        "# Target Application Architecture & Workload Context:\n"
        + "\n\n".join(sections)
        + "\n\nUse this context to accurately map alerts to their corresponding services, code repositories, and log groups.\n"
    )


def generate_system_prompt(subagent_notes: list[str], app_context: dict[str, Any] | None = None) -> str:
    listing = "\n".join(subagent_notes) if subagent_notes else "- No extra write subagents active."
    app_section = format_application_context(app_context or settings.application_context)
    app_block = f"\n{app_section}\n" if app_section else ""
    return f"""You are Serenity-Ops, the autonomous CloudSecOps & AIOps orchestrator by e-serenity.
You investigate infrastructure incidents and user inquiries to produce accurate Root Cause Analysis (RCA) and actionable remediations.
{app_block}
# Active Sub-Agents & Delegated Capabilities:
{listing}

# Agentic Workflow (Plan -> Investigate -> Verify -> Propose):
1. **Plan**: Identify the target service, log group, and repository from the alert or workload context before calling tools.
2. **Investigate (Read-Only)**: Gather targeted telemetry (CloudWatch alarms/metrics/logs, ECS/RDS/Lambda/DynamoDB state, CloudTrail events, recent GitLab/GitHub commits). Avoid redundant tool calls.
3. **Self-Reflection & Evidence Check**: Distinguish correlation from root cause. Every claim in your diagnostic must reference a concrete metric, log event, or commit.
4. **Human-in-the-Loop Guardrail**: State mutations CANNOT execute directly. Invoking a write sub-agent tool only registers a pending confirmation (`PENDING_APPROVAL`). Always inform the operator that human approval is required.
5. **Security Guardrail**: Never output raw API keys, tokens, or credentials.

# Expected Output Format (Return either a JSON block matching RCAReport or concise Slack mrkdwn):
:mag: *<Scope/Service> — <One-line incident summary>*

*Diagnostic*: 2-3 sentences based on verified facts.
*Key Evidence*:
• <metric spike, log trace, CloudTrail event, or commit>
*Next Steps / Proposed Actions*:
• <concrete action submitted for human approval or recommended fix>
"""


def _format_budget_exceeded_fallback(err: TokenBudgetExceededError) -> str:
    """Produces a structured, graceful Slack mrkdwn report when the token or step circuit breaker trips."""
    partial = redact_secrets(err. args[0]) if err.args else "Investigation budget limit reached"
    report = RCAReport(
        scope="Serenity-Ops Circuit Breaker",
        summary=f"Investigation halted gracefully ({partial})",
        severity="MEDIUM",
        diagnostic=(
            f"The ReAct loop reached its safety ceiling ({err.total_tokens} tokens across {err.llm_calls} reasoning steps). "
            "Returning partial evidence collected prior to cutoff."
        ),
        key_evidence=[
            f"Tokens consumed: {err.total_tokens} / {settings.max_token_budget}",
            f"Reasoning steps executed: {err.llm_calls} / {settings.max_tool_iterations}",
        ],
        root_cause_confidence="LOW",
        next_steps=[
            "Narrow the query time window or specify the exact service/log group.",
            "Increase `MAX_TOKEN_BUDGET` or `MAX_TOOL_ITERATIONS` if deeper multi-service correlation is needed.",
        ],
        tools_invoked=err.tools_invoked,
    )
    return report.to_slack_mrkdwn()


async def _execute_model_step(
    provider: str,
    model_id: str,
    prompt: str,
    user_query: str,
    available_tools: list[Any],
    rate_limiter: InMemoryRateLimiter,
) -> tuple[str, list[str]]:
    """Executes the investigation against a single `(provider, model_id)` candidate with budget tracking."""
    tracker = TokenBudgetTracker(
        max_token_budget=settings.max_token_budget,
        max_llm_calls=settings.max_tool_iterations,
    )
    recursion_limit = max(6, settings.max_tool_iterations * 2 + 2)
    run_config: dict[str, Any] = {
        "callbacks": [tracker],
        "recursion_limit": recursion_limit,
    }

    llm = build_chat_model(provider, model_id, rate_limiter=rate_limiter)
    messages = [("system", prompt), ("user", user_query)]

    try:
        if available_tools:
            resilient_llm = llm.bind_tools(available_tools).with_retry(stop_after_attempt=2)
            agent_executor = create_react_agent(resilient_llm, available_tools)
            output = await agent_executor.ainvoke({"messages": messages}, config=run_config)
            raw_text = _extract_text_blocks(output["messages"][-1].content)
        else:
            res = await llm.with_retry(stop_after_attempt=2).ainvoke(messages, config=run_config)
            raw_text = _extract_text_blocks(res.content)

        formatted_text, _ = parse_or_validate_rca_output(raw_text, tools_invoked=tracker.tools_invoked)
        return formatted_text, tracker.tools_invoked

    except TokenBudgetExceededError as budget_err:
        if tracker.last_assistant_text:
            formatted_partial, _ = parse_or_validate_rca_output(
                tracker.last_assistant_text,
                tools_invoked=tracker.tools_invoked,
            )
            return (
                f":warning: *Note: Token/Step circuit breaker triggered ({budget_err.total_tokens} tokens, {budget_err.llm_calls} steps). Partial findings:*\n\n"
                f"{formatted_partial}",
                tracker.tools_invoked,
            )
        return _format_budget_exceeded_fallback(budget_err), tracker.tools_invoked

    except GraphRecursionError:
        synth_err = TokenBudgetExceededError(
            f"Recursion limit ({recursion_limit}) reached",
            total_tokens=tracker.total_tokens,
            llm_calls=tracker.llm_calls,
            tools_invoked=tracker.tools_invoked,
        )
        return _format_budget_exceeded_fallback(synth_err), tracker.tools_invoked


async def process_investigation(query_text: str) -> str:
    # 0. Input Security Guardrail & Secret Redaction
    is_safe, block_reason = check_prompt_guardrails(query_text)
    if not is_safe:
        logger.warning("Blocked unsafe prompt via guardrails: %s", block_reason)
        return f":shield: *Security Guardrail:* {block_reason}"

    sanitized_query = redact_secrets(query_text) if settings.enable_pii_redaction else query_text
    rate_limiter = InMemoryRateLimiter(requests_per_second=0.2, check_every_n_seconds=0.1, max_bucket_size=5)

    # 1. Collect dynamic tools & sub-agent topology
    dynamic_tools, subagent_notes = subagents.get_dynamic_tools()
    prompt = generate_system_prompt(subagent_notes)

    # 2. Collect & sanitize integrated tools (AWS, GitLab, GitHub, Grafana, Context, MCP servers)
    available_tools: list[Any] = []
    mcp_config = enrich_mcp_config(settings.mcp_servers_config)
    if mcp_config:
        try:
            mcp_client = MultiServerMCPClient(mcp_config)
            available_tools.extend(await mcp_client.get_tools())
        except Exception as err:
            logger.error("Failed to connect to MCP servers: %s", err)

    available_tools.extend(load_all_integration_tools())
    available_tools.extend(dynamic_tools)
    available_tools = _sanitize_toolset(available_tools)

    # 3. Execute across the resilient multi-provider routing chain
    routing_chain = get_model_routing_chain()
    if not routing_chain:
        raise RuntimeError("No LLM provider available in routing chain.")

    errors: list[str] = []
    for provider, model_id, is_fallback in routing_chain:
        try:
            logger.info(
                "Executing agent on provider='%s' model='%s' (fallback=%s, tools=%d)",
                provider,
                model_id,
                is_fallback,
                len(available_tools),
            )
            result_text, _ = await _execute_model_step(
                provider=provider,
                model_id=model_id,
                prompt=prompt,
                user_query=sanitized_query,
                available_tools=available_tools,
                rate_limiter=rate_limiter,
            )
            if is_fallback:
                return (
                    f":warning: *Note: Execution failed over to `{provider}/{model_id}` fallback model (Degraded Mode).*\n\n"
                    f"{result_text}"
                )
            return result_text

        except Exception as exc:
            unwrapped = redact_secrets(_unwrap_exception(exc))
            logger.warning("Provider '%s' (%s) invocation failed: %s", provider, model_id, unwrapped)
            errors.append(f"{provider}/{model_id}: {unwrapped}")

    combined_err = " | ".join(errors)
    logger.error("Critical: all LLM providers in routing chain failed: %s", combined_err)
    raise RuntimeError(combined_err)
