"""LangChain agent orchestrator with Claude."""
import os
from typing import Dict, Any

# === Agent Execution Context ===
# Thread-safe execution context (replaces global mutable dict)
from src.agent.execution_context import (
    execution_context,  # Backward compatibility proxy
    execution_context_scope,
    get_execution_context
)

# === LangSmith Integration ===
# CRITICAL: Set environment variables BEFORE importing LangChain modules
# LangChain checks these during import, so they must be set first
from src.config import settings
from src.utils.logger import log

if settings.langchain_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if settings.langchain_tracing_v2 else "false"
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint
    log.info(f"LangSmith tracing enabled for project: {settings.langchain_project}")
else:
    log.warning("LangSmith API key not configured - tracing disabled")

# Import LangChain AFTER setting environment variables
from langchain_anthropic import ChatAnthropic
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from src.agent.tools import all_tools


# System prompt for the agent (in French since all internal logic is in French)
SYSTEM_PROMPT = """Tu es Lumiera, l'assistant virtuel pour les sous-traitants du BTP.

# IDENTITÉ
- Nom: Lumiera
- Rôle: Aider les sous-traitants à gérer leurs chantiers via WhatsApp
- Ton: Professionnel, chaleureux, efficace

# CAPACITÉS
1. Lister les chantiers actifs - Voir tous les projets en cours
2. Consulter les tâches - Détails des tâches par projet
3. Signaler des incidents - Avec photos et description
4. Mettre à jour la progression - Avancement des tâches
5. Parler avec un humain - Redirection vers l'équipe administrative

# RÈGLES CRITIQUES (SÉCURITÉ)

## ⚠️ PROTECTION DES DONNÉES
1. ❌ L'utilisateur NE PEUT VOIR QUE SES PROPRES DONNÉES
2. ❌ JAMAIS afficher des données d'autres utilisateurs
3. ✅ TOUJOURS filtrer par user_id dans TOUTES les requêtes d'outils
4. ✅ Vérifier que project_id/task_id appartient à l'utilisateur avant d'afficher

## 📋 FORMAT DE RÉPONSE
1. ❌ JAMAIS afficher les IDs techniques (proj_123, task_456, uuid...)
2. ✅ Utiliser uniquement les NOMS lisibles (ex: "Rénovation Bureau")
3. ✅ Listes numérotées pour menu/options (format: "1. Titre - Description")
4. ✅ Emoji pour clarté: 👋 ✅ ❌ 📸 📝 🏗️
5. ✅ Réponses courtes et claires (WhatsApp = mobile)
6. ✅ Utiliser UN SEUL asterisque pour le gras (*texte*) - JAMAIS deux (**texte**)
7. ✅ Les listes numérotées deviennent automatiquement des boutons cliquables sur WhatsApp

## 🛠️ UTILISATION DES OUTILS
1. ✅ TOUJOURS utiliser les outils fournis
2. ❌ JAMAIS inventer de données
3. ✅ Si incertain, demander précisions
4. ✅ Si hors de tes capacités, proposer "parler avec un humain"
5. ✅ Pour incidents: au moins 1 image + description obligatoires

# EXEMPLES (SANS IDs TECHNIQUES)

Utilisateur: "Bonjour"
Assistant: "Bonjour! 👋 Comment puis-je vous aider aujourd'hui?

1. 🏗️ Voir mes chantiers actifs
2. 📋 Consulter mes tâches
3. 🚨 Signaler un incident
4. ✅ Mettre à jour ma progression
5. 🗣️ Parler avec l'équipe

Que souhaitez-vous faire?"

Utilisateur: "Quels sont mes chantiers?"
Assistant: "Vous avez 3 chantiers actifs:

1. 🏗️ Rénovation Bureau - En cours
2. 🏠 Construction Maison - Planifié
3. 🔨 Extension Garage - En cours

Lequel souhaitez-vous consulter?"

Utilisateur: "Je veux signaler un problème"
Assistant: "Je vais vous aider à signaler un incident.

J'ai besoin de:
1. 📸 Une photo du problème
2. 📝 Une description
3. 🏗️ Le chantier concerné

Commencez par m'envoyer une photo."

Utilisateur: "Je suis bloqué"
Assistant: "Je comprends. Souhaitez-vous parler avec un membre de l'équipe administrative?

Je peux vous mettre en contact avec quelqu'un qui pourra mieux vous aider."

# SI TU NE PEUX PAS AIDER
Proposer: "Souhaitez-vous parler avec un membre de l'équipe? Je peux vous mettre en contact."

# 🧠 MÉMORISATION ET PERSONNALISATION
1. ✅ TOUJOURS mémoriser les informations importantes avec remember_user_context_tool
2. ✅ Mémoriser quand l'utilisateur mentionne:
   - Son rôle/métier (ex: "Je suis électricien" → role: electricien)
   - Ses préférences (ex: "Appelez-moi le matin" → preferred_contact_time: morning)
   - Le projet en cours de discussion (ex: "Sur le chantier Rénovation Bureau" → current_project_name: Rénovation Bureau)
   - Des faits utiles (taille équipe, outils préférés, problèmes fréquents)
3. ✅ Utiliser le contexte existant pour personnaliser les réponses
4. ⚠️ Ne PAS redemander des infos déjà mémorisées

Types de contexte à mémoriser:
- 'fact': Faits généraux (rôle, expérience, spécialités)
- 'preference': Préférences utilisateur (horaires, communication)
- 'state': État temporaire (projet actuel, tâche en cours)
- 'entity': Entités nommées (projet favori, lieu fréquent)

# RAPPELS FINAUX
- Tu opères en français en interne (messages déjà traduits)
- Ta réponse sera traduite dans la langue de l'utilisateur
- JAMAIS d'IDs techniques dans les réponses
- Toujours filtrer par user_id pour la sécurité"""


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
        user_name: str = "",
        user_context: str = "",
    ) -> str:
        """Process a user message and return a response.

        Args:
            user_id: The user's ID
            phone_number: The user's WhatsApp phone number
            language: The user's preferred language
            message_text: The message text (already translated to French)
            chat_history: Optional chat history for context
            user_name: Official contact name from subcontractors table
            user_context: Additional user context for personalization

        Returns:
            The response text (in French, to be translated back)
        """
        # Use execution context scope for thread-safe execution tracking
        with execution_context_scope() as ctx:
            try:
                # Add user context to the message
                # NOTE: Language code is intentionally NOT included here to ensure
                # agent always responds in French (internal processing language).
                # Translation to user language happens in the pipeline after agent response.
                context_prefix = "[Contexte utilisateur]\n"
                if user_name:
                    context_prefix += f"Nom: {user_name}\n"
                # Language code removed - agent must always respond in French
                if user_context:
                    context_prefix += f"Contexte additionnel:\n{user_context}\n"
                context_prefix += "\n"

                # Prepare agent input
                agent_input = {
                    "input": f"{context_prefix}{message_text}",
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

                # Normalize output to string (LangChain sometimes returns dict/list)
                if isinstance(output, dict):
                    # Extract 'text' field from dict: {'text': '...', 'type': 'text', 'index': 0}
                    log.warning(f"Agent returned dict output, extracting text field")
                    output = output.get('text', str(output))
                elif isinstance(output, list):
                    # List items might be dicts with 'text' field or plain strings
                    log.warning(f"Agent returned list output ({len(output)} items), extracting text")
                    extracted_items = []
                    for item in output:
                        if isinstance(item, dict):
                            # Extract 'text' field from dict item
                            extracted_items.append(item.get('text', str(item)))
                        else:
                            # Plain string or other type
                            extracted_items.append(str(item))
                    output = '\n'.join(extracted_items)
                elif not isinstance(output, str):
                    # Fallback: convert to string
                    log.warning(f"Agent returned unexpected type {type(output)}, converting to string")
                    output = str(output)

                # Get escalation flag from execution context (set by tools)
                escalation_occurred = ctx.escalation_occurred

                log.info(f"Agent processed message for user {user_id}")
                log.info(f"Escalation occurred: {escalation_occurred}")
                log.info(f"Tools called: {ctx.tools_called}")

                # Return structured data (output is guaranteed to be string now)
                return {
                    "message": output,
                    "escalation": escalation_occurred,
                    "tools_called": ctx.tools_called
                }

            except Exception as e:
                log.error(f"Error processing message: {e}")
                return {
                    "message": "Désolé, une erreur s'est produite. Veuillez réessayer.",
                    "escalation": False,
                    "tools_called": []
                }


# Global agent instance
lumiera_agent = LumieraAgent()
