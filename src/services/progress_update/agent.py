"""Specialized agent for progress update multi-step flows."""
from typing import Dict, Any, Optional
from langchain_anthropic import ChatAnthropic
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from src.config import settings
from src.services.progress_update.tools import (
    get_progress_update_context_tool,
    add_progress_image_tool,
    add_progress_comment_tool,
    mark_task_complete_tool,
    start_progress_update_session_tool
)
from src.services.project_context import project_context_service
from src.integrations.supabase import supabase_client
from src.utils.logger import log


PROGRESS_UPDATE_PROMPT = """Tu es un assistant spécialisé pour guider les utilisateurs dans la mise à jour de leurs tâches.

OBJECTIF : Accompagner l'utilisateur étape par étape pour mettre à jour la progression d'une tâche avec :
1. 📸 Photos (via upload)
2. 💬 Commentaires (texte ou transcription vocale)
3. ✅ Changement de statut (marquer comme terminé)

CONTEXTE UTILISATEUR :
- User ID : {user_id}
- Nom : {user_name}
- Langue : {language}

RÈGLES IMPORTANTES :

1. **Contexte de projet/tâche** :
   - Si l'utilisateur n'a pas de projet actif, demande quel projet
   - Si l'utilisateur n'a pas de tâche active, montre les tâches disponibles
   - Utilise start_progress_update_session_tool pour démarrer une session

2. **Actions multiples** :
   - L'utilisateur peut effectuer plusieurs actions (photo + commentaire + compléter)
   - Après chaque action, suggère les actions restantes
   - Sois intelligent : si l'utilisateur ajoute 3 photos et un commentaire, propose "Voulez-vous marquer cette tâche comme terminée ?"

3. **Messages vocaux** :
   - Les messages vocaux sont déjà transcrits par le système
   - Utilise le texte transcrit comme commentaire
   - Confirme toujours : "Commentaire ajouté : '[texte transcrit]'"

4. **Images** :
   - Quand l'utilisateur envoie une image, elle est déjà uploadée en storage
   - Tu reçois l'URL publique
   - Utilise add_progress_image_tool avec cette URL

5. **État de la session** :
   - Utilise get_progress_update_context_tool pour voir ce qui a déjà été fait
   - Adapte tes suggestions en fonction
   - Si tout est fait (image + commentaire + complété), félicite et termine

6. **Confirmation avant completion** :
   - Avant de marquer comme terminé, vérifie que l'utilisateur le veut vraiment
   - "Voulez-vous marquer cette tâche comme terminée ?"

7. **Fluidité** :
   - Sois naturel et conversationnel
   - Pas de menus rigides - adapte-toi au contexte
   - Si l'utilisateur dit "ajoute cette photo et marque comme terminé", fais les deux

8. **Messages clairs** :
   - Utilise des emojis pour clarifier
   - Confirme chaque action effectuée
   - Résume à la fin

OUTILS DISPONIBLES :
- get_progress_update_context_tool : Voir l'état actuel
- start_progress_update_session_tool : Démarrer une session pour une tâche
- add_progress_image_tool : Ajouter une photo
- add_progress_comment_tool : Ajouter un commentaire
- mark_task_complete_tool : Marquer comme terminé

Historique de conversation :
{chat_history}

Message actuel :
{input}

{agent_scratchpad}
"""


class ProgressUpdateAgent:
    """Specialized agent for progress updates."""

    def __init__(self):
        """Initialize progress update agent."""
        self.llm = ChatAnthropic(
            model="claude-3-5-sonnet-20241022",  # Use Sonnet for better UX
            api_key=settings.anthropic_api_key,
            temperature=0.3,  # Slightly creative for natural conversation
        )

        # Create tools list
        self.tools = [
            get_progress_update_context_tool,
            start_progress_update_session_tool,
            add_progress_image_tool,
            add_progress_comment_tool,
            mark_task_complete_tool
        ]

        # Create prompt
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", PROGRESS_UPDATE_PROMPT),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        # Create agent
        agent = create_tool_calling_agent(self.llm, self.tools, self.prompt)
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=10,
            handle_parsing_errors=True
        )

        log.info("✅ Progress Update Agent initialized")

    async def process(
        self,
        user_id: str,
        user_name: str,
        language: str,
        message: str,
        chat_history: list = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process progress update request.

        Args:
            user_id: User ID
            user_name: User name
            language: User language
            message: User message
            chat_history: Recent conversation history
            media_url: Optional media URL (image uploaded by user)
            media_type: Optional media type

        Returns:
            Response dict with message and metadata
        """
        try:
            # Enhance message with media context
            enhanced_message = message
            if media_url and 'image' in (media_type or ''):
                enhanced_message = f"{message}\n\n[SYSTEM: L'utilisateur a envoyé une image. URL: {media_url}]"

            # Run agent
            result = await self.agent_executor.ainvoke({
                "input": enhanced_message,
                "user_id": user_id,
                "user_name": user_name,
                "language": language,
                "chat_history": chat_history or []
            })

            return {
                "success": True,
                "message": result["output"],
                "agent_used": "progress_update"
            }

        except Exception as e:
            log.error(f"Error in progress update agent: {e}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "message": "❌ Erreur lors de la mise à jour. Veuillez réessayer.",
                "error": str(e)
            }


# Global instance
progress_update_agent = ProgressUpdateAgent()
