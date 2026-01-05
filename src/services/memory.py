"""Conversation memory management service."""
from typing import List, Dict, Any
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from src.config import settings
from src.utils.logger import log


class ConversationMemoryService:
    """Service for managing conversation memory and context."""

    def __init__(self):
        """Initialize the conversation memory service."""
        self.llm = ChatAnthropic(
            model="claude-3-5-haiku-20241022",  # Use Haiku for fast summarization
            api_key=settings.anthropic_api_key,
            temperature=0.3,
            max_tokens=500,
        )
        self.max_messages_before_summary = 20
        log.info("Conversation memory service initialized")

    async def summarize_conversation(
        self,
        messages: List[Dict[str, Any]]
    ) -> str:
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
            response = await self.llm.ainvoke([
                SystemMessage(content="Tu es un assistant qui résume des conversations de manière concise et factuelle."),
                HumanMessage(content=summary_prompt)
            ])

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

    async def get_optimized_history(
        self,
        messages: List[Dict[str, Any]],
        recent_message_count: int = 6
    ) -> tuple[List, str]:
        """Get optimized conversation history.

        For long conversations:
        - Summarize older messages
        - Keep recent messages as-is

        Args:
            messages: Full conversation history
            recent_message_count: Number of recent messages to keep unsummarized

        Returns:
            Tuple of (recent_messages, summary_of_older_messages)
        """
        if len(messages) <= recent_message_count:
            # Short conversation, no need to summarize
            return messages, ""

        # Split into older and recent
        older_messages = messages[:-recent_message_count]
        recent_messages = messages[-recent_message_count:]

        # Summarize older messages
        summary = await self.summarize_conversation(older_messages)

        log.info(f"Optimized history: {len(older_messages)} old messages → summary, {len(recent_messages)} recent messages kept")

        return recent_messages, summary


# Global instance
memory_service = ConversationMemoryService()
