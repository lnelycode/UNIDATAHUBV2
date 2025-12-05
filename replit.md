# Overview

This is a simple Telegram bot application built with Python's aiogram framework (version 3.x). The bot responds to the `/start` command with a greeting message in Russian. It uses long polling to receive updates from Telegram's Bot API.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Application Framework
- **Technology**: Python with aiogram 3.x (asynchronous Telegram bot framework)
- **Rationale**: aiogram provides a modern, async/await-based approach to building Telegram bots with type hints and clean architecture
- **Execution Model**: Single-threaded async event loop using Python's asyncio

## Bot Communication Pattern
- **Chosen Solution**: Long polling via `dp.start_polling(bot)`
- **Rationale**: Simple to set up and doesn't require webhook configuration or SSL certificates
- **Alternatives Considered**: Webhook-based updates (requires public HTTPS endpoint)
- **Pros**: Easy to develop and test locally, no server configuration needed
- **Cons**: Less efficient than webhooks for high-traffic bots, maintains constant connection to Telegram servers

## Message Handling Architecture
- **Pattern**: Decorator-based message handlers using filters
- **Implementation**: `@dp.message(CommandStart())` registers handlers for specific commands
- **Rationale**: Provides clean separation of concerns and makes adding new command handlers straightforward

## Configuration Management
- **Approach**: Environment variables for sensitive data
- **Implementation**: `BOT_TOKEN` retrieved from environment with validation
- **Rationale**: Keeps credentials out of source code and allows easy deployment across different environments
- **Security**: Fails fast if required credentials are missing

# External Dependencies

## Telegram Bot API
- **Service**: Telegram's official Bot API
- **Purpose**: Core messaging platform for bot interactions
- **Authentication**: Token-based (BOT_TOKEN environment variable)
- **Integration Method**: aiogram library handles all API communication

## Python Libraries
- **aiogram**: Telegram bot framework (version 3.x based on import structure)
- **asyncio**: Built-in Python async runtime

## Environment Variables Required
- `BOT_TOKEN`: Telegram bot authentication token obtained from @BotFather