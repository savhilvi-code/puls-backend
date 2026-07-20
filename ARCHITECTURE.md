# Architecture

## Overview

PULS backend is a FastAPI service for the web version of the product. It receives requests from the frontend, coordinates backend processing, talks to external AI services when needed, and persists user-facing data in Supabase.

At a high level, the backend is responsible for:

- chat request handling;
- user and vehicle-related API flows;
- persistence of application data in Supabase;
- integration with AI-powered response generation;
- support-related intake and operational service endpoints.

## Main Components

### FastAPI

The application entrypoint is built on FastAPI and exposes HTTP routes for the frontend and supporting product features.

### Supabase

Supabase is used as the hosted data layer for application persistence. The backend reads and writes product data through a server-side integration layer.

### AI Integration

PULS integrates with external AI providers to support assistant-style product features. The backend coordinates request preparation and response handling for those integrations.

### Frontend / Backend Relationship

The public site and app UI call the backend over HTTP. The frontend is responsible for presentation and user interaction, while the backend is responsible for data access, orchestration, and server-side business logic.

## Project Layout

The repository is organized around a standard backend structure:

- `app/` contains FastAPI application code;
- `app/routers/` contains HTTP route modules;
- `app/services/` contains backend service logic;
- `app/schemas/` contains request and response schemas;
- `app/database/` contains database integration helpers;
- `db/` contains SQL and database-related support files;
- `tests/` contains backend tests and verification helpers.

## Runtime Flow

At a high level, the runtime flow is:

1. frontend sends a request to the backend;
2. FastAPI routes the request to the appropriate module;
3. backend services process the request;
4. data is read from or written to Supabase when needed;
5. the backend returns a structured response to the frontend.

## Notes

- This public document intentionally stays at a high level.
- Detailed operational flows, internal routing logic, and private implementation notes are maintained outside the public repository documentation set.
