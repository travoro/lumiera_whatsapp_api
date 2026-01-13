# PlanRadar API Integration

## Overview

PlanRadar is a construction project management platform that provides APIs for managing projects, tasks (tickets), documents, and more.

## Base Configuration

- **Base URL**: Configured in `.env` as `PLANRADAR_API_URL` (default: `https://api.planradar.com/v1`)
- **Authentication**: Bearer token authentication via `PLANRADAR_API_KEY`
- **Account ID**: `PLANRADAR_ACCOUNT_ID` for account-specific operations

## Key Endpoints

### Projects and Tickets

#### List Tickets for a Project
```
GET /projects/{project_id}/tickets
```
- Lists all tickets (tasks) for a specific project
- Optional query parameter: `status` for filtering
- Returns array of ticket objects

#### Get Ticket Details
```
GET /tickets/{ticket_id}
```
- Retrieves detailed information about a specific ticket

#### Create Ticket
```
POST /projects/{project_id}/tickets
```
- Creates a new ticket (task/incident) for a project
- Request body includes: `title`, `description`, `type`, `attachments`

#### Update Ticket
```
PATCH /tickets/{ticket_id}
```
- Updates ticket properties (e.g., status)

### Ticket Attachments and Comments

#### Get Ticket Attachments
```
GET /tickets/{ticket_id}/attachments
```
- Returns all attachments for a ticket
- Can filter by type (e.g., images)

#### Add Ticket Attachment
```
POST /tickets/{ticket_id}/attachments
```
- Adds an attachment to a ticket

#### Get Ticket Comments
```
GET /tickets/{ticket_id}/comments
```
- Returns all comments for a ticket

#### Add Ticket Comment
```
POST /tickets/{ticket_id}/comments
```
- Adds a comment to a ticket

### Documents

#### List Project Documents
```
GET /projects/{project_id}/documents
```
- Lists all documents for a project
- Optional query parameter: `folder_id` for filtering

### Plans

#### Get Ticket Plans
```
GET /tickets/{ticket_id}/plans
```
- Returns plans/blueprints associated with a ticket

## Integration Architecture

### Database Schema
The `projects` table in Supabase includes a `planradar_project_id` field that stores the PlanRadar project ID for each project. This field is used to map internal project IDs to PlanRadar project IDs.

### Action Flow
1. **List Projects**: Retrieve projects from Supabase (includes `planradar_project_id`)
2. **List Tasks**:
   - Get project details from Supabase to retrieve `planradar_project_id`
   - Call PlanRadar API with the PlanRadar project ID
3. **Other Operations**: Similar pattern - retrieve project details first, then use PlanRadar project ID

### Security
- All PlanRadar API calls require authentication via Bearer token
- Project access is validated through Supabase before calling PlanRadar APIs
- User authorization is enforced at the Supabase layer

## Implementation Notes

- The PlanRadar client (`src/integrations/planradar.py`) handles all API interactions
- Actions (`src/actions/`) handle business logic and coordinate between Supabase and PlanRadar
- Tools (`src/agent/tools.py`) expose functionality to the LangChain agent
- All project-related PlanRadar API calls use the `planradar_project_id` field from the database, not the internal project ID

## Error Handling

- Missing `planradar_project_id`: Returns error message "Ce projet n'est pas lié à PlanRadar."
- API errors: Logged and returned as user-friendly French error messages
- HTTP errors: Handled by the PlanRadar client with automatic logging

## Future Enhancements

- Support for more PlanRadar features (forms, checklists, etc.)
- Webhook integration for real-time updates
- Batch operations for improved performance
- Caching layer for frequently accessed data
