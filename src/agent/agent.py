"""LangChain agent orchestrator with Claude."""

import os
from typing import Any, Dict

# === Agent Execution Context ===
# Thread-safe execution context (replaces global mutable dict)
from src.agent.execution_context import execution_context_scope

# === LangSmith Integration ===
# CRITICAL: Set environment variables BEFORE importing LangChain modules
# LangChain checks these during import, so they must be set first
from src.config import settings
from src.utils.logger import log

if settings.langchain_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = (
        "true" if settings.langchain_tracing_v2 else "false"
    )
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint
    log.info(f"LangSmith tracing enabled for project: {settings.langchain_project}")
else:
    log.warning("LangSmith API key not configured - tracing disabled")

# isort: off
# Import LangChain AFTER setting environment variables
from langchain.agents import (
    AgentExecutor,  # type: ignore[attr-defined]
    create_tool_calling_agent,  # type: ignore[attr-defined]
)
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
# isort: on

# NOTE: all_tools import removed - now using build_tools_for_user() for closure pattern


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

# ⚙️ CONTEXTE UTILISATEUR (AUTO-INJECTÉ)
**IMPORTANT**: L'identité de l'utilisateur (user_id, phone_number, language) est automatiquement
gérée par le système via injection de contexte. Tu n'as PAS besoin de:
- ❌ Extraire ou mentionner le user_id dans tes réponses
- ❌ Demander le numéro de téléphone à l'utilisateur
- ❌ Te préoccuper de la langue (gestion automatique)

