"""Conversation memory management service."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.config import settings
from src.utils.logger import log


class ConversationMemoryService:
    """Service for managing conversation memory and context."""

    def __init__(self):
        """Initialize the conversation memory service."""
        if settings.llm_provider == "openai":
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",  # Fast and cheap for summarization
                api_key=settings.openai_api_key,
                temperature=0.3,
                max_tokens=500,
            )
            log.info("Conversation memory service initialized with OpenAI")
        else:
            self.llm = ChatAnthropic(
                model="claude-3-5-haiku-20241022",  # Use Haiku for fast summarization
                api_key=settings.anthropic_api_key,
                temperature=0.3,
                max_tokens=500,
            )
            log.info("Conversation memory service initialized with Claude")

        self.max_messages_before_summary = 20

        # Summary caching: {user_id: {summary: str, timestamp: datetime, message_count: int}}
        self._summary_cache = {}
        self._cache_duration = timedelta(minutes=5)

    async def summarize_conversation(self, messages: List[Dict[str, Any]]) -> str:
        """Summarize a conversation history.

        Args:
            messages: List of message dicts with content and direction

        Returns:
            Summary of the conversation
        """
        try:
            # Format messages for summarization
            conversation_text = []
            for msg in messages:
                role = "Utilisateur" if msg["direction"] == "inbound" else "Assistant"
                content = msg.get("content", "")
                conversation_text.append(f"{role}: {content}")

            conversation = "\n".join(conversation_text)

            # Create summarization prompt
            summary_prompt = f"""Résume cette conversation entre un sous-traitant BTP et un assistant virtuel.
Inclus les points clés, les demandes principales, et les actions effectuées.
Sois concis et factuel.

Conversation:
{conversation}

Résumé:"""

            # Generate summary
            response = await self.llm.ainvoke(
                [
                    SystemMessage(
                        content="Tu es un assistant qui résume des conversations de manière concise et factuelle."
                    ),
                    HumanMessage(content=summary_prompt),
                ]
            )

            summary = response.content.strip()
            log.info(f"Generated conversation summary: {len(summary)} chars")
            return summary

        except Exception as e:
            log.error(f"Error summarizing conversation: {e}")
            return ""

    def should_summarize(self, message_count: int) -> bool:
        """Check if conversation should be summarized.

        Args:
            message_count: Number of messages in history

        Returns:
            True if should summarize, False otherwise
        """
        return message_count >= self.max_messages_before_summary

    def _should_skip_summarization(
        self, user_id: str, messages: List[Dict[str, Any]], recent_message_count: int
    ) -> Optional[str]:
        """Check if we should skip summarization and use cached summary.

        Args:
            user_id: User ID for cache lookup
            messages: Full conversation history
            recent_message_count: Number of recent messages to keep

        Returns:
            Cached summary if available and valid, None otherwise
        """
        # Check if we have a cached summary for this user
        if user_id not in self._summary_cache:
            return None

        cache_entry = self._summary_cache[user_id]
        now = datetime.utcnow()

        # Check if cache is still valid (within 5 minutes)
        if now - cache_entry["timestamp"] > self._cache_duration:
            log.info(f"Cache expired for user {user_id}")
            del self._summary_cache[user_id]
            return None

        # Check if message count hasn't changed significantly
        # (only use cache if we're summarizing the same range)
        older_message_count = len(messages) - recent_message_count
        if older_message_count != cache_entry["message_count"]:
            log.info(f"Message count changed for user {user_id}, invalidating cache")
            del self._summary_cache[user_id]
            return None

        # Check if last message was less than 1 minute ago (rapid-fire protection)
        if messages:
            try:
                last_message = messages[-1]
                last_message_time_str = last_message.get("created_at", "")
                # Parse as naive datetime (remove timezone info to match 'now')
                last_message_time = datetime.fromisoformat(
                    last_message_time_str.replace("Z", "").replace("+00:00", "")
                )
                if now - last_message_time < timedelta(minutes=1):
                    log.info(
                        f"Rapid-fire detected for user {user_id}, using cached summary"
                    )
                    return cache_entry["summary"]
            except Exception as e:
                log.warning(f"Error checking rapid-fire timing: {e}")
                # Continue without rapid-fire check

        log.info(f"Using cached summary for user {user_id}")
        return cache_entry["summary"]

    async def get_optimized_history(
        self,
        messages: List[Dict[str, Any]],
        recent_message_count: int = 15,  # Increased from 6/8 to 15
        user_id: Optional[str] = None,
    ) -> tuple[List, str]:
        """Get optimized conversation history.

        For long conversations:
        - Summarize older messages (with caching)
        - Keep recent messages as-is

        Args:
            messages: Full conversation history
            recent_message_count: Number of recent messages to keep unsummarized (default: 15)
            user_id: Optional user ID for caching

        Returns:
            Tuple of (recent_messages, summary_of_older_messages)
        """
        if len(messages) <= recent_message_count:
            # Short conversation, no need to summarize
            log.info(
                f"Conversation has {len(messages)} messages, no summarization needed (threshold: {recent_message_count})"
            )
            return messages, ""

        # Check if we can use cached summary
        if user_id:
            cached_summary = self._should_skip_summarization(
                user_id, messages, recent_message_count
            )
            if cached_summary:
                recent_messages = messages[-recent_message_count:]
                return recent_messages, cached_summary

        # Split into older and recent
        older_messages = messages[:-recent_message_count]
        recent_messages = messages[-recent_message_count:]

        # Summarize older messages
        summary = await self.summarize_conversation(older_messages)

        # Cache the summary
        if user_id:
            self._summary_cache[user_id] = {
                "summary": summary,
                "timestamp": datetime.utcnow(),
                "message_count": len(older_messages),
            }
            log.info(f"Cached summary for user {user_id}")

        log.info(
            f"Optimized history: {len(older_messages)} old messages → summary, {len(recent_messages)} recent messages kept"
        )

        return recent_messages, summary


# Global instance
memory_service = ConversationMemoryService()
