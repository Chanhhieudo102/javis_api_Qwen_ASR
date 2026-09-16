# Error Handling Documentation

This document describes the standard error handling pattern used across the application.

---

## Overview

The application uses a structured error handling system with:
1. **Error Constants** - Centralized error key definitions
2. **Error YAML** - i18n error messages with codes
3. **Custom Exceptions** - HTTP exception classes
4. **Global Exception Handler** - Catches and formats all errors

---

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    SERVICE / ROUTE LAYER                        │
│  raise BadRequestException(detail=ErrorConstants.Auth.XXX)     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  GLOBAL EXCEPTION HANDLER                       │
│  Catches exception, looks up error in YAML by detail key       │
│  Location: app/common/exceptions/global_exceptions.py          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MESSAGE RESOLVER                             │
│  Resolves error key to {code, message} from YAML               │
│  Location: app/common/i18n/message_resolver.py                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    JSON ERROR RESPONSE                          │
│  { "status": "failure", "error": { "code": "...", "message": "..." } }
└─────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step: Adding a New Error

### Step 1: Define the Error Constant

Add the constant to the appropriate module class in:
`app/common/contants/error_contants.py`

```python
class ErrorConstants:

    class YourModule:
        """Your module error constants."""

        YOUR_ERROR_KEY = "your_error_key"
```

**Rules:**
- Group constants under the appropriate module class
- Constant name should be UPPER_SNAKE_CASE
- Value should be lower_snake_case (matches YAML key)

---

### Step 2: Add Error Message to YAML

Add the error definition to:
`app/common/resources/errors/error_en.yml`

```yaml
# =============================================================================
# YOUR MODULE ERRORS
# =============================================================================

your_error_key:
  code: "ERR.MOD0101"
  message: "Human readable error message"
```

**Error Code Format:**
```
ERR.<MODULE><NUMBER>
```

| Module Code | Description |
|-------------|-------------|
| `SYS` | System/Server errors |
| `AUTH` | Authentication/Authorization |
| `USR` | User module |
| `ZON` | Zone module |
| `TBL` | Table module |
| `ORD` | Order module |
| `MNU` | Menu module |
| `BIL` | Bill module |
| `VAL` | Validation errors |

**Numbering Convention:**
- Start each module at `0101`
- Increment by 1 for each new error: `0101`, `0102`, `0103`, ...

---

### Step 3: Raise the Exception

Use the constant when raising exceptions in your service or route:

```python
from app.common.constants.error_constants import ErrorConstants
from app.common.exceptions import BadRequestException, NotFoundException

# For 400 Bad Request errors
raise BadRequestException(detail=ErrorConstants.User.EMAIL_ALREADY_EXISTS)

# For 404 Not Found errors
raise NotFoundException(detail=ErrorConstants.User.USER_NOT_FOUND)

# For 401 Unauthorized errors
raise UnauthorizedException(detail=ErrorConstants.Auth.INVALID_CREDENTIALS)

# For 403 Forbidden errors
raise ForbiddenException(detail=ErrorConstants.Auth.FORBIDDEN)
```

---

## Available Exception Classes

| Exception Class | HTTP Status | Usage |
|-----------------|-------------|-------|
| `BadRequestException` | 400 | Validation, business rule violations |
| `UnauthorizedException` | 401 | Authentication failures |
| `ForbiddenException` | 403 | Authorization/permission failures |
| `NotFoundException` | 404 | Resource not found |
| `InternalServerException` | 500 | Server errors |

---

## Example Error Response

```json
{
  "status": "failure",
  "error": {
    "code": "ERR.USR0103",
    "message": "Email already exists"
  }
}
```

---

## Current Error Constants Reference

### System Errors
| Constant | Key | Code |
|----------|-----|------|
| `System.INTERNAL_SERVER_ERROR` | `internal_server_error` | `ERR.SYS0101` |
| `System.BAD_REQUEST` | `bad_request` | `ERR.SYS0102` |
| `System.NOT_FOUND` | `not_found` | `ERR.SYS0103` |

### Auth Errors
| Constant | Key | Code |
|----------|-----|------|
| `Auth.UNAUTHORIZED` | `unauthorized` | `ERR.AUTH0101` |
| `Auth.FORBIDDEN` | `forbidden` | `ERR.AUTH0102` |
| `Auth.INVALID_CREDENTIALS` | `invalid_credentials` | `ERR.AUTH0103` |
| `Auth.TOKEN_EXPIRED` | `token_expired` | `ERR.AUTH0104` |
| `Auth.TOKEN_INVALID` | `token_invalid` | `ERR.AUTH0105` |
| `Auth.OWNER_ALREADY_EXISTS` | `owner_already_exists` | `ERR.AUTH0106` |

### User Errors
| Constant | Key | Code |
|----------|-----|------|
| `User.USER_NOT_FOUND` | `user_not_found` | `ERR.USR0101` |
| `User.USER_ALREADY_EXISTS` | `user_already_exists` | `ERR.USR0102` |
| `User.EMAIL_ALREADY_EXISTS` | `email_already_exists` | `ERR.USR0103` |
| `User.USERNAME_ALREADY_EXISTS` | `username_already_exists` | `ERR.USR0104` |
| `User.CANNOT_CREATE_OWNER_AS_EMPLOYEE` | `cannot_create_owner_as_employee` | `ERR.USR0105` |

---

## Checklist for New Errors

When adding a new error, ensure:

- [ ] Constant added to `ErrorConstants` class in correct module group
- [ ] Error key added to `error_en.yml` under correct module section
- [ ] Error code follows format: `ERR.<MODULE><NUMBER>`
- [ ] Error code number is sequential within the module
- [ ] Human-readable message is clear and helpful
- [ ] Exception is raised using the constant, not a hardcoded string

---