Ces informations sont capturées automatiquement lors de l'authentification et injectées
dans tous les outils. Concentre-toi uniquement sur l'extraction des paramètres métier:
- ✅ project_id (UUID du projet depuis l'état explicite ou les données précédentes)
- ✅ task_id (UUID de la tâche depuis l'état explicite ou les données précédentes)
- ✅ status, description, title, etc. (paramètres fonctionnels)

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

Utilisateur: "1"
Assistant: [Utilise list_tasks_tool avec project_id du premier projet de la liste précédente]

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

# 🔢 GESTION DES SÉLECTIONS NUMÉRIQUES ET NOMS DE PROJETS
Quand l'utilisateur envoie un chiffre (1, 2, 3...) ou un nom de projet après avoir vu une liste:
1. ✅ EXAMINER l'historique de conversation pour voir quelle liste tu as affichée
2. ✅ Si c'était une liste de projets → appeler list_tasks_tool avec le project_id (UUID) correspondant
3. ✅ Si c'était une liste de tâches → appeler get_task_description_tool avec le task_id (UUID) correspondant
4. ✅ UTILISER LES UUIDs EXACTS que tu vois dans les données pour les appels d'outils
5. ❌ JAMAIS afficher les IDs techniques (UUIDs) à l'utilisateur dans tes réponses
6. ❌ JAMAIS inventer ou générer de nouveaux IDs (comme "proj_xxx", "task_xxx", "user_xxx")
7. ❌ NE JAMAIS demander à l'utilisateur de répéter ou clarifier - tu as toutes les infos dans l'historique

EXEMPLE CORRECT:
- Liste affichée: "1. 🏗️ Champigny" avec project_id="abc-123-def-456"
- Utilisateur dit: "champigny" OU "1"
- Tu appelles: list_tasks_tool(project_id="abc-123-def-456")  ← user_id auto-injecté
- Tu réponds: "Voici les tâches pour Champigny" ← PAS d'UUID visible
- ❌ JAMAIS: list_tasks_tool(project_id="proj_champigny")  ← ID inventé
- ❌ JAMAIS: "Voici les tâches pour le projet abc-123-def-456" ← UUID visible

# 🎯 ÉTAT EXPLICITE ET CONTEXTE (RÈGLE CRITIQUE)

## État Actif (Source de Vérité)
Quand tu vois [État actuel - Source de vérité] dans le contexte:
1. ✅ CETTE INFORMATION EST AUTHORITATIVE - elle prend toujours la priorité
2. ✅ Projet actif: ID → Utilise cet ID directement pour les outils
3. ✅ Tâche active: ID → Utilise cet ID directement pour les outils
4. ❌ NE JAMAIS inventer de nouveaux IDs si l'état actif existe
5. ❌ NE PAS demander à l'utilisateur ce qu'il a déjà sélectionné

## Utilisation des Outils avec l'État
- Si "Projet actif: X (ID: abc-123)" est présent ET l'utilisateur demande "mes tâches":
  → Appelle: list_tasks_tool(project_id="abc-123")  ← user_id auto-injecté
- Si "Tâche active: Y (ID: def-456)" est présent ET l'utilisateur dit "mettre à jour":
  → Appelle: update_task_progress(task_id="def-456", ...)  ← user_id auto-injecté

## Cycle de Vie de l'État
1. ✅ L'état reste actif pendant 7 heures d'inactivité
2. ✅ Quand un outil est appelé, l'état est mis à jour automatiquement
3. ✅ Si AUCUN état actif n'existe, demande à l'utilisateur de sélectionner

## Priorité des Sources (Du plus au moins prioritaire)
1. **État Explicite** (ID dans [État actuel]) → UTILISER EN PREMIER
2. **Historique récent** (derniers tool outputs, 1-3 tours) → Si état vide
3. **Recherche par nom** (lookup tools) → Si aucune des 2 options précédentes

Exemples:
- État: "Projet actif: Champigny (ID: abc-123)"
  User: "Montre-moi les tâches"
  → list_tasks_tool(user_id, project_id="abc-123")  ✅ Utilise l'ID de l'état

- Pas d'état actif
  User: "Les tâches pour Champigny"
  → Appelle d'abord find_project_by_name("Champigny") pour obtenir l'ID

# RAPPELS FINAUX
- Tu opères en français en interne (messages déjà traduits)
- Ta réponse sera traduite dans la langue de l'utilisateur
- JAMAIS d'IDs techniques dans les réponses
- Toujours filtrer par user_id pour la sécurité"""


def create_agent(user_id: str, phone_number: str, language: str) -> AgentExecutor:
    """Create and configure the LangChain agent with user-specific tools.

    This function builds a fresh agent per request using the closure pattern to inject
    authenticated user context (user_id, phone_number, language) into tools without
    exposing these parameters to the LLM.

    Args:
        user_id: User UUID from authentication (injected into tools via closure)
        phone_number: User WhatsApp phone number (injected into tools via closure)
        language: User preferred language (injected into tools via closure)

    Returns:
        AgentExecutor with tools that have captured user context

    Note:
        This follows LangChain best practices for AgentExecutor which doesn't support
        runtime parameter injection. The closure pattern ensures user_id is always
        the authenticated UUID from the pipeline, preventing extraction errors.
    """
    # Initialize LLM based on provider selection
    if settings.llm_provider == "openai":
        log.debug(
            f"🤖 Initializing OpenAI agent with model: {settings.openai_model} (user: {user_id[:8]}...)"
        )
        llm = ChatOpenAI(  # type: ignore[call-arg]
            model=settings.openai_model,
            api_key=settings.openai_api_key,  # type: ignore[arg-type]
            temperature=settings.openai_temperature,
            max_tokens=settings.openai_max_tokens,
        )
    else:  # Default to Anthropic
        log.debug(
            f"🤖 Initializing Anthropic agent with model: {settings.anthropic_model} (user: {user_id[:8]}...)"
        )
        llm = ChatAnthropic(  # type: ignore[call-arg,assignment]
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,  # type: ignore[arg-type]
            temperature=settings.anthropic_temperature,
            max_tokens=settings.anthropic_max_tokens,
        )

    # Create prompt template
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    # Build user-specific tools with captured context (closure pattern)
    from src.agent.tools import build_tools_for_user

    user_tools = build_tools_for_user(user_id, phone_number, language)

    log.debug(
        f"🔧 Built {len(user_tools)} tools with captured context for user {user_id[:8]}..."
    )

    # Create agent with user-specific tools
    agent = create_tool_calling_agent(llm, user_tools, prompt)

    # Create agent executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=user_tools,  # User-specific tools with captured context
        verbose=settings.debug,
        handle_parsing_errors=True,
        max_iterations=5,
        return_intermediate_steps=True,  # CRITICAL: Capture tool outputs for short-term memory
    )

    log.debug(f"✅ Agent created successfully for user {user_id[:8]}...")
    return agent_executor


class LumieraAgent:
    """Main agent class for handling user requests.

    With the closure pattern, the agent is built per-request to inject user-specific
    context into tools. This class serves as the interface for processing messages.
    """

    def __init__(self):
        """Initialize the Lumiera agent.

        Note: With closure pattern, the agent is NOT created here. Instead, it's
        built fresh for each request in process_message() with the user's context.
        This allows tools to capture authenticated user_id, phone_number, and language
        from the closure scope, following LangChain best practices for AgentExecutor.
        """
        log.info(
            "🚀 Lumiera Agent initialized (agent built per-request with closure pattern)"
        )

    async def process_message(
        self,
        user_id: str,
        phone_number: str,
        language: str,
        message_text: str,
        chat_history: list = None,
        user_name: str = "",
        user_context: str = "",
        state_context: str = "",
    ) -> Dict[str, Any]:
        """Process a user message and return a response with structured data.

        Args:
            user_id: The user's ID
            phone_number: The user's WhatsApp phone number
            language: The user's preferred language
            message_text: The message text (already translated to French)
            chat_history: Optional chat history for context
            user_name: Official contact name from subcontractors table
            user_context: Additional user context for personalization
            state_context: AUTHORITATIVE explicit state (active project/task IDs)

        Returns:
            Dict with:
                - message: Response text (in French)
                - escalation: Whether escalation occurred
                - tools_called: List of tool names that were executed
                - tool_outputs: Structured tool outputs (for short-term memory)
        """
        # Use execution context scope for thread-safe execution tracking
        with execution_context_scope() as ctx:
            try:
                # Build agent with user-specific tools (closure pattern)
                # Tools capture user_id, phone_number, language from closure scope
                log.debug(f"🔨 Building agent for user {user_id[:8]}...")
                agent_executor = create_agent(user_id, phone_number, language)

                # Build context prefix with AUTHORITATIVE state first
                # NOTE: Language code is intentionally NOT included here to ensure
                # agent always responds in French (internal processing language).
                # Translation to user language happens in the pipeline after agent response.
                # NOTE: user_id, phone_number, language are NO LONGER in text context
                # because they're captured in tool closures.
                context_prefix = ""

                # LAYER 1: Explicit State (AUTHORITATIVE - takes precedence)
                if state_context:
                    context_prefix += state_context  # Already formatted with headers

                # LAYER 2: User context (name only - NO user_id)
                context_prefix += "[Contexte utilisateur]\n"
                if user_name:
                    context_prefix += f"Nom: {user_name}\n"
                if user_context:
                    context_prefix += f"Contexte additionnel:\n{user_context}\n"
                context_prefix += "\n"

                # Prepare agent input (SIMPLIFIED - no user_id/phone/language in dict)
                # These are captured in tool closures, not passed to LLM
                agent_input: Dict[str, Any] = {
                    "input": f"{context_prefix}{message_text}",
                }

                if chat_history:
                    agent_input["chat_history"] = chat_history

                # Run agent
                log.debug(f"🤖 Invoking agent for user {user_id[:8]}...")
                result = await agent_executor.ainvoke(agent_input)

                # Extract output
                output = result.get(
                    "output", "Désolé, je n'ai pas pu traiter votre demande."
                )

                # Normalize output to string (LangChain sometimes returns dict/list)
                if isinstance(output, dict):
                    # Extract 'text' field from dict: {'text': '...', 'type': 'text', 'index': 0}
                    log.warning("Agent returned dict output, extracting text field")
                    output = output.get("text", str(output))
                elif isinstance(output, list):
                    # List items might be dicts with 'text' field or plain strings
                    log.warning(
                        f"Agent returned list output ({len(output)} items), extracting text"
                    )
                    extracted_items = []
                    for item in output:
                        if isinstance(item, dict):
                            # Extract 'text' field from dict item
                            extracted_items.append(item.get("text", str(item)))
                        else:
                            # Plain string or other type
                            extracted_items.append(str(item))
                    output = "\n".join(extracted_items)
                elif not isinstance(output, str):
                    # Fallback: convert to string
                    log.warning(
                        f"Agent returned unexpected type {type(output)}, converting to string"
                    )
                    output = str(output)

                # Extract intermediate_steps (tool calls + outputs)
                # Format: List[Tuple[AgentAction, Any]]
                intermediate_steps = result.get("intermediate_steps", [])
                tool_outputs = []

                for action, tool_result in intermediate_steps:
                    # For list_tasks_tool, fetch structured data from action layer
                    # (tool_result is a formatted string, but we need structured data)
                    if action.tool == "list_tasks_tool":
                        # Re-fetch structured data from actions layer
                        from src.actions import tasks as task_actions
                        from src.utils.metadata_helpers import compact_tasks

                        project_id = action.tool_input.get("project_id")
                        user_id_input = action.tool_input.get("user_id")

                        if project_id and user_id_input:
                            task_result = await task_actions.list_tasks(
                                user_id_input, project_id
                            )
                            if task_result.get("success") and task_result.get("data"):
                                structured_output = compact_tasks(task_result["data"])
                                log.info(
                                    f"   🗜️ Stored structured data for list_tasks_tool: {len(structured_output)} tasks"
                                )
                            else:
                                structured_output = []
                        else:
                            structured_output = []

                        tool_output_entry = {
                            "tool": action.tool,
                            "input": action.tool_input,
                            "output": structured_output,  # Structured data, not string
                        }
                    else:
                        # For other tools, store as-is
                        tool_output_entry = {
                            "tool": action.tool,
                            "input": action.tool_input,
                            "output": tool_result,
                        }

                    tool_outputs.append(tool_output_entry)

                if tool_outputs:
                    log.info(
                        f"📦 Captured {len(tool_outputs)} tool outputs for short-term memory"
                    )

                # Get escalation flag from execution context (set by tools)
                escalation_occurred = ctx.escalation_occurred

                log.info(f"Agent processed message for user {user_id}")
                log.info(f"Escalation occurred: {escalation_occurred}")
                log.info(f"Tools called: {ctx.tools_called}")

                # Return structured data (output is guaranteed to be string now)
                return {
                    "message": output,
                    "escalation": escalation_occurred,
                    "tools_called": ctx.tools_called,
                    "tool_outputs": tool_outputs,  # NEW: Short-term tool memory
                }

            except Exception as e:
                log.error(f"Error processing message: {e}")
                return {
                    "message": "Désolé, une erreur s'est produite. Veuillez réessayer.",
                    "escalation": False,
                    "tools_called": [],
                    "tool_outputs": [],
                }


# Global agent instance
lumiera_agent = LumieraAgent()
