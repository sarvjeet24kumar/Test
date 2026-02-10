# MiniMart

A production-grade, multi-tenant shopping list application with real-time synchronization.

## Features

- **Multi-Tenancy**: Strict tenant isolation with role-based access control
- **Real-Time Sync**: WebSocket-based live updates for collaborative shopping
- **Stateless Invitations**: Token-based invites without database persistence
- **JWT Authentication**: Secure access and refresh token management
- **Email Verification**: OTP-based email verification for new users

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2.0 (async) |
| Cache/Tokens | Redis |
| Auth | JWT (python-jose) |
| Real-Time | WebSockets |
| Docs | Swagger/OpenAPI |
| Deployment | Docker |

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop services
docker-compose down
```

The API will be available at `http://localhost:8000`

### Manual Setup

1. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. **Start PostgreSQL and Redis**
   ```bash
   # Using Docker
   docker run -d --name minimart-db -e POSTGRES_USER=minimart -e POSTGRES_PASSWORD=minimart -e POSTGRES_DB=minimart -p 5432:5432 postgres:15-alpine
   docker run -d --name minimart-redis -p 6379:6379 redis:7-alpine
   ```

5. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

6. **Start the application**
   ```bash
   uvicorn app.main:app --reload
   ```

## API Documentation

Once running, access the interactive API docs:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Project Structure

```
minimart/
├── app/
│   ├── api/               # API endpoints
│   │   └── v1/           # Version 1 routes
│   ├── core/             # Security, exceptions
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   ├── websocket/        # WebSocket handling
│   ├── config.py         # Settings
│   ├── database.py       # DB connection
│   ├── dependencies.py   # FastAPI dependencies
│   └── main.py          # Application entry
├── alembic/              # Database migrations
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/login` | Login and get tokens |
| POST | `/api/v1/auth/verify-email` | Verify email with OTP |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| GET | `/api/v1/auth/me` | Get current user profile |

### Tenants (Super Admin)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/tenants` | Create tenant with admin |
| GET | `/api/v1/tenants` | List all tenants |
| GET | `/api/v1/tenants/{id}` | Get tenant details |
| PATCH | `/api/v1/tenants/{id}` | Update tenant |
| DELETE | `/api/v1/tenants/{id}` | Deactivate tenant |

### Users (Tenant Admin)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/users` | Create user |
| GET | `/api/v1/users` | List tenant users |
| PATCH | `/api/v1/users/{id}` | Update user |
| DELETE | `/api/v1/users/{id}` | Deactivate user |

### Shopping Lists
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/shopping-lists` | Create list |
| GET | `/api/v1/shopping-lists` | Get user's lists |
| GET | `/api/v1/shopping-lists/{id}` | Get list details |
| POST | `/api/v1/shopping-lists/{id}/invite` | Invite member |
| DELETE | `/api/v1/shopping-lists/{id}/members/{user_id}` | Remove member |

### Items
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/shopping-lists/{id}/items` | Add item |
| PATCH | `/api/v1/items/{id}` | Update item |
| DELETE | `/api/v1/items/{id}` | Delete item |

### Invitations
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/invitations/accept` | Accept invitation |
| POST | `/api/v1/invitations/reject` | Reject invitation |

## WebSocket Protocol

Connect to `/ws?token=<JWT>` for real-time updates.

### Messages

**Subscribe to list updates:**
```json
{"type": "subscribe", "payload": {"list_id": "uuid"}}
```

**Unsubscribe:**
```json
{"type": "unsubscribe", "payload": {"list_id": "uuid"}}
```

**Events received:**
- `item_added` - New item created
- `item_updated` - Item modified
- `item_deleted` - Item removed
- `member_joined` - New member accepted invite
- `member_left` - Member left the list
- `member_removed` - Member removed by owner

## Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback last migration
alembic downgrade -1
```

## Environment Variables

See `.env.example` for all configuration options.

Key variables:
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `JWT_SECRET_KEY` - Secret for JWT signing
- `SMTP_*` - Email configuration

## License

MIT
