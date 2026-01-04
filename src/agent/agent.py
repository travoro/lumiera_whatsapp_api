"""LangChain agent orchestrator with Claude."""
from typing import Dict, Any
from langchain_anthropic import ChatAnthropic
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from src.agent.tools import all_tools
from src.config import settings
from src.utils.logger import log


# System prompt for the agent (in French since all internal logic is in French)
SYSTEM_PROMPT = """Tu es un assistant virtuel pour les sous-traitants du BTP (construction).

**Rôle**: Aider les sous-traitants à gérer leurs projets via WhatsApp.

**Capacités**:
- Lister les chantiers (projets) actifs
- Consulter les tâches par chantier
- Accéder aux descriptions, plans, images et commentaires des tâches
- Récupérer les documents du projet
- Signaler des incidents avec texte et photos
- Mettre à jour la progression des tâches
- Marquer les tâches comme terminées
- Changer la langue de l'utilisateur
- Escalader vers un humain si nécessaire

**Règles importantes**:
1. Toutes les actions doivent utiliser les outils fournis
2. Ne jamais inventer de données
3. Si une demande n'est pas claire, demander des précisions
4. Si une demande est hors de tes capacités, utiliser l'outil escalate_to_human
5. Pour signaler un incident, au moins une image ET une description sont OBLIGATOIRES
6. Pour ajouter un commentaire, si c'est un audio, il doit d'abord être transcrit en français
7. Rester professionnel et concis
8. Si l'utilisateur demande quelque chose d'impossible ou d'inapproprié, refuser poliment et expliquer pourquoi

**Format de réponse**:
- Réponses claires et structurées
- Utiliser des listes numérotées pour plusieurs items
- Inclure les IDs des projets/tâches quand pertinent
- Être concis mais informatif

Rappel: Tu opères entièrement en français en interne. Les messages de l'utilisateur ont déjà été traduits en français, et ta réponse sera traduite dans la langue de l'utilisateur."""


def create_agent() -> AgentExecutor:
    """Create and configure the LangChain agent with Claude."""

    # Initialize Claude model
    llm = ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
        temperature=settings.anthropic_temperature,
        max_tokens=settings.anthropic_max_tokens,
    )

    # Create prompt template
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    # Create agent with tool calling
    agent = create_tool_calling_agent(llm, all_tools, prompt)

    # Create agent executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=all_tools,
        verbose=settings.debug,
        handle_parsing_errors=True,
        max_iterations=5,
    )

    log.info("Agent created successfully")
    return agent_executor


class LumieraAgent:
    """Main agent class for handling user requests."""

    def __init__(self):
        """Initialize the Lumiera agent."""
        self.agent_executor = create_agent()
        log.info("Lumiera Agent initialized")

    async def process_message(
        self,
        user_id: str,
        phone_number: str,
        language: str,
        message_text: str,
        chat_history: list = None,
    ) -> str:
        """Process a user message and return a response.

        Args:
            user_id: The user's ID
            phone_number: The user's WhatsApp phone number
            language: The user's preferred language
            message_text: The message text (already translated to French)
            chat_history: Optional chat history for context

        Returns:
            The response text (in French, to be translated back)
        """
        try:
            # Prepare agent input
            agent_input = {
                "input": message_text,
                "user_id": user_id,
                "phone_number": phone_number,
                "language": language,
            }

            if chat_history:
                agent_input["chat_history"] = chat_history

            # Run agent
            result = await self.agent_executor.ainvoke(agent_input)

            # Extract output
            output = result.get("output", "Désolé, je n'ai pas pu traiter votre demande.")

            log.info(f"Agent processed message for user {user_id}")
            return output

        except Exception as e:
            log.error(f"Error processing message: {e}")
            return "Désolé, une erreur s'est produite. Veuillez réessayer."


# Global agent instance
lumiera_agent = LumieraAgent()
